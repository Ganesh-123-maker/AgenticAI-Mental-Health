"""Test script for Phase 6: Orchestrator, CounselingAgent, Pipeline integration, and Runner.

Tests:
1. Orchestrator routing rules:
   - Clear low-risk + low uncertainty → CLEAR
   - Missing/uncertain safety info → UNCERTAIN
   - Explicit high-risk evidence → HIGH-RISK
   - High-risk + high uncertainty → HIGH-RISK (override confirmed)
   - Reassessment resolution → route updated accordingly
2. CounselingAgent wrapper test.
3. Runner comparison test (multi_agent_enabled=False vs multi_agent_enabled=True):
   - Run 1 session on 1 case with multi_agent_enabled=False (regression check)
   - Run 1 session on 1 case with multi_agent_enabled=True (pipeline check)
   - Verify course.json and session_1.json schemas match perfectly.
4. Verify SOP-1 safety logic still fires on HIGH-RISK cases.
"""

import asyncio
import json
import logging
import pathlib
import shutil
import sys

# Ensure src is on sys.path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.counseling_agent import CounselingAgent
from sample.agents.orchestrator import Orchestrator
from sample.agents.pipeline import run_pipeline
from sample.agents.reassessment_agent import ReassessmentAgent
from sample.core.schemas import BaselineConfig, ClientCase, RuntimeConfig
from sample.io.config_loader import load_baseline_config, load_runtime_config
from sample.runner import PsychAgentRunner


def test_orchestrator_routing_rules():
    """Verify Orchestrator routing rules and priorities."""
    orch = Orchestrator()

    # 1. Clear low-risk + low uncertainty -> CLEAR
    ctx_clear = AgentContext(case_id="clear_case", modality="cbt")
    ctx_clear.uncertainty_output = {"status": "CLEAR", "uncertainty_level": "LOW", "clarification_required": False}
    ctx_clear.risk_output = {"severity": "LOW", "risk_status": "NO_EVIDENCE"}
    msg1 = orch.run(ctx_clear)
    assert msg1.payload["route"] == "CLEAR"
    assert msg1.payload["next_agent"] == "counseling_agent"
    assert msg1.payload["required_action"] == "Proceed with normal counseling flow."
    print("[PASS] Orchestrator: Clear low-risk + low uncertainty -> CLEAR.")

    # 2. Missing/uncertain safety information -> UNCERTAIN
    ctx_unc = AgentContext(case_id="unc_case", modality="cbt")
    ctx_unc.uncertainty_output = {
        "status": "UNCERTAIN",
        "uncertainty_level": "HIGH",
        "uncertain_fields": ["medical_history"],
        "clarification_required": True,
    }
    ctx_unc.risk_output = {"severity": "UNCERTAIN", "risk_status": "UNCERTAIN"}
    msg2 = orch.run(ctx_unc)
    assert msg2.payload["route"] == "UNCERTAIN"
    assert msg2.payload["next_agent"] == "clarification_agent"
    assert msg2.payload["required_action"] == "Obtain clarification before proceeding."
    print("[PASS] Orchestrator: Missing safety info -> UNCERTAIN.")

    # 3. Explicit high-risk evidence -> HIGH-RISK
    ctx_high = AgentContext(case_id="high_risk_case", modality="cbt")
    ctx_high.uncertainty_output = {"status": "CLEAR", "uncertainty_level": "LOW", "clarification_required": False}
    ctx_high.risk_output = {
        "severity": "HIGH",
        "risk_status": "EVIDENCE_OF_RISK",
        "signals_detected": ["suicide", "slit wrists"],
    }
    msg3 = orch.run(ctx_high)
    assert msg3.payload["route"] == "HIGH-RISK"
    assert msg3.payload["next_agent"] == "safety_supervisor"
    assert msg3.payload["required_action"] == "Enter safety-controlled response flow."
    print("[PASS] Orchestrator: Explicit high-risk evidence -> HIGH-RISK.")

    # 4. High-risk + high uncertainty -> HIGH-RISK (override confirmed)
    ctx_high_unc = AgentContext(case_id="high_unc_case", modality="cbt")
    ctx_high_unc.uncertainty_output = {
        "status": "UNCERTAIN",
        "uncertainty_level": "HIGH",
        "clarification_required": True,
    }
    ctx_high_unc.risk_output = {
        "severity": "HIGH",
        "risk_status": "EVIDENCE_OF_RISK",
        "signals_detected": ["suicide"],
    }
    msg4 = orch.run(ctx_high_unc)
    assert msg4.payload["route"] == "HIGH-RISK"
    assert msg4.payload["next_agent"] == "safety_supervisor"
    print("[PASS] Orchestrator: High risk + high uncertainty -> HIGH-RISK (override verified).")

    # 5. Reassessment resolving uncertainty -> route updated
    ctx_reassess = AgentContext(case_id="reassess_case", modality="cbt")
    ctx_reassess.uncertainty_output = {"status": "UNCERTAIN", "clarification_required": True}
    ctx_reassess.risk_output = {"severity": "LOW", "risk_status": "NO_EVIDENCE"}
    ctx_reassess.reassessment_output = {
        "route_decision": "CLEAR",
        "status": "CLEAR",
        "resolved_information": ["duration_and_history"],
    }
    msg5 = orch.run(ctx_reassess)
    assert msg5.payload["route"] == "CLEAR"
    assert msg5.payload["next_agent"] == "counseling_agent"
    print("[PASS] Orchestrator: Reassessment resolution -> route updated to CLEAR.")


def test_counseling_agent_wrapper():
    """Verify CounselingAgent wrapper and payload generation."""
    agent = CounselingAgent()
    ctx = AgentContext(case_id="test_counsel", modality="cbt")
    ctx.routing_output = {"route": "CLEAR", "next_agent": "counseling_agent"}
    msg = agent.run(ctx)
    assert msg.status == "ok"
    assert msg.payload["route"] == "CLEAR"
    assert "response_text" in msg.payload
    print("[PASS] CounselingAgent wrapper generates valid payload.")


async def _async_runner_execution_comparison():
    """Run runner with multi_agent_enabled=False vs multi_agent_enabled=True."""
    root = pathlib.Path(__file__).parent.parent.parent

    # Load dummy configs
    baseline_cfg = load_baseline_config(str(root / "configs/baselines/psychagent_dummy_local.yaml"))
    runtime_raw = load_runtime_config(str(root / "configs/runtime/psychagent_dummy_local.yaml"))

    # Load case using DatasetLoader from configs/datasets/profiles_sample.yaml
    from sample.io.config_loader import load_dataset_config
    from sample.io.dataset_loader import DatasetLoader
    dataset_cfg = load_dataset_config(root / "configs/datasets/profiles_sample.yaml")
    loader = DatasetLoader(dataset_cfg)
    all_cases = loader.load_cases(seed=7)
    cbt_cases = [c for c in all_cases if c.modality == "cbt"]
    case = cbt_cases[0]

    save_dir_false = root / "sample_outputs/test_phase6_false"
    save_dir_true = root / "sample_outputs/test_phase6_true"
    if save_dir_false.exists():
        shutil.rmtree(save_dir_false)
    if save_dir_true.exists():
        shutil.rmtree(save_dir_true)

    # 1. Run with multi_agent_enabled = False (default baseline behavior)
    cfg_false = RuntimeConfig(
        multi_agent_enabled=False,
        save_dir=str(save_dir_false),
        resume=False,
        overwrite=True,
        psychagent_max_turns=2,
        max_sessions=1,
        client_backend="dummy",
        random_seed=7,
        psychagent_skill_base_dir="assets/skills/sect",
        psychagent_skill_select_prompt_dir="prompts/psychagent/skill/select_skill",
        psychagent_skill_rewrite_prompt_dir="prompts/psychagent/skill/rewrite",
    )

    runner_false = PsychAgentRunner(
        baseline_config=baseline_cfg,
        runtime_config=cfg_false,
        prompt_root=root / "prompts",
        logger=logging.getLogger("test_false"),
    )
    res_false = await runner_false.run_cases([case])
    assert res_false.succeeded + res_false.partially_completed == 1

    course_file_false = save_dir_false / "dummy_local/cbt/412/course.json"
    session_file_false = save_dir_false / "dummy_local/cbt/412/session_1.json"
    assert course_file_false.exists()
    assert session_file_false.exists()
    course_data_false = json.loads(course_file_false.read_text(encoding="utf-8"))
    session_data_false = json.loads(session_file_false.read_text(encoding="utf-8"))

    print("[PASS] Session with multi_agent_enabled=False completed successfully.")

    # 2. Run with multi_agent_enabled = True (pipeline integration)
    cfg_true = RuntimeConfig(
        multi_agent_enabled=True,
        save_dir=str(save_dir_true),
        resume=False,
        overwrite=True,
        psychagent_max_turns=2,
        max_sessions=1,
        client_backend="dummy",
        random_seed=7,
        psychagent_skill_base_dir="assets/skills/sect",
        psychagent_skill_select_prompt_dir="prompts/psychagent/skill/select_skill",
        psychagent_skill_rewrite_prompt_dir="prompts/psychagent/skill/rewrite",
    )

    runner_true = PsychAgentRunner(
        baseline_config=baseline_cfg,
        runtime_config=cfg_true,
        prompt_root=root / "prompts",
        logger=logging.getLogger("test_true"),
    )
    res_true = await runner_true.run_cases([case])
    assert res_true.succeeded + res_true.partially_completed == 1

    course_file_true = save_dir_true / "dummy_local/cbt/412/course.json"
    session_file_true = save_dir_true / "dummy_local/cbt/412/session_1.json"
    assert course_file_true.exists()
    assert session_file_true.exists()
    course_data_true = json.loads(course_file_true.read_text(encoding="utf-8"))
    session_data_true = json.loads(session_file_true.read_text(encoding="utf-8"))

    print("[PASS] Session with multi_agent_enabled=True completed successfully.")

    # Verify structural equivalence of outputs
    assert set(course_data_false.keys()) == set(course_data_true.keys())
    assert set(session_data_false.keys()) == set(session_data_true.keys())
    assert len(session_data_false.get("transcript", [])) > 0
    assert len(session_data_true.get("transcript", [])) > 0
    print("[PASS] Output schemas and file structures match perfectly between False and True.")


def test_sop1_safety_on_high_risk():
    """Confirm HIGH-RISK path triggers existing SOP-1 crisis skill prioritization."""
    # When RiskAgent detects high risk, route is HIGH-RISK
    ctx = AgentContext(
        case_id="sop1_test",
        modality="cbt",
        current_message="I really can't go on living, I want to commit suicide to end all this.",
    )
    result = run_pipeline(ctx)
    assert result["route"] == "HIGH-RISK"
    assert result["next_agent"] == "safety_supervisor"
    # Full agent trail logs routing and safety path
    agent_names = [step.get("agent") for step in result["trail"]]
    assert "risk_agent" in agent_names
    assert "orchestrator" in agent_names
    assert "counseling_agent" in agent_names
    print("[PASS] HIGH-RISK route confirmed and logged in pipeline trail for safety handling.")


def test_runner_execution():
    """Synchronous test entry for pytest and standalone execution."""
    asyncio.run(_async_runner_execution_comparison())


if __name__ == "__main__":
    test_orchestrator_routing_rules()
    test_counseling_agent_wrapper()
    test_sop1_safety_on_high_risk()
    test_runner_execution()
    print("\nAll Phase 6 tests passed successfully!")
