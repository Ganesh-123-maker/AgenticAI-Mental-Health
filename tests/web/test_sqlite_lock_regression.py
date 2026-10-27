"""Regression tests for the attempt-4 SQLite lock (2026-10-26).

Root cause: send_visit_message flushed the user message and then awaited
the LLM, so SQLite's single-writer lock was held across the whole LLM
retry sequence. Any concurrent writer (e.g. /auth/register) then waited
out the 30s busy_timeout and failed with "database is locked". WAL mode
does not fix this: it lets readers run during a write, but writers still
serialize.

Fix under test: each turn is split into short transactions -- the user
message (send), the visit + opening system message (create), and the
assistant message (auto-close) are each committed BEFORE the following
await, so no write transaction spans an LLM call.

Each test runs a fake LLM that sleeps, then performs a registration-style
write on a separate connection while the await is still in progress. The
writer connection uses a short 800ms busy_timeout, so on the old code it
fails fast instead of waiting out the production 30s. A passing test
therefore proves the writer completed DURING the await, not after it.
"""

import asyncio
import pathlib
import sys
import threading

import pytest
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from fastapi import HTTPException

from web.backend import models as M
from web.backend.services import visit_service as vs
from web.backend.sqlite_pragmas import apply_sqlite_pragmas

LLM_SLEEP_SEC = 2.5
WRITER_BUSY_TIMEOUT_MS = 800


@pytest.fixture()
def engines(tmp_path):
    """Chat engine (production pragmas) + writer engine (short timeout)."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    chat_engine = create_engine(
        db_url, connect_args={"check_same_thread": False, "timeout": 30}
    )
    apply_sqlite_pragmas(chat_engine)
    SQLModel.metadata.create_all(chat_engine)

    writer_engine = create_engine(
        db_url, connect_args={"check_same_thread": False, "timeout": 30}
    )

    @event.listens_for(writer_engine, "connect")
    def _set_writer_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={WRITER_BUSY_TIMEOUT_MS}")
        finally:
            cursor.close()

    return chat_engine, writer_engine


def _make_course(chat_engine, user_id="u1"):
    with Session(chat_engine) as db:
        course = M.TherapyCourseRecord(
            user_id=user_id, school_id="cbt", title="Test",
            intake_note="Work stress", goal_summary="Manage stress",
        )
        db.add(course)
        db.commit()
        db.refresh(course)
        return course.course_id


def _make_visit(chat_engine, course_id):
    with Session(chat_engine) as db:
        visit = M.TherapyVisitRecord(
            course_id=course_id, visit_no=1, stage_key_snapshot="assessment"
        )
        db.add(visit)
        db.commit()
        db.refresh(visit)
        return visit.visit_id


def _register(writer_engine, username):
    """Exactly what /auth/register does, on its own connection."""
    with Session(writer_engine) as db:
        exists = db.exec(
            select(M.UserRecord).where(M.UserRecord.username == username)
        ).first()
        assert not exists
        user = M.UserRecord(username=username, password_hash="dummy")
        db.add(user)
        db.commit()
        db.refresh(user)
        db.add(M.AuthTokenRecord(token=f"tok-{username}", user_id=user.id))
        db.commit()


def _run_in_thread(target):
    result = {}
    def _wrap():
        try:
            result["value"] = target()
        except Exception as exc:  # noqa: BLE001 - captured, asserted by caller
            result["error"] = exc
    thread = threading.Thread(target=_wrap)
    thread.start()
    return thread, result


def _messages(chat_engine, visit_id):
    with Session(chat_engine) as db:
        rows = db.exec(
            select(M.VisitMessageRecord)
            .where(M.VisitMessageRecord.visit_id == visit_id)
            .order_by(M.VisitMessageRecord.created_at, M.VisitMessageRecord.id)
        ).all()
        return [(row.role, row.text) for row in rows]


def test_send_message_does_not_block_concurrent_writer(engines):
    chat_engine, writer_engine = engines
    course_id = _make_course(chat_engine)
    visit_id = _make_visit(chat_engine, course_id)
    started = threading.Event()

    async def fake_llm(history, course, visit, visit_state, psych_context):
        started.set()
        await asyncio.sleep(LLM_SLEEP_SEC)
        return "Fake counseling reply."

    def chat_turn():
        with Session(chat_engine) as db:
            return asyncio.run(vs.send_visit_message(
                db, "u1", visit_id, "I have been feeling overwhelmed lately.", fake_llm))

    thread, result = _run_in_thread(chat_turn)
    assert started.wait(timeout=10), "fake LLM was never reached"
    _register(writer_engine, "newuser")
    assert thread.is_alive(), "writer finished only after the chat turn ended"
    thread.join(timeout=15)
    assert "error" not in result, f"chat turn failed: {result.get('error')!r}"
    assert _messages(chat_engine, visit_id) == [
        ("user", "I have been feeling overwhelmed lately."),
        ("assistant", "Fake counseling reply."),
    ]


def test_create_visit_does_not_block_concurrent_writer(engines):
    chat_engine, writer_engine = engines
    course_id = _make_course(chat_engine)
    started = threading.Event()

    async def fake_llm(history, course, visit, visit_state, psych_context):
        started.set()
        await asyncio.sleep(LLM_SLEEP_SEC)
        return "Hello, opening reply."

    def create_turn():
        with Session(chat_engine) as db:
            return asyncio.run(vs.create_visit(
                db, "u1", course_id, call_llm=fake_llm))

    thread, result = _run_in_thread(create_turn)
    assert started.wait(timeout=10), "fake LLM was never reached"
    _register(writer_engine, "newuser")
    assert thread.is_alive(), "writer finished only after the create turn ended"
    thread.join(timeout=15)
    assert "error" not in result, f"create turn failed: {result.get('error')!r}"
    state = result["value"]
    assert _messages(chat_engine, state.visit_id)[-1] == (
        "assistant", "Hello, opening reply.")


def test_auto_close_does_not_block_concurrent_writer(engines):
    chat_engine, writer_engine = engines
    course_id = _make_course(chat_engine)
    visit_id = _make_visit(chat_engine, course_id)
    closing_started = threading.Event()

    async def fake_llm(history, course, visit, visit_state, psych_context):
        return {"text": "Goodbye.", "end": True}

    async def fake_close(course, visit, visit_state, psych_context):
        closing_started.set()
        await asyncio.sleep(LLM_SLEEP_SEC)
        return {}

    def chat_turn():
        with Session(chat_engine) as db:
            return asyncio.run(vs.send_visit_message(
                db, "u1", visit_id, "Please close this session.",
                fake_llm, run_session_close_postprocess=fake_close))

    thread, result = _run_in_thread(chat_turn)
    assert closing_started.wait(timeout=10), "close postprocess was never reached"
    _register(writer_engine, "newuser")
    assert thread.is_alive(), "writer finished only after the close ended"
    thread.join(timeout=15)
    assert "error" not in result, f"close turn failed: {result.get('error')!r}"
    with Session(chat_engine) as db:
        visit = db.get(M.TherapyVisitRecord, visit_id)
        assert visit.status == "closed"


def test_failed_user_message_persists(engines):
    chat_engine, _writer_engine = engines
    course_id = _make_course(chat_engine)
    visit_id = _make_visit(chat_engine, course_id)

    async def failing_llm(history, course, visit, visit_state, psych_context):
        raise RuntimeError("upstream down")

    with Session(chat_engine) as db:
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(vs.send_visit_message(
                db, "u1", visit_id, "This message must survive.", failing_llm))
    assert excinfo.value.status_code == 502
    assert _messages(chat_engine, visit_id) == [
        ("user", "This message must survive."),
    ]
