"""Clarification Agent for PsychAgent.

This agent formulates 1-2 targeted, non-leading clarifying questions to resolve
informational uncertainties identified by the Uncertainty Agent.

IMPORTANT design constraints
-----------------------------
* Only fires when clarification_required is true.
* Minimum questions needed (1-2) covering the priority gap.
* Prioritizes safety-relevant missing information when uncertain.
* Does NOT invent missing facts, diagnose, or provide counseling advice.
* Does NOT make final routing decisions or claim the client is safe.

Output (AgentMessage):
---------------------
status:                 "ok" | "not_required"
evidence:               List of targeted uncertainty fields
payload:
    question:               str (primary clarification question)
    questions:              List[str] (1-2 targeted questions)
    target_information:     List[str] (fields/topics being clarified)
    priority:               "LOW" | "MEDIUM" | "HIGH"
    clarification_required: bool
    reasoning_summary:      str
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import Agent, AgentContext, AgentError, AgentMessage

logger = logging.getLogger(__name__)

# Standard targeted questions for common clinical uncertainty categories
_CLARIFICATION_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "safety_status": {
        "questions": [
            "Have you ever received professional psychological evaluation or treatment before, or do you have any relevant medical records?",
            "Before your current distress began, have similar problems occurred in the past?",
        ],
        "target": ["medical_history", "prior_treatment"],
        "priority": "HIGH",
    },
    "duration_and_history": {
        "questions": [
            "Around when did this feeling start to emerge? Did anything specific happen at that time?",
            "Before this distress occurred, has a similar situation happened previously?",
        ],
        "target": ["growth_experiences", "duration_onset"],
        "priority": "MEDIUM",
    },
    "cognitive_pattern": {
        "questions": [
            "When this event happens, what thoughts or ideas first surface in your mind?",
        ],
        "target": ["automatic_thoughts", "cognitive_reaction"],
        "priority": "MEDIUM",
    },
    "conditional_assumption": {
        "questions": [
            "When facing this situation, what expectations or demands do you usually hold for yourself or others?",
        ],
        "target": ["conditional_assumptions", "rules_beliefs"],
        "priority": "MEDIUM",
    },
    "severity_impact": {
        "questions": [
            "Do these difficulties have any specific impact on your sleep, daily work, or life routine?",
        ],
        "target": ["functional_impairment", "consequence"],
        "priority": "MEDIUM",
    },
    "ambiguous_expression": {
        "questions": [
            "Could you elaborate on what specific situation you were referring to when you mentioned that matter?",
        ],
        "target": ["specific_event_referent"],
        "priority": "MEDIUM",
    },
    "contradictory_information": {
        "questions": [
            "You mentioned having these feelings on one hand while having different thoughts on the other. How do these two experiences interact in your mind?",
        ],
        "target": ["conflicting_feelings_clarification"],
        "priority": "HIGH",
    },
}


class ClarificationAgent(Agent):
    """Generates focused, non-leading clarifying questions for priority informational gaps."""

    name = "clarification_agent"

    def __init__(self, backend: Optional[Any] = None) -> None:
        self.backend = backend

    def run(self, ctx: AgentContext) -> AgentMessage:
        try:
            return self._run(ctx)
        except AgentError:
            raise
        except Exception as exc:
            logger.exception("[%s] unexpected error: %s", self.name, exc)
            return AgentMessage(
                agent=self.name,
                status="error",
                error=str(exc),
                payload={
                    "question": "",
                    "questions": [],
                    "target_information": [],
                    "priority": "LOW",
                    "clarification_required": False,
                    "reasoning_summary": f"Error: {exc}",
                },
            )

    def _run(self, ctx: AgentContext) -> AgentMessage:
        unc_payload = ctx.uncertainty_output or {}
        if not isinstance(unc_payload, dict):
            unc_payload = {}

        clarification_required = bool(unc_payload.get("clarification_required", False))
        uncertainty_types = unc_payload.get("uncertainty_types", []) or []
        uncertain_fields = unc_payload.get("uncertain_fields", []) or []
        missing_info = unc_payload.get("missing_information", []) or []
        unc_priority = unc_payload.get("priority", "LOW")

        # If clarification is NOT required, return valid non-empty schema indicating not needed
        if not clarification_required or unc_payload.get("status") == "CLEAR":
            payload = {
                "question": "",
                "questions": [],
                "target_information": [],
                "priority": "LOW",
                "clarification_required": False,
                "reasoning_summary": "No clarification required; current state information is sufficient.",
            }
            _validate_clarification_payload(payload)
            return AgentMessage(
                agent=self.name,
                status="not_required",
                evidence=["Information is clear; no clarification needed"],
                confidence=1.0,
                payload=payload,
            )

        # Priority 1: Referential ambiguity and contradictions in the client's discourse take precedence
        selected_template: Optional[Dict[str, Any]] = None
        if "contradictory_information" in uncertainty_types:
            selected_template = _CLARIFICATION_TEMPLATES["contradictory_information"]
        elif "ambiguous_expression" in uncertainty_types:
            selected_template = _CLARIFICATION_TEMPLATES["ambiguous_expression"]
        elif "safety_status" in uncertainty_types or any("medical" in f or "safety" in f for f in uncertain_fields):
            selected_template = _CLARIFICATION_TEMPLATES["safety_status"]
        elif "duration_and_history" in uncertainty_types or any("growth" in f for f in uncertain_fields):
            selected_template = _CLARIFICATION_TEMPLATES["duration_and_history"]
        else:
            # Fall back to matching any recognized uncertainty type
            for utype in uncertainty_types:
                if utype in _CLARIFICATION_TEMPLATES:
                    selected_template = _CLARIFICATION_TEMPLATES[utype]
                    break

        if selected_template is None:
            # Generic fallback targeted question
            target_str = uncertain_fields[0] if uncertain_fields else (missing_info[0] if missing_info else "relevant background")
            questions = [f"Regarding what you mentioned, could you tell me more about the background concerning {target_str}?"]
            target_info = [str(target_str)]
            priority = unc_priority
        else:
            questions = list(selected_template["questions"])[:2]
            target_info = list(selected_template["target"])
            priority = selected_template["priority"]

        primary_question = questions[0] if questions else ""
        reasoning = f"Clarification targets priority gap '{', '.join(target_info)}' to resolve informational uncertainty."

        payload = {
            "question": primary_question,
            "questions": questions,
            "target_information": target_info,
            "priority": priority,
            "clarification_required": True,
            "reasoning_summary": reasoning,
        }

        _validate_clarification_payload(payload)

        return AgentMessage(
            agent=self.name,
            status="ok",
            evidence=[f"Targeting missing/uncertain: {', '.join(target_info)}"],
            confidence=0.85,
            payload=payload,
        )


def _validate_clarification_payload(payload: Dict[str, Any]) -> None:
    """Validate clarification output schema."""
    if not isinstance(payload.get("question"), str):
        raise AgentError("clarification_agent", "question must be a string")
    if not isinstance(payload.get("questions"), list):
        raise AgentError("clarification_agent", "questions must be a list")
    if not isinstance(payload.get("target_information"), list):
        raise AgentError("clarification_agent", "target_information must be a list")
    if payload.get("priority") not in ("LOW", "MEDIUM", "HIGH"):
        raise AgentError("clarification_agent", f"Invalid priority: {payload.get('priority')}")
    if not isinstance(payload.get("clarification_required"), bool):
        raise AgentError("clarification_agent", "clarification_required must be a boolean")
