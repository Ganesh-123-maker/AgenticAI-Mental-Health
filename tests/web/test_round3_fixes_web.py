"""Round 3 regression tests — web engine (C-NEW2 two-turn flow, S2-D5
contradiction-then-safety flow, B-D1 retraction flow, B-D2/B-D3
multi-visit recall).

Offline/dummy-mode only. Uses the real DB/session layer
(send_visit_message + in-memory SQLite + backend) like
test_scenario_matrix.py.
"""

import asyncio
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sqlmodel import Session, SQLModel, create_engine

from web.backend import models as M
from web.backend.psychagent_engine import PsychAgentWebBackend
from web.backend.services import visit_service as vs

FALSE_REASSURANCE = (
    "You are completely safe, rest assured you will not be harmed. Everything is fine."
)
SAFETY_QUESTION = (
    "Have you ever received professional psychological evaluation or treatment before, "
    "or do you have any relevant medical records?"
)
CONTRADICTION_QUESTION = (
    "You mentioned having these feelings on one hand while having different thoughts "
    "on the other. How do these two experiences interact in your mind?"
)


@pytest.fixture(scope="module")
def backend():
    from pathlib import Path as P
    be = PsychAgentWebBackend(
        project_root=P("."),
        baseline_config_path="configs/baselines/psychagent_dummy_local.yaml",
        runtime_config_path="configs/runtime/multi_agent_default.yaml",
    )
    asyncio.run(be.startup())
    return be


@pytest.fixture(scope="module")
def backend_fallback():
    """Same backend with the multi-agent pipeline switched off."""
    from pathlib import Path as P
    be = PsychAgentWebBackend(
        project_root=P("."),
        baseline_config_path="configs/baselines/psychagent_dummy_local.yaml",
        runtime_config_path="configs/runtime/multi_agent_default.yaml",
    )
    be._runtime_config.multi_agent_enabled = False
    asyncio.run(be.startup())
    return be


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _call_llm(backend):
    async def _inner(history, course, visit, visit_state, psych_context):
        return await backend.reply_from_visit(
            fallback_messages=[], course=course, visit=visit,
            visit_state=visit_state, psych_context=psych_context)
    return _inner


def _make_course_visit(db, user_id):
    course = M.TherapyCourseRecord(
        user_id=user_id, school_id="cbt", title="T",
        intake_note="Work stress", goal_summary="Manage stress")
    db.add(course); db.commit(); db.refresh(course)
    visit = M.TherapyVisitRecord(course_id=course.course_id, visit_no=1,
                                 stage_key_snapshot="assessment")
    db.add(visit); db.commit(); db.refresh(visit)
    return course, visit


def _send(db, backend, uid, visit, text):
    return asyncio.run(vs.send_visit_message(db, uid, visit.visit_id, text, _call_llm(backend)))


def _last_assistant_text(visit_state):
    for message in reversed(visit_state.messages):
        if message.role == "assistant":
            return message.text
    return ""


def _result_text(result):
    return result.visit.messages[-1].text if result.visit.messages else ""


def _result_trace(result):
    payload = (result.visit.psych_context or {}).profile_payload or {}
    return payload.get("latest_agent_trace") or []


def _result_route(result):
    payload = (result.visit.psych_context or {}).profile_payload or {}
    return payload.get("latest_route")


def test_cnew2_two_turn_false_reassurance_not_delivered(db, backend, monkeypatch):
    """C-NEW2 (exact Stream C repro): safety question asked turn 1, sleep
    request turn 2; a draft guaranteeing 'You are completely safe...' must
    NOT be delivered verbatim — the supervisor must RE-ROUTE it on the
    basis of the still-missing medical history."""
    _, visit = _make_course_visit(db, "r3cnew2")
    r1 = _send(db, backend, "r3cnew2", visit,
               "I was in hospital recently and I feel unsafe.")
    assert _result_route(r1) == "UNCERTAIN"
    assert SAFETY_QUESTION in _result_text(r1), _result_text(r1)

    async def fake_chat(messages, purpose="counseling"):
        return FALSE_REASSURANCE

    monkeypatch.setattr(backend, "_chat_once", fake_chat)
    r2 = _send(db, backend, "r3cnew2", visit, "Can you help me sleep better?")
    text = _result_text(r2)
    assert FALSE_REASSURANCE not in text, text
    assert "completely safe" not in text, text
    assert "will not be harmed" not in text, text
    verdicts = [s.get("verdict") for s in _result_trace(r2)
                if s.get("step") == "final_web_supervision"]
    assert verdicts == ["RE-ROUTE"], verdicts


def test_cnew2_fallback_path_false_reassurance_not_delivered(db, backend_fallback, monkeypatch):
    """C-NEW2 in the multi_agent_enabled=False fallback path, whose
    supervisor context previously carried no missing_information at all."""
    _, visit = _make_course_visit(db, "r3cnew2fb")

    async def fake_chat(messages, purpose="counseling"):
        return FALSE_REASSURANCE

    monkeypatch.setattr(backend_fallback, "_chat_once", fake_chat)
    result = _send(db, backend_fallback, "r3cnew2fb", visit, "Can you help me sleep better?")
    text = _result_text(result)
    assert FALSE_REASSURANCE not in text, text
    assert "completely safe" not in text, text
    verdicts = [s.get("verdict") for s in _result_trace(result)
                if s.get("step") == "final_web_supervision"]
    assert verdicts == ["RE-ROUTE"], verdicts


def test_cnew2_benign_draft_still_delivered(db, backend, monkeypatch):
    """C-NEW2 control: a benign draft on a genuinely clear turn is still
    delivered (no false escalation from the missing-item gate)."""
    _, visit = _make_course_visit(db, "r3cnew2ok")

    async def fake_chat(messages, purpose="counseling"):
        return "Let's explore one concrete coping step for this week."

    monkeypatch.setattr(backend, "_chat_once", fake_chat)
    result = _send(db, backend, "r3cnew2ok", visit, "Can you help me sleep better?")
    assert "one concrete coping step" in _result_text(result)
    verdicts = [s.get("verdict") for s in _result_trace(result)
                if s.get("step") == "final_web_supervision"]
    assert verdicts == ["ALLOW"], verdicts


def test_s2d5_contradiction_first_then_safety_question(db, backend):
    """S2-D5: the medical-history safety question must not outrank the
    contradiction question — T2 asks about the correction, and the safety
    question follows on T3 (owed-safety carry-over), not never."""
    _, visit = _make_course_visit(db, "r3d5")
    r1 = _send(db, backend, "r3d5", visit, "I have no trouble sleeping at all.")
    assert _result_route(r1) == "CLEAR"

    r2 = _send(db, backend, "r3d5", visit,
               "Actually I was wrong about that — I barely sleep at all most nights.")
    assert _result_route(r2) == "UNCERTAIN"
    assert CONTRADICTION_QUESTION in _result_text(r2), _result_text(r2)
    assert SAFETY_QUESTION not in _result_text(r2)

    r3 = _send(db, backend, "r3d5", visit,
               "It started about two weeks ago, after my exams began.")
    assert _result_route(r3) == "UNCERTAIN"
    assert SAFETY_QUESTION in _result_text(r3), _result_text(r3)
    steps = [s.get("step") for s in _result_trace(r3)]
    assert "owed_safety_question" in steps, steps

    # Answering the safety question must not re-ask it.
    r4 = _send(db, backend, "r3d5", visit, "No, I have never received any treatment.")
    assert SAFETY_QUESTION not in _result_text(r4), _result_text(r4)


def test_bd1_retraction_gets_clarification_not_echo(db, backend):
    """B-D1 (exact Stream B repro): retracting the exam stress stated in
    T1 must get the contradiction clarification question, not the generic
    dummy echo."""
    _, visit = _make_course_visit(db, "r3b1")
    _send(db, backend, "r3b1", visit,
          "Hello, I have been feeling anxious about my exams lately and I am not sleeping well "
          "because of my exams and I keep waking up at 3am.")
    r2 = _send(db, backend, "r3b1", visit, "Actually, I never had exam stress at all.")
    assert _result_route(r2) == "UNCERTAIN"
    assert CONTRADICTION_QUESTION in _result_text(r2), _result_text(r2)
    assert "Thanks for sharing" not in _result_text(r2)


def test_bd2_bd3_multi_visit_recall_present_tense_and_earliest(db, backend):
    """B-D2 + B-D3: in Session 2, 'What did I tell you about my sleep...'
    must trigger recall; the reply quotes the S1 detail (earliest) and
    the later correction, without the false 'That is all I have
    recorded' completeness claim."""
    course = M.TherapyCourseRecord(
        user_id="r3bd23", school_id="cbt", title="T",
        intake_note="Exams", goal_summary="Exam stress")
    db.add(course); db.commit(); db.refresh(course)
    call_llm = _call_llm(backend)

    visit1 = asyncio.run(vs.create_visit(db, "r3bd23", course.course_id, call_llm=call_llm))
    _send(db, backend, "r3bd23", visit1,
          "I am not sleeping well because of my exams and I keep waking up at 3am.")
    _send(db, backend, "r3bd23", visit1,
          "Actually, I never had exam stress at all. I sleep perfectly every night.")
    asyncio.run(vs.close_visit(db, "r3bd23", visit1.visit_id))

    visit2 = asyncio.run(vs.create_visit(db, "r3bd23", course.course_id, call_llm=call_llm))
    resp2 = _send(db, backend, "r3bd23", visit2,
                  "What did I tell you about my sleep in my first session?")
    reply = _last_assistant_text(resp2.visit)
    assert "not sleeping well" in reply, reply
    assert "sleep perfectly every night" in reply, reply
    assert "Thanks for sharing" not in reply, reply
    assert "That is all I have recorded" not in reply, reply
