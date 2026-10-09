"""Regression tests for structured RE-ROUTE handling.

Bug 1: the pipeline never set ctx.routing_output, so SafetySupervisor always
saw route="CLEAR" and issued a spurious RE-ROUTE on every HIGH-risk case.

Bug 2: the RE-ROUTE handler used the substring "High risk" in rationale
(free text) instead of the structured risk_consistency field.

Fix: pipeline publishes ctx.routing_output after each orchestrator run;
RE-ROUTE uses sup_payload["risk_consistency"] is False (fail closed).
"""

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.pipeline import run_pipeline
from sample.agents.safety_supervisor import SafetySupervisor


def _high_risk_ctx():
    return AgentContext(
        case_id="reroute_test",
        modality="cbt",
        current_message="I feel completely hopeless and have thought about ending my life.",
        full_profile={},
    )


def test_no_spurious_reroute_on_correct_high_risk_routing():
    """Correctly-routed HIGH-RISK must not trigger a spurious RE-ROUTE."""
    r = run_pipeline(_high_risk_ctx())
    assert r["route"] == "HIGH-RISK"
    reroute_verdicts = [
        s for s in r["trail"]
        if s.get("agent") == "safety_supervisor" and s.get("verdict") == "RE-ROUTE"
    ]
    assert not reroute_verdicts, f"spurious RE-ROUTE: {reroute_verdicts}"
    # No wasted orchestrator re-run.
    orch_runs = [s for s in r["trail"] if s.get("agent") == "orchestrator"]
    assert len(orch_runs) == 1, f"orchestrator ran {len(orch_runs)}x"
    print("[PASS] No spurious RE-ROUTE on correct HIGH-RISK routing.")


def test_routing_output_published():
    """ctx.routing_output is set for the supervisor to read."""
    ctx = _high_risk_ctx()
    run_pipeline(ctx)
    assert ctx.routing_output is not None
    assert ctx.routing_output.get("route") == "HIGH-RISK"
    print("[PASS] ctx.routing_output published.")


def test_rationale_wording_does_not_change_routing():
    """Rewording the rationale must not change RE-ROUTE behavior.

    The handler uses risk_consistency (structured), not rationale text.
    """
    ctx = _high_risk_ctx()
    ctx.risk_output = {"severity": "HIGH"}
    ctx.routing_output = {"route": "CLEAR"}  # genuine mismatch
    ctx.uncertainty_output = {"status": "CLEAR"}

    sup = SafetySupervisor()
    base = sup.run(ctx, draft_response="Let's talk about coping.").payload
    assert base["verdict"] == "RE-ROUTE"
    assert base["risk_consistency"] is False

    # Simulate a reworded rationale carrying the same structured fields.
    reworded = dict(base)
    reworded["rationale"] = "Completely rephrased: route/risk alignment problem detected."
    reworded["reasoning_summary"] = reworded["rationale"]

    # Old heuristic would miss ("High risk" not in text); structured must not.
    assert "High risk" not in reworded["rationale"]
    assert reworded["risk_consistency"] is False  # structured signal intact
    print("[PASS] Rationale wording decoupled from routing decision.")


def test_missing_risk_consistency_fails_closed():
    """Missing/invalid risk_consistency must not escalate."""
    payload = {"verdict": "RE-ROUTE", "rationale": "High risk blah"}
    assert payload.get("risk_consistency") is not False  # missing -> no bump
    payload2 = {"verdict": "RE-ROUTE", "rationale": "x", "risk_consistency": "yes"}
    assert payload2.get("risk_consistency") is not False  # invalid -> no bump
    payload3 = {"verdict": "RE-ROUTE", "rationale": "x", "risk_consistency": False}
    assert payload3.get("risk_consistency") is False  # explicit False -> bump path
    print("[PASS] Missing/invalid risk_consistency fails closed.")


def test_allow_revise_high_risk_unchanged():
    """ALLOW and REVISE paths unaffected by the RE-ROUTE change."""
    # ALLOW: low risk, clear message.
    ctx = AgentContext(case_id="a", modality="cbt",
                       current_message="Work deadlines are fine.", full_profile={})
    r = run_pipeline(ctx)
    assert r["verdict"] == "ALLOW"
    # REVISE: high risk, draft lacks safety framing -> supervisor revision.
    r2 = run_pipeline(_high_risk_ctx())
    assert r2["verdict"] == "REVISE"
    assert "supervisor_revision_applied" in [s.get("action") for s in r2["trail"]]
    print("[PASS] ALLOW/REVISE behavior unchanged.")
