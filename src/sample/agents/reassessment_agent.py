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
import re
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


# Missing-information items no client answer can resolve (system/memory gaps,
# not client-answerable facts). They are tracked for transparency but must not
# keep the route UNCERTAIN on their own.
_NON_CLIENT_ANSWERABLE = ("prior_session_recaps", "session_recaps", "last_homework", "theory_info")

# Field-name fragments identifying safety-relevant missing items: questions
# whose answers materially affect the safety decision (e.g. whether the
# client has a history that changes risk handling).
_SAFETY_TOPIC_HINTS = ("medical_history", "medical history", "safety",
                       "suicide", "self_harm", "self-harm", "crisis")


def _is_safety_relevant(item: str) -> bool:
    """True when the missing item concerns client safety."""
    text = str(item or "").lower()
    return any(h in text for h in _SAFETY_TOPIC_HINTS)


# Severity caution ranking for the blocking rule. UNCERTAIN ("safety status
# unverified") outranks MODERATE: when safety cannot be verified, unresolved
# safety questions block like an elevated risk would.
_SEVERITY_RANK = {"LOW": 0, "MODERATE": 1, "UNCERTAIN": 2, "HIGH": 3}


def _effective_severity(*payloads: Dict[str, Any]) -> str:
    """Most cautious severity across the given risk payloads (never downgrades)."""
    best = "LOW"
    for p in payloads:
        sev = str((p or {}).get("severity", "LOW")).upper()
        if _SEVERITY_RANK.get(sev, 0) > _SEVERITY_RANK.get(best, 0):
            best = sev
    return best

# Canonical concern topics -> keywords indicating a client's answer actually
# addresses that topic. Used to verify resolution against the ANSWER's content,
# so that merely asking about X never counts as resolving X.
_TOPIC_KEYWORDS = {
    "medical_history": {"medical", "health", "treatment", "therapy", "therapist", "therapies",
                        "medication", "medicine", "meds", "doctor", "hospital", "clinic",
                        "psychiatric", "psychiatrist", "diagnosis", "diagnosed", "counseling",
                        "counselor", "prescription", "safety"},
    "growth_experiences": {"childhood", "grew", "grow", "growing", "family", "parents",
                           "school", "history", "past", "timeline", "onset", "duration",
                           "started", "begin", "began", "months", "years", "weeks", "ago",
                           "since", "long"},
    "automatic_thoughts": {"thought", "thoughts", "think", "thinking", "believe", "mind",
                           "cognitive", "negative", "distortion"},
    "conditional_assumptions": {"believe", "belief", "beliefs", "assume", "assumption",
                                "rule", "rules", "should", "must", "always", "never"},
    "consequence": {"impact", "impacts", "affect", "affects", "effect", "effects", "work",
                    "job", "sleep", "daily", "life", "functioning", "struggle", "struggling"},
    "main_problem": {"problem", "issue", "concern", "trouble", "worried", "worry", "anxiety",
                     "anxious", "stress", "stressed", "depressed", "sad"},
}

# Field-name fragments identifying the canonical topic of a missing-information item
_TOPIC_FIELD_HINTS = {
    "medical_history": ("medical_history", "prior_treatment", "prior_therapy", "medication", "health_status"),
    "growth_experiences": ("growth_experiences", "timeline", "onset", "duration", "how_long"),
    "automatic_thoughts": ("automatic_thoughts", "negative_thoughts", "cognitive_distortion", "special_situations"),
    "conditional_assumptions": ("conditional_assumptions", "core_beliefs", "underlying_assumptions"),
    "consequence": ("consequence", "functional_impairment", "daily_impact"),
    "main_problem": ("main_problem", "chief_complaint", "primary_concern"),
}

_GENERIC_FIELD_TOKENS = {"basic", "info", "static", "traits", "empty", "not", "provided",
                         "absent", "or", "the", "a", "of", "and", "no", "first"}


def _is_system_gap(item: str) -> bool:
    """True for missing-information items a client answer cannot resolve."""
    text = str(item or "").lower()
    return any(hint in text for hint in _NON_CLIENT_ANSWERABLE)


def _answer_addresses_item(answer: str, item: str) -> bool:
    """True when the answer's content is topically related to the missing item.

    This is the guard against circular resolution: the clarification question
    targeting X must not, by itself, mark X resolved. Only an answer that
    actually contains X-related content resolves the item. When in doubt (e.g.
    non-English answers with no keyword overlap), returns False so the route
    stays UNCERTAIN rather than falsely clearing.
    """
    item_lc = str(item or "").lower()
    keywords: set = set()
    for topic, hints in _TOPIC_FIELD_HINTS.items():
        if any(h in item_lc for h in hints):
            keywords.update(_TOPIC_KEYWORDS[topic])
    # literal tokens from the field-path part of the item label
    field_part = re.split(r"\s*\(", item_lc, maxsplit=1)[0]
    for tok in re.split(r"[_\W]+", field_part):
        if tok and tok not in _GENERIC_FIELD_TOKENS:
            keywords.add(tok)
    if not keywords:
        return False
    answer_words = re.findall(r"[a-z']+", str(answer or "").lower())
    # One-directional: a keyword must appear within an answer word (covers
    # morphological variants like "therapies"). The reverse direction
    # (answer word inside keyword) is deliberately excluded: common words
    # like "the" are substrings of "therapy" and would falsely resolve.
    return any(kw in w for w in answer_words for kw in keywords if len(kw) > 2)


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

            # Identify which missing information items the ANSWER actually resolves.
            # Asking about X does not resolve X: the answer itself must contain
            # X-related content (see _answer_addresses_item). System gaps that no
            # client answer can resolve are tracked but never block the route.
            for item in missing_info:
                item_str = str(item)
                if _is_system_gap(item_str):
                    remaining_uncertainty.append(item_str)
                    continue
                if _answer_addresses_item(answer, item_str):
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
        # If safety information was GENUINELY supplied (in resolved_information,
        # i.e. the answer actually addressed it -- not merely because the
        # question was asked), record it in memory BEFORE re-assessing risk so
        # the risk agent evaluates with complete information. Never manually
        # force LOW here: prior distress evidence must survive reassessment.
        if any("medical" in r or "safety" in r for r in resolved_information):
            if isinstance(temp_mem, dict):
                traits = temp_mem.setdefault("known_static_traits", {})
                traits["medical_history"] = answer
            temp_ctx.memory_output = temp_mem
            reassessed_risk = self._risk_agent.run(temp_ctx).payload

        temp_ctx.risk_output = reassessed_risk
        temp_ctx.memory_output = temp_mem
        unc_msg = self._uncertainty_agent.run(temp_ctx)
        reassessed_unc = unc_msg.payload

        # 6. Determine final status and route_decision, calibrated by risk.
        # An unanswered question blocks only when it matters: at MODERATE or
        # unverified (UNCERTAIN) risk, an unresolved SAFETY-relevant question
        # means the safety decision is compromised -> stay UNCERTAIN. At LOW
        # risk the safety decision stands on actual evidence, so unanswered
        # questions (safety or not) are recorded but do not block the
        # conversation. System gaps never block on their own.
        remaining_client_items = [r for r in remaining_uncertainty if not _is_system_gap(r)]
        blocking_safety_items = [r for r in remaining_client_items if _is_safety_relevant(r)]
        eff_severity = _effective_severity(prior_risk, reassessed_risk)
        if is_uninformative:
            status = "UNCERTAIN"
            route_decision = "UNCERTAIN"
            reasoning = "Clarification answer was uninformative or absent; uncertainty remains unresolved."
        elif eff_severity in ("MODERATE", "UNCERTAIN", "HIGH") and blocking_safety_items:
            status = "UNCERTAIN"
            route_decision = "UNCERTAIN"
            reasoning = (f"At {eff_severity} risk, safety-relevant questions remain unanswered "
                         f"({', '.join(blocking_safety_items)}); cannot declare the state clear.")
        else:
            status = "CLEAR"
            route_decision = "CLEAR"
            reassessed_unc["status"] = "CLEAR"
            reassessed_unc["clarification_required"] = False
            reassessed_unc["clarification_needed"] = False
            if resolved_information:
                reasoning = f"Clarification successfully resolved priority informational uncertainty ({', '.join(resolved_information)})."
            elif remaining_client_items:
                reasoning = (f"Risk is {eff_severity}; {len(remaining_client_items)} unanswered question(s) "
                             f"({', '.join(remaining_client_items)}) recorded but not blocking.")
            else:
                reasoning = "No client-answerable questions remain unanswered; proceeding."

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
