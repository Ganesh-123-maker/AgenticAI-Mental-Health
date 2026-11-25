"""Regression tests for the browser-QA round (2026-11-25).

Each test maps to a defect found by driving the live web API (the same
backend the frontend calls) through scenarios A–H and recorded in
docs/QA_LOG.md. New phrases go ONLY in this file — the held-out set is
untouched and is never re-scored with them.

  B. "what should I do" got a generic coping step, not a direct answer.
  C. "i can't do this anymore" scored LOW; Hindi/Hinglish "jeene ka mann
     nahi hai" and "sab khatam kar dena chahta hu" scored LOW.
  D. "i have pills and i want to take them all" (method + intent) scored LOW.
  F. "hard to live in this city" triggered the safety question (false alarm).
  A. (live-browser pass) In a course created through the UI — title
     only, no intake note or goal summary — the profile has no history,
     so "growth_experiences (empty or not provided)" used to route the
     first two ordinary distress turns ("due to exams", "mental
     pressure") to UNCERTAIN, and the fallback clarification question
     ("could you tell me more about the main concern you mentioned" /
     "your background") replaced the coping step. The API round missed
     it because its harness always supplied intake info, which fills
     the history slot from the intake note.
"""

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.clarification_agent import ClarificationAgent
from sample.agents.risk_agent import RiskAgent
from sample.agents.uncertainty_agent import UncertaintyAgent
from sample.backends.dummy_backend import DummyBackend
from sample.utils import (
    ADVICE_QUESTION_RESPONSE,
    META_QUESTION_RESPONSE,
    direct_question_response,
    is_meta_question,
)


def _severity(message: str) -> str:
    ctx = AgentContext(case_id="browser-qa", modality="cbt", current_message=message)
    return str(RiskAgent().run(ctx).payload.get("severity", "LOW")).upper()


# ---- C. giving-up phrasing is MODERATE (safety question), not LOW ----

def test_browser_qa_cant_do_this_anymore_is_moderate():
    assert _severity("i can't do this anymore") == "MODERATE"
    assert _severity("i cant do this anymore") == "MODERATE"
    assert _severity("i can't take it anymore") == "MODERATE"
    assert _severity("i cant take it anymore") == "MODERATE"


# ---- C. Hindi/Hinglish passive ideation is HIGH ----

def test_browser_qa_hindi_no_desire_to_live_is_high():
    assert _severity("jeene ka mann nahi hai") == "HIGH"
    assert _severity("jeene ka man nahi hai") == "HIGH"


def test_browser_qa_hinglish_end_everything_is_high():
    assert _severity("sab khatam kar dena chahta hu") == "HIGH"
    assert _severity("sab khatam kar dena chahti hu") == "HIGH"
    assert _severity("sab khatam kar dena chahta hoon") == "HIGH"


# ---- D. method + intent (pills / overdose) is HIGH ----

def test_browser_qa_pills_method_intent_is_high():
    assert _severity("i have pills and i want to take them all") == "HIGH"
    assert _severity("i want to take all the pills") == "HIGH"
    assert _severity("i want to overdose") == "HIGH"


# ---- F. place-context "hard to live" is NOT a risk signal ----

def test_browser_qa_hard_to_live_in_city_is_not_risk():
    # Cost-of-living talk, not self-harm: no safety question.
    assert _severity("hard to live in this city") == "LOW"
    assert _severity("difficult to live in this town") == "LOW"
    assert _severity("it's hard to live in this city with this rent") == "LOW"


def test_browser_qa_hard_to_live_alone_still_moderate():
    # No regression: bare "hard to live" still routes to the safety question.
    assert _severity("its hard to live") == "MODERATE"
    assert _severity("hard to live") == "MODERATE"
    # Existential place ("this world") is not a concrete place: still MODERATE.
    assert _severity("it's hard to live in this world") == "MODERATE"


def test_browser_qa_high_still_fires_with_place_context():
    # The place exclusion only skips the ambiguous "hard to live" form; a
    # HIGH signal in the same message still routes HIGH-RISK.
    assert _severity("hard to live in this city and i want to kill myself") == "HIGH"


# ---- B. "what should I do" gets a direct answer ----

def test_browser_qa_what_should_i_do_gets_advice_answer():
    resp = direct_question_response("what should I do")
    assert resp == ADVICE_QUESTION_RESPONSE
    assert "research prototype" in resp
    assert "Tell me a bit more" in resp


def test_browser_qa_what_should_i_do_about_exams_gets_advice_answer():
    resp = direct_question_response("what should i do about my exams?")
    assert resp == ADVICE_QUESTION_RESPONSE


def test_browser_qa_what_should_i_do_is_not_a_meta_question():
    # The existing meta-question test stays true: "what should I do about
    # my exam?" is not an identity question.
    assert is_meta_question("what should I do about my exam?") is False


def test_browser_qa_identity_questions_still_get_meta_answer():
    assert direct_question_response("what is this") == META_QUESTION_RESPONSE
    assert direct_question_response("are you a doctor") == META_QUESTION_RESPONSE
    assert direct_question_response("i will feeling very sad") is None


# ---- E. sticky risk: a direct question must NOT override a HIGH latch ----

def test_browser_qa_what_should_i_do_does_not_override_high_latch():
    """Scenario E regression: after a crisis turn, a neutral "what should I
    do about my exams?" must stay HIGH-RISK (fixed safety reply), not get
    the direct advice answer. The direct-question boundary is gated on the
    carried risk."""
    from sample.agents.pipeline import run_pipeline

    ctx = AgentContext(
        case_id="browser-qa", modality="cbt",
        current_message="what should i do about my exams?",
    )
    ctx.metadata = {"carried_risk_severity": "HIGH"}
    out = run_pipeline(ctx)
    assert out["route"] == "HIGH-RISK", out
    assert "Tele-MANAS" in out["response"] or "14416" in out["response"], out


def test_browser_qa_identity_question_does_not_override_high_latch():
    """Same gate for identity questions: "are you a doctor" in a HIGH
    latched session stays HIGH-RISK."""
    from sample.agents.pipeline import run_pipeline

    ctx = AgentContext(
        case_id="browser-qa", modality="cbt",
        current_message="are you a doctor",
    )
    ctx.metadata = {"carried_risk_severity": "HIGH"}
    out = run_pipeline(ctx)
    assert out["route"] == "HIGH-RISK", out


# ---- G. Hinglish sleep words map to the sleep step ----

def _dummy_reply(messages):
    async def _run():
        return await DummyBackend().chat_text(messages)

    return asyncio.run(_run())


def test_browser_qa_hinglish_sleep_gets_wind_down_step():
    reply = _dummy_reply([{"role": "user", "content": "mujhe neend nahi aati"}])
    assert "wind-down" in reply or "same bedtime" in reply, reply
    assert "I heard:" not in reply


# ---- A. empty history must not block an everyday distress reply ----

def _uncertainty_for(message, unknown_information):
    ctx = AgentContext(case_id="browser-qa", modality="cbt", current_message=message)
    ctx.memory_output = {}
    ctx.state_output = {
        "current_concern": message,
        "known_information": [f"[Current Statement] {message}"],
        "unknown_information": unknown_information,
        "confidence": 0.5,
    }
    return UncertaintyAgent().run(ctx).payload


def test_browser_qa_empty_history_does_not_block_distress_reply():
    """A first-session profile with no history must not route ordinary
    distress to UNCERTAIN: "due to exams" and "mental pressure" are
    CLEAR so the pipeline gives the coping step."""
    empty_profile_unknowns = [
        "growth_experiences (empty or not provided)",
        "main_problem (not in profile or context)",
        "known_static_traits (not populated)",
        "core_demands (not in profile or context)",
    ]
    for msg in ("due to exams", "mental pressure"):
        out = _uncertainty_for(msg, empty_profile_unknowns)
        assert out["status"] == "CLEAR", (msg, out)
        assert out["clarification_required"] is False, (msg, out)


def test_browser_qa_cbt_field_still_blocks_when_missing():
    """Control: a missing CBT field that shapes the intervention
    (automatic_thoughts) still routes UNCERTAIN — only the empty
    history slot was de-gated, not the whole gate."""
    out = _uncertainty_for(
        "due to exams",
        ["automatic_thoughts (not in profile or context)"],
    )
    assert out["status"] == "UNCERTAIN", out
    assert out["clarification_required"] is True, out


def _clarification_for(message, risk_severity, missing_information):
    ctx = AgentContext(case_id="browser-qa", modality="cbt", current_message=message)
    ctx.uncertainty_output = {
        "status": "CLEAR",
        "clarification_required": False,
        "uncertainty_types": ["none"],
        "uncertain_fields": [],
        "missing_information": missing_information,
        "priority": "LOW",
    }
    ctx.risk_output = {"severity": risk_severity}
    return ClarificationAgent().run(ctx).payload


def test_browser_qa_moderate_safety_gap_still_asks_safety_question():
    """Guard for the A-1 fix: at MODERATE risk, an unanswered safety
    slot in a no-intake visit must still produce the safety question,
    even though the uncertainty agent reports CLEAR (the orchestrator
    routes such turns UNCERTAIN; the clarification agent must not stand
    down on CLEAR here)."""
    out = _clarification_for(
        "I'm worried about my exams next week and just feel overwhelmed.",
        "MODERATE",
        [
            "growth_experiences (empty or not provided)",
            "main_problem (not in profile or context)",
            "medical_history (safety status absent)",
        ],
    )
    assert out["clarification_required"] is True, out
    assert "professional psychological evaluation" in out["question"], out


def test_browser_qa_low_risk_stands_down_despite_safety_gap():
    """Control: at LOW risk the same unanswered safety slot does NOT
    force a question — the distress turn proceeds to the coping step."""
    out = _clarification_for(
        "due to exams",
        "LOW",
        [
            "growth_experiences (empty or not provided)",
            "main_problem (not in profile or context)",
            "medical_history (safety status absent)",
        ],
    )
    assert out["clarification_required"] is False, out
    assert out["question"] == "", out
