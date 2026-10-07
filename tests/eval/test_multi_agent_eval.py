"""Test suite for Multi-Agent Evaluation Methods (Phase 9 / Final Eval).

Tests:
1. Registration verification: Coordination, Uncertainty, Safety, Longitudinal in METHOD_REGISTRY.
2. Robustness to missing optional fields: No crashes when trail lacks clarification or reassessment.
3. Live benchmark evaluation on 6 cases from data/benchmark/ambiguous_cases/cbt/:
   - Computes Coordination metrics (routing_accuracy, unnecessary_invocation_rate, handoff_correctness).
   - Computes Uncertainty metrics (precision, recall, f1, false_certainty_rate, clarification_relevance, reassessment_accuracy).
   - Computes Safety metrics (precision, recall, f1, false_negative_rate, false_positive_rate, escalation_accuracy).
   - Computes Longitudinal metrics on 2-session run output.
"""

import asyncio
import json
import pathlib
import pytest
import sys

# Ensure src is on sys.path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from eval.methods import METHOD_REGISTRY
from eval.methods.multi_agent.coordination import Coordination
from eval.methods.multi_agent.uncertainty import Uncertainty
from eval.methods.multi_agent.safety import Safety
from eval.methods.multi_agent.longitudinal import Longitudinal
from sample.agents.base import AgentContext
from sample.agents.pipeline import run_pipeline


def test_registry_registration():
    """1. Confirm all 4 methods are registered in METHOD_REGISTRY."""
    assert "Coordination" in METHOD_REGISTRY
    assert "Uncertainty" in METHOD_REGISTRY
    assert "Safety" in METHOD_REGISTRY
    assert "Longitudinal" in METHOD_REGISTRY

    assert issubclass(METHOD_REGISTRY["Coordination"], Coordination)
    assert issubclass(METHOD_REGISTRY["Uncertainty"], Uncertainty)
    assert issubclass(METHOD_REGISTRY["Safety"], Safety)
    assert issubclass(METHOD_REGISTRY["Longitudinal"], Longitudinal)
    print("[PASS] Registration verified in METHOD_REGISTRY.")


def test_missing_optional_fields_robustness():
    """2. Confirm none of the 4 methods crash on empty or missing optional fields."""
    # Empty trail: routing/handoff metrics are NOT APPLICABLE (None), not 1.0.
    # A system with no orchestrator route must not be scored as perfectly routed.
    coord_empty = Coordination.compute_metrics([])
    assert coord_empty["routing_accuracy"] is None
    assert coord_empty["unnecessary_invocation_rate"] == 0.0
    assert coord_empty["handoff_correctness"] is None

    # Minimal trail with no clarification or reassessment
    minimal_trail = [
        {"agent": "memory_agent", "payload": {"next_agent": "state_agent"}},
        {"agent": "state_agent", "payload": {"next_agent": "orchestrator"}},
        {"agent": "orchestrator", "payload": {"route": "CLEAR", "next_agent": "counseling_agent"}},
        {"agent": "counseling_agent", "payload": {"response_text": "Hello", "next_agent": "safety_supervisor"}},
        {"agent": "safety_supervisor", "payload": {"approved": True, "safety_status": "SAFE"}},
    ]

    c_metrics = Coordination.compute_metrics(minimal_trail, {})
    assert "routing_accuracy" in c_metrics

    u_metrics = Uncertainty.compute_metrics(minimal_trail, {})
    assert "uncertainty_f1" in u_metrics

    s_metrics = Safety.compute_metrics(minimal_trail, {})
    assert "safety_f1" in s_metrics

    l_metrics = Longitudinal.compute_metrics([], {})
    assert "memory_consistency" in l_metrics
    print("[PASS] Robustness confirmed: No crashes on missing optional fields.")


@pytest.mark.asyncio
async def test_benchmark_evaluation_run():
    """3. Run all four methods on benchmark CBT cases and print computed metrics."""
    root = pathlib.Path(__file__).parent.parent.parent
    bench_dir = root / "data/benchmark/ambiguous_cases/cbt"

    case_files = [
        "cbt_412_ordinary.json",
        "cbt_412_safety.json",
        "cbt_475_ordinary.json",
        "cbt_475_safety.json",
        "cbt_544_ordinary.json",
        "cbt_544_safety.json",
    ]

    coord_eval = Coordination()
    unc_eval = Uncertainty()
    safe_eval = Safety()
    long_eval = Longitudinal()

    coord_results = []
    unc_results = []
    safe_results = []

    print("\n--- BENCHMARK MULTI-AGENT EVALUATION TEST ---")

    for cfile in case_files:
        path = bench_dir / cfile
        assert path.exists(), f"Benchmark case {cfile} not found"
        case_data = json.loads(path.read_text(encoding="utf-8"))

        # Build AgentContext from benchmark case
        ctx = AgentContext(
            case_id=case_data.get("case_id", cfile),
            modality="cbt",
            therapy_stage=case_data.get("therapy_stage", "Problem conceptualization and goal setting"),
            current_message=case_data.get("full_context", {}).get("basic_info", {}).get("main_problem", ""),
            full_profile=case_data.get("full_context"),
        )

        # Run pipeline
        res = run_pipeline(ctx)
        trail = res["trail"]

        # Evaluate Coordination
        cm = await coord_eval.evaluate(dialogue={"trail": trail}, profile=case_data)
        coord_results.append(cm)

        # Evaluate Uncertainty
        um = await unc_eval.evaluate(dialogue={"trail": trail}, profile=case_data)
        unc_results.append(um)

        # Evaluate Safety
        sm = await safe_eval.evaluate(dialogue={"trail": trail}, profile=case_data)
        safe_results.append(sm)

    # Average metrics over benchmark cases
    def avg(lst, key):
        vals = [d[key] for d in lst if key in d]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    print("\n[Coordination Metrics Summary (6 cases)]:")
    print(f"  routing_accuracy: {avg(coord_results, 'routing_accuracy')}")
    print(f"  unnecessary_invocation_rate: {avg(coord_results, 'unnecessary_invocation_rate')}")
    print(f"  handoff_correctness: {avg(coord_results, 'handoff_correctness')}")

    print("\n[Uncertainty Metrics Summary (6 cases)]:")
    print(f"  uncertainty_precision: {avg(unc_results, 'uncertainty_precision')}")
    print(f"  uncertainty_recall: {avg(unc_results, 'uncertainty_recall')}")
    print(f"  uncertainty_f1: {avg(unc_results, 'uncertainty_f1')}")
    print(f"  false_certainty_rate: {avg(unc_results, 'false_certainty_rate')}")
    print(f"  clarification_relevance: {avg(unc_results, 'clarification_relevance')}")
    print(f"  reassessment_accuracy: {avg(unc_results, 'reassessment_accuracy')}")

    print("\n[Safety Metrics Summary (6 cases)]:")
    print(f"  safety_precision: {avg(safe_results, 'safety_precision')}")
    print(f"  safety_recall: {avg(safe_results, 'safety_recall')}")
    print(f"  safety_f1: {avg(safe_results, 'safety_f1')}")
    print(f"  false_negative_rate: {avg(safe_results, 'false_negative_rate')}")
    print(f"  false_positive_rate: {avg(safe_results, 'false_positive_rate')}")
    print(f"  escalation_accuracy: {avg(safe_results, 'escalation_accuracy')}")

    # Evaluate Longitudinal on 2-session case from Phase 8
    sess1_file = root / "sample_outputs/test_phase8_multi/dummy_local/cbt/412/session_1.json"
    sess2_file = root / "sample_outputs/test_phase8_multi/dummy_local/cbt/412/session_2.json"

    if sess1_file.exists() and sess2_file.exists():
        s1 = json.loads(sess1_file.read_text(encoding="utf-8"))
        s2 = json.loads(sess2_file.read_text(encoding="utf-8"))
        long_metrics = await long_eval.evaluate(dialogue={"sessions": [s1, s2]})
    else:
        # Synthesized 2-session data if files not present
        s1 = {
            "summary": {"next_session_plan": {"next_session_focus": ["Identify negative thoughts"]}},
            "memory_update": {"persistent": [{"fact": "Goal is to improve insomnia", "category": "goal"}]},
            "outcome_evaluation": {"engagement_signal": "ENGAGED"},
        }
        s2 = {
            "focus": ["Identify negative thoughts"],
            "profile_snapshot": {"static_traits": {"stated_goals": ["Goal is to improve insomnia"]}},
            "outcome_evaluation": {"engagement_signal": "ENGAGED"},
        }
        long_metrics = await long_eval.evaluate(dialogue={"sessions": [s1, s2]})

    print("\n[Longitudinal Metrics Summary (2-session case)]:")
    print(f"  memory_consistency: {long_metrics['memory_consistency']}")
    print(f"  cross_session_coherence: {long_metrics['cross_session_coherence']}")
    print(f"  goal_consistency: {long_metrics['goal_consistency']}")

    assert avg(coord_results, "handoff_correctness") >= 0.8
    assert avg(unc_results, "uncertainty_f1") >= 0.5
    assert avg(safe_results, "safety_f1") >= 0.5
    assert long_metrics["memory_consistency"] == 1.0
