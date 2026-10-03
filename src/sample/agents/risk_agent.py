"""Risk Agent for PsychAgent.

This agent evaluates safety and crisis signals across the client message,
state assessment output, and memory output.

IMPORTANT design constraints
-----------------------------
* It ONLY identifies safety and crisis signals.
* It must NOT output clinical diagnosis labels (e.g. depression, PTSD, borderline).
* It must NOT choose counseling skills or change what gets generated.
* It keeps NO EVIDENCE / UNCERTAIN / EVIDENCE OF RISK genuinely distinct.
* Evidence MUST contain specific signals (e.g., exact keywords, absent safety fields),
  NOT clinical reasoning or interpretive narratives.

Output (AgentMessage):
---------------------
status:                 "ok"
confidence:             0.0–1.0
evidence:               List of specific detected signals (not reasoning)
payload:
    severity:           "LOW" | "MODERATE" | "HIGH" | "UNCERTAIN"
    risk_status:        "NO_EVIDENCE" | "UNCERTAIN" | "EVIDENCE_OF_RISK"
    evidence:           List of specific signal strings
    confidence:         0.0–1.0
    signals_detected:   List of specific tokens or condition strings
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .base import Agent, AgentContext, AgentError, AgentMessage

logger = logging.getLogger(__name__)

# Explicit high-risk crisis signals (matched case-insensitively)
_HIGH_RISK_SIGNALS = [
    "suicide", "suicidal", "self-harm", "self harm", "self-injury", "don't want to live", "end my life", "ending my life",
    "end life", "ending life", "end it all", "ending it all", "jump off building", "slit wrists", "want to die", "can't go on",
    "hopeless want to die", "leave this world", "cannot survive", "psychiatric emergency", "involuntary hospitalization",
    "severe mental disorder", "severe violence", "kill myself", "killing myself", "take my own life", "hurt myself",
    "harm myself", "better off dead", "better off without me", "not waking up", "don't want to wake up",
]

# Moderate distress / impairment signals (matched case-insensitively)
_MODERATE_DISTRESS_SIGNALS = [
    "insomnia all night", "severe insomnia", "unable to work", "cannot work", "extreme panic", "panic attack",
    "verge of collapse", "feeling broken", "completely hopeless", "no hope", "perishing", "destruction",
]

# Negation cues that, when they precede a signal within the same clause, mark the
# mention as explicitly denied (e.g. "I have never had thoughts of suicide").
_NEGATION_CUES = (
    "no", "not", "never", "without", "denies", "denied", "deny", "don't", "do not", "didn't",
    "haven't", "have not", "hasn't", "wouldn't", "won't", "none", "nor",
)
_CLAUSE_BREAK = re.compile(r"[.,;!?]|\bbut\b|\bhowever\b|\balthough\b", re.IGNORECASE)
_NEGATION_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in _NEGATION_CUES) + r")\b", re.IGNORECASE)


def _find_signal(text: str, signal: str) -> Optional[str]:
    """Return "affirmed", "negated" or None for a signal in text (case-insensitive).

    A mention counts as negated only if a negation cue appears earlier in the
    same clause (up to 6 words before the signal) and the signal itself does
    not already contain a negation (e.g. "don't want to live"). Ambiguous
    cases are resolved towards "affirmed" (i.e. towards flagging risk).
    """
    lowered = text.lower()
    sig = signal.lower()
    found_negated = False
    start = lowered.find(sig)
    while start != -1:
        prefix = lowered[:start]
        breaks = list(_CLAUSE_BREAK.finditer(prefix))
        clause = prefix[breaks[-1].end():] if breaks else prefix
        window = " ".join(clause.split()[-6:])
        if _NEGATION_RE.search(sig) or not _NEGATION_RE.search(window):
            return "affirmed"
        found_negated = True
        start = lowered.find(sig, start + len(sig))
    return "negated" if found_negated else None


class RiskAgent(Agent):
    """Detects explicit safety and crisis signals without diagnostic labeling."""

    name = "risk_agent"

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
                confidence=0.0,
                missing_information=[],
                evidence=[f"Agent error: {exc}"],
                payload={
                    "severity": "UNCERTAIN",
                    "risk_status": "UNCERTAIN",
                    "evidence": [f"Error during risk assessment: {exc}"],
                    "confidence": 0.0,
                    "signals_detected": [],
                },
                error=str(exc),
            )

    def _run(self, ctx: AgentContext) -> AgentMessage:
        # Extract inputs from state, memory, and raw message
        state_payload = ctx.state_output or {}
        if not isinstance(state_payload, dict):
            state_payload = {}

        mem_payload = ctx.memory_output or {}
        if not isinstance(mem_payload, dict):
            mem_payload = {}

        raw_message = str(ctx.current_message or "").strip()
        current_concern = str(state_payload.get("current_concern", "")).strip()
        main_problem = str(mem_payload.get("main_problem", "")).strip()
        static_traits = mem_payload.get("known_static_traits", {}) or {}
        medical_history = str(static_traits.get("medical_history", "")).strip()
        unknown_info = state_payload.get("unknown_information", []) or []

        # 1. Scan for explicit HIGH-RISK signals (case-insensitive, negation-aware
        #    for client-authored text)
        high_signals: List[str] = []
        negated_signals: List[str] = []
        for sig in _HIGH_RISK_SIGNALS:
            for label, text in (("client_message", raw_message), ("current_concern", current_concern), ("main_problem", main_problem)):
                if not text:
                    continue
                hit = _find_signal(text, sig)
                if hit == "affirmed":
                    high_signals.append(f"{label}:'{sig}'")
                elif hit == "negated":
                    negated_signals.append(f"negated:{label}:'{sig}'")
            # Note: in medical_history, check if it's an affirmative risk (e.g. past attempt)
            # rather than "no prior psychological problems"
            if medical_history and sig in medical_history.lower() and not any(
                neg in medical_history.lower() for neg in ("no ", "none", "denies", "without", "never", "not mentioned", "unknown")
            ):
                high_signals.append(f"medical_history:'{sig}'")

        if high_signals:
            evidence = [f"Direct crisis signal detected: {s}" for s in high_signals]
            payload = {
                "severity": "HIGH",
                "risk_status": "EVIDENCE_OF_RISK",
                "evidence": evidence,
                "confidence": 0.95,
                "signals_detected": high_signals,
            }
            _validate_risk_payload(payload)
            return AgentMessage(
                agent=self.name,
                status="HIGH",
                evidence=evidence,
                confidence=0.95,
                missing_information=[],
                payload=payload,
            )

        # 2. Check for UNCERTAIN safety status (safety status missing / unverified)
        safety_status_missing = False
        for item in unknown_info:
            item_str = str(item).lower()
            if "medical_history" in item_str or "safety" in item_str:
                safety_status_missing = True
                break

        if not medical_history or medical_history.lower() in ("(unavailable)", "not mentioned", "unknown"):
            # If medical history is explicitly not populated or unknown in the context
            if any("medical_history" in str(x) for x in unknown_info) or any("medical_history" in str(x) for x in (ctx.metadata.get("missing_information") or [])):
                safety_status_missing = True

        # 3. Scan for MODERATE distress / functional impairment signals
        moderate_signals: List[str] = []
        for sig in _MODERATE_DISTRESS_SIGNALS:
            for label, text in (("client_message", raw_message), ("current_concern", current_concern), ("main_problem", main_problem)):
                if text and _find_signal(text, sig) == "affirmed":
                    moderate_signals.append(f"{label}:'{sig}'")

        if safety_status_missing:
            evidence = ["Safety status unverified: medical/psychiatric history missing from intake evidence"]
            if moderate_signals:
                evidence.extend([f"Distress signal: {s}" for s in moderate_signals])
            payload = {
                "severity": "UNCERTAIN",
                "risk_status": "UNCERTAIN",
                "evidence": evidence,
                "confidence": 0.60,
                "signals_detected": moderate_signals + ["missing_safety_status"],
            }
            _validate_risk_payload(payload)
            return AgentMessage(
                agent=self.name,
                status="UNCERTAIN",
                evidence=evidence,
                confidence=0.60,
                missing_information=["medical_history"],
                payload=payload,
            )

        if moderate_signals:
            evidence = [f"Functional distress signal detected: {s}" for s in moderate_signals]
            payload = {
                "severity": "MODERATE",
                "risk_status": "UNCERTAIN",
                "evidence": evidence,
                "confidence": 0.75,
                "signals_detected": moderate_signals,
            }
            _validate_risk_payload(payload)
            return AgentMessage(
                agent=self.name,
                status="MODERATE",
                evidence=evidence,
                confidence=0.75,
                missing_information=[],
                payload=payload,
            )

        # 4. NO EVIDENCE
        evidence = ["NO EVIDENCE: No risk or crisis signals detected in current message, state, or memory context"]
        if negated_signals:
            evidence.append(
                "Safety-related terms appeared only in explicitly negated form and were not treated as risk: "
                + ", ".join(sorted(set(negated_signals)))
            )
        payload = {
            "severity": "LOW",
            "risk_status": "NO_EVIDENCE",
            "evidence": evidence,
            "confidence": 0.90,
            "signals_detected": sorted(set(negated_signals)),
        }
        _validate_risk_payload(payload)
        return AgentMessage(
            agent=self.name,
            status="LOW",
            evidence=evidence,
            confidence=0.90,
            missing_information=[],
            payload=payload,
        )


def _validate_risk_payload(payload: Dict[str, Any]) -> None:
    """Validate risk output schema."""
    valid_severities = ("LOW", "MODERATE", "HIGH", "UNCERTAIN")
    valid_statuses = ("NO_EVIDENCE", "UNCERTAIN", "EVIDENCE_OF_RISK")
    if payload.get("severity") not in valid_severities:
        raise AgentError("risk_agent", f"Invalid severity: {payload.get('severity')}")
    if payload.get("risk_status") not in valid_statuses:
        raise AgentError("risk_agent", f"Invalid risk_status: {payload.get('risk_status')}")
    conf = payload.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
        raise AgentError("risk_agent", f"Invalid confidence: {conf}")
    if not isinstance(payload.get("evidence"), list):
        raise AgentError("risk_agent", "evidence must be a list")
