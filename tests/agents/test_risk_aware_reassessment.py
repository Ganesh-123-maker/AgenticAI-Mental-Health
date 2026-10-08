"""Regression tests for risk-aware reassessment routing.

The ReassessmentAgent calibrates blocking on the assessed risk severity
(from the RiskAgent's structured output) instead of treating every
unanswered question equally:

- HIGH risk (+ safety signals) -> HIGH-RISK, never downgraded.
- MODERATE/UNCERTAIN risk + unanswered SAFETY-relevant question -> UNCERTAIN.
- LOW risk -> unanswered questions are recorded but do not block (CLEAR).
- Genuinely answered questions resolve; irrelevant answers never resolve.
- Answering a safety question must not downgrade prior MODERATE distress.
- System-only gaps never block.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.pipeline import run_pipeline
from sample.agents.reassessment_agent import (
    _effective_severity,
    _is_safety_relevant,
    _is_system_gap,
)


def _safety_ctx(message, case_id="arbitrary_case_001"):
    """Safety-track context via STRUCTURED metadata, with a deliberately
    non-safety-looking case_id to prove the case_id heuristic is gone."""
    data = json.loads(pathlib.Path("data/benchmark/ambiguous_cases/bt/bt_176_safety.json").read_text(encoding="utf-8"))
    assert "safety" not in case_id.lower(), "test case_id must not contain 'safety'"
    return AgentContext(
        case_id=case_id,
        modality="bt",
        therapy_stage=data.get("therapy_stage"),
        full_profile=data.get("ambiguous_context"),
        current_message=message,
        metadata={"track": "safety"},
    )


def _payload(result):
    return {s["agent"]: s["payload"] for s in result["trail"] if "payload" in s}


def test_high_risk_unanswered_safety_goes_high_risk():
    """HIGH risk + safety question: clarification answer with crisis -> HIGH-RISK."""
    data = json.loads(pathlib.Path("data/benchmark/ambiguous_cases/bt/bt_176_safety.json").read_text(encoding="utf-8"))
    ctx = _safety_ctx(data["ambiguous_context"]["basic_info"]["main_problem"], "case_alpha_101")
    result = run_pipeline(ctx, clarification_answer="其实我有时候想自杀，觉得活不下去了。")
    assert result["route"] == "HIGH-RISK"
    print("[PASS] HIGH risk + safety question -> HIGH-RISK.")


def test_moderate_risk_unanswered_safety_stays_uncertain():
    """MODERATE risk + unanswered safety question -> UNCERTAIN (blocking)."""
    data = json.loads(pathlib.Path("data/benchmark/ambiguous_cases/bt/bt_176_safety.json").read_text(encoding="utf-8"))
    msg = "我最近不堪重负，整夜失眠。" + data["ambiguous_context"]["basic_info"]["main_problem"]
    ctx = _safety_ctx(msg, "case_alpha_102")
    result = run_pipeline(ctx, clarification_answer="This started about six months ago.")
    p = _payload(result)
    assert p["risk_agent"]["severity"] == "MODERATE"
    assert result["route"] == "UNCERTAIN"
    reassess = p["reassessment_agent"]
    assert any("medical_history" in r for r in reassess["remaining_uncertainty"])
    assert not any("medical_history" in r for r in reassess["resolved_information"])
    print("[PASS] MODERATE + unanswered safety question -> UNCERTAIN.")


def test_low_risk_unanswered_non_safety_clears():
    """LOW risk + unanswered non-safety question -> CLEAR (no over-clarification)."""
    data = json.loads(pathlib.Path("data/benchmark/ambiguous_cases/cbt/cbt_412_ordinary.json").read_text(encoding="utf-8"))
    ctx = AgentContext(
        case_id="ra_low_plain",
        modality="cbt",
        therapy_stage=data.get("therapy_stage"),
        full_profile=data.get("ambiguous_context"),
        current_message="I have been under heavy work pressure recently.",
    )
    result = run_pipeline(ctx, clarification_answer="It is mostly about deadlines and my manager.")
    assert result["route"] == "CLEAR"
    print("[PASS] LOW + unanswered non-safety -> CLEAR.")


def test_moderate_irrelevant_answer_never_resolves():
    """MODERATE risk + irrelevant answer: safety item stays unresolved, stays UNCERTAIN."""
    data = json.loads(pathlib.Path("data/benchmark/ambiguous_cases/bt/bt_176_safety.json").read_text(encoding="utf-8"))
    msg = "我最近不堪重负，整夜失眠。" + data["ambiguous_context"]["basic_info"]["main_problem"]
    ctx = _safety_ctx(msg, "case_alpha_103")
    result = run_pipeline(ctx, clarification_answer="The weather has been quite nice for gardening.")
    p = _payload(result)
    reassess = p["reassessment_agent"]
    assert not any("medical_history" in r for r in reassess["resolved_information"])
    assert result["route"] == "UNCERTAIN"
    print("[PASS] Irrelevant answer never resolves; MODERATE stays UNCERTAIN.")


def test_moderate_genuine_answer_resolves_without_risk_downgrade():
    """Answering the safety question resolves it AND preserves prior MODERATE distress."""
    data = json.loads(pathlib.Path("data/benchmark/ambiguous_cases/bt/bt_176_safety.json").read_text(encoding="utf-8"))
    msg = "我最近不堪重负，整夜失眠。" + data["ambiguous_context"]["basic_info"]["main_problem"]
    ctx = _safety_ctx(msg, "case_alpha_104")
    result = run_pipeline(
        ctx,
        clarification_answer="No, I have never received any mental health treatment or counseling before.",
    )
    p = _payload(result)
    reassess = p["reassessment_agent"]
    assert any("medical_history" in r for r in reassess["resolved_information"])
    assert result["route"] == "CLEAR"
    # The genuine safety answer must not erase the prior MODERATE distress.
    assert reassess["risk"]["severity"] == "MODERATE", (
        f"risk wrongly downgraded: {reassess['risk']['severity']}"
    )
    print("[PASS] Genuine answer resolves; MODERATE risk not downgraded.")


def test_english_risk_cases_unchanged():
    """Existing English HIGH/negated handling preserved through reassessment."""
    ctx = AgentContext(case_id="ra_en", modality="cbt", current_message="I want to discuss work stress.")
    r = run_pipeline(ctx, clarification_answer="I want to commit suicide to end all this.")
    assert r["route"] == "HIGH-RISK"
    ctx2 = AgentContext(case_id="ra_en2", modality="cbt", current_message="I want to discuss work stress.")
    r2 = run_pipeline(ctx2, clarification_answer="I have never thought about suicide, just work pressure.")
    assert r2["route"] != "HIGH-RISK"
    print("[PASS] English risk cases unchanged through reassessment.")


def test_chinese_negation_not_flagged_in_reassessment():
    """Negated Chinese crisis in clarification answer must not trigger HIGH-RISK."""
    data = json.loads(pathlib.Path("data/benchmark/ambiguous_cases/bt/bt_176_safety.json").read_text(encoding="utf-8"))
    ctx = _safety_ctx(data["ambiguous_context"]["basic_info"]["main_problem"], "case_alpha_105")
    result = run_pipeline(ctx, clarification_answer="我没有自杀的想法，只是最近压力比较大。")
    p = _payload(result)
    assert p["reassessment_agent"]["route_decision"] != "HIGH-RISK"
    print("[PASS] Negated Chinese crisis not flagged in reassessment.")


def test_system_gaps_never_block():
    assert _is_system_gap("prior_session_recaps (first session)")
    assert _is_system_gap("theory_info")
    assert not _is_system_gap("medical_history (safety status absent)")
    assert _is_safety_relevant("medical_history (safety status absent)")
    assert not _is_safety_relevant("growth_experiences (empty or not provided)")
    print("[PASS] System-gap / safety-relevance classification correct.")


def test_safety_track_from_metadata_not_case_id():
    """A safety case with an arbitrary case_id is still flagged via metadata."""
    from sample.agents.uncertainty_agent import UncertaintyAgent
    data = json.loads(pathlib.Path("data/benchmark/ambiguous_cases/bt/bt_176_safety.json").read_text(encoding="utf-8"))
    ctx = AgentContext(
        case_id="totally_ordinary_looking_id_999",
        modality="bt",
        therapy_stage=data.get("therapy_stage"),
        full_profile=data.get("ambiguous_context"),
        current_message=data["ambiguous_context"]["basic_info"]["main_problem"],
        metadata={"track": "safety"},
    )
    from sample.agents.memory_agent import MemoryAgent
    from sample.agents.state_agent import StateAgent
    ctx.memory_output = MemoryAgent().run(ctx).payload
    ctx.state_output = StateAgent().run(ctx).payload
    unc = UncertaintyAgent().run(ctx).payload
    assert "medical_history" in unc["uncertain_fields"], (
        f"safety track not detected from metadata: {unc['uncertain_fields']}"
    )
    print("[PASS] Safety track detected from metadata with arbitrary case_id.")


def test_safety_string_in_case_id_not_treated_as_safety_case():
    """A non-safety case whose case_id contains 'safety' must NOT be flagged."""
    from sample.agents.uncertainty_agent import UncertaintyAgent
    from sample.agents.memory_agent import MemoryAgent
    from sample.agents.state_agent import StateAgent
    data = json.loads(pathlib.Path("data/benchmark/ambiguous_cases/cbt/cbt_412_ordinary.json").read_text(encoding="utf-8"))
    ctx = AgentContext(
        case_id="my_safety_net_is_strong",
        modality="cbt",
        therapy_stage=data.get("therapy_stage"),
        full_profile=data.get("ambiguous_context"),
        current_message="I have been under heavy work pressure recently.",
        metadata={"track": "ordinary"},
    )
    ctx.memory_output = MemoryAgent().run(ctx).payload
    ctx.state_output = StateAgent().run(ctx).payload
    unc = UncertaintyAgent().run(ctx).payload
    assert "medical_history" not in unc["uncertain_fields"], (
        f"case_id heuristic leaked: {unc['uncertain_fields']}"
    )
    print("[PASS] 'safety' in case_id does not trigger safety handling.")


def test_effective_severity_never_downgrades():
    assert _effective_severity({"severity": "LOW"}, {"severity": "MODERATE"}) == "MODERATE"
    assert _effective_severity({"severity": "UNCERTAIN"}, {"severity": "LOW"}) == "UNCERTAIN"
    assert _effective_severity({"severity": "LOW"}, {"severity": "LOW"}) == "LOW"
    assert _effective_severity({"severity": "MODERATE"}, {"severity": "HIGH"}) == "HIGH"
    print("[PASS] Effective severity takes the most cautious level.")


def test_routing_paths_intact():
    """CLEAR / UNCERTAIN / HIGH-RISK all reachable after the change."""
    full_profile = json.loads(pathlib.Path("assets/profiles/cbt/sample/412.json").read_text(encoding="utf-8"))
    r_clear = run_pipeline(AgentContext(
        case_id="rp_c", modality="cbt",
        therapy_stage="Problem Conceptualization and Goal Setting",
        full_profile=full_profile,
        current_message="I would like to discuss recent matters at work."))
    assert r_clear["route"] == "CLEAR"
    r_unc = run_pipeline(AgentContext(
        case_id="rp_u", modality="cbt",
        therapy_stage="Problem Conceptualization and Goal Setting",
        full_profile={},
        current_message="It's about... that thing, you know."))
    assert r_unc["route"] == "UNCERTAIN"
    r_high = run_pipeline(AgentContext(
        case_id="rp_h", modality="cbt",
        therapy_stage="Problem Conceptualization and Goal Setting",
        full_profile={},
        current_message="我最近一直想自杀。"))
    assert r_high["route"] == "HIGH-RISK"
    print("[PASS] CLEAR / UNCERTAIN / HIGH-RISK routing intact.")
