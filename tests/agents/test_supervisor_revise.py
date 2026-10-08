"""Regression tests for the SafetySupervisor REVISE handler.

Bug: when the supervisor issued REVISE, the pipeline stored the rationale in
ctx.metadata and re-ran the CounselingAgent -- which never reads the
rationale and returns the identical flagged draft. The supervisor's own
revised_response was discarded, making the revision a no-op.

Fix: prefer the supervisor's structured revised_response; only fall back to
a counseling re-run when no structured revision exists.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.pipeline import run_pipeline
from sample.agents.safety_supervisor import SafetySupervisor


def _high_risk_ctx():
    return AgentContext(
        case_id="rev_test",
        modality="cbt",
        current_message="I feel completely hopeless and have thought about ending my life.",
        full_profile={},
    )


def test_revise_uses_supervisor_revision():
    """REVISE applies the supervisor's revised_response, not the flagged draft."""
    r = run_pipeline(_high_risk_ctx())
    assert r["route"] == "HIGH-RISK"
    actions = [s.get("action") for s in r["trail"]]
    assert "supervisor_revision_applied" in actions, f"trail actions: {actions}"
    # The stub draft ("[Counselor response generated...") must NOT be delivered.
    assert "[Counselor response generated" not in r["response"]
    assert "safety" in r["response"].lower()
    print("[PASS] REVISE uses supervisor's revised_response.")


def test_revise_fallback_without_structured_revision():
    """If the supervisor gives no revised_response, fall back to counseling re-run."""
    ctx = _high_risk_ctx()
    # Monkeypatch the supervisor to emit REVISE without a revised_response.
    orig_run = SafetySupervisor.run

    def _no_revision(self, ctx, draft_response=""):
        msg = orig_run(self, ctx, draft_response=draft_response)
        msg.payload["revised_response"] = None
        msg.payload["suggested_revision"] = None
        # Force REVISE verdict to exercise the fallback path.
        if msg.payload.get("verdict") != "REVISE":
            msg.payload["verdict"] = "REVISE"
        return msg

    SafetySupervisor.run = _no_revision
    try:
        r = run_pipeline(ctx)
    finally:
        SafetySupervisor.run = orig_run
    steps = [s.get("step") for s in r["trail"] if s.get("agent") == "counseling_agent"]
    assert "revision" in steps, f"counseling revision step missing: {steps}"
    print("[PASS] REVISE falls back to counseling re-run without structured revision.")


def test_allow_unchanged():
    """ALLOW verdict still delivers the counseling draft untouched."""
    ctx = AgentContext(
        case_id="allow_test",
        modality="cbt",
        current_message="I'd like to discuss recent matters at work.",
        full_profile={},
    )
    r = run_pipeline(ctx)
    assert r["verdict"] == "ALLOW"
    assert "[Counselor response generated" in r["response"]
    actions = [s.get("action") for s in r["trail"]]
    assert "supervisor_revision_applied" not in actions
    print("[PASS] ALLOW path unchanged.")
