"""Skill coarse-filter deferral tests (Item 2b, 2026-10-24).

Before this fix, PsychAgentWebBackend.reply_from_visit built candidate
skills (one SkillManager coarse-filter chat call) on EVERY turn before
routing was known — including turns that return a template HIGH-RISK
or clarification reply and never use any skill. That is the call the
2026-10-24 live report attributed to clarification turns.

Pinned behavior (dummy backend, real service layer):
- clarification turns add ZERO coarse-filter calls;
- the counseling turn builds candidates exactly once (lazily);
- routing itself is unchanged (UNCERTAIN safety question, then CLEAR).
"""

import asyncio
import pathlib
import sys

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

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


def _route(db, visit):
    return vs.get_visit_psych_context_snapshot(db, visit.visit_id).profile_payload.get("latest_route")


def test_clarification_turns_make_no_coarse_filter_calls(db, backend):
    orig = backend._skill_manager.corse_filter
    calls = []

    async def counting(*args, **kwargs):
        calls.append(1)
        return await orig(*args, **kwargs)

    backend._skill_manager.corse_filter = counting
    try:
        course = _make_course(db)
        visit = _start_visit(db, backend, course)
        after_opening = len(calls)

        _send(db, backend, visit, MSGS[0])
        assert _route(db, visit) == "UNCERTAIN"
        assert len(calls) == after_opening, (
            f"clarification turn 1 fired the coarse filter: {len(calls) - after_opening} call(s)"
        )

        _send(db, backend, visit, MSGS[1])
        assert _route(db, visit) == "UNCERTAIN"
        assert len(calls) == after_opening, (
            f"clarification turn 2 fired the coarse filter: {len(calls) - after_opening} call(s)"
        )

        _send(db, backend, visit, MSGS[2])
        assert _route(db, visit) == "CLEAR"
        assert len(calls) == after_opening + 1, (
            f"counseling turn should build candidates exactly once, got {len(calls) - after_opening}"
        )
        print("[PASS] Clarification turns: 0 coarse-filter calls; counseling turn: exactly 1.")
    finally:
        backend._skill_manager.corse_filter = orig
