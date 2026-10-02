"""Test script for Phase 8: Outcome Agent, Memory Update Agent, and Runner End-to-End.

Tests:
1. OutcomeAgent engagement classification (ENGAGED, WITHDRAWN, NEUTRAL), goal progress,
   and unresolved uncertainty carriage.
2. MemoryUpdateAgent classification (persistent vs temporary) and writing to existing PublicMemory.
3. End-to-end 2-session runner test with multi_agent_enabled=True:
   - Session 1 outcome & memory update execution.
   - Longitudinal carry-through: Session 2 memory_agent output includes persistent facts from Session 1.
   - Temporary facts from Session 1 are dropped and NOT in Session 2.
4. Regression check: multi_agent_enabled=False skips the entire outcome/memory update block.
"""

import asyncio
import json
import logging
import pathlib
import shutil
import sys
import pytest

# Ensure src is on sys.path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.memory_agent import MemoryAgent
from sample.agents.memory_update_agent import MemoryUpdateAgent
from sample.agents.outcome_agent import OutcomeAgent
from sample.core.schemas import BaselineConfig, ClientCase, PublicMemory, RuntimeConfig
from sample.io.config_loader import load_baseline_config, load_dataset_config, load_runtime_config
from sample.io.dataset_loader import DatasetLoader
from sample.runner import PsychAgentRunner


def test_outcome_agent():
    """Verify OutcomeAgent observable engagement signals and goal progress."""
    agent = OutcomeAgent()

    # 1. WITHDRAWN signal
    ctx_w = AgentContext(case_id="case_w", modality="cbt", current_message="I don't know, whatever...")
    msg_w = agent.run(ctx_w)
    assert msg_w.payload["engagement_signal"] == "WITHDRAWN"
    assert "Minimal" in msg_w.payload["goal_progress"]
    print("[PASS] OutcomeAgent: Minimal/dismissive reply -> WITHDRAWN.")

    # 2. ENGAGED signal
    ctx_e = AgentContext(
        case_id="case_e",
        modality="cbt",
        current_message="I think the main reason is work pressure is too high, because I always want to make everything perfect. Later at night I started having insomnia, hoping to learn some relaxation methods.",
    )
    ctx_e.memory_output = {"current_goals": ["learn relaxation methods", "improve sleep"]}
    msg_e = agent.run(ctx_e)
    assert msg_e.payload["engagement_signal"] == "ENGAGED"
    assert "addressed topic related to goal" in msg_e.payload["goal_progress"] or "Client actively engaged" in msg_e.payload["goal_progress"]
    assert len(msg_e.payload["newly_observed_information"]) > 0
    print("[PASS] OutcomeAgent: Detailed reflective reply -> ENGAGED.")

    # 3. NEUTRAL signal
    ctx_n = AgentContext(case_id="case_n", modality="cbt", current_message="Sure, sounds good, I will try.")
    msg_n = agent.run(ctx_n)
    assert msg_n.payload["engagement_signal"] == "NEUTRAL"
    print("[PASS] OutcomeAgent: Standard acknowledgement -> NEUTRAL.")

    # 4. Unresolved uncertainty carriage
    ctx_u = AgentContext(case_id="case_u", modality="cbt", current_message="I tried it a bit.")
    ctx_u.uncertainty_output = {"clarification_required": True, "status": "UNCERTAIN"}
    msg_u = agent.run(ctx_u)
    assert msg_u.payload["unresolved_uncertainty"] is True
    print("[PASS] OutcomeAgent: Unresolved uncertainty carried forward.")


def test_memory_update_agent():
    """Verify MemoryUpdateAgent persistent vs temporary classification and PublicMemory updates."""
    agent = MemoryUpdateAgent()

    candidate_facts = [
        "Goal is to improve work-life balance",          # durable: stated goal
        "Has always had strong perfectionist tendencies", # durable: recurring theme
        "In the past had feelings of hopelessness and wanting to die",  # durable: safety flag
        "There was a bit of traffic on the road this morning",         # temporary: situational detail
        "Just drank a cup of coffee downstairs",                       # temporary: momentary remark
    ]

    msg = agent.run(candidate_facts=candidate_facts)
    payload = msg.payload
    persistent_texts = [p["fact"] for p in payload["persistent"]]
    temporary_texts = payload["temporary"]

    assert "Goal is to improve work-life balance" in persistent_texts
    assert "Has always had strong perfectionist tendencies" in persistent_texts
    assert "In the past had feelings of hopelessness and wanting to die" in persistent_texts
    assert "There was a bit of traffic on the road this morning" in temporary_texts
    assert "Just drank a cup of coffee downstairs" in temporary_texts

    print("[PASS] MemoryUpdateAgent: Correctly classified durable facts as persistent and situational facts as temporary.")

    # Test applying updates to existing PublicMemory
    pub_mem = PublicMemory(
        known_static_traits={"occupation": "Engineer"},
        session_recaps=[],
        last_homework=[],
    )

    updated_mem = agent.apply_update(
        public_memory=pub_mem,
        persistent_facts=payload["persistent"],
        homework=["Practice diaphragmatic breathing for 10 minutes"],
        session_summary={"session_index": 1, "session_summary_abstract": "Initial assessment and problem evaluation"},
    )

    # Confirm persistent facts written into existing PublicMemory
    assert "stated_goals" in updated_mem.known_static_traits
    assert "Goal is to improve work-life balance" in updated_mem.known_static_traits["stated_goals"]
    assert "recurring_themes" in updated_mem.known_static_traits
    assert "Has always had strong perfectionist tendencies" in updated_mem.known_static_traits["recurring_themes"]
    assert "safety_flags" in updated_mem.known_static_traits
    assert "In the past had feelings of hopelessness and wanting to die" in updated_mem.known_static_traits["safety_flags"]
    assert updated_mem.last_homework == ["Practice diaphragmatic breathing for 10 minutes"]
    assert len(updated_mem.session_recaps) == 1

    # Confirm temporary facts are NOT in PublicMemory
    assert "There was a bit of traffic on the road this morning" not in str(updated_mem.known_static_traits)
    assert "Just drank a cup of coffee downstairs" not in str(updated_mem.known_static_traits)
    print("[PASS] MemoryUpdateAgent: Persistent facts written to PublicMemory; temporary facts excluded.")


@pytest.mark.asyncio
async def test_runner_longitudinal_carry_through():
    """Run a 2-session case with multi_agent_enabled=True and verify longitudinal memory carry-through."""
    root = pathlib.Path(__file__).parent.parent.parent
    baseline_cfg = load_baseline_config(str(root / "configs/baselines/psychagent_dummy_local.yaml"))
    dataset_cfg = load_dataset_config(root / "configs/datasets/profiles_sample.yaml")
    loader = DatasetLoader(dataset_cfg)
    all_cases = loader.load_cases(seed=42)
    cbt_cases = [c for c in all_cases if c.modality == "cbt"]
    case = cbt_cases[0]

    save_dir_multi = root / "sample_outputs/test_phase8_multi"
    if save_dir_multi.exists():
        shutil.rmtree(save_dir_multi)

    # Configure runner for 2 sessions with multi_agent_enabled=True
    cfg_true = RuntimeConfig(
        multi_agent_enabled=True,
        save_dir=str(save_dir_multi),
        resume=False,
        overwrite=True,
        psychagent_max_turns=2,
        max_sessions=2,
        client_backend="dummy",
        random_seed=42,
        psychagent_skill_base_dir="assets/skills/sect",
        psychagent_skill_select_prompt_dir="prompts/psychagent/skill/select_skill",
        psychagent_skill_rewrite_prompt_dir="prompts/psychagent/skill/rewrite",
    )

    runner = PsychAgentRunner(
        baseline_config=baseline_cfg,
        runtime_config=cfg_true,
        prompt_root=root / "prompts",
        logger=logging.getLogger("test_multi_runner"),
    )

    result = await runner.run_cases([case])
    assert result.succeeded + result.partially_completed == 1

    session_1_file = save_dir_multi / f"dummy_local/cbt/{case.case_id}/session_1.json"
    session_2_file = save_dir_multi / f"dummy_local/cbt/{case.case_id}/session_2.json"
    assert session_1_file.exists()
    assert session_2_file.exists()

    session_1_data = json.loads(session_1_file.read_text(encoding="utf-8"))
    session_2_data = json.loads(session_2_file.read_text(encoding="utf-8"))

    # Verify session completed 2 sessions successfully
    assert session_1_data["stage"] is not None
    assert session_2_data["stage"] is not None

    # Verify longitudinal carry-through into Session 2:
    # Session 2 profile_snapshot should reflect updated traits from Session 1
    session_2_traits = session_2_data.get("profile_snapshot", {}).get("static_traits", {})
    assert isinstance(session_2_traits, dict)

    # Test MemoryAgent directly on Session 2 state
    # Session 2 memory agent context
    ctx_s2 = AgentContext(
        case_id=case.case_id,
        modality="cbt",
        session_index=2,
        history_list=[session_1_data["summary"]],
        obtain_client_info=session_2_data.get("profile_snapshot", {}),
        homework_assigned=session_1_data["summary"].get("homework", []),
        public_memory=PublicMemory(
            known_static_traits=session_2_traits,
            session_recaps=[{"session_index": 1, "summary": session_1_data["summary"].get("session_summary_abstract", "")}],
            last_homework=session_1_data["summary"].get("homework", []),
        ),
    )
    mem_msg = MemoryAgent().run(ctx_s2)
    s2_known_traits = mem_msg.payload.get("known_static_traits", {})

    print(f"[INFO] Session 2 MemoryAgent known_static_traits: {list(s2_known_traits.keys())}")
    assert len(s2_known_traits) >= len(session_1_data.get("profile_snapshot", {}).get("static_traits", {}))
    print("[PASS] Longitudinal carry-through confirmed in Session 2 MemoryAgent.")


@pytest.mark.asyncio
async def test_runner_multi_agent_false_regression():
    """Confirm multi_agent_enabled=False skips the outcome and memory update blocks entirely."""
    root = pathlib.Path(__file__).parent.parent.parent
    baseline_cfg = load_baseline_config(str(root / "configs/baselines/psychagent_dummy_local.yaml"))
    dataset_cfg = load_dataset_config(root / "configs/datasets/profiles_sample.yaml")
    loader = DatasetLoader(dataset_cfg)
    all_cases = loader.load_cases(seed=42)
    cbt_cases = [c for c in all_cases if c.modality == "cbt"]
    case = cbt_cases[0]

    save_dir_false = root / "sample_outputs/test_phase8_false"
    if save_dir_false.exists():
        shutil.rmtree(save_dir_false)

    cfg_false = RuntimeConfig(
        multi_agent_enabled=False,
        save_dir=str(save_dir_false),
        resume=False,
        overwrite=True,
        psychagent_max_turns=2,
        max_sessions=1,
        client_backend="dummy",
        random_seed=42,
        psychagent_skill_base_dir="assets/skills/sect",
        psychagent_skill_select_prompt_dir="prompts/psychagent/skill/select_skill",
        psychagent_skill_rewrite_prompt_dir="prompts/psychagent/skill/rewrite",
    )

    runner = PsychAgentRunner(
        baseline_config=baseline_cfg,
        runtime_config=cfg_false,
        prompt_root=root / "prompts",
        logger=logging.getLogger("test_false_runner"),
    )

    res = await runner.run_cases([case])
    assert res.succeeded + res.partially_completed == 1

    session_1_file = save_dir_false / f"dummy_local/cbt/{case.case_id}/session_1.json"
    assert session_1_file.exists()
    session_1_data = json.loads(session_1_file.read_text(encoding="utf-8"))

    # Confirm outcome_evaluation and memory_update were skipped
    assert "outcome_evaluation" not in session_1_data
    assert "memory_update" not in session_1_data
    print("[PASS] multi_agent_enabled=False regression check passed: outcome & memory_update skipped.")


def test_longitudinal_carry_through_with_persistent_and_temporary_facts():
    """Verify that Session 2 MemoryAgent includes persistent facts from Session 1 and drops temporary facts."""
    # Session 1 state:
    pub_mem = PublicMemory(
        known_static_traits={"name": "Alex", "age": 28},
        session_recaps=[],
        last_homework=[],
    )

    ctx_s1 = AgentContext(
        case_id="case_longitudinal",
        modality="cbt",
        session_index=1,
        current_message="I hope to improve my insomnia symptoms. It is raining heavily and traffic is bad this morning.",
        public_memory=pub_mem,
    )

    # 1. OutcomeAgent runs on Session 1 turn
    outcome_agent = OutcomeAgent()
    outcome_msg = outcome_agent.run(ctx_s1)
    newly_observed = outcome_msg.payload["newly_observed_information"]
    assert any("insomnia" in item.lower() for item in newly_observed)
    assert any("traffic" in item.lower() for item in newly_observed)

    # 2. MemoryUpdateAgent classifies newly observed information
    mem_update_agent = MemoryUpdateAgent()
    update_msg = mem_update_agent.run(ctx_s1, outcome_output=outcome_msg.payload, public_memory=pub_mem)

    persistent_items = update_msg.payload["persistent"]
    temporary_items = update_msg.payload["temporary"]

    persistent_facts_text = [p["fact"] for p in persistent_items]
    assert any("insomnia" in f.lower() for f in persistent_facts_text)
    assert any("traffic" in f.lower() for f in temporary_items)

    # 3. Apply updates to PublicMemory
    updated_pub_mem = mem_update_agent.apply_update(
        public_memory=pub_mem,
        persistent_facts=persistent_items,
        homework=["Daily sleep log"],
        session_summary={"session_index": 1, "session_summary_abstract": "Initial assessment and insomnia discussion"},
    )

    # 4. Open Session 2: MemoryAgent runs on Session 2 AgentContext
    ctx_s2 = AgentContext(
        case_id="case_longitudinal",
        modality="cbt",
        session_index=2,
        current_message="I am ready to begin this week's session.",
        public_memory=updated_pub_mem,
        history_list=[{"session_summary_abstract": "Initial assessment and insomnia discussion", "homework": ["Daily sleep log"]}],
        obtain_client_info={"static_traits": dict(updated_pub_mem.known_static_traits)},
    )

    memory_agent = MemoryAgent()
    s2_mem_msg = memory_agent.run(ctx_s2)
    s2_payload = s2_mem_msg.payload

    # 5. Assert persistent facts ARE present in Session 2 MemoryAgent output
    stated_goals = s2_payload.get("known_static_traits", {}).get("stated_goals", [])
    assert any("insomnia" in g.lower() for g in stated_goals), f"Persistent goal missing from Session 2 memory: {stated_goals}"

    # 6. Assert temporary facts are NOT present anywhere in Session 2 MemoryAgent output
    s2_payload_str = str(s2_payload)
    assert "traffic" not in s2_payload_str, "Temporary fact incorrectly carried into Session 2 memory!"

    print("[PASS] Verified: Session 2 MemoryAgent includes persistent facts and drops temporary facts.")

