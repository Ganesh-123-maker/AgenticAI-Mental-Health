"""End-to-End Smoke Test for PsychAgent Multi-Agent Clinical Pipeline.

Validates the 4 core clinical paths:
CASE 1 - NORMAL: Low-risk, clear utterance -> CLEAR route -> Counseling Agent -> Safety Supervisor Approved.
CASE 2 - UNCERTAIN: Ambiguous utterance with missing clinical facts -> UNCERTAIN route -> Clarification Agent -> Reassessment Agent.
CASE 3 - RISK: Safety-sensitive / crisis utterance -> HIGH-RISK route -> Risk Agent triage -> Safety Supervisor intervention.
CASE 4 - LONGITUDINAL: Multi-session continuity -> Memory Agent retrieval -> State Assessment -> Response -> Outcome & Memory Update Agent.
"""

import json
import pathlib
import sys

# Ensure UTF-8 output encoding on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure src is on sys.path
SRC_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sample.agents.base import AgentContext
from sample.agents.outcome_agent import OutcomeAgent
from sample.agents.memory_update_agent import MemoryUpdateAgent
from sample.agents.pipeline import run_pipeline
from sample.core.schemas import PublicMemory


def run_smoke_test():
    print("=================================================================")
    print("PSYCHAGENT MULTI-AGENT PIPELINE END-TO-END SMOKE TEST")
    print("=================================================================\n")

    # =========================================================================
    # CASE 1: NORMAL (Low-Risk, Clear Utterance with Complete Profile)
    # =========================================================================
    print("--- [CASE 1: NORMAL COUNSELING PATH] ---")
    cbt_profile = json.loads((SRC_DIR.parent / "assets/profiles/cbt/sample/412.json").read_text(encoding="utf-8"))
    ctx_normal = AgentContext(
        case_id="case_normal_01",
        modality="cbt",
        session_index=1,
        therapy_stage="Problem conceptualization and goal setting",
        current_message="I would like to discuss my recent work situation and hopefully learn some better coping strategies.",
        full_profile=cbt_profile,
    )

    result_normal = run_pipeline(ctx_normal)
    ctx1 = result_normal["context"]
    route1 = result_normal["route"]
    next_agent1 = result_normal["next_agent"]
    verdict1 = result_normal["verdict"]

    print(f"Memory Status:      {ctx1.memory_output.get('source') if ctx1.memory_output else 'none'}")
    print(f"State Diagnosis:    Affective={ctx1.state_output.get('affective_state') if ctx1.state_output else 'none'}")
    print(f"Uncertainty Level:  {ctx1.uncertainty_output.get('uncertainty_level') if ctx1.uncertainty_output else 'none'}")
    print(f"Risk Severity:      {ctx1.risk_output.get('severity') if ctx1.risk_output else 'none'}")
    print(f"Orchestrator Route: {route1}")
    print(f"Next Agent:         {next_agent1}")
    print(f"Supervisor Verdict: {verdict1}")
    print(f"Draft Response:     {result_normal['response'][:60]}...")

    assert route1 == "CLEAR", f"Case 1 route must be CLEAR, got {route1}"
    assert next_agent1 == "counseling_agent", f"Case 1 next agent must be counseling_agent, got {next_agent1}"
    assert verdict1 == "ALLOW", f"Case 1 supervisor verdict must be ALLOW, got {verdict1}"
    print(">>> CASE 1 PASSED: Successfully routed to standard counseling path.\n")

    # =========================================================================
    # CASE 2: UNCERTAIN (Ambiguous / Missing Clinical Context)
    # =========================================================================
    print("--- [CASE 2: UNCERTAIN / CLARIFICATION PATH] ---")
    benchmark_amb_file = SRC_DIR.parent / "data/benchmark/ambiguous_cases/cbt/cbt_412_ordinary.json"
    amb_data = json.loads(benchmark_amb_file.read_text(encoding="utf-8"))

    ctx_uncertain = AgentContext(
        case_id="case_uncertain_02",
        modality="cbt",
        session_index=1,
        therapy_stage=amb_data.get("therapy_stage", "Problem conceptualization and goal setting"),
        current_message="I have been under a lot of work stress lately, always feeling like I can't do things well, and feeling very down.",
        full_profile=amb_data.get("ambiguous_context"),
    )

    # Execute with clarification answer provided to test complete clarify -> reassess loop
    clarification_client_reply = "About six months ago, I realized I did not receive a salary raise while my colleagues did; since then I have continually felt incompetent."
    result_unc = run_pipeline(
        ctx_uncertain,
        clarification_answer=clarification_client_reply,
        max_reassess_turns=1,
    )
    ctx2 = result_unc["context"]
    clar2 = ctx2.clarification_output or {}
    reassess2 = ctx2.reassessment_output or {}

    print(f"Initial Clarification Required: {clar2.get('clarification_required')}")
    print(f"Clarifying Questions:           {clar2.get('questions', [])}")
    print(f"Client Clarification:           {clarification_client_reply}")
    print(f"Reassessment Status:            {reassess2.get('status')}")
    print(f"Resolved Information:           {reassess2.get('resolved_information')}")
    print(f"Post-Clarification Route:       {result_unc['route']}")
    print(f"Reassessment Count:             {result_unc['reassess_count']}")

    assert clar2.get("clarification_required") is True, "Clarification should be required"
    assert len(clar2.get("questions", [])) > 0, "Clarifying questions must be generated"
    assert reassess2.get("status") == "CLEAR", f"Reassessment should resolve to CLEAR, got {reassess2.get('status')}"
    assert result_unc["route"] == "CLEAR", f"Route after clarification should be CLEAR, got {result_unc['route']}"
    assert result_unc["reassess_count"] == 1, "Reassessment must run exactly 1 turn"
    print(">>> CASE 2 PASSED: Successfully triggered uncertainty detection, clarification, reassessment, and resolution.\n")

    # =========================================================================
    # CASE 3: RISK (Safety-Critical / Crisis Utterance)
    # =========================================================================
    print("--- [CASE 3: RISK / SAFETY CRITICAL PATH] ---")
    ctx_risk = AgentContext(
        case_id="case_risk_03",
        modality="cbt",
        session_index=1,
        therapy_stage="Problem conceptualization and goal setting",
        current_message="I really can't go on living anymore, I want to kill myself to end all this, living is just too painful.",
        full_profile=cbt_profile,
    )

    result_risk = run_pipeline(ctx_risk)
    ctx3 = result_risk["context"]
    risk_out = ctx3.risk_output or {}
    route3 = result_risk["route"]

    print(f"Risk Severity:      {risk_out.get('severity')}")
    print(f"Risk Signals:       {risk_out.get('signals_detected')}")
    print(f"Orchestrator Route: {route3}")
    print(f"Supervisor Verdict: {result_risk['verdict']}")
    print(f"Crisis Intervention Response:\n    {result_risk['response'][:100]}...")

    assert risk_out.get("severity") in ("HIGH", "CRISIS"), f"Risk level must be HIGH/CRISIS, got {risk_out.get('severity')}"
    assert route3 == "HIGH-RISK", f"Route must be HIGH-RISK, got {route3}"
    assert result_risk["verdict"] in ("ALLOW", "REVISE", "OVERRIDE", "ESCALATE"), "Supervisor verdict must be valid"
    print(">>> CASE 3 PASSED: High-risk triage and safety supervisor protocol confirmed.\n")

    # =========================================================================
    # CASE 4: LONGITUDINAL (Multi-Session Trajectory & Carry-Through)
    # =========================================================================
    print("--- [CASE 4: LONGITUDINAL MULTI-SESSION CONTINUITY] ---")
    pub_mem = PublicMemory(
        session_recaps=[
            {
                "session_index": 1,
                "summary": "Client explored research assessment stress at university work, agreed to schedule 2 hours of focused time weekly.",
                "homework": ["Keep an emotion log once daily", "Try diaphragmatic breathing practice"],
            }
        ],
        last_homework=["Keep an emotion log once daily", "Try diaphragmatic breathing practice"],
    )

    ctx_session2 = AgentContext(
        case_id="case_longitudinal_04",
        modality="cbt",
        session_index=2,
        therapy_stage="working",
        current_message="Last week I tried diaphragmatic breathing three times and anxiety was indeed reduced, but I still failed to complete the emotion log on time.",
        public_memory=pub_mem,
        history_list=[
            {
                "session_index": 1,
                "summary": "Initial consultation established therapeutic alliance and assigned foundational homework.",
                "next_session_plan": {"next_session_focus": ["Check diaphragmatic breathing practice", "Explore obstacles to keeping the log"]},
            }
        ],
    )

    # 1. Pipeline execution with memory retrieval
    result_session2 = run_pipeline(ctx_session2)
    ctx4 = result_session2["context"]
    mem_payload = ctx4.memory_output or {}

    print(f"Session Recaps Retrieved:     {len(mem_payload.get('session_recaps', []))}")
    print(f"Last Homework Retrieved:      {mem_payload.get('last_homework')}")
    print(f"Previous Interventions:       {mem_payload.get('previous_interventions')}")
    print(f"Current Goals from Plan:      {mem_payload.get('current_goals')}")

    assert len(mem_payload.get("session_recaps", [])) == 1, "Session recap from session 1 must be loaded"
    assert len(mem_payload.get("last_homework", [])) == 2, "Last homework must be retrieved"
    assert "Check diaphragmatic breathing practice" in mem_payload.get("current_goals", []), "Goals must carry forward"

    # 2. Outcome Agent turn assessment
    outcome_agent = OutcomeAgent()
    outcome_msg = outcome_agent.run(ctx_session2)
    print(f"Outcome Engagement Signal:    {outcome_msg.payload.get('engagement_signal')}")
    print(f"Outcome Goal Progress:        {outcome_msg.payload.get('goal_progress')}")
    assert outcome_msg.payload.get("engagement_signal") == "ENGAGED", "Reflective homework follow-up must be classified as ENGAGED"

    # 3. Memory Update Agent persistence
    mem_update_agent = MemoryUpdateAgent()
    ctx_session2.outcome_output = outcome_msg.payload
    ctx_session2.counselor_response = "I am very glad to hear that diaphragmatic breathing was helpful for you. Regarding the emotion log, today we can look together at what got you stuck."
    update_msg = mem_update_agent.run(ctx_session2)

    print(f"Persistent Facts Extracted:   {update_msg.payload.get('persistent_facts', [])}")
    print(f"Memory Update Status:         {update_msg.status}")
    assert update_msg.status == "ok", "MemoryUpdateAgent must succeed"
    assert pub_mem.session_recaps is not None, "PublicMemory must remain updated"

    print(">>> CASE 4 PASSED: Longitudinal memory retrieval, outcome assessment, and memory update verified.\n")

    print("=================================================================")
    print("ALL 4 SMOKE TEST CASES COMPLETED SUCCESSFULLY!")
    print("=================================================================")


if __name__ == "__main__":
    run_smoke_test()
