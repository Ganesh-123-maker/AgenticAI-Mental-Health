"""REG-1 regression: cross-session recall quotes Session 1's own words.

The web engine used to build the counseling chat history from the
current visit only, so a Session 2 "remind me what I said about my sleep"
got "You haven't mentioned specific sleep details in this conversation
yet" even though Session 1 had said "I am not sleeping well because of
my exams." The engine now prepends prior visits' user turns (same
course) to the chat history. Exercises the REAL service layer
(create/send/close visit + SQLite) and the REAL PsychAgentWebBackend
(dummy) end to end, plus unit checks on the prior-message loader.
"""

import asyncio
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sqlmodel import Session, SQLModel, create_engine

from web.backend import models as M
from web.backend.psychagent_engine import PsychAgentWebBackend
from web.backend.schemas import VisitMessageOut, VisitState
from web.backend.services import visit_service as vs

SLEEP_DETAIL = "I am not sleeping well because of my exams and I keep waking up at 3am."
RECALL_QUESTION = "Can you remind me what I said about my sleep and exams?"
NO_SLEEP_DETAIL = "You haven't mentioned specific sleep details in this conversation yet."


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
        intake_note="Work stress", goal_summary="Manage stress",
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _last_assistant_text(visit_state):
    for message in reversed(visit_state.messages):
        if message.role == "assistant":
            return message.text
    return ""


def _send(db, backend, user_id, visit_id, text):
    return asyncio.run(vs.send_visit_message(
        db, user_id, visit_id, text, _call_llm(backend)))


def test_session2_recall_quotes_session1_sleep_detail(db, backend):
    """REG-1: Session 2 recall quotes Session 1's sleep words verbatim."""
    course = _make_course(db, user_id="reg1_a")
    call_llm = _call_llm(backend)

    visit1 = asyncio.run(vs.create_visit(db, "reg1_a", course.course_id, call_llm=call_llm))
    opening1 = _last_assistant_text(visit1)
    assert "Welcome. Before we start" in opening1
    resp1 = _send(db, backend, "reg1_a", visit1.visit_id, SLEEP_DETAIL)
    assert "not sleeping well" in _last_assistant_text(resp1.visit)
    asyncio.run(vs.close_visit(db, "reg1_a", visit1.visit_id))

    visit2 = asyncio.run(vs.create_visit(db, "reg1_a", course.course_id, call_llm=call_llm))
    # The Session 2 opening must still be the welcome: prior user turns
    # must not change which dummy branch answers the opening (the seed
    # contains "opening" and counselor_turn still counts 1).
    assert _last_assistant_text(visit2) == opening1

    resp2 = _send(db, backend, "reg1_a", visit2.visit_id, RECALL_QUESTION)
    reply = _last_assistant_text(resp2.visit)
    assert "not sleeping well" in reply, reply
    assert "waking up at 3am" in reply, reply
    assert NO_SLEEP_DETAIL not in reply, reply
    print("[PASS] REG-1: Session 2 recall quotes Session 1 sleep words.")


def test_session2_recall_no_fabrication_when_nothing_mentioned(db, backend):
    """No-invention half still holds: no sleep detail in S1, none recalled."""
    course = _make_course(db, user_id="reg1_b")
    call_llm = _call_llm(backend)

    visit1 = asyncio.run(vs.create_visit(db, "reg1_b", course.course_id, call_llm=call_llm))
    _send(db, backend, "reg1_b", visit1.visit_id, "Work has been really stressful lately.")
    asyncio.run(vs.close_visit(db, "reg1_b", visit1.visit_id))

    visit2 = asyncio.run(vs.create_visit(db, "reg1_b", course.course_id, call_llm=call_llm))
    resp2 = _send(db, backend, "reg1_b", visit2.visit_id, RECALL_QUESTION)
    reply = _last_assistant_text(resp2.visit)
    assert NO_SLEEP_DETAIL in reply, reply
    for invented in ("11 PM", "three weeks", "six hours", "four hours", "3am"):
        assert invented not in reply, reply
    print("[PASS] REG-1: no sleep detail recorded, none invented in recall.")


def test_no_cross_user_recall_leak(db, backend):
    """User B's Session 2 must not quote user A's Session 1 words."""
    course_a = _make_course(db, user_id="reg1_c_a")
    call_llm = _call_llm(backend)
    visit_a1 = asyncio.run(vs.create_visit(db, "reg1_c_a", course_a.course_id, call_llm=call_llm))
    _send(db, backend, "reg1_c_a", visit_a1.visit_id, SLEEP_DETAIL)
    asyncio.run(vs.close_visit(db, "reg1_c_a", visit_a1.visit_id))

    course_b = _make_course(db, user_id="reg1_c_b")
    visit_b1 = asyncio.run(vs.create_visit(db, "reg1_c_b", course_b.course_id, call_llm=call_llm))
    _send(db, backend, "reg1_c_b", visit_b1.visit_id, "Hello, I'd like to talk about work.")
    asyncio.run(vs.close_visit(db, "reg1_c_b", visit_b1.visit_id))

    visit_b2 = asyncio.run(vs.create_visit(db, "reg1_c_b", course_b.course_id, call_llm=call_llm))
    # create_visit already returns the built VisitState (not a record).
    # B's own Session 1 words are present; A's words must not be.
    assert [m.text for m in visit_b2.prior_visit_user_messages] == [
        "Hello, I'd like to talk about work."
    ]
    resp_b2 = _send(db, backend, "reg1_c_b", visit_b2.visit_id, RECALL_QUESTION)
    reply = _last_assistant_text(resp_b2.visit)
    assert NO_SLEEP_DETAIL in reply, reply
    assert "3am" not in reply, reply
    print("[PASS] REG-1: no cross-user recall leak.")


def test_no_cross_course_recall_leak_same_user(db, backend):
    """Same user, different course: course 2 must not recall course 1."""
    course1 = _make_course(db, user_id="reg1_d")
    call_llm = _call_llm(backend)
    visit1 = asyncio.run(vs.create_visit(db, "reg1_d", course1.course_id, call_llm=call_llm))
    _send(db, backend, "reg1_d", visit1.visit_id, SLEEP_DETAIL)
    asyncio.run(vs.close_visit(db, "reg1_d", visit1.visit_id))

    course2 = _make_course(db, user_id="reg1_d")
    visit2a = asyncio.run(vs.create_visit(db, "reg1_d", course2.course_id, call_llm=call_llm))
    _send(db, backend, "reg1_d", visit2a.visit_id, "Hello, new course.")
    asyncio.run(vs.close_visit(db, "reg1_d", visit2a.visit_id))

    visit2b = asyncio.run(vs.create_visit(db, "reg1_d", course2.course_id, call_llm=call_llm))
    # create_visit already returns the built VisitState (not a record).
    assert [m.text for m in visit2b.prior_visit_user_messages] == ["Hello, new course."]
    resp2 = _send(db, backend, "reg1_d", visit2b.visit_id, RECALL_QUESTION)
    reply = _last_assistant_text(resp2.visit)
    assert NO_SLEEP_DETAIL in reply, reply
    assert "3am" not in reply, reply
    print("[PASS] REG-1: no cross-course recall leak for the same user.")


def test_prior_messages_only_user_turns_chronological(db):
    """Loader: user turns only, oldest first; excludes assistant/system/current."""
    course = _make_course(db, user_id="reg1_e")
    visit1 = M.TherapyVisitRecord(
        course_id=course.course_id, visit_no=1, stage_key_snapshot="assessment")
    visit2 = M.TherapyVisitRecord(
        course_id=course.course_id, visit_no=2, stage_key_snapshot="assessment")
    db.add_all([visit1, visit2])
    db.commit()
    db.refresh(visit1)
    db.refresh(visit2)
    db.add_all([
        M.VisitMessageRecord(visit_id=visit1.visit_id, role="user", text="first sleep note"),
        M.VisitMessageRecord(visit_id=visit1.visit_id, role="assistant", text="assistant reply"),
        M.VisitMessageRecord(visit_id=visit1.visit_id, role="user", text="second sleep note"),
        M.VisitMessageRecord(visit_id=visit1.visit_id, role="system", text="--- session ended ---"),
        M.VisitMessageRecord(visit_id=visit2.visit_id, role="user", text="current visit note"),
    ])
    db.commit()

    assert vs.build_visit_state(db, visit1).prior_visit_user_messages == []
    prior2 = vs.build_visit_state(db, visit2).prior_visit_user_messages
    assert [m.text for m in prior2] == ["first sleep note", "second sleep note"]
    assert all(m.role == "user" for m in prior2)
    print("[PASS] REG-1: prior loader returns user turns only, in order.")


def test_chat_history_with_prior_orders_prior_before_current(backend):
    """Helper: prior user turns come first, current visit turns follow."""
    # model_construct: the helper only reads messages +
    # prior_visit_user_messages, so no full VisitState is needed here.
    state = VisitState.model_construct(
        messages=[VisitMessageOut(id="m1", role="user", text="current question")],
        prior_visit_user_messages=[
            VisitMessageOut(id="p1", role="user", text="prior sleep note"),
        ],
    )
    history = backend._build_chat_history_with_prior(state)
    assert [m["content"] for m in history] == ["prior sleep note", "current question"]
    assert [m["role"] for m in history] == ["user", "user"]
    print("[PASS] REG-1: chat-history helper orders prior before current.")
