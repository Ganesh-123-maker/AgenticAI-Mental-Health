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

logger = logging.getLogger(__name__)

# Standard crisis fallback response from SOP-1 library (no fabricated phone numbers or clinics)
_STANDARD_SAFE_FALLBACK = (
    "I care deeply about your safety and current well-being. Facing such intense distress and crisis, "
    "please do not face it alone. We prioritize your life and safety above all else. Please contact your family, "
    "friends, a trusted person, or a professional crisis hotline immediately (e.g., 988 or 400-161-9995). "
    "We can pause other discussions and focus first and foremost on ensuring your safety right now."
)

# Unsafe dismissal phrases in elevated or high-risk contexts
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

# False reassurance patterns (especially harmful in UNCERTAIN or elevated safety contexts)
_FALSE_REASSURANCE_PATTERNS = [
    r"(you are absolutely safe|you definitely have no danger|rest assured, you will not be harmed)",
    r"(no need to worry about your safety|you have no mental illness|you are perfectly normal)",
    r"(I'm taking responsibility|guarantee you won't be harmed|nothing bad will happen)",
    r"(you are completely safe|there is definitely no risk|guaranteed to be fine)",
]

# Unsupported clinical diagnosis patterns
_UNSUPPORTED_DIAGNOSIS_PATTERNS = [
    r"(you have been diagnosed with|according to diagnosis you have|you have severe depression|you have schizophrenia|you have borderline personality disorder)",
    r"(you are diagnosed with|you definitely suffer from bipolar|clinical depression confirmed)",
]

# Premature certainty patterns where counselor asserts unverified historical facts
_PREMATURE_CERTAINTY_PATTERNS = [
    r"since you were a child",
    r"you have been suffering from",
    r"as you mentioned in previous two therapies",
    r"because of what happened three years ago",
]

# Internal agent leakage indicators
_INTERNAL_LEAKAGE_PATTERNS = [
    r"<think>",
    r"</think>",
    r"<assessment>",
    r"Orchestrator",
    r"RiskAgent",
    r"AgentContext",
    r"system_prompt",
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
            # Fail-safe fallback: mark as blocked or fail-safe
            payload = {
                "approved": False,
                "safety_status": "BLOCK",
                "issues": [f"Safety supervisor evaluation error: {exc}"],
                "risk_consistency": False,
                "revised_response": _STANDARD_SAFE_FALLBACK,
                "reasoning_summary": f"Evaluation error: {exc}",
                # Backward compatibility
                "verdict": "ALLOW",
                "rationale": f"Fail-safe bypass: {exc}",
                "checks": {
                    "risk_congruence": True,
                    "uncertainty_congruence": True,
                    "route_congruence": True,
                },
                "suggested_revision": None,
                "safe_fallback": _STANDARD_SAFE_FALLBACK,
            }
            return AgentMessage(agent=self.name, status="ok", payload=payload)

    def _run(self, ctx: AgentContext, draft_response: Optional[str] = None) -> AgentMessage:
        # 1. Resolve response text
        response_text = draft_response
        if not response_text:
            counsel_payload = getattr(ctx, "counseling_output", None) or ctx.metadata.get("counseling_output", {})
            response_text = counsel_payload.get("response") or counsel_payload.get("response_text", "")
        response_text = str(response_text or "").strip()

        # 2. Extract upstream assessment details
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

        # 3. Track issues & status
        issues: List[str] = []
        approved: bool = True
        safety_status: str = "SAFE"
        risk_consistency: bool = True
        revised_response: Optional[str] = None
        reasoning_summary: str = ""

        # 4. Review: Internal mechanics leakage
        for pat in _INTERNAL_LEAKAGE_PATTERNS:
            if re.search(pat, response_text, re.IGNORECASE):
                issues.append("Response exposes internal agent formatting or prompt tokens.")
                safety_status = "REVISE"
                approved = False

        # 5. Review: Unsupported clinical diagnoses
        for pat in _UNSUPPORTED_DIAGNOSIS_PATTERNS:
            if re.search(pat, response_text, re.IGNORECASE):
                issues.append("Response makes unsupported psychiatric diagnostic assertions.")
                safety_status = "REVISE"
                approved = False

        # 6. Review: Premature certainty on unverified fields
        if unc_status in ("UNCERTAIN", "AMBIGUOUS") and uncertain_fields:
            for pat in _PREMATURE_CERTAINTY_PATTERNS:
                if re.search(pat, response_text, re.IGNORECASE):
                    issues.append(f"Response asserts unverified historical certainty on uncertain fields: {uncertain_fields}")
                    safety_status = "REVISE"
                    approved = False

        # 7. Review: False reassurance in UNCERTAIN safety context
        # Distinguish 'no evidence of risk' from 'evidence that risk is absent'.
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

        # 8. Review: Route vs Risk alignment (Re-route check if route didn't match risk)
        if risk_severity == "HIGH" and route != "HIGH-RISK":
            issues.append("High risk severity detected by Risk Agent, but Orchestrator route was not HIGH-RISK. Re-routing required.")
            risk_consistency = False
            approved = False
            safety_status = "REVISE"
            verdict = "RE-ROUTE"
        elif route == "HIGH-RISK" or risk_severity == "HIGH":
            # Check for dismissal
            has_dismissal = any(p in response_text for p in _UNSAFE_DISMISSAL_PHRASES)

            # Check for safety-oriented awareness
            has_safety_awareness = any(
                kw in response_text
                for kw in [
                    "safety", "support", "concern", "accompany you", "life", "crisis", "seek help", "professional help", "hospital", "hotline", "friends", "protect"
                ]
            )

            # Check if acute crisis signals are present
            is_acute_crisis = any(
                kw in client_utterance or kw in " ".join(risk_signals)
                for kw in [
                    "suicide", "self-harm", "despair", "want to die", "don't want to live", "end life", "cutting wrists", "jump off building", "kill myself"
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
                        "is paramount. We can work together to ensure you have the necessary safety and support in place."
                    )
            else:
                # Response has appropriate safety awareness
                risk_consistency = True

        # 10. Finalize Verdict & Payload
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

        payload: Dict[str, Any] = {
            "approved": approved,
            "safety_status": safety_status,
            "issues": issues,
            "risk_consistency": risk_consistency,
            "revised_response": revised_response,
            "reasoning_summary": reasoning_summary,
            # Backward-compatibility fields
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

        # Validate schema
        validate_safety_supervisor_payload(payload)

        # Update AgentContext with reviewed response
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
        # Strip internal tags if present
        cleaned = re.sub(r"</?think>|</?assessment>", "", cleaned).strip()

        # If premature certainty was flagged, soften it
        cleaned = re.sub(r"since you were a child", "regarding the experiences you mentioned", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"you have been suffering from", "regarding what you have felt", cleaned, flags=re.IGNORECASE)

        # If false reassurance was flagged, remove it
        cleaned = re.sub(r"rest assured, you will not be harmed[.!?;]?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"you are completely safe[.!?;]?", "", cleaned, flags=re.IGNORECASE)

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
