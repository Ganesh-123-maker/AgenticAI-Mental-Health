"""Backend integration tests for the multi-turn clarification conversation flow.

Exercises the REAL service layer (send_visit_message + SQLite) and the REAL
PsychAgentWebBackend (reply_from_visit), tracing:
  user message -> pipeline -> persisted trace/profile -> next user message.

Verifies:
- UNCERTAIN + clarification question persisted correctly.
- Next request detects pending clarification from persisted state.
- The answer is evaluated as the new current message.
- Reassessment updates state and the new route is persisted.
- State does not leak between users/visits.
"""

import asyncio
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sqlmodel import SQLModel, Session, create_engine

from web.backend import models as M
from web.backend.psychagent_engine import PsychAgentWebBackend
from web.backend.services import visit_service as vs


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


def _make_visit(db, user_id="u1"):
    course = M.TherapyCourseRecord(
        user_id=user_id, school_id="cbt", title="Test",
        intake_note="Work stress", goal_summary="Manage stress",
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    visit = M.TherapyVisitRecord(
        course_id=course.course_id, visit_no=1, stage_key_snapshot="assessment"
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)
    return course, visit


def _call_llm(backend):
    async def _inner(history, course, visit, visit_state, psych_context):
        return await backend.reply_from_visit(
            fallback_messages=[], course=course, visit=visit,
            visit_state=visit_state, psych_context=psych_context,
        )
    return _inner


def _persisted(db, visit):
    return vs.get_visit_psych_context_snapshot(db, visit.visit_id)


def test_uncertain_answer_clear_flow(db, backend):
    """UNCERTAIN -> clarification -> answer -> CLEAR, state tracked."""
    _, visit = _make_visit(db)
    call_llm = _call_llm(backend)

    asyncio.run(vs.send_visit_message(
        db, "u1", visit.visit_id,
        "It's about... that thing, you know. I've been feeling off.", call_llm))
    snap1 = _persisted(db, visit)
    assert snap1.profile_payload.get("latest_route") == "UNCERTAIN"
    assert backend._clarification_pending(snap1) is True
    trace1 = snap1.profile_payload.get("latest_agent_trace") or []
    q1 = [s for s in trace1 if s.get("agent") == "clarification_agent"][0]["payload"]["question"]
    assert q1  # a real question was persisted

    asyncio.run(vs.send_visit_message(
        db, "u1", visit.visit_id,
        "I was referring to the conflict with my manager last week.", call_llm))
    snap2 = _persisted(db, visit)
    assert snap2.profile_payload.get("latest_route") == "CLEAR"
    assert backend._clarification_pending(snap2) is False
    print("[PASS] UNCERTAIN -> answer -> CLEAR with correct state tracking.")


def test_second_clarification_turn(db, backend):
    """Still-ambiguous answer -> reassessment runs, pending remains."""
    _, visit = _make_visit(db)
    call_llm = _call_llm(backend)

    asyncio.run(vs.send_visit_message(
        db, "u1", visit.visit_id,
        "It's about... that thing, you know. I've been feeling off.", call_llm))
    # Still-ambiguous + distressed reply: stays UNCERTAIN, reassessment evaluates it.
    t2_msg = "It's still about that thing... 我最近不堪重负，整夜失眠。"
    asyncio.run(vs.send_visit_message(db, "u1", visit.visit_id, t2_msg, call_llm))
    snap2 = _persisted(db, visit)
    assert snap2.profile_payload.get("latest_route") == "UNCERTAIN"
    trace2 = snap2.profile_payload.get("latest_agent_trace") or []
    reas = [s for s in trace2 if s.get("agent") == "reassessment_agent"]
    assert len(reas) >= 1, "reassessment did not evaluate the second message"
    # The answer actually processed was the new message, not the old one.
    assert reas[0].get("clarification_answer") == t2_msg
    assert backend._clarification_pending(snap2) is True
    print("[PASS] Second turn evaluates the new message via reassessment.")


def test_acute_risk_answer_escalates(db, backend):
    """UNCERTAIN -> acute-risk answer -> HIGH-RISK, safety preserved."""
    _, visit = _make_visit(db)
    call_llm = _call_llm(backend)

    asyncio.run(vs.send_visit_message(
        db, "u1", visit.visit_id,
        "It's about... that thing, you know. I've been feeling off.", call_llm))
    asyncio.run(vs.send_visit_message(
        db, "u1", visit.visit_id,
        "I feel completely hopeless and have thought about ending my life.", call_llm))
    snap2 = _persisted(db, visit)
    assert snap2.profile_payload.get("latest_route") == "HIGH-RISK"
    assert backend._clarification_pending(snap2) is False
    print("[PASS] Acute-risk answer escalates to HIGH-RISK.")


def test_no_cross_user_state_leak(db, backend):
    """User A's pending clarification does not affect user B."""
    _, visit_a = _make_visit(db, user_id="user_a")
    _, visit_b = _make_visit(db, user_id="user_b")
    call_llm = _call_llm(backend)

    asyncio.run(vs.send_visit_message(
        db, "user_a", visit_a.visit_id,
        "It's about... that thing, you know. I've been feeling off.", call_llm))
    snap_a = _persisted(db, visit_a)
    assert backend._clarification_pending(snap_a) is True

    # User B starts fresh; their message must not be treated as an answer.
    asyncio.run(vs.send_visit_message(
        db, "user_b", visit_b.visit_id,
        "Hello, I'd like to talk about work.", call_llm))
    snap_b = _persisted(db, visit_b)
    assert backend._clarification_pending(snap_b) is False
    # A's state untouched.
    assert _persisted(db, visit_a).profile_payload.get("latest_route") == "UNCERTAIN"
    print("[PASS] No clarification state leaks between users.")


def test_new_question_after_clear_not_answer(db, backend):
    """After CLEAR, a new user question is a new message, not an answer."""
    _, visit = _make_visit(db, user_id="user_c")
    call_llm = _call_llm(backend)

    asyncio.run(vs.send_visit_message(
        db, "user_c", visit.visit_id,
        "It's about... that thing, you know. I've been feeling off.", call_llm))
    asyncio.run(vs.send_visit_message(
        db, "user_c", visit.visit_id,
        "I was referring to the conflict with my manager last week.", call_llm))
    assert _persisted(db, visit).profile_payload.get("latest_route") == "CLEAR"

    # New question: must not be treated as a clarification answer.
    snap_before = _persisted(db, visit)
    assert backend._clarification_pending(snap_before) is False
    asyncio.run(vs.send_visit_message(
        db, "user_c", visit.visit_id,
        "What techniques can help me manage deadline stress?", call_llm))
    snap_after = _persisted(db, visit)
    trace = snap_after.profile_payload.get("latest_agent_trace") or []
    reas = [s for s in trace if s.get("agent") == "reassessment_agent"]
    assert not reas, "new question was wrongly fed to reassessment as an answer"
    print("[PASS] New question after CLEAR not treated as clarification answer.")
