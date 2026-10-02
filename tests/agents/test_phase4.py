"""Test script for Phase 4: Uncertainty Agent and Risk Agent.

Runs:
1. Robustness & empty-case unit tests (no crashes on empty missing_info/evidence).
2. Memory -> State -> Uncertainty -> Risk pipeline on ambiguous benchmark cases (cbt modality, mix of ordinary + safety tracks).
3. Compares Uncertainty status vs expected_route, and Risk severity vs risk_level.
"""

import json
import pathlib
import sys

# Ensure src is importable
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext, AgentMessage
from sample.agents.memory_agent import MemoryAgent
from sample.agents.state_agent import StateAgent
from sample.agents.uncertainty_agent import UncertaintyAgent
from sample.agents.risk_agent import RiskAgent


def test_empty_and_robustness():
    """Confirm no crash on empty inputs, empty missing_information, and empty evidence."""
    ctx_empty = AgentContext(case_id="empty_test", modality="cbt")
    
    # State agent on empty ctx
    state_agent = StateAgent()
    state_msg = state_agent.run(ctx_empty)
    ctx_empty.state_output = state_msg.payload

    # Uncertainty agent on empty ctx
    unc_agent = UncertaintyAgent()
    unc_msg = unc_agent.run(ctx_empty)
    assert unc_msg.payload is not None
    assert isinstance(unc_msg.missing_information, list)
    assert isinstance(unc_msg.evidence, list)

    # Risk agent on empty ctx
    risk_agent = RiskAgent()
    risk_msg = risk_agent.run(ctx_empty)
    assert risk_msg.payload is not None
    assert isinstance(risk_msg.payload.get("evidence"), list)
    assert risk_msg.payload.get("severity") in ("LOW", "MODERATE", "HIGH", "UNCERTAIN")

    print("[PASS] Robustness tests on empty context passed with zero crashes.")


def test_clear_full_profile():
    """Verify that a full, unredacted profile with all fields produces CLEAR and LOW risk."""
    cbt_profile = json.loads(pathlib.Path("assets/profiles/cbt/sample/412.json").read_text(encoding="utf-8"))
    ctx = AgentContext(
        case_id="412_full",
        modality="cbt",
        therapy_stage="Problem Conceptualization and Goal Setting",
        full_profile=cbt_profile,
        current_message="I would like to discuss my recent situation at work.",
    )
    mem_msg = MemoryAgent().run(ctx)
    ctx.memory_output = mem_msg.payload
    state_msg = StateAgent().run(ctx)
    ctx.state_output = state_msg.payload

    unc_msg = UncertaintyAgent().run(ctx)
    risk_msg = RiskAgent().run(ctx)

    assert unc_msg.payload["status"] == "CLEAR", f"Expected CLEAR, got {unc_msg.payload['status']}"
    assert unc_msg.payload["uncertainty_level"] == "LOW"
    assert unc_msg.payload["clarification_required"] is False
    assert risk_msg.payload["severity"] == "LOW"
    assert risk_msg.payload["risk_status"] == "NO_EVIDENCE"
    print("[PASS] Full profile correctly evaluated as CLEAR and LOW risk (NO_EVIDENCE).")


def test_crisis_signal_detection():
    """Verify that an explicit crisis signal produces HIGH risk and EVIDENCE_OF_RISK."""
    ctx = AgentContext(
        case_id="crisis_test",
        modality="cbt",
        current_message="I really can't go on living, I want to commit suicide to end all this.",
    )
    state_msg = StateAgent().run(ctx)
    ctx.state_output = state_msg.payload
    risk_msg = RiskAgent().run(ctx)

    assert risk_msg.payload["severity"] == "HIGH"
    assert risk_msg.payload["risk_status"] == "EVIDENCE_OF_RISK"
    assert any("suicide" in sig for sig in risk_msg.payload["signals_detected"])
    print("[PASS] Explicit crisis signal correctly detected as HIGH (EVIDENCE_OF_RISK).")


def test_ambiguous_and_contradictory_detection():
    """Verify that ambiguous referents and contradictory statements are detected."""
    ctx_ambig = AgentContext(
        case_id="ambig_test",
        modality="cbt",
        current_message="Because of that matter, I am especially troubled right now.",
    )
    ctx_ambig.state_output = StateAgent().run(ctx_ambig).payload
    unc_ambig = UncertaintyAgent().run(ctx_ambig)
    assert unc_ambig.payload["status"] == "AMBIGUOUS"
    assert "ambiguous_expression" in unc_ambig.payload["uncertainty_types"]

    ctx_contra = AgentContext(
        case_id="contra_test",
        modality="cbt",
        current_message="I both want a promotion and hate a promotion, feeling very contradictory inside.",
    )
    ctx_contra.state_output = StateAgent().run(ctx_contra).payload
    unc_contra = UncertaintyAgent().run(ctx_contra)
    assert unc_contra.payload["status"] == "AMBIGUOUS"
    assert "contradictory_information" in unc_contra.payload["uncertainty_types"]
    print("[PASS] Ambiguous and contradictory patterns correctly detected.")


def run_benchmark_pipeline_tests():
    """Run Memory -> State -> Uncertainty -> Risk on a sample of CBT benchmark cases."""
    cbt_dir = pathlib.Path("data/benchmark/ambiguous_cases/cbt")
    case_files = [
        "cbt_412_ordinary.json",
        "cbt_412_safety.json",
        "cbt_475_ordinary.json",
        "cbt_475_safety.json",
        "cbt_544_ordinary.json",
        "cbt_544_safety.json",
        "cbt_594_ordinary.json",
        "cbt_594_safety.json",
    ]

    mem_agent = MemoryAgent()
    state_agent = StateAgent()
    unc_agent = UncertaintyAgent()
    risk_agent = RiskAgent()

    results = []

    print("\n" + "=" * 90)
    print(f"{'Case ID':<18} | {'Track':<9} | {'Unc Status':<10} | {'Exp Route':<10} | {'Risk Sev':<9} | {'Exp Risk':<9} | {'Notes'}")
    print("-" * 90)

    for fname in case_files:
        fpath = cbt_dir / fname
        if not fpath.exists():
            continue

        data = json.loads(fpath.read_text(encoding="utf-8"))
        case_id = data["case_id"]
        track = data.get("track", "ordinary")
        ambig_profile = data.get("ambiguous_context", {})
        expected_route = data.get("expected_route", "CLEAR")
        expected_risk = data.get("risk_level", "LOW")
        missing_fields = data.get("missing_information", [])

        # Default client utterance for test
        current_msg = "I feel work and life pressures have been very heavy recently, and I don't know what to do."

        ctx = AgentContext(
            case_id=case_id,
            modality="cbt",
            therapy_stage=data.get("therapy_stage"),
            full_profile=ambig_profile,
            current_message=current_msg,
            metadata={"missing_information": missing_fields},
        )

        # 1. Memory Agent
        mem_msg = mem_agent.run(ctx)
        ctx.memory_output = mem_msg.payload

        # 2. State Agent
        state_msg = state_agent.run(ctx)
        ctx.state_output = state_msg.payload

        # 3. Uncertainty Agent
        unc_msg = unc_agent.run(ctx)
        ctx.uncertainty_output = unc_msg.payload

        # 4. Risk Agent
        risk_msg = risk_agent.run(ctx)
        ctx.risk_output = risk_msg.payload

        unc_status = unc_msg.payload.get("status")
        risk_sev = risk_msg.payload.get("severity")

        # Check comparisons
        # Note: on redacted cases, Uncertainty status may detect UNCERTAIN where expected_route (from full GT) was CLEAR.
        unc_match = (unc_status == expected_route)
        risk_match = (risk_sev == expected_risk)

        notes = []
        if unc_status != expected_route:
            notes.append(f"Unc discrepancy ({unc_status} vs GT:{expected_route})")
        if risk_sev != expected_risk:
            notes.append(f"Risk discrepancy ({risk_sev} vs GT:{expected_risk})")
        if not notes:
            notes.append("Match")

        print(f"{case_id:<18} | {track:<9} | {unc_status:<10} | {expected_route:<10} | {risk_sev:<9} | {expected_risk:<9} | {'; '.join(notes)}")

        results.append({
            "case_id": case_id,
            "track": track,
            "unc_status": unc_status,
            "expected_route": expected_route,
            "risk_sev": risk_sev,
            "expected_risk": expected_risk,
            "unc_match": unc_match,
            "risk_match": risk_match,
            "missing_detected": bool(unc_msg.missing_information),
            "evidence_signals": risk_msg.payload.get("evidence", []),
        })

    print("=" * 90)
    return results


if __name__ == "__main__":
    test_empty_and_robustness()
    test_clear_full_profile()
    test_crisis_signal_detection()
    test_ambiguous_and_contradictory_detection()
    run_benchmark_pipeline_tests()
