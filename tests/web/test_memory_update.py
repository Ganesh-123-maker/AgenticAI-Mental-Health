"""Day 2 tests: live-path memory update behavior in the web backend.

Covers the previously untested memory layer: static-trait merge/extract/
overlay rules (including placeholder filtering) and the per-visit snapshot
builder that carries focus, homework, and history from one visit to the
next. These are the functions a Session 2 recall probe depends on: if the
snapshot builder did not inherit the previous visit's focus and homework,
longitudinal recall would have nothing to recall from.
"""

import json
import pathlib
import sys

import pytest
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from web.backend import models as M
from web.backend.services import visit_service as vs


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_course_visit(db, visit_no, summary=None):
    course = M.TherapyCourseRecord(
        user_id="u1", school_id="cbt", title="Test",
        intake_note="Work stress", goal_summary="Manage stress",
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    visit = M.TherapyVisitRecord(
        course_id=course.course_id, visit_no=visit_no,
        stage_key_snapshot="assessment", summary=summary,
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)
    return course, visit


def test_merge_static_traits_placeholder_never_clobbers():
    # "Unknown" (capitalised, as stored profiles write it) must not wipe a
    # real value merged in from an earlier session.
    base = {"name": "Asha", "medical_history": "Asthma", "occupation": "Nurse"}
    override = {"medical_history": "Unknown", "occupation": "Teacher", "age": "UNKNOWN"}
    merged = vs._merge_static_traits(base, override)
    assert merged == {"name": "Asha", "medical_history": "Asthma", "occupation": "Teacher"}


def test_extract_global_base_profile_filters_placeholders_and_caps_growth():
    client_info = {
        "static_traits": {"name": "Asha", "age": "Unknown",
                          "medical_history": "unknown", "gender": "Female"},
        "growth_experiences": [f"exp {i}" for i in range(25)],
        "main_problem": "Stress",
        "topic": "Work",
    }
    extracted = vs._extract_global_base_profile(client_info)
    assert extracted["static_traits"] == {"name": "Asha", "gender": "Female"}
    assert extracted["growth_experiences"] == [f"exp {i}" for i in range(20)]
    assert "main_problem" not in extracted
    assert "topic" not in extracted


def test_merge_global_base_profile_incoming_wins_and_growth_fallback():
    existing = {"static_traits": {"name": "Old"}, "growth_experiences": ["old exp"]}
    incoming = {"static_traits": {"name": "New"}}
    merged = vs._merge_global_base_profile(existing, incoming)
    assert merged["static_traits"]["name"] == "New"
    assert merged["growth_experiences"] == ["old exp"]


def test_overlay_global_base_profile_course_wins():
    course_profile = {"static_traits": {"name": "Course Name"},
                      "growth_experiences": ["course exp"]}
    global_base = {"static_traits": {"name": "Global Name", "occupation": "Teacher"},
                   "growth_experiences": ["global exp"]}
    profile = vs._overlay_global_base_profile(course_profile, global_base)
    assert profile["static_traits"]["name"] == "Course Name"
    assert profile["static_traits"]["occupation"] == "Teacher"
    assert profile["growth_experiences"] == ["course exp"]


def test_snapshot_visit1_uses_default_focus(db):
    course, visit1 = _make_course_visit(db, 1)
    snap = vs.build_derived_psych_context_snapshot(db, course, visit1)
    assert snap["session_focus"] == list(vs.SESSION_FOCUS_DEFAULT)
    assert snap["history"] == []
    assert snap["homework"] == []


def test_snapshot_visit2_inherits_previous_focus_and_homework(db):
    course, visit1 = _make_course_visit(db, 1, summary="First summary")
    ctx1 = M.VisitPsychContextRecord(
        visit_id=visit1.visit_id,
        client_info_json=json.dumps({
            "next_session_focus": ["Focus A", "Focus B"],
            "static_traits": {"name": "Asha"},
        }),
        session_focus_json=json.dumps(["Old focus"]),
        history_json=json.dumps([]),
        homework_json=json.dumps(["HW1"]),
        summary_payload_json=json.dumps({}),
        profile_payload_json=json.dumps({}),
    )
    db.add(ctx1)
    db.commit()
    visit2 = M.TherapyVisitRecord(
        course_id=course.course_id, visit_no=2,
        stage_key_snapshot="assessment",
    )
    db.add(visit2)
    db.commit()
    db.refresh(visit2)

    snap = vs.build_derived_psych_context_snapshot(db, course, visit2)
    assert snap["session_focus"] == ["Focus A", "Focus B"]
    assert snap["homework"] == ["HW1"]
    assert len(snap["history"]) == 1
    assert snap["history"][0]["visit_no"] == 1
    assert snap["client_info"]["course_id"] == course.course_id
    assert snap["client_info"]["static_traits"]["name"] == "Asha"
