"""Reassessment Agent for PsychAgent.

This agent evaluates the client's clarification answer in conjunction with
prior state, uncertainty, and risk assessments to produce an updated state,
determine resolved vs remaining uncertainties, and reassess safety/risk.

IMPORTANT design constraints
-----------------------------
* Does NOT blindly trust the clarification answer.
* Preserves previously known information and incorporates genuinely new facts.
* Must detect whether safety/risk became apparent during clarification.
* Determines updated status (CLEAR / UNCERTAIN / AMBIGUOUS) and route_decision.

Output (AgentMessage):
---------------------
status:                 "CLEAR" | "UNCERTAIN" | "AMBIGUOUS"
payload:
    updated_state:          Dict[str, Any]
    uncertainty:            Dict[str, Any]
    risk:                   Dict[str, Any]
    resolved_information:   List[str]
    remaining_uncertainty:  List[str]
    status:                 "CLEAR" | "UNCERTAIN" | "AMBIGUOUS"
    route_decision:         "CLEAR" | "UNCERTAIN" | "HIGH-RISK"
    confidence:             float (0.0–1.0)
    reasoning_summary:      str
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

from .base import Agent, AgentContext, AgentError, AgentMessage
from .risk_agent import RiskAgent
from .uncertainty_agent import UncertaintyAgent

logger = logging.getLogger(__name__)

# Signals indicating evasive or uninformative answers that fail to resolve uncertainty
_UNINFORMATIVE_ANSWERS = [
    "i don't know", "not clear", "not sure", "nothing", "not much", "just so-so", "don't want to say", "whatever", "can't remember"
]

_FILLER_WORDS = {
    "i", "i'm", "im", "um", "uh", "well", "just", "so", "yeah", "no", "maybe", "the", "a", "it", "is", "that",
    "really", "mean", "and", "or", "to", "of", "my", "me", "you", "know",
}


def _is_uninformative_answer(answer: str) -> bool:
    """True when the answer carries (almost) no new content.

    Evasive phrases are removed first; the answer is uninformative if fewer
    than 4 non-filler words remain. Comparison is case-insensitive.
    """
    text = str(answer or "").strip().lower()
    if len(text) < 4:
        return True
    for phrase in _UNINFORMATIVE_ANSWERS:
        text = text.replace(phrase, " ")
    words = [w.strip(".,!?;:'\"()") for w in text.split()]
    content_words = [w for w in words if w and w not in _FILLER_WORDS]
    return len(content_words) < 4


class ReassessmentAgent(Agent):
    """Reassesses client state, uncertainty, and risk after receiving clarification."""

    name = "reassessment_agent"

    def __init__(self, backend: Optional[Any] = None) -> None:
        self.backend = backend
        self._uncertainty_agent = UncertaintyAgent()
        self._risk_agent = RiskAgent()

    def run(self, ctx: AgentContext, clarification_answer: Optional[str] = None) -> AgentMessage:
        try:
            return self._run(ctx, clarification_answer)
        except AgentError:
            raise
        except Exception as exc:
            logger.exception("[%s] unexpected error: %s", self.name, exc)
            return AgentMessage(
                agent=self.name,
                status="UNCERTAIN",
                error=str(exc),
                payload={
                    "updated_state": ctx.state_output or {},
                    "uncertainty": ctx.uncertainty_output or {},
                    "risk": ctx.risk_output or {},
                    "resolved_information": [],
                    "remaining_uncertainty": ["reassessment_error"],
                    "status": "UNCERTAIN",
                    "route_decision": "UNCERTAIN",
                    "confidence": 0.0,
                    "reasoning_summary": f"Reassessment error: {exc}",
                },
            )

    def _run(self, ctx: AgentContext, clarification_answer: Optional[str] = None) -> AgentMessage:
        # 1. Obtain the clarification answer
        answer = clarification_answer
        if not answer:
            # Check context fields
            answer = getattr(ctx, "clarification_answer", None)
            if not answer and ctx.metadata.get("clarification_answer"):
                answer = str(ctx.metadata["clarification_answer"])
            elif not answer and ctx.current_message:
                answer = ctx.current_message
        answer = str(answer or "").strip()

        # 2. Pull prior outputs
        prior_state = copy.deepcopy(ctx.state_output or {})
        prior_unc = copy.deepcopy(ctx.uncertainty_output or {})
        prior_risk = copy.deepcopy(ctx.risk_output or {})
        clar_payload = getattr(ctx, "clarification_output", {}) or ctx.metadata.get("clarification_output", {})

        target_info = clar_payload.get("target_information", [])
        uncertain_fields = prior_unc.get("uncertain_fields", [])
        missing_info = prior_unc.get("missing_information", [])

        # 3. Check for new RISK signals in the clarification answer
        temp_ctx = ctx.copy()
        temp_ctx.current_message = answer
        risk_msg = self._risk_agent.run(temp_ctx)
        reassessed_risk = risk_msg.payload

        # If prior risk was already HIGH or new answer contains HIGH risk signals
        if prior_risk.get("severity") == "HIGH" or reassessed_risk.get("severity") == "HIGH":
            final_risk = reassessed_risk if reassessed_risk.get("severity") == "HIGH" else prior_risk
            payload: Dict[str, Any] = {
                "updated_state": prior_state,
                "uncertainty": prior_unc,
                "risk": final_risk,
                "resolved_information": [],
                "remaining_uncertainty": missing_info,
                "status": "HIGH-RISK",
                "route_decision": "HIGH-RISK",
                "confidence": 0.95,
                "reasoning_summary": "High-risk safety signal detected in client clarification response.",
            }
            _validate_reassessment_payload(payload)
            return AgentMessage(
                agent=self.name,
                status="HIGH",
                evidence=final_risk.get("evidence", []),
                confidence=0.95,
                payload=payload,
            )

        # 4. Check if clarification answer is informative or uninformative
        is_uninformative = _is_uninformative_answer(answer)

        resolved_information: List[str] = []
        remaining_uncertainty: List[str] = []

        updated_state = prior_state
        known_info = list(updated_state.get("known_information", []))
        unknown_info = list(updated_state.get("unknown_information", []))

        if not is_uninformative and len(answer) >= 5:
            # Genuine new factual content provided
            new_fact = f"[Clarification Gained] {answer}"
            if new_fact not in known_info:
                known_info.append(new_fact)
            updated_state["known_information"] = known_info

            # Identify which missing information items were resolved by the answer
            for item in missing_info:
                item_str = str(item)
                resolved = False
                for t in target_info:
                    if t.lower() in item_str.lower() or item_str.lower() in t.lower():
                        resolved = True
                        break
                if not resolved:
                    for f in uncertain_fields:
                        if f.lower() in item_str.lower():
                            resolved = True
                            break

                if resolved:
                    resolved_information.append(item_str)
                    if item in unknown_info:
                        unknown_info.remove(item)
                else:
                    remaining_uncertainty.append(item_str)

            updated_state["unknown_information"] = unknown_info
        else:
            # Answer was evasive, uninformative, or missing — nothing resolved
            remaining_uncertainty = list(missing_info)
            uninf_fact = f"[Uninformative Clarification] Client response: '{answer}'"
            if uninf_fact not in known_info:
                known_info.append(uninf_fact)
            updated_state["known_information"] = known_info

        # 5. Re-run Uncertainty Assessment on the updated state
        temp_ctx.state_output = updated_state
        temp_mem = copy.deepcopy(ctx.memory_output or {})
        # If safety information was resolved and no other risk detected, update risk status and traits
        if any("medical" in r or "safety" in r for r in resolved_information):
            reassessed_risk["severity"] = "LOW"
            reassessed_risk["risk_status"] = "NO_EVIDENCE"
            reassessed_risk["evidence"] = [f"Clarified safety status: {answer}"]
            if isinstance(temp_mem, dict):
                traits = temp_mem.setdefault("known_static_traits", {})
                traits["medical_history"] = answer

        temp_ctx.risk_output = reassessed_risk
        temp_ctx.memory_output = temp_mem
        unc_msg = self._uncertainty_agent.run(temp_ctx)
        reassessed_unc = unc_msg.payload

        # 6. Determine final status and route_decision
        if is_uninformative:
            status = "UNCERTAIN"
            route_decision = "UNCERTAIN"
            reasoning = "Clarification answer was uninformative or absent; uncertainty remains unresolved."
        elif remaining_uncertainty:
            # Partial resolution
            status = "UNCERTAIN" if len(remaining_uncertainty) >= 2 else "CLEAR"
            route_decision = status
            reasoning = f"Clarification resolved {len(resolved_information)} items; {len(remaining_uncertainty)} items remain."
        else:
            status = "CLEAR"
            route_decision = "CLEAR"
            reassessed_unc["status"] = "CLEAR"
            reassessed_unc["clarification_required"] = False
            reassessed_unc["clarification_needed"] = False
            reasoning = f"Clarification successfully resolved priority informational uncertainty ({', '.join(resolved_information)})."

        payload = {
            "updated_state": updated_state,
            "uncertainty": reassessed_unc,
            "risk": reassessed_risk,
            "resolved_information": resolved_information,
            "remaining_uncertainty": remaining_uncertainty,
            "status": status,
            "route_decision": route_decision,
            "confidence": 0.85 if status == "CLEAR" else 0.65,
            "reasoning_summary": reasoning,
        }

        _validate_reassessment_payload(payload)

        return AgentMessage(
            agent=self.name,
            status=status,
            evidence=[f"Resolved: {len(resolved_information)}, Remaining: {len(remaining_uncertainty)}"],
            confidence=payload["confidence"],
            payload=payload,
        )


def _validate_reassessment_payload(payload: Dict[str, Any]) -> None:
    """Validate reassessment output schema."""
    conf = payload.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
        raise AgentError("reassessment_agent", f"Invalid confidence: {conf}")
    for req in ("updated_state", "uncertainty", "risk", "resolved_information", "remaining_uncertainty", "status", "route_decision", "reasoning_summary"):
        if req not in payload:
            raise AgentError("reassessment_agent", f"Missing required payload field: {req}")
    if payload.get("route_decision") not in ("CLEAR", "UNCERTAIN", "HIGH-RISK"):
        raise AgentError("reassessment_agent", f"Invalid route_decision: {payload.get('route_decision')}")
