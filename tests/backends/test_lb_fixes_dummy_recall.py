"""Live-browser fix regression tests — dummy backend recall (LB-M2, LB-M1).

LB-M2: recall trigger misses natural phrasings — E-03 "How much sleep
did I tell you I was getting?" and E-04 "What is the latest information
you have?" echoed instead of recalling.
LB-M1: cross-session recall is sleep-only — challenges / concentration /
routine / progress questions echoed instead of quoting prior turns.

All offline/dummy-mode. No live model calls, no network.
"""

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.backends.dummy_backend import DummyBackend


def _chat(*user_turns, end_after_turn=999):
    messages = [{"role": "system", "content": "counselor"}]
    messages.extend({"role": "user", "content": t} for t in user_turns)
    return asyncio.run(
        DummyBackend(default_end_after_turn=end_after_turn).chat_text(messages)
    )


def _chat_with_assistant_boundary(prior_turns, current_turns):
    """Messages shaped like the web engine's history: prior-visit user
    turns, then an assistant turn (the current visit's opening), then
    current-visit user turns — so the prior/current split is visible."""
    messages = [{"role": "system", "content": "counselor"}]
    messages.extend({"role": "user", "content": t} for t in prior_turns)
    messages.append({"role": "assistant", "content": "Welcome back."})
    messages.extend({"role": "user", "content": t} for t in current_turns)
    return asyncio.run(
        DummyBackend(default_end_after_turn=999).chat_text(messages)
    )


# ---------------------------------------------------------------- LB-M2 (E flow)
def test_e03_how_much_sleep_did_i_tell_you_returns_latest():
    """E-03: 'How much sleep did I tell you I was getting?' must state
    the latest sleep info (three hours recently), noting the earlier
    eight-hour claim."""
    reply = _chat(
        "I have been sleeping eight hours every night.",
        "Actually, I have been sleeping only three hours recently.",
        "How much sleep did I tell you I was getting?",
    )
    assert "three hours" in reply, reply
    assert "eight hours" in reply, reply
    assert "Thanks for sharing" not in reply, reply


def test_e04_latest_information_quotes_latest_turn():
    """E-04: 'What is the latest information you have?' quotes the most
    recent prior user turn verbatim."""
    reply = _chat(
        "I have been sleeping eight hours every night.",
        "Actually, I have been sleeping only three hours recently.",
        "What is the latest information you have?",
    )
    assert "three hours recently" in reply, reply
    assert "Thanks for sharing" not in reply, reply


def test_e04_fresh_visit_reports_nothing_recorded():
    reply = _chat("What is the latest information you have?")
    assert "don't have any information recorded" in reply, reply
    assert "Thanks for sharing" not in reply, reply


# ---------------------------------------------------------------- LB-M1 (B flow)
B_CONCERNS = (
    "I am preparing for an important examination.",
    "I am struggling to concentrate because I keep thinking about my future.",
    "I also feel that I am not making enough progress.",
)


def test_b04_three_concerns_lists_all_three():
    reply = _chat(*B_CONCERNS, "What were the three concerns I mentioned?")
    assert "examination" in reply, reply
    assert "concentrate" in reply, reply
    assert "future" in reply, reply
    assert "progress" in reply, reply
    assert "Thanks for sharing" not in reply, reply


def test_b05_concentration_blocker_is_future_worry():
    reply = _chat(
        *B_CONCERNS,
        "Which of those concerns did I say was affecting my concentration?",
    )
    assert "future" in reply, reply
    assert "concentrate" in reply, reply
    assert "Thanks for sharing" not in reply, reply


# ---------------------------------------------------------------- LB-M1 (C flow)
C_S1 = (
    "I am a university student.",
    "I have been experiencing academic stress.",
    "I find it difficult to concentrate when I worry about my future.",
    "I usually feel better when I follow a structured daily routine.",
)


def test_c05_main_challenges_quotes_prior_session():
    reply = _chat(*C_S1, "Do you remember the main challenges I discussed earlier?")
    assert "academic stress" in reply, reply
    assert "concentrate" in reply, reply
    assert "Thanks for sharing" not in reply, reply


def test_c06_concentration_quotes_prior_session():
    reply = _chat(*C_S1, "What did I mention about my concentration?")
    assert "concentrate" in reply, reply
    assert "future" in reply, reply
    assert "Thanks for sharing" not in reply, reply


def test_c07_routine_quotes_prior_session():
    reply = _chat(*C_S1, "What kind of routine did I say helps me?")
    assert "structured" in reply, reply
    assert "Thanks for sharing" not in reply, reply


def test_c10_current_routine_quotes_current_session_only():
    """C-10: 'current routine' quotes this session's flexible schedule,
    not the prior session's structured routine."""
    reply = _chat_with_assistant_boundary(
        list(C_S1),
        [
            "I want to correct something from our previous conversation. "
            "I am no longer following a structured daily routine.",
            "Recently, I have been trying a flexible schedule instead.",
            "What do you understand about my current routine?",
        ],
    )
    assert "flexible" in reply, reply
    assert "Thanks for sharing" not in reply, reply


def test_c11_previous_routine_quotes_prior_session_only():
    """C-11: 'previously' quotes the earlier structured routine, not the
    current session's flexible schedule."""
    reply = _chat_with_assistant_boundary(
        list(C_S1),
        [
            "I want to correct something from our previous conversation. "
            "I am no longer following a structured daily routine.",
            "Recently, I have been trying a flexible schedule instead.",
            "What did I previously tell you about my routine?",
        ],
    )
    assert "structured" in reply, reply
    assert "flexible" not in reply, reply
    assert "Thanks for sharing" not in reply, reply


def test_progress_recall_quotes_prior_turn():
    reply = _chat(
        "I also feel that I am not making enough progress.",
        "What progress did I mention?",
    )
    assert "progress" in reply, reply
    assert "Thanks for sharing" not in reply, reply


def test_recall_no_match_reports_nothing_recorded():
    """Control: with no matching prior turn, recall reports nothing
    recorded and invents nothing."""
    reply = _chat(
        "Hello, I would like to talk about work.",
        "What did I mention about my concentration?",
    )
    assert "haven't mentioned anything about your concentration" in reply, reply
    assert "Thanks for sharing" not in reply, reply


def test_sleep_recall_still_behaves_as_before():
    """Control: the generalised recall must not change the pinned sleep
    recall (earliest quote, duration denial only when no duration)."""
    reply = _chat(
        "I usually get about 6 hours of sleep.",
        "Remind me what I told you about my sleep.",
    )
    assert "6 hours of sleep" in reply, reply
    assert "no bedtimes, durations" not in reply, reply
    reply2 = _chat(
        "I have trouble falling asleep most nights.",
        "Remind me what I told you about my sleep.",
    )
    assert "no bedtimes, durations" in reply2, reply2
