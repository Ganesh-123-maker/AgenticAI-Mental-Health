"""Regression tests for risk-aware clarification prioritization.

The ClarificationAgent now reads the RiskAgent's structured severity when
choosing which question to ask:

- HIGH/MODERATE/UNCERTAIN risk + safety-relevant gap -> safety question first.
- LOW risk -> standard discourse order (no safety boost).
- Items resolved in a previous turn are never asked again (uses
  resolved_information, never target_information).
- Selection is deterministic for identical inputs.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.clarification_agent import ClarificationAgent
from sample.agents.memory_agent import MemoryAgent
from sample.agents.pipeline import run_pipeline
from sample.agents.risk_agent import RiskAgent
from sample.agents.state_agent import StateAgent
from sample.agents.uncertainty_agent import UncertaintyAgent


def _run_clarification(message, track=None, profile=None, reassessment_output=None):
    ctx = AgentContext(
        case_id="clar_test",
        modality="cbt",
        current_message=message,
        full_profile=profile or {},
        metadata={"track": track} if track else {},
    )
    ctx.memory_output = MemoryAgent().run(ctx).payload
    ctx.state_output = StateAgent().run(ctx).payload
    ctx.uncertainty_output = UncertaintyAgent().run(ctx).payload
    ctx.risk_output = RiskAgent().run(ctx).payload
    if reassessment_output is not None:
        ctx.reassessment_output = reassessment_output
    return ctx, ClarificationAgent().run(ctx).payload


def _safety_profile():
    return json.loads(
        pathlib.Path("data/benchmark/ambiguous_cases/bt/bt_176_safety.json").read_text(encoding="utf-8")
    )["ambiguous_context"]


def test_high_risk_safety_question_first():
    """HIGH risk with safety + non-safety gaps -> safety question chosen first."""
    ctx, out = _run_clarification(
        "我最近一直想自杀。It's about... that thing, you know.",
        track="safety",
    )
    assert ctx.risk_output["severity"] == "HIGH"
    assert "medical_history" in out["target_information"], f"got {out['target_information']}"
    assert out["priority"] == "HIGH"
    print("[PASS] HIGH risk -> safety question first.")


def test_moderate_risk_safety_prioritized():
    """MODERATE risk with unresolved safety item -> safety information prioritized."""
    profile = _safety_profile()
    msg = "我最近不堪重负，整夜失眠。" + profile["basic_info"]["main_problem"]
    ctx, out = _run_clarification(msg, track="safety", profile=profile)
    assert ctx.risk_output["severity"] == "MODERATE"
    assert "medical_history" in out["target_information"], f"got {out['target_information']}"
    print("[PASS] MODERATE risk -> safety prioritized.")


def test_low_risk_normal_clarification():
    """LOW risk -> standard order, no safety boost over discourse issues."""
    ctx, out = _run_clarification("It's about... that thing, you know.", track="safety")
    assert ctx.risk_output["severity"] == "LOW"
    # Ambiguous expression keeps its normal priority at LOW risk.
    assert "specific_event_referent" in out["target_information"], f"got {out['target_information']}"
    print("[PASS] LOW risk -> normal clarification order.")


def test_deterministic_prioritization():
    """Identical inputs always yield the identical question."""
    profile = _safety_profile()
    msg = "我最近不堪重负，整夜失眠。" + profile["basic_info"]["main_problem"]
    _, out1 = _run_clarification(msg, track="safety", profile=profile)
    _, out2 = _run_clarification(msg, track="safety", profile=profile)
    assert out1["question"] == out2["question"]
    assert out1["target_information"] == out2["target_information"]
    print("[PASS] Prioritization is deterministic.")


def test_resolved_information_not_asked_again():
    """A previously answered item is skipped in favor of the next gap."""
    profile = _safety_profile()
    msg = "我最近不堪重负，整夜失眠。" + profile["basic_info"]["main_problem"]
    # Simulate turn 2: medical_history was resolved on turn 1, but the
    # (stale) uncertainty output still lists it alongside an open gap.
    # The agent must not re-ask the resolved item.
    ctx, _ = _run_clarification(msg, track="safety", profile=profile)
    ctx.uncertainty_output = {
        **ctx.uncertainty_output,
        "uncertain_fields": ["medical_history", "growth_experiences"],
        "missing_information": [
            "medical_history (safety status absent)",
            "growth_experiences (empty or not provided)",
        ],
    }
    ctx.reassessment_output = {"resolved_information": ["medical_history (safety status absent)"]}
    out = ClarificationAgent().run(ctx).payload
    assert "medical_history" not in out["target_information"], (
        f"re-asked resolved item: {out['target_information']}"
    )
    print("[PASS] Resolved information not asked again.")


def test_all_resolved_returns_not_required():
    """When every gap is resolved, clarification reports not required."""
    profile = _safety_profile()
    msg = "我最近不堪重负，整夜失眠。" + profile["basic_info"]["main_problem"]
    ctx, _ = _run_clarification(msg, track="safety", profile=profile)
    ctx.reassessment_output = {"resolved_information": ["medical_history (safety status absent)"]}
    out = ClarificationAgent().run(ctx).payload
    assert out["clarification_required"] is False
    assert out["target_information"] == []
    print("[PASS] All-resolved returns not required.")


def test_asking_does_not_count_as_answering():
    """target_information from a previous turn alone must not suppress re-asking."""
    profile = _safety_profile()
    msg = "我最近不堪重负，整夜失眠。" + profile["basic_info"]["main_problem"]
    ctx = AgentContext(
        case_id="clar_test",
        modality="cbt",
        current_message=msg,
        full_profile=profile,
        metadata={"track": "safety"},
    )
    ctx.memory_output = MemoryAgent().run(ctx).payload
    ctx.state_output = StateAgent().run(ctx).payload
    ctx.uncertainty_output = UncertaintyAgent().run(ctx).payload
    ctx.risk_output = RiskAgent().run(ctx).payload
    # Previous turn ASKED about medical_history but it was NOT resolved.
    ctx.clarification_output = {"target_information": ["medical_history", "prior_treatment"]}
    ctx.reassessment_output = {"resolved_information": []}
    out = ClarificationAgent().run(ctx).payload
    assert "medical_history" in out["target_information"], (
        f"asking wrongly counted as answering: {out['target_information']}"
    )
    print("[PASS] Asking does not count as answering.")


def test_english_and_chinese_inputs():
    """Prioritization works for both English and Chinese risk inputs."""
    ctx_en, out_en = _run_clarification(
        "I want to commit suicide and end my life.", track="safety"
    )
    assert ctx_en.risk_output["severity"] == "HIGH"
    assert "medical_history" in out_en["target_information"]
    ctx_zh, out_zh = _run_clarification("我最近一直想自杀。", track="safety")
    assert ctx_zh.risk_output["severity"] == "HIGH"
    assert "medical_history" in out_zh["target_information"]
    print("[PASS] English and Chinese HIGH risk both prioritize safety.")


def test_full_loop_still_routes_correctly():
    """Clarification -> reassessment -> routing intact with prioritization."""
    profile = _safety_profile()
    msg = "我最近不堪重负，整夜失眠。" + profile["basic_info"]["main_problem"]
    ctx = AgentContext(
        case_id="loop_check",
        modality="bt",
        therapy_stage="Problem Conceptualization and Goal Setting",
        full_profile=profile,
        current_message=msg,
        metadata={"track": "safety"},
    )
    # Irrelevant answer -> safety still unresolved -> UNCERTAIN
    r1 = run_pipeline(ctx, clarification_answer="This started about six months ago.")
    assert r1["route"] == "UNCERTAIN"
    # Genuine safety answer -> resolves -> CLEAR, risk not downgraded
    ctx2 = AgentContext(
        case_id="loop_check2",
        modality="bt",
        therapy_stage="Problem Conceptualization and Goal Setting",
        full_profile=profile,
        current_message=msg,
        metadata={"track": "safety"},
    )
    r2 = run_pipeline(
        ctx2,
        clarification_answer="No, I have never received any mental health treatment before.",
    )
    assert r2["route"] == "CLEAR"
    print("[PASS] Full clarify -> reassess -> routing loop correct.")
