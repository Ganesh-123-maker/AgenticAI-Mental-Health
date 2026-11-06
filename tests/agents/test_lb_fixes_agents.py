"""Live-browser fix regression tests — agents (LB-C1, LB-T1).

LB-C1: a routine/schedule correction outside the sleep/exam patterns
("I am no longer following a structured daily routine") got a bare echo
instead of a contradiction flag + clarification.
LB-T1: the clarification fallback produced "the background concerning
your background" when the target was "your background".

All offline/dummy-mode. No live model calls, no network.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.clarification_agent import (
    ClarificationAgent,
    _fallback_asked_targets,
)
from sample.agents.uncertainty_agent import UncertaintyAgent


# ---------------------------------------------------------------- LB-C1
def _unc_ctx(current, prior_user_turns):
    ctx = AgentContext(case_id="lbfix", modality="cbt", current_message=current)
    ctx.memory_output = {
        "main_problem": "Feeling low",
        "known_static_traits": {"medical_history": "None"},
        "current_goals": [], "missing_information": [], "session_recaps": [],
        "last_homework": [],
    }
    ctx.state_output = {
        "current_concern": current,
        "known_information": [f"[Current Statement] {current}"],
        "unknown_information": [], "confidence": 0.8,
    }
    ctx.prior_transcript = [{"role": "user", "content": t} for t in prior_user_turns]
    return ctx


def test_uncertainty_routine_correction_flagged():
    """C-08 exact turn: a routine correction is contradictory information."""
    ctx = _unc_ctx(
        "I want to correct something from our previous conversation. "
        "I am no longer following a structured daily routine.",
        ["I usually feel better when I follow a structured daily routine."],
    )
    out = UncertaintyAgent().run(ctx).payload
    assert out["status"] == "AMBIGUOUS", out
    assert "contradictory_information" in out["uncertainty_types"], out


def test_uncertainty_stopped_following_routine_flagged():
    ctx = _unc_ctx("I stopped following my routine.", [])
    out = UncertaintyAgent().run(ctx).payload
    assert "contradictory_information" in out["uncertainty_types"], out


def test_uncertainty_changed_routine_flagged():
    ctx = _unc_ctx("I changed my routine last week.", [])
    out = UncertaintyAgent().run(ctx).payload
    assert "contradictory_information" in out["uncertainty_types"], out


def test_uncertainty_changed_schedule_flagged():
    ctx = _unc_ctx("I changed my schedule.", [])
    out = UncertaintyAgent().run(ctx).payload
    assert "contradictory_information" in out["uncertainty_types"], out


def test_uncertainty_no_longer_doing_routine_flagged():
    ctx = _unc_ctx("I am no longer doing my morning routine.", [])
    out = UncertaintyAgent().run(ctx).payload
    assert "contradictory_information" in out["uncertainty_types"], out


def test_uncertainty_new_routine_as_fresh_fact_not_flagged():
    """Negative: 'I started a new routine' is a fresh fact, not a
    correction of an established routine."""
    ctx = _unc_ctx("I started a new routine this week.", [])
    out = UncertaintyAgent().run(ctx).payload
    assert "contradictory_information" not in out["uncertainty_types"], out


def test_uncertainty_unrelated_denial_not_flagged():
    """Negative: a denial about something else must not flag."""
    ctx = _unc_ctx(
        "Actually, I never had coffee this morning.",
        ["Hello, I am here for my first session."],
    )
    out = UncertaintyAgent().run(ctx).payload
    assert "contradictory_information" not in out["uncertainty_types"], out


def test_uncertainty_changed_mind_not_flagged():
    """Negative: changing one's mind about the exam mentions no routine."""
    ctx = _unc_ctx("I changed my mind about the exam.", [])
    out = UncertaintyAgent().run(ctx).payload
    assert "contradictory_information" not in out["uncertainty_types"], out


# ---------------------------------------------------------------- LB-T1
def _clar_ctx(uncertain_fields, missing_info, message="I find it difficult to concentrate."):
    ctx = AgentContext(
        case_id="lbfix", modality="cbt", current_message=message,
        prior_transcript=[], metadata={},
    )
    ctx.uncertainty_output = {
        "status": "UNCERTAIN",
        "uncertainty_types": ["unspecified_uncertainty"],
        "uncertain_fields": uncertain_fields,
        "missing_information": missing_info,
        "clarification_required": True,
        "priority": "LOW",
    }
    ctx.risk_output = {"severity": "LOW"}
    return ctx


def test_clarification_background_target_is_grammatical():
    """C-03/D-02 shape: a 'your background' target must not produce
    'the background concerning your background'."""
    ctx = _clar_ctx(
        ["known_static_traits"], ["known_static_traits (not populated)"],
    )
    out = ClarificationAgent().run(ctx).payload
    assert out["clarification_required"] is True, out
    assert out["target_information"] == ["known_static_traits"], out
    assert "background concerning your background" not in out["question"], out
    assert out["question"] == (
        "Regarding what you mentioned, could you tell me more about your background?"
    ), out


def test_clarification_normal_target_keeps_existing_wording():
    """Control: a normal target keeps the established 'background
    concerning' frame verbatim."""
    ctx = _clar_ctx(
        ["main_problem"], ["main_problem (not in profile or context)"],
    )
    out = ClarificationAgent().run(ctx).payload
    assert out["question"] == (
        "Regarding what you mentioned, could you tell me more about the "
        "background concerning the main concern you mentioned?"
    ), out


def test_fallback_asked_targets_recognises_grammatical_wording():
    """The anti-repeat guard must still recognise a 'your background'
    fallback question as having asked that slot, even though it no
    longer carries the 'background concerning' frame."""
    asked = _fallback_asked_targets([
        {"role": "assistant", "content": (
            "Regarding what you mentioned, could you tell me more about "
            "your background?"
        )},
    ])
    assert asked == ["known_static_traits"], asked


def test_fallback_asked_targets_still_recognises_old_wording():
    asked = _fallback_asked_targets([
        {"role": "assistant", "content": (
            "Regarding what you mentioned, could you tell me more about the "
            "background concerning the main concern you mentioned?"
        )},
    ])
    assert asked == ["main_problem"], asked
