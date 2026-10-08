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
        risk_payload = ctx.risk_output or {}
        if not isinstance(risk_payload, dict):
            risk_payload = {}

        clarification_required = bool(unc_payload.get("clarification_required", False))
        uncertainty_types = unc_payload.get("uncertainty_types", []) or []
        uncertain_fields = unc_payload.get("uncertain_fields", []) or []
        missing_info = unc_payload.get("missing_information", []) or []
        unc_priority = unc_payload.get("priority", "LOW")
        risk_severity = str(risk_payload.get("severity", "LOW")).upper()

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

        # Items genuinely resolved in a previous clarification turn must not be
        # asked again. This uses resolved_information (answers that actually
        # addressed the item), never target_information: merely asking does
        # not count as answering.
        reassess_payload = getattr(ctx, "reassessment_output", None) or {}
        if not isinstance(reassess_payload, dict):
            reassess_payload = {}
        resolved_items = reassess_payload.get("resolved_information", []) or []

        def _target_resolved(target_fields: List[str]) -> bool:
            """True if any target field is covered by a resolved item.

            A template's targets are facets of a single question; if the
            client answered any facet, re-asking the template is repetitive.
            """
            return any(
                any(t.lower() in str(r).lower() for r in resolved_items)
                for t in target_fields
            )

        has_safety_gap = (
            "safety_status" in uncertainty_types
            or any("medical" in f or "safety" in f for f in uncertain_fields)
        )

        # Ordered candidate templates. At elevated risk, a safety-relevant gap
        # jumps to first priority (it materially affects the safety decision);
        # at LOW risk the standard discourse order applies. Deterministic:
        # identical inputs always yield the same question.
        candidates: List[str] = []
        if risk_severity in ("HIGH", "MODERATE", "UNCERTAIN") and has_safety_gap:
            candidates.append("safety_status")
        if "contradictory_information" in uncertainty_types:
            candidates.append("contradictory_information")
        if "ambiguous_expression" in uncertainty_types:
            candidates.append("ambiguous_expression")
        if has_safety_gap and "safety_status" not in candidates:
            candidates.append("safety_status")
        if "duration_and_history" in uncertainty_types or any("growth" in f for f in uncertain_fields):
            candidates.append("duration_and_history")
        # Fall back to any other recognized uncertainty type, in order
        for utype in uncertainty_types:
            if utype in _CLARIFICATION_TEMPLATES and utype not in candidates:
                candidates.append(utype)

        # Pick the first candidate with at least one unresolved target.
        selected_name: Optional[str] = None
        selected_template: Optional[Dict[str, Any]] = None
        for name in candidates:
            tmpl = _CLARIFICATION_TEMPLATES[name]
            if not _target_resolved(tmpl["target"]):
                selected_name = name
                selected_template = tmpl
                break

        if selected_template is None:
            # Generic fallback: first field that is not already resolved.
            candidate_fields = [
                f for f in uncertain_fields if not _target_resolved([str(f)])
            ]
            if not candidate_fields:
                candidate_fields = [
                    m for m in missing_info if not _target_resolved([str(m)])
                ]
            if not candidate_fields:
                # Everything is already resolved: nothing left to clarify.
                payload = {
                    "question": "",
                    "questions": [],
                    "target_information": [],
                    "priority": "LOW",
                    "clarification_required": False,
                    "reasoning_summary": "All identified gaps were resolved in a previous turn; no clarification needed.",
                }
                _validate_clarification_payload(payload)
                return AgentMessage(
                    agent=self.name,
                    status="not_required",
                    evidence=["No unresolved gaps remain"],
                    confidence=1.0,
                    payload=payload,
                )
            target_str = candidate_fields[0]
            questions = [f"Regarding what you mentioned, could you tell me more about the background concerning {target_str}?"]
            target_info = [str(target_str)]
            priority = unc_priority
        else:
            questions = list(selected_template["questions"])[:2]
            target_info = list(selected_template["target"])
            priority = selected_template["priority"]

        primary_question = questions[0] if questions else ""
        reasoning = (
            f"Clarification targets priority gap '{', '.join(target_info)}' "
            f"to resolve informational uncertainty."
        )
        if risk_severity in ("HIGH", "MODERATE", "UNCERTAIN") and selected_name == "safety_status":
            reasoning += f" Safety prioritized at {risk_severity} risk."

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
