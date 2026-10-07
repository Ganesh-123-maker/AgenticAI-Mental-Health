"""Coordination Evaluation Method for PsychAgent Multi-Agent System.

Computes metrics from the agent trail logged by pipeline.py:
- routing_accuracy: orchestrator route vs benchmark expected_route
  (None / not applicable when the system produced no orchestrator route,
  e.g. single-prompt baselines without a multi-agent trail)
- unnecessary_invocation_rate: rate of unneeded agent calls (e.g. clarification when clear)
- handoff_correctness: whether next_agent matched what actually ran next
  (None / not applicable when there is no multi-agent trail to evaluate)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...core.base import EvaluationMethod


class Coordination(EvaluationMethod):
    """Evaluates multi-agent orchestration, routing accuracy, and handoff validity."""

    async def evaluate(
        self,
        gpt_api: Any = None,
        dialogue: Any = None,
        profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Optional[float]]:
        """Compute coordination metrics from dialogue/trail and benchmark profile."""
        trail, meta = self._extract_trail_and_meta(dialogue, profile)
        return self.compute_metrics(trail, meta)

    @classmethod
    def compute_metrics(
        cls,
        trail: List[Dict[str, Any]],
        benchmark_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Optional[float]]:
        """Synchronous metric computation for testing and offline evaluation.

        Returns None (not applicable) for routing_accuracy / handoff_correctness
        when the trail contains no orchestrator route to evaluate — e.g. for
        baseline systems without a multi-agent trail. A missing route must not
        be scored as 0.0 (mis-routed) or 1.0 (perfectly routed); both would be
        misleading.
        """
        if not trail:
            return {
                "routing_accuracy": None,
                "unnecessary_invocation_rate": 0.0,
                "handoff_correctness": None,
            }

        meta = benchmark_meta or {}
        expected_route = str(meta.get("expected_route", "")).upper()

        # 1. Routing Accuracy
        # Find the final route chosen by orchestrator
        actual_route = None
        for step in reversed(trail):
            if step.get("agent") == "orchestrator":
                actual_route = str(step.get("route") or step.get("payload", {}).get("route", "")).upper()
                break

        if expected_route and actual_route:
            routing_accuracy: Optional[float] = 1.0 if actual_route == expected_route else 0.0
        else:
            # No orchestrator route present in the trail: routing accuracy is
            # not applicable (not 0.0 = mis-routed, not 1.0 = perfectly routed).
            routing_accuracy = None

        # 2. Unnecessary Invocation Rate
        # e.g. clarification invoked when uncertainty was CLEAR or clarification not required
        unc_status = "CLEAR"
        clarification_required = False
        for step in trail:
            if step.get("agent") == "uncertainty_agent":
                payload = step.get("payload", {})
                unc_status = str(payload.get("status", "CLEAR")).upper()
                clarification_required = bool(payload.get("clarification_required", False))
                break

        unnecessary_calls = 0
        total_agent_calls = len(trail)

        for step in trail:
            agent = step.get("agent")
            if agent == "clarification_agent":
                if unc_status == "CLEAR" and not clarification_required:
                    unnecessary_calls += 1

        unnecessary_rate = unnecessary_calls / total_agent_calls if total_agent_calls > 0 else 0.0

        # 3. Handoff Correctness
        # Check if each agent's next_agent matches the actual next agent
        correct_handoffs = 0
        evaluated_handoffs = 0

        for i in range(len(trail) - 1):
            curr_step = trail[i]
            next_step = trail[i + 1]

            curr_payload = curr_step.get("payload", {})
            declared_next = curr_payload.get("next_agent") or curr_step.get("next_agent")
            actual_next = next_step.get("agent")

            if declared_next is not None and actual_next is not None:
                evaluated_handoffs += 1
                if declared_next == actual_next or (curr_step.get("agent") == "uncertainty_agent" and actual_next in ("risk_agent", "orchestrator")):
                    correct_handoffs += 1

        handoff_correctness: Optional[float] = (
            correct_handoffs / evaluated_handoffs if evaluated_handoffs > 0 else None
        )

        return {
            "routing_accuracy": round(float(routing_accuracy), 4) if routing_accuracy is not None else None,
            "unnecessary_invocation_rate": round(float(unnecessary_rate), 4),
            "handoff_correctness": round(float(handoff_correctness), 4) if handoff_correctness is not None else None,
        }

    def _extract_trail_and_meta(
        self,
        dialogue: Any,
        profile: Optional[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        trail: List[Dict[str, Any]] = []
        meta: Dict[str, Any] = profile or {}

        if isinstance(dialogue, dict):
            if "trail" in dialogue and isinstance(dialogue["trail"], list):
                trail = dialogue["trail"]
            if "profile" in dialogue and isinstance(dialogue["profile"], dict):
                meta = dialogue["profile"]
            elif "expected_route" in dialogue:
                meta = dialogue
        elif isinstance(dialogue, list):
            # Check if list of trail steps
            if dialogue and isinstance(dialogue[0], dict) and "agent" in dialogue[0]:
                trail = dialogue

        return trail, meta
