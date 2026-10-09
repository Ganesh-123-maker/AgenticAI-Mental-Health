"""Regression tests for explicit clarification-pending state in the web backend.

The backend previously inferred whether the user's message answers a
clarification question via string heuristics on the last assistant message
('?' in text, 'Could you', ...). It now uses explicit pipeline state:
previous route == UNCERTAIN *and* the persisted trace shows the
clarification agent produced a required question.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from web.backend.psychagent_engine import PsychAgentWebBackend
from web.backend.schemas import VisitPsychContextOut


def _ctx(route=None, clar_payload=None):
    profile = {}
    if route is not None:
        profile["latest_route"] = route
    if clar_payload is not None:
        profile["latest_agent_trace"] = [
            {"agent": "clarification_agent", "turn": 1, "payload": clar_payload}
        ]
    return VisitPsychContextOut(profile_payload=profile)


def _required_question():
    return {
        "question": "Have you ever received professional psychological evaluation before?",
        "questions": ["Have you ever received professional psychological evaluation before?"],
        "target_information": ["medical_history"],
        "clarification_required": True,
    }


def test_uncertain_with_question_pending():
    """UNCERTAIN + required clarification question -> answer expected."""
    assert PsychAgentWebBackend._clarification_pending(_ctx("UNCERTAIN", _required_question())) is True
    print("[PASS] UNCERTAIN + question -> pending.")


def test_uncertain_without_question_not_pending():
    """UNCERTAIN but no clarification question asked -> not an answer.

    This is the case the old '?' heuristic got wrong in reverse: an
    UNCERTAIN turn whose assistant message was not a clarification
    question must not capture the user's next message as an answer.
    """
    not_required = {"question": "", "questions": [], "clarification_required": False}
    assert PsychAgentWebBackend._clarification_pending(_ctx("UNCERTAIN", not_required)) is False
    # No clarification turn in the trace at all.
    assert PsychAgentWebBackend._clarification_pending(_ctx("UNCERTAIN", None)) is False
    print("[PASS] UNCERTAIN without a question -> not pending.")


def test_user_question_without_pending_not_answer():
    """No pending clarification -> user's question is a new message, not an answer."""
    assert PsychAgentWebBackend._clarification_pending(_ctx("CLEAR", _required_question())) is False
    assert PsychAgentWebBackend._clarification_pending(_ctx(None, None)) is False
    assert PsychAgentWebBackend._clarification_pending(None) is False
    print("[PASS] No pending clarification -> not treated as answer.")


def test_high_risk_not_pending():
    """HIGH-RISK flow unchanged: never treated as clarification-pending."""
    assert PsychAgentWebBackend._clarification_pending(_ctx("HIGH-RISK", _required_question())) is False
    print("[PASS] HIGH-RISK not pending.")


def test_pending_clears_after_route_changes():
    """After the answer is consumed and the route becomes CLEAR, pending resets.

    The state is derived from the latest persisted route+trace, so it
    self-clears without a separate flag to get out of sync.
    """
    # Turn N: UNCERTAIN with question -> pending.
    assert PsychAgentWebBackend._clarification_pending(_ctx("UNCERTAIN", _required_question())) is True
    # Turn N+1: answer consumed, route now CLEAR -> not pending.
    assert PsychAgentWebBackend._clarification_pending(_ctx("CLEAR", _required_question())) is False
    print("[PASS] Pending state clears after route changes.")


def test_pending_persists_across_uncertain_turns():
    """If clarification is still required after an answer, pending remains."""
    assert PsychAgentWebBackend._clarification_pending(_ctx("UNCERTAIN", _required_question())) is True
    # Second UNCERTAIN turn with a fresh question -> still pending.
    assert PsychAgentWebBackend._clarification_pending(_ctx("UNCERTAIN", _required_question())) is True
    print("[PASS] Pending persists across UNCERTAIN turns.")


def test_malformed_trace_fails_safe():
    """Malformed/missing trace never reports pending (fail closed)."""
    ctx = VisitPsychContextOut(profile_payload={"latest_route": "UNCERTAIN", "latest_agent_trace": "not-a-list"})
    assert PsychAgentWebBackend._clarification_pending(ctx) is False
    ctx2 = VisitPsychContextOut(profile_payload={"latest_route": "UNCERTAIN"})
    assert PsychAgentWebBackend._clarification_pending(ctx2) is False
    print("[PASS] Malformed trace fails safe.")
