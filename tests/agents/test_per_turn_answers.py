"""Regression tests for per-turn client answers in the clarification loop.

Before the fix, run_pipeline reused a single clarification_answer for every
turn and never updated ctx.current_message, so turn 2+ re-evaluated the same
response. Now clarification_answer accepts a list (one answer per turn,
backward compatible with a single string), each turn consumes the next
answer, and ctx.current_message tracks the latest client message.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.pipeline import _normalize_answer_sequence, run_pipeline


def _ctx_two_gaps(case_id="perturn"):
    data = json.loads(
        pathlib.Path("data/benchmark/ambiguous_cases/bt/bt_176_safety.json").read_text(encoding="utf-8")
    )
    profile = data["ambiguous_context"]
    profile["basic_info"]["growth_experiences"] = ""
    msg = "我最近不堪重负，整夜失眠。" + profile["basic_info"]["main_problem"]
    return AgentContext(
        case_id=case_id,
        modality="bt",
        therapy_stage="Problem Conceptualization and Goal Setting",
        full_profile=profile,
        current_message=msg,
        metadata={"track": "safety"},
    )


def _trail_answers(res):
    return [s["clarification_answer"] for s in res["trail"] if s["agent"] == "reassessment_agent"]


def test_two_turn_distinct_answers():
    """Turn 2 processes a different answer than turn 1 (no replay)."""
    ctx = _ctx_two_gaps()
    a1 = "This started about six months ago, around last spring."
    a2 = "No, I have never had any mental health treatment before."
    r = run_pipeline(ctx, clarification_answer=[a1, a2], max_reassess_turns=2)
    answers = _trail_answers(r)
    assert answers == [a1, a2], f"answers reused or out of order: {answers}"
    print("[PASS] Two turns consume distinct answers.")


def test_each_turn_resolves_its_own_item():
    """Answer 1 resolves growth; answer 2 resolves medical_history -> CLEAR."""
    ctx = _ctx_two_gaps()
    r = run_pipeline(
        ctx,
        clarification_answer=[
            "This started about six months ago, around last spring.",
            "No, I have never had any mental health treatment before.",
        ],
        max_reassess_turns=2,
    )
    assert r["route"] == "CLEAR"
    assert r["reassess_count"] == 2
    print("[PASS] Each turn resolves its own item; loop terminates CLEAR.")


def test_irrelevant_second_answer_keeps_uncertainty():
    """A deflected second answer does not resolve the remaining gap."""
    ctx = _ctx_two_gaps()
    r = run_pipeline(
        ctx,
        clarification_answer=[
            "This started about six months ago, around last spring.",
            "The weather is nice today.",
        ],
        max_reassess_turns=2,
    )
    assert r["route"] == "UNCERTAIN"
    reassesses = [s for s in r["trail"] if s["agent"] == "reassessment_agent"]
    assert len(reassesses) == 2
    assert not any("medical_history" in x for x in reassesses[1]["payload"]["resolved_information"])
    print("[PASS] Irrelevant second answer keeps uncertainty unresolved.")


def test_current_message_tracks_latest_answer():
    """ctx.current_message reflects the latest client message after the loop."""
    ctx = _ctx_two_gaps()
    original = ctx.current_message
    a2 = "No, I have never had any mental health treatment before."
    run_pipeline(
        ctx,
        clarification_answer=["This started about six months ago.", a2],
        max_reassess_turns=2,
    )
    assert ctx.current_message == a2
    assert ctx.current_message != original
    print("[PASS] ctx.current_message tracks the latest client answer.")


def test_risk_recalculated_from_latest_message():
    """Turn-2 risk assessment sees the latest client message."""
    ctx = _ctx_two_gaps("riskturn")
    # Turn 1 answer is benign; turn 2 answer carries acute distress.
    r = run_pipeline(
        ctx,
        clarification_answer=[
            "This started about six months ago.",
            "I feel completely hopeless and have thought about ending my life.",
        ],
        max_reassess_turns=3,
    )
    reassesses = [s for s in r["trail"] if s["agent"] == "reassessment_agent"]
    # The acute answer must surface as HIGH risk -> HIGH-RISK route.
    assert r["route"] == "HIGH-RISK", f"got {r['route']}"
    print("[PASS] Risk recalculated from latest client message.")


def test_single_answer_backward_compatible():
    """Existing single-string callers behave exactly as before."""
    ctx = _ctx_two_gaps("single1")
    r = run_pipeline(
        ctx,
        clarification_answer="This started about six months ago, around last spring.",
        max_reassess_turns=2,
    )
    answers = _trail_answers(r)
    assert answers == ["This started about six months ago, around last spring."]
    # Turn 2 clarifies but does NOT replay the answer (sequence exhausted).
    assert len(answers) == 1
    # None still works.
    ctx2 = _ctx_two_gaps("single2")
    r2 = run_pipeline(ctx2, clarification_answer=None, max_reassess_turns=2)
    assert r2["reassess_count"] == 0 or _trail_answers(r2) == []
    print("[PASS] Single-answer callers unchanged.")


def test_normalize_answer_sequence():
    assert _normalize_answer_sequence(None) == []
    assert _normalize_answer_sequence("a") == ["a"]
    assert _normalize_answer_sequence(["a", "b"]) == ["a", "b"]
    print("[PASS] Answer sequence normalization.")


def test_prioritization_intact_across_turns():
    """Safety still prioritized on turn 2 at elevated risk."""
    ctx = _ctx_two_gaps("prioturn")
    r = run_pipeline(
        ctx,
        clarification_answer=[
            "This started about six months ago, around last spring.",
            "The weather is nice today.",
        ],
        max_reassess_turns=2,
    )
    clars = [s for s in r["trail"] if s["agent"] == "clarification_agent"]
    assert len(clars) == 2
    assert "medical_history" in clars[1]["payload"]["target_information"], (
        f"turn 2 lost safety prioritization: {clars[1]['payload']['target_information']}"
    )
    print("[PASS] Risk-aware prioritization intact across turns.")
