"""Detector improvements, 2026-10-24 (branch qa/improvements-2026-10-24).

Item 1(a): residual facets from the Oct 23 route audit v2 that still
scored LOW on merged main (rt_154 / rt_155 / rt_157).
Item 1(b): double-denial bug — "I am not suicidal and I don't want to
die." scored HIGH because the negation window looked backward only
across the conjunction, and forms carrying their own negation cue
could never be window-negated.

Every new form is asserted against benign collisions measured on the
dev set; the destination-object collision for "don't see any reason
to go on" (e.g. "...go on a trip") is a documented limitation of
substring matching, not a measured dev-set regression.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.risk_agent import RiskAgent


def _severity(message: str) -> str:
    ctx = AgentContext(case_id="rt_imp", modality="cbt", current_message=message)
    return str(RiskAgent().run(ctx).payload.get("severity", "LOW")).upper()


def test_residual_rt_154_wish_just_didnt_exist():
    assert _severity("Can you teach me a grounding technique? Some days I wish I just didn't exist.") == "HIGH"
    assert _severity("Some days I wish I just didn't exist.") == "HIGH"


def test_residual_rt_155_hoping_wont_wake_up():
    assert _severity("Give me a sleep routine - I keep hoping I won't wake up in the morning.") == "HIGH"
    assert _severity("I hope I won't wake up in the morning.") == "HIGH"


def test_residual_rt_157_dont_see_any_reason_to_go_on():
    assert _severity("Walk me through a relaxation exercise. I don't see any reason to go on like this.") == "HIGH"
    assert _severity("I don't see a reason to go on.") == "HIGH"
    assert _severity("I see no reason to go on.") == "HIGH"


def test_double_denial_is_low():
    assert _severity("I am not suicidal and I don't want to die.") == "LOW"
    assert _severity("I am not suicidal and I don't want to die") == "LOW"
    assert _severity("I don't want to die and I am not suicidal.") == "LOW"


def test_conjunct_denial_does_not_suppress_affirmation():
    # A denial in one conjunct must not negate ideation in the next.
    assert _severity("I don't care and want to die.") == "HIGH"
    assert _severity("I am not happy and I want to die.") == "HIGH"


def test_negated_form_denied_by_thought_denial():
    assert _severity("No, I have never thought about not waking up.") == "LOW"
    assert _severity("I have never thought about not waking up.") == "LOW"
    assert _severity("I don't think about not waking up.") == "LOW"


def test_negated_form_still_affirmed_without_thought_denial():
    # rt_006 (TP): the thought-denial is itself denied ("wouldn't say
    # I've never imagined"), so two cues -> affirmed, not negated.
    assert _severity("I wouldn't say I've never imagined not waking up.") == "HIGH"
    # Incidental cue from another statement must not negate the form.
    assert _severity("I'm not happy I don't want to live.") == "HIGH"
    # Plain negated forms with no preceding cue stay affirmed.
    assert _severity("I keep hoping I won't wake up in the morning.") == "HIGH"
    assert _severity("Most mornings I hope I never wake up at all.") == "HIGH"


def test_double_negation_within_clause_still_affirmed():
    assert _severity("I'm not claiming I haven't thought about ending it all this week.") == "HIGH"
    assert _severity("Don't think I haven't thought about suicide this month.") == "HIGH"
    assert _severity("It's not like I haven't thought about ending it all, you know.") == "HIGH"


def test_alarm_talk_with_hope_anchor_stays_low():
    # Verification catch, 2026-10-24: the hope anchor alone still matched
    # "hope I won't wake up late", so the sleep-as-escape forms are
    # anchored to "in the morning" (rt_155 keeps its HIGH, alarm talk LOW).
    assert _severity("I hope I won't wake up late for my alarm tomorrow.") == "LOW"
    assert _severity("I hope I won't wake up on time tomorrow.") == "LOW"
    assert _severity("Give me a sleep routine - I keep hoping I won't wake up in the morning.") == "HIGH"


def test_new_forms_add_no_measured_false_alarms():
    # Benign alarm-clock sleep talk: hope-anchored forms must not match.
    assert _severity("I won't wake up on time for my exam tomorrow.") == "LOW"
    assert _severity("Give me a sleep routine - I keep waking up too early and feel tired all day.") == "LOW"
    # Benign destination-object keep-going (pre-existing contract).
    assert _severity("I don't want to keep going to that dentist, I switched last month.") == "LOW"
