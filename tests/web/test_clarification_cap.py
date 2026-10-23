"""Web-path regression tests for the repeated-clarification loop.

Reproduces the reported defect end to end through the real service layer
(create_visit opening + send_visit_message, dummy backend): three
different user messages in a fresh CBT visit must not receive the same
clarification question three times. Before the fix, the session opening
(a pipeline clarification question itself) blocked the duration
template as "already asked", the generic fallback re-asked
"main_problem" forever, and no visit-level cap existed.

Pinned behavior:
- turn 1 may be a clarification; turn 2 is never the same question;
- by turn 3 the conversation has proceeded to counseling (the direct
  low-risk request is answered), with the clarification budget (<= 2
  turns per visit) respected and the unknowns noted in persisted state;
- reply_source is persisted for trace transparency ("template" under
  the dummy backend);
- a HIGH-risk first message still takes the safety path immediately.
"""

import asyncio
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sqlmodel import Session, SQLModel, create_engine, select

from web.backend import models as M
from web.backend.psychagent_engine import PsychAgentWebBackend
from web.backend.services import visit_service as vs

MSGS = [
    "I'm worried about my exams next week and just feel overwhelmed.",
    "I can't sleep at night because my mind keeps racing.",
    "Walk me through a breathing exercise.",
]


@pytest.fixture(scope="module")
def backend():
    from pathlib import Path as P
    be = PsychAgentWebBackend(
        project_root=P("."),
        baseline_config_path="configs/baselines/psychagent_dummy_local.yaml",
        runtime_config_path="configs/runtime/psychagent_dummy_local.yaml",
    )
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
            visit_state=visit_state, psych_context=psych_context,
        )
    return _inner


def _make_course(db, user_id="u1"):
    # Mirrors a UI-created course: no intake note or goal summary, so the
    # profile's core fields start unpopulated (the condition under which
    # the reported loop occurred).
    course = M.TherapyCourseRecord(
        user_id=user_id, school_id="cbt", title="Test",
        intake_note="", goal_summary="",
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _start_visit(db, backend, course, user_id="u1"):
    asyncio.run(vs.create_visit(db, user_id, course.course_id, call_llm=_call_llm(backend)))
    visit = db.exec(
        select(M.TherapyVisitRecord).where(M.TherapyVisitRecord.course_id == course.course_id)
    ).first()
    return visit


def _send(db, backend, visit, text, user_id="u1"):
    resp = asyncio.run(vs.send_visit_message(db, user_id, visit.visit_id, text, _call_llm(backend)))
    assistants = [m for m in resp.visit.messages if m.role == "assistant"]
    return assistants[-1].text


def _snap(db, visit):
    return vs.get_visit_psych_context_snapshot(db, visit.visit_id)


def test_three_messages_no_repeated_clarification(db, backend):
    course = _make_course(db)
    visit = _start_visit(db, backend, course)
    replies = [_send(db, backend, visit, m) for m in MSGS]

    # The reported defect: one identical clarification question three times.
    assert len(set(replies)) == 3, f"replies not distinct: {replies}"
    assert all("main_problem" not in r for r in replies)

    snap = _snap(db, visit)
    payload = snap.profile_payload
    # By turn 3 the direct request was answered by counseling, not intake.
    assert payload.get("latest_route") == "CLEAR"
    assert payload.get("latest_reply_source") == "template"  # dummy backend
    state = payload.get("clarification_state") or {}
    assert state.get("turns", 0) <= 2, f"clarification budget exceeded: {state}"
    assert state.get("proceeded_with_unknowns"), "unknowns were not noted when proceeding"
    print("[PASS] Three different messages: no repeated clarification; counseling by turn 3.")


def test_direct_request_first_message_is_answered(db, backend):
    course = _make_course(db)
    visit = _start_visit(db, backend, course)
    reply = _send(db, backend, visit, "Walk me through a breathing exercise.")
    assert "background concerning" not in reply
    snap = _snap(db, visit)
    assert snap.profile_payload.get("latest_route") == "CLEAR"
    print("[PASS] A direct low-risk request as the first message is answered, not held behind intake.")


def test_high_risk_first_message_takes_safety_path(db, backend):
    course = _make_course(db)
    visit = _start_visit(db, backend, course)
    reply = _send(db, backend, visit, "I don't want to live anymore.")
    snap = _snap(db, visit)
    assert snap.profile_payload.get("latest_route") == "HIGH-RISK"
    assert "14416" in reply and "988" in reply
    print("[PASS] HIGH-risk first message escalates immediately with crisis resources.")
