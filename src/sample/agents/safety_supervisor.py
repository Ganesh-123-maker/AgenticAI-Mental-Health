"""Safety Supervisor Agent for PsychAgent (Phase 8).

Reviews proposed counseling responses before they are considered final.

Outputs:
{
    "approved": bool,
    "safety_status": "SAFE" | "REVISE" | "BLOCK",
    "issues": List[str],
    "risk_consistency": bool,
    "revised_response": Optional[str],
    "reasoning_summary": str
}

Rules:
- SAFE: The response can proceed unchanged. Approved is True.
- REVISE: The response contains a correctable safety problem and requires modification. Approved is False.
- BLOCK: The response should not be returned because it is incompatible with the safety state. Approved is False.
- Does NOT replace the Risk Agent.
- Does NOT perform general counseling.
- Does NOT update memory.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .base import Agent, AgentContext, AgentError, AgentMessage
from .risk_agent import ROMAN_HIGH_CRISIS_FORMS, ZH_HIGH_CRISIS_FORMS

logger = logging.getLogger(__name__)

_CRISIS_RESOURCE_GUIDANCE = (
    "Please contact your family, friends, a trusted person, your local emergency number, or a crisis helpline right now "
    "(for example, Tele-MANAS 14416 in India or 988 in the United States)."
)

_STANDARD_SAFE_FALLBACK = (
    "I care deeply about your safety and current well-being. Facing such intense distress and crisis, "
    "please do not face it alone. We prioritize your life and safety above all else. "
    f"{_CRISIS_RESOURCE_GUIDANCE} "
    "We can pause other discussions and focus first and foremost on ensuring your safety right now."
)

_UNSAFE_DISMISSAL_PHRASES = [
    "don't overthink",
    "it's not a big deal",
    "that's nothing important",
    "you're overreacting",
    "everyone experiences this",
    "no need to worry",
    "relax, it's fine",
    "no need to make a mountain out of a molehill",
    "don't worry about it",
    "it's no big deal",
    "you are overreacting",
    "that's nothing",
]

_FALSE_REASSURANCE_PATTERNS = [
    r"(you are absolutely safe|you definitely have no danger|rest assured, you will not be harmed)",
    r"(no need to worry about your safety|you have no mental illness|you are perfectly normal)",
    r"(I'm taking responsibility|guarantee you won't be harmed|nothing bad will happen)",
    r"(you are completely safe|there is definitely no risk|guaranteed to be fine)",
    # Round 2 fix (D-09 follow-up): the bare guarantees "will not be
    # harmed" and "will be completely fine" were only caught when
    # attached to another flagged phrase, so a partial strip could leave
    # them behind in a revision. They are safety guarantees on their own.
    # Same for "have no mental illness": after "You are completely safe"
    # is stripped, "and have no mental illness" survives without its
    # pronoun, so the bare fragment must match too.
    r"(will not be harmed|won't be harmed)",
    r"will be completely fine",
    r"have no mental illness",
]

_UNSUPPORTED_DIAGNOSIS_PATTERNS = [
    r"(you have been diagnosed with|according to diagnosis you have|you have severe depression|you have schizophrenia|you have borderline personality disorder)",
    r"(you are diagnosed with|you definitely suffer from bipolar|clinical depression confirmed)",
]

_PREMATURE_CERTAINTY_PATTERNS = [
    r"since you were a child",
    r"you have been suffering from",
    r"as you mentioned in previous two therapies",
    r"because of what happened three years ago",
]

_INTERNAL_LEAKAGE_PATTERNS = [
    r"<think>",
    r"</think>",
    r"<assessment>",
    r"Orchestrator",
    r"RiskAgent",
    r"AgentContext",
    r"system_prompt",
]

# Neutral revision used when a flagged draft cannot be cleaned by
# substitution: a safe, non-diagnostic acknowledgement with no internal
# tokens and no fabricated facts.
_NEUTRAL_REVISION = (
    "I hear what you're sharing. Let's focus on what you're "
    "experiencing right now and one small, safe step that could help."
)
# violence (Round 2 fix, D-07). These match *instructional* phrasing
# ("here is how you can hurt yourself", "cut deeply"), not mere mentions
# of self-harm ("if you have thoughts of hurting yourself, please call…"
# does not match). A draft matching any of these is BLOCKed, never
# delivered, regardless of route or risk severity.
_HARMFUL_INSTRUCTIONS_PATTERNS = [
    r"how (to|can you|do you|i can) (hurt|harm|kill) (yourself|myself|oneself)",
    r"here'?s how (you can|to) (hurt|harm|kill|end)",
    r"cut (yourself|deeply|deep)",
    r"cut deeply",
    r"(easiest|best|quickest|simplest) way to (end|kill|hurt|harm)",
    r"steps? to (end|kill) (your|my) life",
    r"steps? to (kill|hurt|harm) (yourself|myself|oneself)",
    r"take (an )?overdose",
    r"\b(hang|shoot|stab) yourself\b",
    r"how to (end|take) (your|my) (life|own life)",
]


class SafetySupervisor(Agent):
    """Supervises counselor responses for safety, uncertainty congruence, and route adherence."""

    name = "safety_supervisor"

    def __init__(self, backend: Optional[Any] = None) -> None:
        self.backend = backend

    def run(self, ctx: AgentContext, draft_response: Optional[str] = None) -> AgentMessage:
        """Review the proposed response and determine approval and safety status.

        Args:
            ctx: Shared AgentContext containing upstream agent outputs.
            draft_response: Proposed response string. Defaults to counseling_output.

        Returns:
            AgentMessage containing approved, safety_status, issues, risk_consistency,
            revised_response, and reasoning_summary.
        """
        try:
            return self._run(ctx, draft_response)
        except AgentError:
            raise
        except Exception as exc:
            logger.exception("[%s] unexpected error: %s", self.name, exc)
            payload = {
                "approved": False,
                "safety_status": "BLOCK",
                "issues": [f"Safety supervisor evaluation error: {exc}"],
                "risk_consistency": False,
                "revised_response": _STANDARD_SAFE_FALLBACK,
                "reasoning_summary": f"Evaluation error: {exc}",
                "verdict": "ESCALATE",
                "rationale": f"Fail-closed after supervisor error: {exc}",
                "checks": {
                    "risk_congruence": False,
                    "uncertainty_congruence": False,
                    "route_congruence": False,
                },
                "suggested_revision": None,
                "safe_fallback": _STANDARD_SAFE_FALLBACK,
            }
            return AgentMessage(agent=self.name, status="error", error=str(exc), payload=payload)

    def _run(self, ctx: AgentContext, draft_response: Optional[str] = None) -> AgentMessage:
        response_text = draft_response
        if not response_text:
            counsel_payload = getattr(ctx, "counseling_output", None) or ctx.metadata.get("counseling_output", {})
            response_text = counsel_payload.get("response") or counsel_payload.get("response_text", "")
        response_text = str(response_text or "").strip()

        risk_payload = ctx.risk_output or {}
        risk_severity = str(risk_payload.get("severity", "LOW")).upper()
        risk_status = str(risk_payload.get("risk_status", "NO_EVIDENCE")).upper()
        risk_signals = list(risk_payload.get("signals_detected", []) or [])
        immediate_safety_concern = bool(risk_payload.get("immediate_safety_concern", False))

        unc_payload = ctx.uncertainty_output or {}
        unc_status = str(unc_payload.get("status", "CLEAR")).upper()
        uncertain_fields = list(unc_payload.get("uncertain_fields", []) or [])

        orch_payload = getattr(ctx, "routing_output", None) or {}
        route = str(orch_payload.get("route", "CLEAR")).upper()

        client_utterance = str(ctx.current_message or "")

        issues: List[str] = []
        approved: bool = True
        safety_status: str = "SAFE"
        risk_consistency: bool = True
        revised_response: Optional[str] = None
        reasoning_summary: str = ""

        for pat in _INTERNAL_LEAKAGE_PATTERNS:
            if re.search(pat, response_text, re.IGNORECASE):
                issues.append("Response exposes internal agent formatting or prompt tokens.")
                safety_status = "REVISE"
                approved = False

        for pat in _UNSUPPORTED_DIAGNOSIS_PATTERNS:
            if re.search(pat, response_text, re.IGNORECASE):
                issues.append("Response makes unsupported psychiatric diagnostic assertions.")
                safety_status = "REVISE"
                approved = False

        if unc_status in ("UNCERTAIN", "AMBIGUOUS") and uncertain_fields:
            for pat in _PREMATURE_CERTAINTY_PATTERNS:
                if re.search(pat, response_text, re.IGNORECASE):
                    issues.append(f"Response asserts unverified historical certainty on uncertain fields: {uncertain_fields}")
                    safety_status = "REVISE"
                    approved = False

        is_uncertain_safety = (
            risk_severity == "UNCERTAIN"
            or (unc_status in ("UNCERTAIN", "AMBIGUOUS") and any("medical" in f or "risk" in f for f in uncertain_fields))
        )
        if is_uncertain_safety:
            for pat in _FALSE_REASSURANCE_PATTERNS:
                if re.search(pat, response_text, re.IGNORECASE):
                    issues.append("Response provides false reassurance guaranteeing client safety while safety information remains uncertain.")
                    safety_status = "REVISE"
                    risk_consistency = False
                    approved = False

        # Round 2 fix (Stream A D1): risk_status and
        # immediate_safety_concern are now actually used below — the
        # route-mismatch branch fires on EVIDENCE_OF_RISK as well as HIGH
        # severity, and the HIGH-RISK branch runs when either flag says
        # there is an immediate concern, so a future detector that emits
        # EVIDENCE_OF_RISK without the HIGH severity wording is still
        # gated. (The live RiskAgent sets all three consistently, so this
        # changes no current live-input outcome.)
        if (risk_severity == "HIGH" or risk_status == "EVIDENCE_OF_RISK" or immediate_safety_concern) and route != "HIGH-RISK":
            issues.append("High risk severity detected by Risk Agent, but Orchestrator route was not HIGH-RISK. Re-routing required.")
            risk_consistency = False
            approved = False
            safety_status = "REVISE"
            verdict = "RE-ROUTE"
        elif route == "HIGH-RISK" or risk_severity == "HIGH" or risk_status == "EVIDENCE_OF_RISK" or immediate_safety_concern:
            response_lower = response_text.lower()
            utterance_lower = client_utterance.lower()
            signals_lower = " ".join(str(s) for s in risk_signals).lower()

            has_dismissal = any(p in response_lower for p in _UNSAFE_DISMISSAL_PHRASES)

            # NOTE: "life" was deliberately removed from this list (Day 2):
            # any draft mentioning "life" ("Life has many chapters...")
            # previously counted as safety-aware on HIGH-RISK turns, which
            # let generic counseling drafts pass the safety gate. The
            # remaining keywords all name safety, support, or help-seeking.
            has_safety_awareness = any(
                kw in response_lower
                for kw in [
                    "safety", "support", "concern", "accompany you", "crisis", "seek help", "professional help", "hospital", "hotline", "helpline", "friends", "protect"
                ]
            )

            # Round 2 fix (D-07): the acute list was narrower than the risk
            # agent's HIGH forms — "hurt/harm myself" is detected as HIGH
            # by the risk agent but did not count as acute here, so a
            # no-safety-awareness draft on such a turn only got REVISE.
            is_acute_crisis = any(
                kw in utterance_lower or kw in signals_lower
                for kw in [
                    "suicide", "self-harm", "despair", "want to die", "don't want to live", "end life", "cutting wrists", "jump off building", "kill myself", "killing myself", "end my life", "take my own life",
                    "hurt myself", "hurting myself", "harm myself", "harming myself",
                    "hurt yourself", "hurting yourself", "harm yourself", "harming yourself",
                    "hurt oneself", "harm oneself",
                    *ZH_HIGH_CRISIS_FORMS,
                    *ROMAN_HIGH_CRISIS_FORMS,
                ]
            )

            if has_dismissal:
                issues.append("Response improperly minimizes or dismisses acute crisis/safety risk.")
                risk_consistency = False
                approved = False
                safety_status = "BLOCK"
                revised_response = _STANDARD_SAFE_FALLBACK
            elif not has_safety_awareness:
                risk_consistency = False
                approved = False
                if is_acute_crisis:
                    issues.append("Response ignores acute safety risk and lacks mandatory safety-controlled crisis protocol.")
                    safety_status = "BLOCK"
                    revised_response = _STANDARD_SAFE_FALLBACK
                else:
                    issues.append("Route is HIGH-RISK but response lacks supportive safety framing.")
                    safety_status = "REVISE"
                    revised_response = (
                        "I can sense the distress and pressure you are experiencing. Please remember that your safety "
                        "is paramount. We can work together to ensure you have the necessary safety and support in place. "
                        f"{_CRISIS_RESOURCE_GUIDANCE}"
                    )
            else:
                risk_consistency = True

        # Round 2 fix (D-07): the supervisor never inspected the draft
        # itself for instructions facilitating self-harm, so a draft
        # containing explicit instructions only got a generic REVISE.
        # This check runs regardless of route/severity and BLOCKs.
        if any(re.search(pat, response_text, re.IGNORECASE) for pat in _HARMFUL_INSTRUCTIONS_PATTERNS):
            issues.append("Response contains instructions facilitating self-harm or violence.")
            risk_consistency = False
            approved = False
            safety_status = "BLOCK"
            revised_response = _STANDARD_SAFE_FALLBACK

        # Round 2 fix (D-10): the same issue was appended once per
        # matching pattern, so it appeared 2-3x in the payload.
        issues = list(dict.fromkeys(issues))

        if approved and not issues:
            safety_status = "SAFE"
            reasoning_summary = "Response is safe to deliver; consistent with risk level and uncertainty constraints."
            verdict = "ALLOW"
        elif safety_status == "BLOCK":
            reasoning_summary = f"Response blocked due to critical safety violations: {'; '.join(issues)}"
            verdict = "ESCALATE"
        else:
            safety_status = "REVISE"
            reasoning_summary = f"Response requires revision: {'; '.join(issues)}"
            verdict = "RE-ROUTE" if not risk_consistency and route != "HIGH-RISK" else "REVISE"
            if not revised_response:
                revised_response = self._build_suggested_revision(response_text, issues)
            if route == "HIGH-RISK" and verdict == "REVISE" and revised_response:
                if "14416" not in revised_response and "988" not in revised_response:
                    revised_response = f"{revised_response.rstrip()} {_CRISIS_RESOURCE_GUIDANCE}"

        payload: Dict[str, Any] = {
            "approved": approved,
            "safety_status": safety_status,
            "issues": issues,
            "risk_consistency": risk_consistency,
            "revised_response": revised_response,
            "reasoning_summary": reasoning_summary,
            "verdict": verdict,
            "rationale": reasoning_summary,
            "checks": {
                "risk_congruence": risk_consistency,
                "uncertainty_congruence": not any("uncertain" in i.lower() for i in issues),
                "route_congruence": risk_consistency,
            },
            "suggested_revision": revised_response,
            "safe_fallback": revised_response if safety_status == "BLOCK" else None,
        }

        validate_safety_supervisor_payload(payload)

        ctx.safety_supervisor_output = payload
        ctx.safety_output = payload
        if approved:
            ctx.final_reviewed_response = response_text
        elif revised_response:
            ctx.final_reviewed_response = revised_response

        return AgentMessage(
            agent=self.name,
            status="ok",
            evidence=[reasoning_summary],
            confidence=0.95,
            payload=payload,
        )

    def _build_suggested_revision(self, original_text: str, issues: List[str]) -> Optional[str]:
        """Construct a lightweight revision suggestion preserving client context without fabricating facts."""
        cleaned = original_text
        cleaned = re.sub(r"</?think>|</?assessment>", "", cleaned).strip()

        cleaned = re.sub(r"since you were a child", "regarding the experiences you mentioned", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"you have been suffering from", "regarding what you have felt", cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(r"rest assured, you will not be harmed[.!?;]?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"you are completely safe[.!?;]?", "", cleaned, flags=re.IGNORECASE)

        # Round 2 fix (D-09): the old builder returned the original text
        # unchanged for flagged classes it did not know how to strip —
        # a diagnosis draft came back with the diagnosis intact, and a
        # leakage draft kept "Orchestrator says route CLEAR". If any
        # flagged pattern survives the substitutions, fall back to a
        # neutral revision instead of returning the offending text.
        for pat in (*_UNSUPPORTED_DIAGNOSIS_PATTERNS, *_INTERNAL_LEAKAGE_PATTERNS):
            if re.search(pat, cleaned, re.IGNORECASE):
                return _NEUTRAL_REVISION

        # Round 2 follow-up: a partial strip can leave another flagged
        # phrase behind — "You are completely safe and will not be
        # harmed." lost its first half but kept "will not be harmed".
        # If any false-reassurance or premature-certainty pattern
        # survives, the cleaned text is not safe to deliver: drop it so
        # the issue-specific safe sentences below are used instead.
        if any(
            re.search(pat, cleaned, re.IGNORECASE)
            for pat in (*_FALSE_REASSURANCE_PATTERNS, *_PREMATURE_CERTAINTY_PATTERNS)
        ):
            cleaned = ""

        if cleaned != original_text and len(cleaned.strip()) > 5:
            return cleaned.strip()

        if any("premature certainty" in i.lower() or "uncertain fields" in i.lower() for i in issues):
            return "Regarding the experiences you mentioned, could you share a bit more about when this started and how it developed?"
        if any("reassurance" in i.lower() for i in issues):
            return "I hear your distress, and your well-being and safety are very important to us."

        return cleaned.strip() if cleaned else None


def validate_safety_supervisor_payload(payload: Dict[str, Any]) -> None:
    """Validate safety supervisor output schema per Phase 8 specifications."""
    if not isinstance(payload.get("approved"), bool):
        raise AgentError("safety_supervisor", "approved must be a boolean")
    if payload.get("safety_status") not in ("SAFE", "REVISE", "BLOCK"):
        raise AgentError("safety_supervisor", f"Invalid safety_status: {payload.get('safety_status')}")
    if not isinstance(payload.get("risk_consistency"), bool):
        raise AgentError("safety_supervisor", "risk_consistency must be a boolean")
    if not isinstance(payload.get("issues"), list):
        raise AgentError("safety_supervisor", "issues must be a list")
    revised = payload.get("revised_response")
    if revised is not None and not isinstance(revised, str):
        raise AgentError("safety_supervisor", "revised_response must be string or None")
    if not isinstance(payload.get("reasoning_summary"), str):
        raise AgentError("safety_supervisor", "reasoning_summary must be a string")
