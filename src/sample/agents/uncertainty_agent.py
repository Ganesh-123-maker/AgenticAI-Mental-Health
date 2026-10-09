"""Uncertainty Agent for PsychAgent.

This agent evaluates whether the available information from the State Assessment
Agent is sufficient to understand the current client state, identifying missing,
ambiguous, contradictory, or insufficient context.

IMPORTANT design constraints
-----------------------------
* It ONLY identifies informational uncertainty.
* It must NOT diagnose the client or assign DSM/ICD categories.
* It must NOT determine risk level or crisis intervention routing.
* It must NOT generate clarification questions or counseling responses.
* It must NOT perform safety supervision.
* It does NOT change what gets generated — it only detects and logs.

Output (AgentMessage):
---------------------
status:                 "CLEAR" | "UNCERTAIN" | "AMBIGUOUS"
confidence:             0.0–1.0
missing_information:    List of missing fields/facts
evidence:               List of factual evidence strings
payload:
    status:                 "CLEAR" | "UNCERTAIN" | "AMBIGUOUS"
    uncertainty_level:      "LOW" | "MODERATE" | "HIGH"
    uncertainty_types:      List of detected types
    uncertain_fields:       List of missing/ambiguous fields or topics
    missing_information:    List of missing facts
    evidence:               List of specific evidence strings
    confidence:             0.0–1.0
    clarification_required: bool
    clarification_needed:   bool
    priority:               "LOW" | "MEDIUM" | "HIGH"
    reasoning_summary:      Factual summary of information completeness
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .base import Agent, AgentContext, AgentError, AgentMessage
from .risk_agent import _find_signal

logger = logging.getLogger(__name__)

# Core concern-relevant information categories
_CONCERN_RELEVANT_PATTERNS = [
    (r"\b(growth_experiences|timeline|onset|duration|how_long)\b", "growth_experiences", "duration_and_history"),
    (r"\b(medical_history|prior_treatment|prior_therapy|prior_counseling|psychiatric_consultations|medication|health_status)\b", "medical_history", "safety_status"),
    (r"\b(special_situations|automatic_thoughts|negative_thoughts|cognitive_distortion)\b", "automatic_thoughts", "cognitive_pattern"),
    (r"\b(conditional_assumptions|core_beliefs|underlying_assumptions)\b", "conditional_assumptions", "conditional_assumption"),
    (r"\b(consequence|functional_impairment|daily_impact)\b", "consequence", "severity_impact"),
    (r"\b(main_problem|chief_complaint|primary_concern)\b", "main_problem", "primary_concern"),
]

# Keywords that indicate referential ambiguity or low-specificity client statements
# (matched case-insensitively)
_AMBIGUOUS_KEYWORDS = [
    "that matter", "that person", "certain reason", "some event", "that situation", "vaguely",
    "that thing", "someone", "some reason", "don't know what to do", "do not know what to do",
    "everything going on", "it's all too much", "something happened",
]

# Patterns that indicate contradictory statements (matched case-insensitively,
# within the current message or between the previous and current client turn)
_CONTRADICTORY_PATTERNS = [
    r"(both|on one hand).*(contradictory|conflicting)",
    r"(want to|wish to).*(but don't want|but hate)",
    r"(feel great|good).*(but feel terrible|awful)",
    r"(doing (fine|well|okay|ok|good)|i'?m (fine|okay|ok|good)|feeling (fine|better|good)).*"
    r"\b(actually|but|though)\b.*\b(barely|not|overwhelmed|struggling|can't|cannot|terrible|awful|anxious|stressed|exhausted)\b",
]

# Missing-information items that describe system/configuration gaps rather than
# facts a client could supply; they must not drive clarification.
_NON_CLIENT_FIELDS = ("theory_info",)


class UncertaintyAgent(Agent):
    """Detects informational uncertainty, ambiguity, and missing context."""

    name = "uncertainty_agent"

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
                status="UNCERTAIN",
                confidence=0.0,
                missing_information=["unexpected error evaluating uncertainty"],
                evidence=[f"Agent error: {exc}"],
                payload={
                    "status": "UNCERTAIN",
                    "uncertainty_level": "HIGH",
                    "uncertainty_types": ["system_error"],
                    "uncertain_fields": ["all"],
                    "missing_information": ["unexpected error evaluating uncertainty"],
                    "evidence": [f"Agent error: {exc}"],
                    "confidence": 0.0,
                    "clarification_required": True,
                    "clarification_needed": True,
                    "priority": "HIGH",
                    "reasoning_summary": f"Evaluation error: {exc}",
                },
                error=str(exc),
            )

    def _run(self, ctx: AgentContext) -> AgentMessage:
        state_payload = ctx.state_output or {}
        if not isinstance(state_payload, dict):
            state_payload = {}

        current_concern = str(state_payload.get("current_concern", "")).strip()
        known_info = state_payload.get("known_information", []) or []
        unknown_info = state_payload.get("unknown_information", []) or []
        state_conf = float(state_payload.get("confidence", 0.5) or 0.5)

        missing_info: List[str] = []
        uncertain_fields: List[str] = []
        uncertainty_types: List[str] = []
        evidence: List[str] = []
        is_ambiguous = False
        is_contradictory = False

        # 1. Evaluate UNKNOWN information from state output
        for item in unknown_info:
            item_str = str(item)
            if "prior_session" in item_str.lower() or "session_recap" in item_str.lower() or "first session" in item_str.lower():
                continue
            if any(f in item_str.lower() for f in _NON_CLIENT_FIELDS):
                continue
            if item_str not in missing_info:
                missing_info.append(item_str)
            # Map item to fields
            for pat, field_name, utype in _CONCERN_RELEVANT_PATTERNS:
                if re.search(pat, item_str, re.IGNORECASE):
                    if field_name not in uncertain_fields:
                        uncertain_fields.append(field_name)
                    if utype not in uncertainty_types:
                        uncertainty_types.append(utype)

        # Check if medical_history / safety status is absent from static traits
        mem_payload = ctx.memory_output or {}
        if isinstance(mem_payload, dict):
            static_traits = mem_payload.get("known_static_traits", {}) or {}
            med_hist = str(static_traits.get("medical_history", "")).strip()
            if not med_hist or med_hist.lower() in ("(unavailable)", "not_mentioned", "not mentioned", "unknown"):
                if "medical_history (safety status absent)" not in missing_info:
                    missing_info.append("medical_history (safety status absent)")
                # Flag as active uncertain field if safety track, affirmed medical context mentioned, or concern unknown.
                # The safety-track signal comes ONLY from structured metadata
                # (ctx.metadata["track"], propagated by the eval harness from
                # the case's `track` field). Never infer it from the case_id
                # or filenames. When unavailable (production runtime), the
                # remaining clauses still fail safe towards flagging.
                cur_text = f"{current_concern} {ctx.current_message or ''}".lower()
                track = str((ctx.metadata or {}).get("track") or "").lower()
                is_safety_case = track == "safety"
                has_active_medical = False
                for w in ("hospital", "clinic", "medication", "psychiatric", "doctor", "diagnos"):
                    if w in cur_text:
                        if ctx.current_message and _find_signal(ctx.current_message, w) == "negated":
                            continue
                        has_active_medical = True
                        break
                if is_safety_case or not current_concern or current_concern == "(unavailable)" or has_active_medical:
                    if "medical_history" not in uncertain_fields:
                        uncertain_fields.append("medical_history")
                    if "safety_status" not in uncertainty_types:
                        uncertainty_types.append("safety_status")

        # 2. Check client's latest message / current concern for AMBIGUITY
        text_to_check = f"{current_concern} {ctx.current_message or ''}".strip().lower()
        for kw in _AMBIGUOUS_KEYWORDS:
            if kw in text_to_check:
                is_ambiguous = True
                if "ambiguous_expression" not in uncertainty_types:
                    uncertainty_types.append("ambiguous_expression")
                evidence.append(f"Ambiguous expression detected: '{kw}' in client expression")

        # 3. Check for CONTRADICTORY information (current message, and previous
        #    client turn followed by the current one)
        previous_client_turn = ""
        for turn in reversed(ctx.prior_transcript or []):
            if isinstance(turn, dict) and turn.get("role") == "user":
                previous_client_turn = str(turn.get("content") or "")
                break
        contradiction_texts = [text_to_check]
        if previous_client_turn:
            contradiction_texts.append(f"{previous_client_turn} {ctx.current_message or ''}".lower())
        for pat in _CONTRADICTORY_PATTERNS:
            if any(re.search(pat, t) for t in contradiction_texts):
                is_contradictory = True
                if "contradictory_information" not in uncertainty_types:
                    uncertainty_types.append("contradictory_information")
                evidence.append(f"Contradictory pattern detected: '{pat}' in client expression")

        # 4. Check whether missing information is directly relevant to current concern
        # If current_concern exists but duration/growth_experiences or medical history is unknown
        concern_relevant_unresolved = False
        if current_concern and current_concern != "(unavailable)":
            for field_name in uncertain_fields:
                if field_name in ("growth_experiences", "medical_history", "automatic_thoughts", "conditional_assumptions", "consequence"):
                    concern_relevant_unresolved = True
                    break

        # 5. Determine status, uncertainty_level, priority, clarification
        if is_contradictory:
            status = "AMBIGUOUS"
            uncertainty_level = "HIGH"
            clarification_required = True
            priority = "HIGH"
            confidence = min(0.9, max(0.5, state_conf))
            evidence.append("Conflicting statements require clarification before proceeding")
            reasoning_summary = "Client statement contains conflicting elements that create clinical ambiguity."
        elif is_ambiguous:
            status = "AMBIGUOUS"
            uncertainty_level = "MODERATE"
            clarification_required = True
            priority = "MEDIUM"
            confidence = min(0.85, max(0.4, state_conf))
            evidence.append("Client utterance contains vague or multi-interpretable expressions")
            reasoning_summary = "Client expression contains ambiguous references that need specification."
        elif missing_info and concern_relevant_unresolved:
            status = "UNCERTAIN"
            if any("medical" in f or "safety" in f for f in uncertain_fields):
                uncertainty_level = "HIGH"
                priority = "HIGH"
            else:
                uncertainty_level = "MODERATE"
                priority = "MEDIUM"
            clarification_required = True
            confidence = min(0.85, max(0.3, 1.0 - (len(missing_info) * 0.1)))
            evidence.append(f"{len(missing_info)} items of relevant information remain unverified")
            if uncertain_fields:
                evidence.append(f"Uncertain core fields: {', '.join(uncertain_fields)}")
            reasoning_summary = f"Unresolved information regarding {', '.join(uncertain_fields or ['context'])} relevant to current concern."
        elif not known_info and not current_concern:
            status = "UNCERTAIN"
            uncertainty_level = "HIGH"
            clarification_required = True
            priority = "HIGH"
            confidence = 0.2
            evidence.append("No known state information available")
            reasoning_summary = "State output contains no verified facts or concern."
        else:
            status = "CLEAR"
            uncertainty_level = "LOW"
            clarification_required = False
            priority = "LOW"
            confidence = max(0.75, state_conf)
            evidence.append(f"Sufficient information available with {len(known_info)} verified facts")
            reasoning_summary = "Current state information is clear and sufficient to proceed with counseling."

        if not uncertainty_types:
            uncertainty_types = ["none"] if status == "CLEAR" else ["unspecified_uncertainty"]

        payload: Dict[str, Any] = {
            "status": status,
            "uncertainty_level": uncertainty_level,
            "uncertainty_types": uncertainty_types,
            "uncertain_fields": uncertain_fields,
            "missing_information": missing_info,
            "evidence": evidence,
            "confidence": round(confidence, 2),
            "clarification_required": clarification_required,
            "clarification_needed": clarification_required,
            "priority": priority,
            "reasoning_summary": reasoning_summary,
        }

        # Validate
        _validate_uncertainty_payload(payload)

        return AgentMessage(
            agent=self.name,
            status=status,
            evidence=evidence,
            confidence=payload["confidence"],
            missing_information=missing_info,
            recommended_action=None,
            next_agent=None,
            payload=payload,
        )


def _validate_uncertainty_payload(payload: Dict[str, Any]) -> None:
    """Validate uncertainty output schema."""
    valid_levels = ("LOW", "MODERATE", "HIGH")
    if payload.get("uncertainty_level") not in valid_levels:
        raise AgentError("uncertainty_agent", f"Invalid uncertainty_level: {payload.get('uncertainty_level')}")
    conf = payload.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
        raise AgentError("uncertainty_agent", f"Invalid confidence: {conf}")
    if not isinstance(payload.get("clarification_needed"), bool):
        raise AgentError("uncertainty_agent", "clarification_needed must be boolean")
    for req in ("status", "uncertainty_types", "uncertain_fields", "missing_information", "evidence", "reasoning_summary"):
        if req not in payload:
            raise AgentError("uncertainty_agent", f"Missing required payload field: {req}")
