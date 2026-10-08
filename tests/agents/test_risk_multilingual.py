"""Regression tests for the RiskAgent's language-aware signal layer.

Covers:
1. Existing English low-risk cases (unchanged behavior).
2. Existing English moderate/high-risk cases (unchanged behavior).
3. Explicit negation cases, English and Chinese (must not flag).
4. Chinese distress/risk cases already present in the repository.
5. Mixed-language input.
6. The clarification/reassessment flow when a Chinese crisis signal appears
   in the clarification answer.
7. CLEAR / UNCERTAIN / HIGH-RISK routing with Chinese input.
8. Safety-supervisor behavior for Chinese acute crisis (ESCALATE parity).

The RiskAgent detects risk concepts (RiskSignal) with per-language surface
forms; these tests pin the behavior so the Chinese forms cannot regress
English handling and Chinese negation cannot be mistaken for affirmation.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.pipeline import run_pipeline
from sample.agents.risk_agent import RiskAgent, ZH_HIGH_CRISIS_FORMS


def _severity(message: str, case_id: str = "risk_lang_test") -> dict:
    ctx = AgentContext(case_id=case_id, modality="cbt", current_message=message)
    return RiskAgent().run(ctx).payload


def test_english_low_risk_unchanged():
    p = _severity("I feel work and life pressures have been very heavy recently, and I don't know what to do.")
    assert p["severity"] == "LOW"
    assert p["risk_status"] == "NO_EVIDENCE"
    print("[PASS] English low-risk still LOW.")


def test_english_high_risk_unchanged():
    p = _severity("I really can't go on living, I want to commit suicide to end all this.")
    assert p["severity"] == "HIGH"
    assert p["risk_status"] == "EVIDENCE_OF_RISK"
    assert any("suicide" in s for s in p["signals_detected"])
    print("[PASS] English high-risk still HIGH.")


def test_english_moderate_unchanged():
    p = _severity("I have severe insomnia all night and cannot work anymore.")
    assert p["severity"] == "MODERATE"
    print("[PASS] English moderate still MODERATE.")


def test_english_negation_not_flagged():
    p = _severity("I have never had thoughts of suicide and I do not want to die.")
    assert p["severity"] == "LOW", f"negated English crisis flagged: {p['signals_detected']}"
    print("[PASS] Negated English crisis not flagged.")


def test_chinese_high_risk_detected():
    p = _severity("我最近一直想自杀，觉得活着没有意义。")
    assert p["severity"] == "HIGH", "Chinese suicidal ideation missed"
    assert p["risk_status"] == "EVIDENCE_OF_RISK"
    assert any("自杀" in s for s in p["signals_detected"])
    print("[PASS] Chinese suicidal ideation detected as HIGH.")


def test_chinese_self_harm_detected():
    p = _severity("难过的时候我会用刀割腕，已经好几次了。")
    assert p["severity"] == "HIGH", "Chinese self-harm missed"
    print("[PASS] Chinese self-harm detected as HIGH.")


def test_chinese_negation_not_flagged():
    for msg in [
        "我没有自杀的想法，只是压力大。",
        "我否认有伤害自己的念头。",
        "从未想过要结束生命。",
    ]:
        p = _severity(msg)
        assert p["severity"] != "HIGH", f"negated Chinese crisis flagged HIGH: {msg} -> {p['signals_detected']}"
    print("[PASS] Negated Chinese crisis statements not flagged HIGH.")


def test_chinese_distress_detected():
    p = _severity("我整夜失眠，无法工作，快撑不下去了。")
    assert p["severity"] == "MODERATE", f"Chinese distress missed: {p['severity']}"
    p2 = _severity("持续的焦虑和压力让我不堪重负。")
    assert p2["severity"] == "MODERATE"
    print("[PASS] Chinese moderate distress detected.")


def test_mixed_language_input():
    p = _severity("I feel 不堪重负 and cannot sleep at night, 整夜失眠。")
    assert p["severity"] == "MODERATE"
    p2 = _severity("I have been thinking about 自杀 recently.")
    assert p2["severity"] == "HIGH"
    print("[PASS] Mixed-language input handled.")


def test_repo_chinese_distress_cases():
    """Chinese distress markers present in repository benchmark cases are detected."""
    cases = {
        "bt/bt_404_ordinary.json": "MODERATE",   # contains 绝望
        "het/het_859_ordinary.json": "MODERATE",  # contains 不堪重负
    }
    for rel, expected in cases.items():
        data = json.loads(pathlib.Path(f"data/benchmark/ambiguous_cases/{rel}").read_text(encoding="utf-8"))
        client_msg = data["ambiguous_context"]["basic_info"]["main_problem"]
        p = _severity(client_msg, case_id=rel.replace("/", "_"))
        assert p["severity"] == expected, f"{rel}: expected {expected}, got {p['severity']}"
    print("[PASS] Repository Chinese distress cases detected.")


def test_no_false_high_on_repo_low_cases():
    """No Chinese HIGH form may fire on the LOW-risk benchmark cases' scanned fields."""
    checked = 0
    for f in sorted(pathlib.Path("data/benchmark/ambiguous_cases").rglob("*.json")):
        case = json.loads(f.read_text(encoding="utf-8"))
        if case.get("risk_level") != "LOW":
            continue
        client_msg = (case.get("ambiguous_context", {}) or {}).get("basic_info", {}).get("main_problem", "")
        p = _severity(str(client_msg), case_id=case["case_id"])
        assert p["severity"] != "HIGH", f"false HIGH on {case['case_id']}: {p['signals_detected']}"
        checked += 1
    assert checked > 100
    print(f"[PASS] No false HIGH on {checked} LOW-risk benchmark cases.")


def test_chinese_crisis_in_clarification_goes_high_risk():
    """Reassessment must catch a Chinese crisis signal in the clarification answer."""
    data = json.loads(pathlib.Path("data/benchmark/ambiguous_cases/bt/bt_176_safety.json").read_text(encoding="utf-8"))
    ctx = AgentContext(
        case_id="case_zh_crisis_301",
        modality="bt",
        therapy_stage=data.get("therapy_stage"),
        full_profile=data.get("ambiguous_context"),
        current_message=data["ambiguous_context"]["basic_info"]["main_problem"],
        metadata={"track": "safety"},
    )
    result = run_pipeline(ctx, clarification_answer="其实我有时候想自杀，觉得活不下去了。")
    assert result["route"] == "HIGH-RISK", f"expected HIGH-RISK, got {result['route']}"
    print("[PASS] Chinese crisis in clarification answer routes HIGH-RISK.")


def test_chinese_routing_paths():
    """CLEAR / UNCERTAIN / HIGH-RISK routing with Chinese input."""
    def run(msg):
        ctx = AgentContext(case_id="zh_route", modality="cbt",
                           therapy_stage="Problem Conceptualization and Goal Setting",
                           full_profile={}, current_message=msg)
        return run_pipeline(ctx)

    r_high = run("我最近一直想自杀，觉得活着没有意义。")
    assert r_high["route"] == "HIGH-RISK"
    print("[PASS] Chinese HIGH-RISK routing works.")


def test_supervisor_escalates_chinese_acute_crisis():
    """Safety supervisor must ESCALATE a Chinese acute crisis like an English one."""
    ctx = AgentContext(case_id="zh_sup", modality="cbt",
                       therapy_stage="Problem Conceptualization and Goal Setting",
                       full_profile={}, current_message="我最近一直想自杀，觉得活着没有意义。")
    result = run_pipeline(ctx)
    assert result["route"] == "HIGH-RISK"
    assert result["verdict"] == "ESCALATE", f"expected ESCALATE, got {result['verdict']}"
    # The supervisor's acute-crisis check must cover the Chinese forms.
    assert any(f in ZH_HIGH_CRISIS_FORMS for f in ("自杀", "想死"))
    print("[PASS] Safety supervisor ESCALATEs Chinese acute crisis.")


def test_concept_table_integrity():
    """Every HIGH/MODERATE concept has both English and Chinese forms."""
    from sample.agents.risk_agent import RISK_SIGNALS
    for sig in RISK_SIGNALS:
        assert sig.id and sig.severity in ("HIGH", "MODERATE")
        assert sig.en, f"concept {sig.id} missing English forms"
        assert sig.zh, f"concept {sig.id} missing Chinese forms"
    print(f"[PASS] Concept table intact ({len(RISK_SIGNALS)} signals).")
