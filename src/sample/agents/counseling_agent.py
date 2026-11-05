"""Counseling Agent for PsychAgent.

This agent acts as a thin wrapper that takes the Orchestrator's routing decision,
upstream agent trail, and current session context, and delegates to the existing
SkillManager and PsychAgentPromptManager to generate the counselor's response.

IMPORTANT design constraints
-----------------------------
* Does NOT reimplement skill retrieval or prompt construction.
* `generate_response` is only reached for non-HIGH-RISK turns: the async
  pipeline skips it entirely on HIGH-RISK turns (no retrieval, no LLM
  call) and lets the supervisor deliver safe text instead.
* Generates counselor response text in the exact format runner.py expects.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .base import Agent, AgentContext, AgentMessage

logger = logging.getLogger(__name__)


class CounselingAgent(Agent):
    """Thin wrapper delegating counseling generation to SkillManager and PromptManager."""

    name = "counseling_agent"

    def __init__(
        self,
        counselor_backend: Optional[Any] = None,
        skill_manager: Optional[Any] = None,
        prompt_manager: Optional[Any] = None,
    ) -> None:
        self.counselor_backend = counselor_backend
        self.skill_manager = skill_manager
        self.prompt_manager = prompt_manager

    def run(self, ctx: AgentContext) -> AgentMessage:
        """Synchronous Agent interface for offline/unit testing.

        PLACEHOLDER — this is NOT a counseling reply. It returns a routing
        marker ("[Counselor response generated via route=...]") so the
        sync pipeline can exercise routing, clarification, and supervision
        without an LLM call. Real counselor text comes only from
        `generate_response()` (async batch runner path) or from the web
        engine's own generation. Consumers MUST check
        `payload["response_source"] == "stub"` / `run_pipeline`'s
        `"response_is_placeholder"` and never deliver this text to a user.
        """
        route = (ctx.routing_output or {}).get("route", "CLEAR")
        response_text = f"[Counselor response generated via route={route}]"
        payload = {
            "route": route,
            "response_text": response_text,
            # Round 2 fix (Stream B D5): mark the stub explicitly so no
            # future consumer mistakes it for a counseling reply.
            "response_source": "stub",
            "is_counseling_reply": False,
            "next_agent": "safety_supervisor",
            "trail_summary": {
                "memory_loaded": bool(ctx.memory_output),
                "state_assessed": bool(ctx.state_output),
                "uncertainty_status": (ctx.uncertainty_output or {}).get("status"),
                "risk_severity": (ctx.risk_output or {}).get("severity"),
            },
        }
        return AgentMessage(
            agent=self.name,
            status="ok",
            evidence=[f"Routing: {route}"],
            payload=payload,
        )

    async def generate_response(
        self,
        ctx: AgentContext,
        *,
        runner_instance: Any,
        transcript: List[Dict[str, Any]],
        counselor_messages: List[Dict[str, str]],
        session_goals: Dict[str, Any],
        stage: str,
        candidate_skills: List[Dict[str, Any]],
        case_id: str,
        turn_tag: str,
        render_counselor_system: Any,
        each_turn_system: Optional[List[str]] = None,
    ) -> Tuple[str, str]:
        """Generate counselor response by calling existing skill manager and prompt manager.

        Returns (c_resp_pure, c_resp_raw) tuple exactly matching runner._chat_with_retry.
        """
        modality = ctx.modality.lower()
        route = (ctx.routing_output or {}).get("route", "CLEAR")

        logger.info(
            "[case=%s] counseling_agent executing with route=%s (upstream risk=%s, unc=%s)",
            case_id,
            route,
            (ctx.risk_output or {}).get("severity"),
            (ctx.uncertainty_output or {}).get("status"),
        )

        skill_suggestion, _ = await runner_instance._retrieve_skill(
            modality=modality,
            transcript=transcript,
            session_goals=session_goals,
            stage=stage,
            candidate_skills=candidate_skills,
            case_id=case_id,
        )

        # Suitability weights travel with the prompt as fixed data. On a
        # HIGH-RISK turn no weights are presented at all: the supervisor
        # gates whatever is delivered, and crisis responses never carry
        # exercise percentages.
        if route == "HIGH-RISK":
            weights: Any = {"mode": "none", "options": []}
        else:
            weights_fn = getattr(
                getattr(runner_instance, "_skill_manager", None),
                "suitability_weights",
                None,
            )
            weights = weights_fn(skill_suggestion) if weights_fn is not None else None

        counselor_messages[0]["content"] = render_counselor_system(skill_suggestion, weights)
        if each_turn_system is not None:
            each_turn_system.append(counselor_messages[0]["content"])

        c_resp_pure, c_resp_raw = await runner_instance._chat_with_retry(
            runner_instance._counselor_backend,
            counselor_messages,
            turn_tag,
        )
        return c_resp_pure, c_resp_raw
