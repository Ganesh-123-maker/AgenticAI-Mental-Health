"""Orchestrator for PsychAgent.

This agent evaluates outputs from State Assessment, Uncertainty, Risk, and
Reassessment agents to decide the pipeline route (CLEAR / UNCERTAIN / HIGH-RISK)
and the target next_agent.

Routing Rules:
-------------
1. HIGH-RISK: Triggered whenever Risk Agent or Reassessment indicates HIGH severity.
   HIGH-RISK overrides CLEAR/UNCERTAIN regardless of informational completeness.
   Target: "safety_supervisor".
2. UNCERTAIN: Triggered when risk is not HIGH and Uncertainty Agent or Reassessment
   indicates UNCERTAIN or AMBIGUOUS (clarification needed).
   Target: "clarification_agent".
3. CLEAR: Triggered when risk is not HIGH and informational status is CLEAR.
   Target: "counseling_agent" (stub target name).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .base import Agent, AgentContext, AgentError, AgentMessage

logger = logging.getLogger(__name__)


class Orchestrator(Agent):
    """Routes the session based on risk severity and informational uncertainty."""

    name = "orchestrator"

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
                    "route": "UNCERTAIN",
                    "next_agent": "clarification_agent",
                    "reason": f"Routing error: {exc}",
                    "risk_severity": "UNCERTAIN",
                    "uncertainty_status": "UNCERTAIN",
                    "reassessment_applied": False,
                },
            )

    def _run(self, ctx: AgentContext) -> AgentMessage:
        # Check if reassessment has been run
        reassess_payload = getattr(ctx, "reassessment_output", None) or ctx.metadata.get("reassessment_output")
        has_reassessment = isinstance(reassess_payload, dict) and bool(reassess_payload)

        # Pull uncertainty and risk payloads
        if has_reassessment:
            unc_payload = reassess_payload.get("uncertainty", {}) or ctx.uncertainty_output or {}
            risk_payload = reassess_payload.get("risk", {}) or ctx.risk_output or {}
            unc_status = reassess_payload.get("status") or unc_payload.get("status", "CLEAR")
        else:
            unc_payload = ctx.uncertainty_output or {}
            risk_payload = ctx.risk_output or {}
            unc_status = unc_payload.get("status", "CLEAR")

        risk_severity = risk_payload.get("severity", "LOW")
        clarification_required = bool(unc_payload.get("clarification_required", False))

        # Rule 1: HIGH-RISK override (must override CLEAR and UNCERTAIN)
        if risk_severity == "HIGH" or (has_reassessment and reassess_payload.get("route_decision") == "HIGH-RISK"):
            route = "HIGH-RISK"
            next_agent = "safety_supervisor"
            reason = "High-risk safety signals detected; emergency safety path prioritized over counseling."

        # Rule 2: Reassessment decision takes precedence over initial uncertainty status
        elif has_reassessment:
            if reassess_payload.get("route_decision") == "CLEAR":
                route = "CLEAR"
                next_agent = "counseling_agent"
                reason = "Clarification successfully resolved informational gaps; proceeding to counseling intervention."
            else:
                route = "UNCERTAIN"
                next_agent = "clarification_agent"
                reason = "Informational gaps remain unresolved after clarification; further clarification needed."

        # Rule 3: Initial UNCERTAIN route
        elif unc_status in ("UNCERTAIN", "AMBIGUOUS") or clarification_required:
            route = "UNCERTAIN"
            next_agent = "clarification_agent"
            reason = f"Informational uncertainty detected ({unc_status}); clarification needed before proceeding."

        # Rule 4: CLEAR route
        else:
            route = "CLEAR"
            next_agent = "counseling_agent"
            reason = "No high risk and informational state is clear; proceeding to counseling intervention."

        if route == "HIGH-RISK":
            required_action = "Enter safety-controlled response flow."
            triggered_by = list(risk_payload.get("signals_detected") or ["high_risk_safety_concern"])
            confidence = 0.95
        elif route == "UNCERTAIN":
            required_action = "Obtain clarification before proceeding."
            triggered_by = list(unc_payload.get("uncertain_fields") or unc_payload.get("uncertainty_types") or ["informational_uncertainty"])
            confidence = 0.75
        else:
            required_action = "Proceed with normal counseling flow."
            triggered_by = ["verified_state_and_low_risk"]
            confidence = 0.85

        payload: Dict[str, Any] = {
            "route": route,
            "next_agent": next_agent,
            "reason": reason,
            "triggered_by": triggered_by,
            "confidence": confidence,
            "required_action": required_action,
            "risk_severity": risk_severity,
            "uncertainty_status": unc_status,
            "reassessment_applied": has_reassessment,
        }

        _validate_orchestrator_payload(payload)

        # Store routing decision on context
        ctx.routing_output = payload

        return AgentMessage(
            agent=self.name,
            status="ok",
            recommended_action=route,
            next_agent=next_agent,
            evidence=[reason],
            confidence=confidence,
            payload=payload,
        )


def _validate_orchestrator_payload(payload: Dict[str, Any]) -> None:
    """Validate orchestrator output schema."""
    valid_routes = ("CLEAR", "UNCERTAIN", "HIGH-RISK")
    if payload.get("route") not in valid_routes:
        raise AgentError("orchestrator", f"Invalid route: {payload.get('route')}")
    conf = payload.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
        raise AgentError("orchestrator", f"Invalid confidence: {conf}")
    for req in ("route", "reason", "triggered_by", "required_action"):
        if req not in payload:
            raise AgentError("orchestrator", f"Missing required payload field: {req}")
