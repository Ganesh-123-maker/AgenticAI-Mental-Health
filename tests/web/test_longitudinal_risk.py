"""Integration tests for longitudinal risk carry-forward across backend turns.

Verifies that HIGH/MODERATE risk severities persist across turns in a visit
via profile_payload["longitudinal_risk"], preventing downgrades from benign
follow-up messages, while LOW conversations stay unblocked and state never
leaks between users/visits.
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
    return visit


def _call_llm(backend):
    async def _inner(history, course, visit, visit_state, psych_context):
        return await backend.reply_from_visit(
            fallback_messages=[], course=course, visit=visit,
            visit_state=visit_state, psych_context=psych_context,
        )
    return _inner


def _snap(db, visit):
    return vs.get_visit_psych_context_snapshot(db, visit.visit_id)


def _send(db, backend, user_id, visit, text):
    return asyncio.run(vs.send_visit_message(
        db, user_id, visit.visit_id, text, _call_llm(backend)))


def test_high_persists_over_benign(db, backend):
    """HIGH-risk T1 -> benign T2 remains HIGH-risk (no downgrade)."""
    visit = _make_visit(db)
    _send(db, backend, "u1", visit,
          "I feel completely hopeless and have thought about ending my life.")
    assert _snap(db, visit).profile_payload.get("latest_route") == "HIGH-RISK"
    assert _snap(db, visit).profile_payload["longitudinal_risk"]["severity"] == "HIGH"

    _send(db, backend, "u1", visit, "Thanks, I'm feeling much better today.")
    snap2 = _snap(db, visit)
    assert snap2.profile_payload.get("latest_route") == "HIGH-RISK"
    assert snap2.profile_payload["longitudinal_risk"]["severity"] == "HIGH"
    print("[PASS] HIGH persists over benign follow-up.")


def test_moderate_persists_over_benign(db, backend):
    """MODERATE-risk T1 -> benign T2 remains at least MODERATE."""
    visit = _make_visit(db)
    _send(db, backend, "u1", visit, "我最近不堪重负，整夜失眠。")
    snap1 = _snap(db, visit)
    sev1 = (snap1.profile_payload.get("longitudinal_risk") or {}).get("severity")
    assert sev1 == "MODERATE", f"setup failed: {sev1}"

    _send(db, backend, "u1", visit, "Thanks, today was fine.")
    snap2 = _snap(db, visit)
    sev2 = (snap2.profile_payload.get("longitudinal_risk") or {}).get("severity")
    assert sev2 in ("MODERATE", "HIGH"), f"downgraded to {sev2}"
    print("[PASS] MODERATE persists over benign follow-up.")


def test_low_stays_low(db, backend):
    """LOW-risk T1 -> benign T2 remains LOW (not artificially raised)."""
    visit = _make_visit(db)
    _send(db, backend, "u1", visit, "I'd like to discuss recent matters at work.")
    snap1 = _snap(db, visit)
    assert (snap1.profile_payload.get("longitudinal_risk") or {}).get("severity") in (None, "LOW")

    _send(db, backend, "u1", visit, "Deadlines have been manageable this week.")
    snap2 = _snap(db, visit)
    assert (snap2.profile_payload.get("longitudinal_risk") or {}).get("severity") in (None, "LOW")
    print("[PASS] LOW stays LOW.")


def test_new_acute_evidence_escalates(db, backend):
    """Benign T1 -> acute-risk T2 escalates to HIGH."""
    visit = _make_visit(db)
    _send(db, backend, "u1", visit, "I'd like to discuss recent matters at work.")
    _send(db, backend, "u1", visit,
          "Actually I feel completely hopeless and have thought about ending my life.")
    snap2 = _snap(db, visit)
    assert snap2.profile_payload.get("latest_route") == "HIGH-RISK"
    assert snap2.profile_payload["longitudinal_risk"]["severity"] == "HIGH"
    print("[PASS] New acute evidence escalates to HIGH.")


def test_no_cross_visit_leak(db, backend):
    """Carried risk does not leak between users/visits."""
    visit_a = _make_visit(db, user_id="user_a")
    visit_b = _make_visit(db, user_id="user_b")
    _send(db, backend, "user_a", visit_a,
          "I feel completely hopeless and have thought about ending my life.")
    assert _snap(db, visit_a).profile_payload["longitudinal_risk"]["severity"] == "HIGH"

    _send(db, backend, "user_b", visit_b, "I'd like to discuss recent matters at work.")
    snap_b = _snap(db, visit_b)
    assert (snap_b.profile_payload.get("longitudinal_risk") or {}).get("severity") in (None, "LOW")
    assert snap_b.profile_payload.get("latest_route") != "HIGH-RISK"
    print("[PASS] No risk state leaks between users.")
