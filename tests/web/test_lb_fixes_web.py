"""Live-browser fix regression tests — web engine (LB-D2W, LB-M1, LB-C1).

LB-D2W: after a RE-ROUTE turn (and after a clarification/question turn)
the stored latest_recommendation_weights must be cleared, not left as
the previous turn's options.
LB-M1: B/C cross-session recall flows end to end through the real
service layer + dummy backend.
LB-C1: the exact C-08 routine-correction turn routes UNCERTAIN with
contradictory_information and gets a clarification question, not echo.

Offline/dummy-mode only. Uses the real DB/session layer
(send_visit_message + in-memory SQLite + backend).
"""

import asyncio
import pathlib
import sys

import pytest
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from web.backend import models as M
from web.backend.psychagent_engine import PsychAgentWebBackend
from web.backend.services import visit_service as vs

FALSE_REASSURANCE = (
    "You are completely safe, rest assured you will not be harmed. Everything is fine."
)
SAFETY_QUESTION = (
    "Have you ever received professional psychological evaluation or treatment before, "
    "or do you have any relevant medical records?"
)
CONTRADICTION_QUESTION = (
    "You mentioned having these feelings on one hand while having different thoughts "
    "on the other. How do these two experiences interact in your mind?"
)


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


def _call_llm(backend):
    async def _inner(history, course, visit, visit_state, psych_context):
        return await backend.reply_from_visit(
            fallback_messages=[], course=course, visit=visit,
            visit_state=visit_state, psych_context=psych_context)
    return _inner


def _make_course(db, user_id, intake="Work stress", goal="Manage stress"):
    course = M.TherapyCourseRecord(
        user_id=user_id, school_id="cbt", title="T",
        intake_note=intake, goal_summary=goal)
    db.add(course); db.commit(); db.refresh(course)
    return course


def _send(db, backend, uid, visit, text):
    return asyncio.run(vs.send_visit_message(db, uid, visit.visit_id, text, _call_llm(backend)))


def _last_assistant_text(visit_state):
    for message in reversed(visit_state.messages):
        if message.role == "assistant":
            return message.text
    return ""


def _payload(result):
    return (result.visit.psych_context or {}).profile_payload or {}


def _route(result):
    return _payload(result).get("latest_route")


def _trace(result):
    return _payload(result).get("latest_agent_trace") or []


def _weights(result):
    return _payload(result).get("latest_recommendation_weights")


# ---------------------------------------------------------------- LB-D2W
def test_reroute_turn_clears_stored_weights(db, backend, monkeypatch):
    """W flow: a CLEAR turn stores weights; a T1 safety-question turn
    clears them; a RE-ROUTE turn leaves them cleared (None), so the
    InfoPanel cannot render the previous turn's options under the
    re-routed reply."""
    course = _make_course(db, "lbd2w_a")
    call_llm = _call_llm(backend)
    visit = asyncio.run(vs.create_visit(db, "lbd2w_a", course.course_id, call_llm=call_llm))

    r1 = _send(db, backend, "lbd2w_a", visit,
               "I have been feeling stressed about my exams lately and I am not sleeping well.")
    assert _route(r1) == "CLEAR", _last_assistant_text(r1.visit)
    w1 = _weights(r1)
    assert isinstance(w1, dict) and len(w1.get("options") or []) == 3, w1

    # T1: safety question (clarification turn) — engine returns no weights.
    r2 = _send(db, backend, "lbd2w_a", visit, "I was in hospital recently and I feel unsafe.")
    assert _route(r2) == "UNCERTAIN", _last_assistant_text(r2.visit)
    assert SAFETY_QUESTION in _last_assistant_text(r2.visit), _last_assistant_text(r2.visit)
    assert _weights(r2) is None, _weights(r2)

    # T2: false-reassurance draft -> supervisor RE-ROUTE, weights None.
    async def fake_chat(messages, purpose="counseling"):
        return FALSE_REASSURANCE

    monkeypatch.setattr(backend, "_chat_once", fake_chat)
    r3 = _send(db, backend, "lbd2w_a", visit,
               "I keep telling myself that you are completely safe and there is definitely "
               "no risk, but I still feel unsafe.")
    verdicts = [s.get("verdict") for s in _trace(r3) if s.get("step") == "final_web_supervision"]
    assert verdicts == ["RE-ROUTE"], verdicts
    assert FALSE_REASSURANCE not in _last_assistant_text(r3.visit)
    assert _weights(r3) is None, _weights(r3)

    # And a normal CLEAR turn afterwards stores fresh weights again.
    monkeypatch.undo()
    r4 = _send(db, backend, "lbd2w_a", visit, "I have been feeling stressed about my exams lately.")
    assert _route(r4) == "CLEAR", _last_assistant_text(r4.visit)
    assert isinstance(_weights(r4), dict), _weights(r4)
    print("[PASS] LB-D2W: RE-ROUTE + clarification turns clear stored weights; CLEAR re-stores.")


# ---------------------------------------------------------------- LB-M1 (B flow)
def test_b_flow_same_session_concern_recall(db, backend):
    """B flow: three concerns in one session, then recall probes quote them."""
    course = _make_course(db, "lbm1_b")
    call_llm = _call_llm(backend)
    visit = asyncio.run(vs.create_visit(db, "lbm1_b", course.course_id, call_llm=call_llm))
    _send(db, backend, "lbm1_b", visit, "I am preparing for an important examination.")
    _send(db, backend, "lbm1_b", visit,
          "I am struggling to concentrate because I keep thinking about my future.")
    _send(db, backend, "lbm1_b", visit, "I also feel that I am not making enough progress.")

    r4 = _send(db, backend, "lbm1_b", visit, "What were the three concerns I mentioned?")
    reply4 = _last_assistant_text(r4.visit)
    assert "examination" in reply4, reply4
    assert "concentrate" in reply4 and "future" in reply4, reply4
    assert "progress" in reply4, reply4

    r5 = _send(db, backend, "lbm1_b", visit,
               "Which of those concerns did I say was affecting my concentration?")
    reply5 = _last_assistant_text(r5.visit)
    assert "future" in reply5, reply5
    print("[PASS] LB-M1 B flow: same-session concern recall quotes all three concerns.")


# ---------------------------------------------------------------- LB-M1 (C flow)
def test_c_flow_cross_session_recall(db, backend):
    """C flow: S1 establishes stress/concentration/routine; S2 recall
    probes quote S1; S3 flexible-schedule establishment, then the current
    routine (flexible) and the previous routine (structured) are quoted
    distinctly."""
    course = _make_course(db, "lbm1_c")
    call_llm = _call_llm(backend)

    v1 = asyncio.run(vs.create_visit(db, "lbm1_c", course.course_id, call_llm=call_llm))
    _send(db, backend, "lbm1_c", v1, "I am a university student.")
    _send(db, backend, "lbm1_c", v1, "I have been experiencing academic stress.")
    _send(db, backend, "lbm1_c", v1,
          "I find it difficult to concentrate when I worry about my future.")
    _send(db, backend, "lbm1_c", v1,
          "I usually feel better when I follow a structured daily routine.")
    asyncio.run(vs.close_visit(db, "lbm1_c", v1.visit_id))

    v2 = asyncio.run(vs.create_visit(db, "lbm1_c", course.course_id, call_llm=call_llm))
    r5 = _send(db, backend, "lbm1_c", v2,
               "Do you remember the main challenges I discussed earlier?")
    assert "academic stress" in _last_assistant_text(r5.visit), _last_assistant_text(r5.visit)
    r6 = _send(db, backend, "lbm1_c", v2, "What did I mention about my concentration?")
    assert "concentrate" in _last_assistant_text(r6.visit), _last_assistant_text(r6.visit)
    r7 = _send(db, backend, "lbm1_c", v2, "What kind of routine did I say helps me?")
    assert "structured" in _last_assistant_text(r7.visit), _last_assistant_text(r7.visit)
    asyncio.run(vs.close_visit(db, "lbm1_c", v2.visit_id))

    v3 = asyncio.run(vs.create_visit(db, "lbm1_c", course.course_id, call_llm=call_llm))
    _send(db, backend, "lbm1_c", v3, "Recently, I have been trying a flexible schedule instead.")
    r10 = _send(db, backend, "lbm1_c", v3, "What do you understand about my current routine?")
    assert "flexible" in _last_assistant_text(r10.visit), _last_assistant_text(r10.visit)
    r11 = _send(db, backend, "lbm1_c", v3, "What did I previously tell you about my routine?")
    reply11 = _last_assistant_text(r11.visit)
    assert "structured" in reply11, reply11
    assert "flexible" not in reply11, reply11
    print("[PASS] LB-M1 C flow: cross-session recall quotes the right routine per scope.")


# ---------------------------------------------------------------- LB-C1 (C-08)
def test_c08_routine_correction_gets_clarification_not_echo(db, backend):
    """C-08 exact turn in a session-3 flow: after the routine was
    established in S1, the correction must route UNCERTAIN with
    contradictory_information and ask a clarification question."""
    course = _make_course(db, "lbc1_c")
    call_llm = _call_llm(backend)

    v1 = asyncio.run(vs.create_visit(db, "lbc1_c", course.course_id, call_llm=call_llm))
    _send(db, backend, "lbc1_c", v1,
          "I usually feel better when I follow a structured daily routine.")
    asyncio.run(vs.close_visit(db, "lbc1_c", v1.visit_id))

    v2 = asyncio.run(vs.create_visit(db, "lbc1_c", course.course_id, call_llm=call_llm))
    r = _send(db, backend, "lbc1_c", v2,
              "I want to correct something from our previous conversation. "
              "I am no longer following a structured daily routine.")
    reply = _last_assistant_text(r.visit)
    assert _route(r) == "UNCERTAIN", reply
    assert "Thanks for sharing" not in reply, reply
    assert CONTRADICTION_QUESTION in reply, reply
    # LB-C1 web half: "I want to correct..." starts with "I want to", so
    # the direct-request shortcut used to wave this correction through to
    # counseling. It must not fire on a detected contradiction.
    assert not [
        s for s in _trace(r)
        if s.get("step") == "clarification_budget"
        and s.get("reason") == "direct_low_risk_request"
    ], _trace(r)
    types = []
    for step in _trace(r):
        payload = step.get("payload") or {}
        if isinstance(payload, dict):
            types.extend(payload.get("uncertainty_types") or [])
    assert "contradictory_information" in types, _trace(r)
    print("[PASS] LB-C1: C-08 routine correction routes UNCERTAIN with a clarification question.")
