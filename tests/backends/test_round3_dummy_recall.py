"""Round 3 regression tests — dummy backend recall (S2-D2, B-D2, B-D3).

All offline/dummy-mode. No live model calls, no network.
"""

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.backends.dummy_backend import DummyBackend


def _chat(*user_turns):
    messages = [{"role": "system", "content": "counselor"}]
    messages.extend({"role": "user", "content": t} for t in user_turns)
    return asyncio.run(DummyBackend().chat_text(messages))


def test_sleep_recall_does_not_deny_quoted_duration():
    """S2-D2: quoting 'five hours of sleep' and then denying any duration
    was mentioned contradicts the quote itself."""
    reply = _chat(
        "I have trouble falling asleep and I usually get about five hours of sleep.",
        "Remind me what I told you about my sleep.",
    )
    assert "five hours of sleep" in reply, reply
    assert "no bedtimes, durations" not in reply, reply


def test_sleep_recall_digit_duration_not_denied():
    reply = _chat(
        "I usually get about 6 hours of sleep.",
        "Remind me what I told you about my sleep.",
    )
    assert "6 hours of sleep" in reply, reply
    assert "no bedtimes, durations" not in reply, reply


def test_sleep_recall_keeps_denial_when_no_duration_mentioned():
    """S2-D2 control: when the quoted turn really mentions no duration or
    bedtime, the denial sentence is still accurate and stays."""
    reply = _chat(
        "I have trouble falling asleep most nights.",
        "Remind me what I told you about my sleep.",
    )
    assert "trouble falling asleep" in reply, reply
    assert "no bedtimes, durations" in reply, reply


def test_sleep_recall_present_tense_tell_you_about_triggers():
    """B-D2: 'What did I tell you about my sleep...' (present-tense
    'tell') must trigger recall, not the generic echo."""
    reply = _chat(
        "I am not sleeping well because of my exams and I keep waking up at 3am.",
        "What did I tell you about my sleep in my first session?",
    )
    assert "not sleeping well" in reply, reply
    assert "Thanks for sharing" not in reply, reply


def test_sleep_recall_quotes_earliest_detail_and_later_statement():
    """B-D3: recall must quote the EARLIEST sleep turn (the original
    fact), surface a later sleep statement too, and not claim the single
    quote is all that was recorded when two exist."""
    reply = _chat(
        "I am not sleeping well because of my exams and I keep waking up at 3am.",
        "Actually, I never had exam stress at all. I sleep perfectly every night.",
        "Can you remind me what I said about my sleep and exams?",
    )
    assert "not sleeping well" in reply, reply
    assert "sleep perfectly every night" in reply, reply
    assert "also mentioned sleep again later" in reply, reply
    assert "That is all I have recorded" not in reply, reply


def test_sleep_recall_nothing_mentioned_still_reports_nothing():
    """Control: with no prior sleep turn, recall still reports nothing
    recorded and invents nothing."""
    reply = _chat(
        "The breathing exercise helped me a little with my work stress.",
        "Remind me what I told you about my sleep.",
    )
    assert "haven't mentioned specific sleep details" in reply, reply
    assert "11 PM" not in reply and "six hours" not in reply, reply
