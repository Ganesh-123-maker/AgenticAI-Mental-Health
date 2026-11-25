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
  G. "mujhe neend nahi aati" (Hinglish: I can't sleep) got the default
     reply instead of the sleep wind-down step.
"""

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.risk_agent import RiskAgent
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
