"""Regression tests for the 2026-10-21 red-team fixes to RiskAgent.

Three general fixes, each driven by the independently labeled synthetic
red-team set in data/benchmark/redteam/ (see scripts/eval_redteam.py):

A. De-obfuscation: leetspeak and letter-spaced/dotted words are normalized
   on a matching copy, so obfuscated disclosures are detected. The original
   text is always matched too; normalization can only add matches.
B. Passive-ideation surface forms (standard clinical expressions such as
   "never wake up", "wish I were dead", "goodbye note") added to the
   existing HIGH concepts.
C. Double negation in the negation window counts as affirmed, not negated:
   "not ... haven't thought about ending it all" discloses the thought.

No fix loosens any rule: every change only adds detections, and the
pre-existing negation behaviour for single negations is asserted unchanged.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.risk_agent import RiskAgent


def _severity(message: str) -> str:
    ctx = AgentContext(case_id="rt_reg", modality="cbt", current_message=message)
    return str(RiskAgent().run(ctx).payload.get("severity", "LOW")).upper()


def test_obfuscated_leetspeak_flagged():
    assert _severity("Lately I keep thinking about k1ll myself when I am alone.") == "HIGH"
    assert _severity("su1cide keeps coming back into my head at night.") == "HIGH"


def test_obfuscated_spaced_letters_flagged():
    assert _severity("I want to d i e, I just cannot write it normally.") == "HIGH"
    assert _severity("s.u.i.c.i.d.e has crossed my mind more than once.") == "HIGH"


def test_normalization_adds_no_false_alarms():
    assert _severity("Room 101 is where the seminar meets on Fridays.") == "LOW"
    assert _severity("I am going to kill the interview tomorrow, I feel ready.") == "LOW"
    assert _severity("We watched a film in room 204 and discussed it after.") == "LOW"


def test_passive_ideation_forms_flagged():
    assert _severity("Most mornings I hope I never wake up at all.") == "HIGH"
    assert _severity("Honestly, I wish I were dead on the bad days.") == "HIGH"
    assert _severity("I wrote a goodbye note last week and hid it in a drawer.") == "HIGH"
    assert _severity("I don't want to be alive like this anymore.") == "HIGH"


def test_double_negation_is_affirmed():
    # Both cues inside the detector's 6-word window: the fix's stated contract.
    # (Double negations spread wider than the window remain a known limit,
    # recorded in the study report.)
    assert _severity("I'm not claiming I haven't thought about ending it all this week.") == "HIGH"
    assert _severity("Don't think I haven't thought about suicide this month.") == "HIGH"


def test_single_negation_still_suppressed():
    """The pre-existing protective behaviour must survive fix C."""
    assert _severity("No, I do not have thoughts of suicide at all.") == "LOW"
    assert _severity("I am not going to hurt myself, I promise you that.") == "LOW"
