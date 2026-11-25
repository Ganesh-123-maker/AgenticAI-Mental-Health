"""Web-path regression tests for the live-browser UI pass (2026-11-25, A-1).

Defect found only by driving the real React app: in a course created
through the UI — title only, no intake note or goal summary — the
auto-generated opening was an intake question ("Around when did this
feeling start to emerge?") instead of the welcome greeting, and the
first two ordinary distress turns ("due to exams", "mental pressure")
got generic clarification questions ("could you tell me more about the
main concern you mentioned" / "your background") instead of the coping
step. The API round missed it because its harness always supplied
intake info, which fills the history slot from the intake note.

Root cause: the uncertainty agent treated an empty
growth_experiences list as concern-relevant unresolved information,
and the clarification agent used intake/profile fields as fallback
question targets. Both are fixed; these tests pin the UI path.

Pinned behavior (dummy backend, title-only course):
- the opening assistant message is the welcome greeting;
- all 7 everyday-distress turns in one session are CLEAR with their
  coping step, never a "could you tell me more about ..." question;
- the direct safety question still fires for ambiguous passive
  distress in a no-intake course (the fix did not touch that path).
"""

import asyncio
import pathlib
import sys

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from web.backend import models as M  # noqa: E402
from web.backend.psychagent_engine import PsychAgentWebBackend  # noqa: E402
from web.backend.services import visit_service as vs  # noqa: E402


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


def _make_ui_course(db, user_id="ui-qa"):
    # Exactly what the UI sends: title only, no intake note or goal
    # summary (CreateCourseModal submits {title} and the hook adds
    # auto_start_first_visit: true).
    course = M.TherapyCourseRecord(
        user_id=user_id, school_id="behavioral", title="UI QA course",
        intake_note="", goal_summary="",
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _start_visit(db, backend, course, user_id="ui-qa"):
    asyncio.run(vs.create_visit(db, user_id, course.course_id, call_llm=_call_llm(backend)))
    visit = db.exec(
        select(M.TherapyVisitRecord).where(M.TherapyVisitRecord.course_id == course.course_id)
    ).first()
    return visit


def _send(db, backend, visit, text, user_id="ui-qa"):
    resp = asyncio.run(vs.send_visit_message(db, user_id, visit.visit_id, text, _call_llm(backend)))
    assistants = [m for m in resp.visit.messages if m.role == "assistant"]
    route = (resp.visit.psych_context or {}).profile_payload.get("latest_route")
    return assistants[-1].text, route


def _opening(db, visit):
    msgs = db.exec(
        select(M.VisitMessageRecord).where(M.VisitMessageRecord.visit_id == visit.visit_id)
    ).all()
    assistants = [m for m in msgs if m.role == "assistant"]
    return assistants[0].text if assistants else ""


def test_ui_course_opening_is_welcome(db, backend):
    course = _make_ui_course(db)
    visit = _start_visit(db, backend, course)
    opening = _opening(db, visit)
    assert opening.startswith("Welcome."), opening
    assert "Around when did this feeling start" not in opening, opening


def test_ui_course_everyday_distress_gets_coping_steps(db, backend):
    course = _make_ui_course(db)
    visit = _start_visit(db, backend, course)
    turns = [
        ("i will feeling very sad", "paced-breathing"),
        ("due to exams", "25"),
        ("mental pressure", "walk"),
        ("i cant sleep at night, i keep waking up", "wind-down"),
        ("i feel anxious all the time", "worries"),
        ("i feel so lonely, nobody talks to me", "paced-breathing"),
        ("exams are coming and i havent studied anything", "25"),
    ]
    for text, step in turns:
        reply, route = _send(db, backend, visit, text)
        assert route == "CLEAR", (text, route, reply)
        assert step in reply, (text, reply)
        assert "could you tell me more about" not in reply, (text, reply)
        assert "I heard:" not in reply, (text, reply)


def test_ui_course_safety_question_still_asked(db, backend):
    # Guard: the A-1 fix must not touch the MODERATE ambiguous-distress
    # path — "its hard to live" in a no-intake course still gets the
    # one-time direct safety question with all three helplines.
    course = _make_ui_course(db, user_id="ui-qa-safety")
    visit = _start_visit(db, backend, course, user_id="ui-qa-safety")
    reply, route = _send(db, backend, visit, "its hard to live", user_id="ui-qa-safety")
    assert route == "UNCERTAIN", (route, reply)
    assert "Are you having thoughts of ending your life?" in reply, reply
    assert "14416" in reply and "112" in reply and "988" in reply, reply
