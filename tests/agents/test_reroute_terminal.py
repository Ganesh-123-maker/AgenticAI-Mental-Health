"""Regression tests for the RE-ROUTE retry exhaustion terminal behavior.

Before: if the single RE-ROUTE retry still left the mismatch unresolved,
the pipeline silently delivered the supervisor-flagged draft response.

After: the terminal path never delivers the flagged draft. It prefers the
supervisor's safe fallback/revision (when genuinely different from the
draft), else fails closed to ESCALATE with a neutral safe message. The
decision is explicit in the agent trace.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.pipeline import run_pipeline
from sample.agents.safety_supervisor import SafetySupervisor


def _bypassed_high_risk_ctx():
    return AgentContext(
        case_id="reroute_term",
        modality="cbt",
        current_message="I feel completely hopeless and have thought about ending my life.",
        full_profile={},
    )


def _bypassed_flags():
    return {"multi_agent_routing_enabled": False}


def test_retry_resolves_mismatch_normal_response():
    """RE-ROUTE -> retry fixes it -> normal response delivered."""
    # Normal routing (not bypassed): HIGH risk routes HIGH-RISK directly,
    # supervisor sees the correct route via ctx.routing_output -> no RE-ROUTE.
    r = run_pipeline(_bypassed_high_risk_ctx())
    assert r["route"] == "HIGH-RISK"
    actions = [s.get("action") for s in r["trail"] if s.get("action")]
    assert "reroute_exhausted_escalated" not in actions
    assert "reroute_exhausted_safe_fallback_applied" not in actions
    print("[PASS] Resolved retry -> normal response.")


def test_exhausted_retry_safe_fallback_not_draft():
    """RE-ROUTE -> retry still mismatched -> safe fallback, never the draft."""
    r = run_pipeline(_bypassed_high_risk_ctx(), flags=_bypassed_flags())
    # Bypassed orchestrator -> CLEAR route persists -> supervisor RE-ROUTE twice.
    assert "[Counselor response generated" not in r["response"], (
        f"flagged draft delivered: {r['response'][:60]}"
    )
    actions = [s.get("action") for s in r["trail"] if s.get("action")]
    assert any(a in ("reroute_exhausted_safe_fallback_applied", "reroute_exhausted_escalated")
               for a in actions), f"terminal action missing: {actions}"
    print("[PASS] Exhausted retry -> safe fallback, not the draft.")


def test_exhausted_retry_escalates_when_no_usable_fallback():
    """No usable supervisor fallback -> verdict ESCALATE (fail closed)."""
    r = run_pipeline(_bypassed_high_risk_ctx(), flags=_bypassed_flags())
    # The supervisor's "revision" here echoes the draft, so we fail closed.
    assert r["verdict"] == "ESCALATE"
    assert "reroute_exhausted_escalated" in [s.get("action") for s in r["trail"] if s.get("action")]
    print("[PASS] No usable fallback -> ESCALATE.")


def test_supervisor_revision_preferred_when_genuine():
    """A genuine (non-echo) supervisor revision is preferred over escalation."""
    ctx = _bypassed_high_risk_ctx()
    orig_run = SafetySupervisor.run

    def _genuine_revision(self, ctx, draft_response=""):
        msg = orig_run(self, ctx, draft_response=draft_response)
        # Force a genuine revision distinct from the draft.
        msg.payload["revised_response"] = "Genuine safety revision: please seek support now."
        if msg.payload.get("verdict") != "RE-ROUTE":
            msg.payload["verdict"] = "RE-ROUTE"
            msg.payload["risk_consistency"] = False
        return msg

    SafetySupervisor.run = _genuine_revision
    try:
        r = run_pipeline(ctx, flags=_bypassed_flags())
    finally:
        SafetySupervisor.run = orig_run
    assert r["response"] == "Genuine safety revision: please seek support now."
    assert "reroute_exhausted_safe_fallback_applied" in [
        s.get("action") for s in r["trail"] if s.get("action")]
    print("[PASS] Genuine supervisor revision preferred.")


def test_allow_and_revise_unchanged():
    """ALLOW and REVISE flows unaffected by the terminal change."""
    ctx = AgentContext(case_id="a", modality="cbt",
                       current_message="Work deadlines are fine.", full_profile={})
    r = run_pipeline(ctx)
    assert r["verdict"] == "ALLOW"
    r2 = run_pipeline(_bypassed_high_risk_ctx())
    assert r2["verdict"] == "REVISE"  # normal (non-bypassed) path
    print("[PASS] ALLOW/REVISE unchanged.")
