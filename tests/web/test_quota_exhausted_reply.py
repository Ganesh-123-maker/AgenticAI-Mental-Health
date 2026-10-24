"""Quota-exhausted reply tests (Item 3d, 2026-10-24).

Before this fix, a counseling chat call failing with HTTP 429 fell
through to a fallback LLM call (which also 429s) and then raised,
which the service layer turned into a raw 502 with no assistant
reply. Now the engine returns a visible quota-exhausted state: an
assistant message, a trace entry meaning "counseling attempted,
upstream failed", reply_source "error", and the routing state
preserved — with no fallback call and no routing change.

The engine backend is stubbed to raise QuotaExhaustedError on the
counseling call only: the skill manager keeps the real dummy backend
(it was constructed with the original backend object), so filter and
rewrite succeed and exactly one counseling attempt is observed.
"""

import asyncio
import pathlib
import sys

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.core.retry import QuotaExhaustedError
from web.backend import models as M
from web.backend.psychagent_engine import PsychAgentWebBackend
from web.backend.services import visit_service as vs

MSGS = [
    "I'm worried about my exams next week and just feel overwhelmed.",
    "I can't sleep at night because my mind keeps racing.",
    "Walk me through a breathing exercise.",
]

QUOTA_TEXT = "temporarily unavailable because its daily quota is exhausted"


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
    return db.exec(
        select(M.TherapyVisitRecord).where(M.TherapyVisitRecord.course_id == course.course_id)
    ).first()


def _send(db, backend, visit, text, user_id="u1"):
    resp = asyncio.run(vs.send_visit_message(db, user_id, visit.visit_id, text, _call_llm(backend)))
    assistants = [m for m in resp.visit.messages if m.role == "assistant"]
    return assistants[-1].text


class _QuotaBackend:
    """Raises QuotaExhaustedError on every chat call, counting attempts."""

    def __init__(self):
        self.calls = 0

    async def chat_text(self, messages, **kwargs):
        self.calls += 1
        raise QuotaExhaustedError("quota exhausted: http status 429")


def test_counseling_quota_failure_surfaces_without_fallback(db, backend):
    stub = _QuotaBackend()
    original_backend = backend._backend
    backend._backend = stub
    try:
        course = _make_course(db)
        visit = _start_visit(db, backend, course)
        _send(db, backend, visit, MSGS[0])
        _send(db, backend, visit, MSGS[1])
        assert stub.calls == 0, "template clarification turns must not call the chat backend"
        reply = _send(db, backend, visit, MSGS[2])
        assert QUOTA_TEXT in reply
        assert stub.calls == 1, f"fallback must not fire after quota exhaustion, got {stub.calls} calls"
        snap = vs.get_visit_psych_context_snapshot(db, visit.visit_id)
        payload = snap.profile_payload
        assert payload.get("latest_reply_source") == "error"
        assert payload.get("latest_route") == "CLEAR"
        trace = payload.get("latest_agent_trace") or []
        assert any(
            step.get("step") == "counseling_attempted_upstream_failed"
            and step.get("error") == "quota_exhausted"
            for step in trace
        ), f"trace lacks the failed-counseling entry: {trace}"
        print("[PASS] Quota failure surfaced visibly; no fallback call; routing preserved.")
    finally:
        backend._backend = original_backend
