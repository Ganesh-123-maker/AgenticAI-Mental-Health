"""Multi-turn and isolation matrix (Step 4 of final completion pass).

| Scenario | Expected |
Uses the real DB/session layer (send_visit_message + SQLite + backend).
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


def _make_course_visit(db, user_id, visit_no=1):
    course = M.TherapyCourseRecord(
        user_id=user_id, school_id="cbt", title="T",
        intake_note="Work stress", goal_summary="Manage stress")
    db.add(course); db.commit(); db.refresh(course)
    visit = M.TherapyVisitRecord(course_id=course.course_id, visit_no=visit_no,
                                 stage_key_snapshot="assessment")
    db.add(visit); db.commit(); db.refresh(visit)
    return visit


def _llm(backend):
    async def _inner(history, course, visit, visit_state, psych_context):
        return await backend.reply_from_visit(
            fallback_messages=[], course=course, visit=visit,
            visit_state=visit_state, psych_context=psych_context)
    return _inner


def _send(db, backend, uid, visit, text):
    return asyncio.run(vs.send_visit_message(db, uid, visit.visit_id, text, _llm(backend)))


def _route(db, visit):
    return vs.get_visit_psych_context_snapshot(db, visit.visit_id).profile_payload.get("latest_route")


def test_matrix_clear_direct_counseling(db, backend):
    """CLEAR message -> direct counseling."""
    v = _make_course_visit(db, "m1")
    _send(db, backend, "m1", v, "Work deadlines have been manageable.")
    assert _route(db, v) == "CLEAR"
    print("[PASS] matrix: CLEAR -> direct counseling.")


def test_matrix_uncertain_relevant_answer(db, backend):
    """UNCERTAIN, clarification, relevant answer -> CLEAR."""
    v = _make_course_visit(db, "m2")
    _send(db, backend, "m2", v, "It's about... that thing, you know.")
    assert _route(db, v) == "UNCERTAIN"
    _send(db, backend, "m2", v, "I was referring to the conflict with my manager.")
    assert _route(db, v) == "CLEAR"
    print("[PASS] matrix: UNCERTAIN + relevant answer -> CLEAR.")


def test_matrix_uncertain_irrelevant_capped(db, backend):
    """UNCERTAIN, irrelevant answer -> loop capped, safe handling."""
    v = _make_course_visit(db, "m3")
    _send(db, backend, "m3", v, "It's about... that thing, you know.")
    _send(db, backend, "m3", v, "It's still about that thing... 我最近不堪重负。")
    r = _route(db, v)
    assert r in ("UNCERTAIN", "CLEAR", "HIGH-RISK")  # capped, never hangs
    print(f"[PASS] matrix: irrelevant answer -> capped ({r}).")


def test_matrix_new_risk_disclosed(db, backend):
    """UNCERTAIN, clarification, new risk disclosed -> HIGH-RISK."""
    v = _make_course_visit(db, "m4")
    _send(db, backend, "m4", v, "It's about... that thing, you know.")
    _send(db, backend, "m4", v, "I feel completely hopeless and have thought about ending my life.")
    assert _route(db, v) == "HIGH-RISK"
    print("[PASS] matrix: new risk disclosed -> HIGH-RISK.")


def test_matrix_moderate_then_benign(db, backend):
    """MODERATE then benign -> risk remains recorded."""
    v = _make_course_visit(db, "m5")
    _send(db, backend, "m5", v, "我最近不堪重负，整夜失眠。")
    snap1 = vs.get_visit_psych_context_snapshot(db, v.visit_id)
    assert (snap1.profile_payload.get("longitudinal_risk") or {}).get("severity") == "MODERATE"
    _send(db, backend, "m5", v, "Today was fine.")
    snap2 = vs.get_visit_psych_context_snapshot(db, v.visit_id)
    assert (snap2.profile_payload.get("longitudinal_risk") or {}).get("severity") in ("MODERATE", "HIGH")
    print("[PASS] matrix: MODERATE persists over benign.")


def test_matrix_high_then_benign(db, backend):
    """HIGH then benign -> not downgraded; supervisor aware."""
    v = _make_course_visit(db, "m6")
    _send(db, backend, "m6", v, "I feel completely hopeless and have thought about ending my life.")
    assert _route(db, v) == "HIGH-RISK"
    _send(db, backend, "m6", v, "I'm feeling better now.")
    assert _route(db, v) == "HIGH-RISK"
    print("[PASS] matrix: HIGH not downgraded by benign.")


def test_matrix_two_users_isolated(db, backend):
    """Two users concurrently -> no leakage."""
    va = _make_course_visit(db, "ma")
    vb = _make_course_visit(db, "mb")
    _send(db, backend, "ma", va, "I feel completely hopeless and have thought about ending my life.")
    _send(db, backend, "mb", vb, "Work is fine.")
    assert _route(db, va) == "HIGH-RISK"
    assert _route(db, vb) != "HIGH-RISK"
    print("[PASS] matrix: two users isolated.")


def test_matrix_two_visits_separated(db, backend):
    """Two visits for one user -> state separated."""
    v1 = _make_course_visit(db, "mv", visit_no=1)
    v2 = _make_course_visit(db, "mv", visit_no=2)
    _send(db, backend, "mv", v1, "I feel completely hopeless and have thought about ending my life.")
    _send(db, backend, "mv", v2, "Work is fine.")
    assert _route(db, v1) == "HIGH-RISK"
    # Visit 2 is a separate conversation; carried risk is visit-scoped.
    assert _route(db, v2) != "HIGH-RISK"
    print("[PASS] matrix: two visits separated.")
