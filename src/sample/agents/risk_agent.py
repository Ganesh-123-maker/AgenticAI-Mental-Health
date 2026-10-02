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
from typing import Any, Dict, List, Optional

from .base import Agent, AgentContext, AgentError, AgentMessage

logger = logging.getLogger(__name__)

# Explicit high-risk crisis signals
_HIGH_RISK_SIGNALS = [
    "suicide", "self-harm", "self-injury", "don't want to live", "end my life", "end life",
    "jump off building", "slit wrists", "want to die", "can't go on", "hopeless want to die", "leave this world",
    "cannot survive", "psychiatric emergency", "involuntary hospitalization", "severe mental disorder", "severe violence",
]

# Moderate distress / impairment signals
_MODERATE_DISTRESS_SIGNALS = [
    "insomnia all night", "severe insomnia", "unable to work", "cannot work", "extreme panic", "panic attack",
    "verge of collapse", "feeling broken", "completely hopeless", "no hope", "perishing", "destruction",
]


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

        # 1. Scan for explicit HIGH-RISK signals
        high_signals: List[str] = []
        for sig in _HIGH_RISK_SIGNALS:
            if sig in raw_message:
                high_signals.append(f"client_message:'{sig}'")
            if current_concern and sig in current_concern:
                high_signals.append(f"current_concern:'{sig}'")
            if main_problem and sig in main_problem:
                high_signals.append(f"main_problem:'{sig}'")
            # Note: in medical_history, check if it's an affirmative risk (e.g. past attempt)
            # rather than "no prior psychological problems"
            if medical_history and sig in medical_history and not any(
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
            if sig in raw_message:
                moderate_signals.append(f"client_message:'{sig}'")
            if current_concern and sig in current_concern:
                moderate_signals.append(f"current_concern:'{sig}'")
            if main_problem and sig in main_problem:
                moderate_signals.append(f"main_problem:'{sig}'")

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
        payload = {
            "severity": "LOW",
            "risk_status": "NO_EVIDENCE",
            "evidence": evidence,
            "confidence": 0.90,
            "signals_detected": [],
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
