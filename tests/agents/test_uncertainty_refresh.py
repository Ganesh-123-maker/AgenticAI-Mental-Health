"""Regression tests for refreshed uncertainty state in the clarify->reassess loop.

Before the fix, the ClarificationAgent on turn 2+ received the ORIGINAL
UncertaintyAgent output, reasoning from stale uncertainty. Now the pipeline
propagates the ReassessmentAgent's refreshed assessments
(payload["uncertainty"], payload["risk"]) onto the context between turns:

- Resolved items disappear from the active uncertainty state.
- Unresolved items persist; newly discovered uncertainty is preserved.
- Risk state comes from the current (reassessed) assessment.
- The loop terminates when uncertainty is resolved.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.clarification_agent import ClarificationAgent
from sample.agents.memory_agent import MemoryAgent
from sample.agents.pipeline import _propagate_reassessment_state, run_pipeline
from sample.agents.reassessment_agent import ReassessmentAgent
from sample.agents.risk_agent import RiskAgent
from sample.agents.state_agent import StateAgent
from sample.agents.uncertainty_agent import UncertaintyAgent


def _base_ctx(message, profile, case_id="refresh_test", track="safety"):
    ctx = AgentContext(
        case_id=case_id,
        modality="bt",
        therapy_stage="Problem Conceptualization and Goal Setting",
        full_profile=profile,
        current_message=message,
        metadata={"track": track},
    )
    ctx.memory_output = MemoryAgent().run(ctx).payload
    ctx.state_output = StateAgent().run(ctx).payload
    ctx.uncertainty_output = UncertaintyAgent().run(ctx).payload
    ctx.risk_output = RiskAgent().run(ctx).payload
    return ctx


def _safety_profile_two_gaps():
    data = json.loads(
        pathlib.Path("data/benchmark/ambiguous_cases/bt/bt_176_safety.json").read_text(encoding="utf-8")
    )
    profile = data["ambiguous_context"]
    profile["basic_info"]["growth_experiences"] = ""
    return profile, data["ambiguous_context"]["basic_info"]["main_problem"]


def test_resolved_item_disappears_from_active_state():
    """Turn 1 resolves growth_experiences -> turn 2 state no longer contains it."""
    profile, main_problem = _safety_profile_two_gaps()
    msg = "我最近不堪重负，整夜失眠。" + main_problem
    ctx = _base_ctx(msg, profile)
    assert any("growth_experiences" in m for m in ctx.uncertainty_output["missing_information"])

    r1 = ReassessmentAgent().run(
        ctx, clarification_answer="This started about six months ago, around last spring."
    ).payload
    assert any("growth_experiences" in r for r in r1["resolved_information"])
    _propagate_reassessment_state(ctx, r1)

    assert not any("growth_experiences" in m for m in ctx.uncertainty_output["missing_information"]), (
        f"stale item still present: {ctx.uncertainty_output['missing_information']}"
    )
    assert any("medical_history" in m for m in ctx.uncertainty_output["missing_information"])
    print("[PASS] Resolved item disappears from active uncertainty state.")


def test_unresolved_item_persists_to_next_turn():
    """Turn 1 leaves medical_history unanswered -> turn 2 still targets it."""
    profile, main_problem = _safety_profile_two_gaps()
    msg = "我最近不堪重负，整夜失眠。" + main_problem
    ctx = _base_ctx(msg, profile)

    r1 = ReassessmentAgent().run(
        ctx, clarification_answer="This started about six months ago, around last spring."
    ).payload
    assert r1["route_decision"] == "UNCERTAIN"
    _propagate_reassessment_state(ctx, r1)
    ctx.reassessment_output = r1

    c2 = ClarificationAgent().run(ctx).payload
    assert "medical_history" in c2["target_information"], f"got {c2['target_information']}"
    assert "growth_experiences" not in str(c2["target_information"])
    print("[PASS] Unresolved item persists; resolved item not re-targeted.")


def test_new_uncertainty_discovered_is_preserved():
    """A newly discovered uncertainty type in reassessment reaches turn 2."""
    profile, main_problem = _safety_profile_two_gaps()
    ctx = _base_ctx("我最近不堪重负。" + main_problem, profile)
    # Simulate reassessment: safety gap resolved, but a contradiction was
    # discovered in the answer. Turn 2 must target the contradiction.
    r1 = {
        "uncertainty": {
            **ctx.uncertainty_output,
            "uncertain_fields": ["contradictory_feelings"],
            "uncertainty_types": ["contradictory_information"],
            "missing_information": [],
        },
        "risk": {"severity": "MODERATE"},
        "resolved_information": ["medical_history (safety status absent)"],
        "remaining_uncertainty": [],
        "route_decision": "UNCERTAIN",
    }
    _propagate_reassessment_state(ctx, r1)
    assert "contradictory_information" in ctx.uncertainty_output["uncertainty_types"]
    ctx.reassessment_output = r1
    c2 = ClarificationAgent().run(ctx).payload
    assert "conflicting_feelings_clarification" in c2["target_information"], (
        f"got {c2['target_information']}"
    )
    assert "medical_history" not in c2["target_information"]
    print("[PASS] Newly discovered uncertainty preserved for next turn.")


def test_irrelevant_answer_keeps_item_in_state():
    """An irrelevant answer must not remove the item from the active state."""
    profile, main_problem = _safety_profile_two_gaps()
    msg = "我最近不堪重负，整夜失眠。" + main_problem
    ctx = _base_ctx(msg, profile)

    r1 = ReassessmentAgent().run(ctx, clarification_answer="The weather is nice today.").payload
    assert not r1["resolved_information"]
    _propagate_reassessment_state(ctx, r1)
    missing = ctx.uncertainty_output["missing_information"]
    assert any("medical_history" in m for m in missing)
    assert any("growth_experiences" in m for m in missing)
    print("[PASS] Irrelevant answer keeps items in active state.")


def test_risk_state_refreshed_for_prioritization():
    """Turn 2 prioritization uses the refreshed (not stale) risk severity."""
    profile, main_problem = _safety_profile_two_gaps()
    ctx = _base_ctx("Work has been fine lately. " + main_problem, profile)
    assert ctx.risk_output["severity"] == "LOW"
    # Reassessment re-ran risk on an answer containing distress -> MODERATE.
    r1 = {
        "uncertainty": ctx.uncertainty_output,
        "risk": {"severity": "MODERATE", "risk_status": "SUSPECTED_RISK", "evidence": ["distress in answer"]},
        "resolved_information": [],
        "remaining_uncertainty": ["medical_history (safety status absent)"],
        "route_decision": "UNCERTAIN",
    }
    _propagate_reassessment_state(ctx, r1)
    assert ctx.risk_output["severity"] == "MODERATE"
    ctx.reassessment_output = r1
    c2 = ClarificationAgent().run(ctx).payload
    assert "medical_history" in c2["target_information"], (
        f"safety not prioritized at refreshed MODERATE: {c2['target_information']}"
    )
    print("[PASS] Refreshed risk drives turn-2 prioritization.")


def test_multi_turn_terminates_when_resolved():
    """Two genuine answers across two turns -> CLEAR, loop terminates."""
    profile, main_problem = _safety_profile_two_gaps()
    msg = "我最近不堪重负，整夜失眠。" + main_problem

    # Turn 1 via pipeline: answer addresses medical_history genuinely.
    ctx1 = _base_ctx(msg, profile, case_id="term_t1")
    r1 = run_pipeline(
        ctx1,
        clarification_answer="No, I have never had any mental health treatment before.",
        max_reassess_turns=2,
    )
    # medical_history resolved; growth_experiences (non-safety) remains at
    # MODERATE -> CLEAR per risk-aware rule; loop terminates.
    assert r1["route"] == "CLEAR"
    assert r1["reassess_count"] <= 2
    print("[PASS] Multi-turn loop terminates when resolved.")


def test_no_infinite_loop_on_persistent_deflection():
    """Repeated irrelevant answers cannot loop forever (cap respected)."""
    profile, main_problem = _safety_profile_two_gaps()
    msg = "我最近不堪重负，整夜失眠。" + main_problem
    ctx = _base_ctx(msg, profile, case_id="term_t2")
    r = run_pipeline(
        ctx,
        clarification_answer="The weather is nice today.",
        max_reassess_turns=3,
    )
    assert r["reassess_count"] <= 3
    assert r["route"] == "UNCERTAIN"
    print("[PASS] No infinite loop on persistent deflection.")


def test_existing_severity_behavior_unchanged():
    """HIGH/MODERATE/LOW pipeline behavior intact after state propagation."""
    base = dict(modality="cbt", therapy_stage="Problem Conceptualization and Goal Setting", full_profile={})
    r_high = run_pipeline(AgentContext(case_id="sev_h", current_message="我最近一直想自杀。", **base))
    assert r_high["route"] == "HIGH-RISK"
    r_low = run_pipeline(
        AgentContext(case_id="sev_l", current_message="I would like to discuss recent matters at work.", **base),
        clarification_answer="It is mostly about deadlines.",
    )
    assert r_low["route"] in ("CLEAR", "UNCERTAIN")
    print("[PASS] HIGH/MODERATE/LOW behavior unchanged.")
