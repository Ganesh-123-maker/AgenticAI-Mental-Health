"""Round 3 regression tests — defects found in Stage 2 verification.

Covers (by defect id):
- C-NEW1 (regression): reassessment over-triggering on AMBIGUOUS — an
  informative clarification answer to a vague opening must resolve to
  CLEAR; only a genuine contradiction (contradictory_information) stays
  UNCERTAIN. Also Stream C O3: a CLEAR reassessment must not carry
  populated uncertain_fields.
- C-NEW2 (pre-existing, high): supervisor false-reassurance guard must
  fire when missing_information carries the medical/safety item, even on
  a CLEAR turn; benign drafts must still ALLOW.
- B-D1: within-session retraction of a distress claim ("Actually, I never
  had exam stress at all.") must be flagged contradictory; unrelated
  denials and additive statements must not be.
- S2-D4: bare vague affect ("I feel bad.") gets a question that does not
  presuppose a referent; deictic vagueness keeps its question.
- S2-D5: at MODERATE risk the contradiction question is asked before the
  safety question; at HIGH risk the safety question stays first.

All offline/dummy-mode. No live model calls, no network.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import AgentContext
from sample.agents.clarification_agent import ClarificationAgent
from sample.agents.memory_agent import MemoryAgent
from sample.agents.pipeline import run_pipeline
from sample.agents.risk_agent import RiskAgent
from sample.agents.safety_supervisor import SafetySupervisor
from sample.agents.state_agent import StateAgent
from sample.agents.uncertainty_agent import UncertaintyAgent

ROOT = pathlib.Path(__file__).parent.parent.parent
REAL_PROFILE = json.loads((ROOT / "assets/profiles/cbt/sample/412.json").read_text())


# ---------------------------------------------------------------- C-NEW1
def test_reassessment_informative_answer_to_vague_opening_resolves_clear():
    """C-NEW1: the Round 2 D-03 branch fired on any reassessed AMBIGUOUS,
    so an informative answer to a vague opening stayed UNCERTAIN (was
    CLEAR on 4068b2bc). It must resolve to CLEAR now."""
    ctx = AgentContext(
        case_id="r3", modality="cbt",
        current_message="It's about... that thing, you know.",
        full_profile=REAL_PROFILE,
    )
    out = run_pipeline(
        ctx, clarification_answer="It started six months ago after a conflict with my manager."
    )
    assert out["route"] == "CLEAR", out


def test_reassessment_genuine_sleep_contradiction_stays_uncertain():
    """C-NEW1 control: the D-03 case the branch was written for — a real
    contradiction in the answer — must still stay UNCERTAIN."""
    ctx = AgentContext(
        case_id="r3", modality="cbt",
        current_message="Actually, I haven't slept properly in weeks.",
        prior_transcript=[{"role": "user", "content": "I sleep fine, no problems at all."}],
        full_profile=REAL_PROFILE,
    )
    out = run_pipeline(
        ctx, clarification_answer="Actually, I haven't slept properly in weeks."
    )
    assert out["route"] == "UNCERTAIN", out


def test_reassessment_uninformative_answer_stays_uncertain():
    """C-NEW1 control: an uninformative answer must still stay UNCERTAIN."""
    ctx = AgentContext(
        case_id="r3", modality="cbt",
        current_message="It's about... that thing, you know.",
        full_profile=REAL_PROFILE,
    )
    out = run_pipeline(ctx, clarification_answer="I don't know.")
    assert out["route"] == "UNCERTAIN", out


def test_reassessment_clear_payload_has_empty_uncertain_fields():
    """Stream C O3: the reassessment else-branch forced status CLEAR while
    leaving uncertain_fields populated — the same self-contradictory
    payload shape the D6 fix removed in UncertaintyAgent."""
    ctx = AgentContext(
        case_id="r3", modality="cbt",
        current_message="It's about... that thing, you know.",
        full_profile=REAL_PROFILE,
    )
    out = run_pipeline(
        ctx, clarification_answer="It started six months ago after a conflict with my manager."
    )
    assert out["route"] == "CLEAR"
    reassessed = out["context"].uncertainty_output
    assert reassessed["status"] == "CLEAR"
    assert reassessed["uncertain_fields"] == [], reassessed
    assert reassessed["uncertainty_types"] == ["none"], reassessed


# ---------------------------------------------------------------- C-NEW2
def _supervisor_ctx_cnew2(missing_information):
    ctx = AgentContext(case_id="r3", modality="cbt", current_message="Can you help me sleep better?")
    ctx.routing_output = {"route": "CLEAR"}
    ctx.risk_output = {"severity": "LOW", "risk_signals": []}
    ctx.uncertainty_output = {
        "status": "CLEAR", "uncertain_fields": [], "uncertainty_types": ["none"],
        "missing_information": missing_information,
    }
    return ctx


FALSE_REASSURANCE = (
    "You are completely safe, rest assured you will not be harmed. Everything is fine."
)


def test_supervisor_false_reassurance_flagged_on_clear_with_missing_medical_item():
    """C-NEW2: the supervisor never read missing_information, so a CLEAR
    turn carrying 'medical_history (safety status absent)' ALLOWed an
    absolute-safety draft verbatim. It must RE-ROUTE now."""
    ctx = _supervisor_ctx_cnew2(["medical_history (safety status absent)"])
    out = SafetySupervisor().run(ctx, FALSE_REASSURANCE).payload
    assert out["verdict"] == "RE-ROUTE", out
    assert "completely safe" not in (out.get("revised_response") or "").lower()
    assert "will not be harmed" not in (out.get("revised_response") or "").lower()


def test_supervisor_benign_draft_still_allowed_with_missing_medical_item():
    """C-NEW2 control: the missing-item gate only fires on absolute-safety
    drafts — a benign draft on the same CLEAR turn must still ALLOW (no
    false escalation on genuinely clear turns)."""
    ctx = _supervisor_ctx_cnew2(["medical_history (safety status absent)"])
    out = SafetySupervisor().run(
        ctx, "Let's explore one concrete coping step for this week."
    ).payload
    assert out["verdict"] == "ALLOW", out


def test_supervisor_benign_draft_allowed_without_missing_item():
    ctx = _supervisor_ctx_cnew2([])
    out = SafetySupervisor().run(
        ctx, "Let's explore one concrete coping step for this week."
    ).payload
    assert out["verdict"] == "ALLOW", out


# ---------------------------------------------------------------- B-D1
def _unc_ctx(current, prior_user_turns):
    ctx = AgentContext(case_id="r3", modality="cbt", current_message=current)
    ctx.memory_output = {
        "main_problem": "Feeling low",
        "known_static_traits": {"medical_history": "None"},
        "current_goals": [], "missing_information": [], "session_recaps": [],
        "last_homework": [],
    }
    ctx.state_output = {
        "current_concern": current,
        "known_information": [f"[Current Statement] {current}"],
        "unknown_information": [],
        "confidence": 0.8,
    }
    ctx.prior_transcript = [{"role": "user", "content": t} for t in prior_user_turns]
    return ctx


def test_uncertainty_retraction_of_exam_stress_flagged():
    """B-D1: within-session retraction of a just-stated problem ('Actually,
    I never had exam stress at all.') must be flagged contradictory."""
    ctx = _unc_ctx(
        "Actually, I never had exam stress at all.",
        ["Hello, I have been feeling anxious about my exams lately and I am not sleeping well because of my exams and I keep waking up at 3am."],
    )
    out = UncertaintyAgent().run(ctx).payload
    assert out["status"] == "AMBIGUOUS"
    assert "contradictory_information" in out["uncertainty_types"], out


def test_uncertainty_sleep_retraction_flagged():
    ctx = _unc_ctx(
        "Actually, I never had exam stress at all. I sleep perfectly every night.",
        ["I am not sleeping well because of my exams and I keep waking up at 3am."],
    )
    out = UncertaintyAgent().run(ctx).payload
    assert "contradictory_information" in out["uncertainty_types"], out


def test_uncertainty_not_anxious_retraction_flagged():
    ctx = _unc_ctx(
        "Actually, I'm not anxious at all.",
        ["I have been feeling really anxious about my exams lately."],
    )
    out = UncertaintyAgent().run(ctx).payload
    assert "contradictory_information" in out["uncertainty_types"], out


def test_uncertainty_unrelated_denial_not_flagged():
    """B-D1 control: an unrelated denial must not be flagged — the
    retraction patterns require a distress/symptom object."""
    ctx = _unc_ctx(
        "Actually, I never had coffee this morning.",
        ["Hello, I am here for my first session."],
    )
    out = UncertaintyAgent().run(ctx).payload
    assert "contradictory_information" not in out["uncertainty_types"], out


def test_uncertainty_additive_stress_and_poor_sleep_not_flagged():
    """B-D1 control: an additive statement ('stressed but I never sleep
    well') is not a retraction. Guards the concern/message duplication
    in the uncertainty scan, which used to let the sleep pattern match
    across the duplicated sentence boundary."""
    ctx = _unc_ctx(
        "I'm stressed about work but I never sleep well.",
        ["I have been feeling stressed about work lately."],
    )
    out = UncertaintyAgent().run(ctx).payload
    assert "contradictory_information" not in out["uncertainty_types"], out


# ---------------------------------------------------------------- S2-D4 / S2-D5
def _run_clarification(message, profile=None):
    ctx = AgentContext(
        case_id="r3", modality="cbt", current_message=message,
        full_profile=profile or REAL_PROFILE,
    )
    ctx.memory_output = MemoryAgent().run(ctx).payload
    ctx.state_output = StateAgent().run(ctx).payload
    ctx.uncertainty_output = UncertaintyAgent().run(ctx).payload
    ctx.risk_output = RiskAgent().run(ctx).payload
    return ctx, ClarificationAgent().run(ctx).payload


def test_clarification_vague_affect_question_has_no_presupposed_referent():
    """S2-D4: 'I feel bad.' names no situation, so the deictic question
    ('...when you mentioned that matter?') presupposes a referent the
    user never gave. The vague-affect question must be asked instead."""
    _, out = _run_clarification("I feel bad.")
    assert "that matter" not in out["question"], out
    assert "vague_affect_feeling" in out["target_information"], out


def test_clarification_deictic_vagueness_keeps_its_question():
    """S2-D4 control: genuine deictic vagueness still gets the deictic
    question."""
    _, out = _run_clarification("It's about... that thing, you know.")
    assert "that matter" in out["question"], out
    assert "specific_event_referent" in out["target_information"], out


def test_clarification_contradiction_first_at_moderate_risk():
    """S2-D5: at MODERATE risk the contradiction question must be asked
    before the medical-history safety question, so a correction is
    acknowledged instead of being answered with only the safety question."""
    ctx = AgentContext(
        case_id="r3", modality="cbt",
        current_message="Actually I was wrong about that — I barely sleep at all most nights.",
        prior_transcript=[{"role": "user", "content": "I have no trouble sleeping at all."}],
        full_profile=REAL_PROFILE,
    )
    ctx.memory_output = MemoryAgent().run(ctx).payload
    ctx.state_output = StateAgent().run(ctx).payload
    ctx.uncertainty_output = UncertaintyAgent().run(ctx).payload
    ctx.risk_output = RiskAgent().run(ctx).payload
    assert ctx.risk_output["severity"] == "MODERATE"
    assert "contradictory_information" in ctx.uncertainty_output["uncertainty_types"]
    out = ClarificationAgent().run(ctx).payload
    assert "conflicting_feelings_clarification" in out["target_information"], out


def test_clarification_safety_first_at_high_risk_with_contradiction():
    """S2-D5 control: at HIGH risk the safety question stays first even
    when a contradiction is also present. (An empty profile is used so a
    genuine safety gap exists — profile 412 already records a medical
    history, so there would be no safety item to prioritize.)"""
    ctx = AgentContext(
        case_id="r3", modality="cbt",
        current_message="I have been thinking about suicide lately and I was in hospital recently. "
                        "I sleep fine but actually I barely sleep at all.",
        full_profile={},
    )
    ctx.memory_output = MemoryAgent().run(ctx).payload
    ctx.state_output = StateAgent().run(ctx).payload
    ctx.uncertainty_output = UncertaintyAgent().run(ctx).payload
    ctx.risk_output = RiskAgent().run(ctx).payload
    assert ctx.risk_output["severity"] == "HIGH"
    assert "contradictory_information" in ctx.uncertainty_output["uncertainty_types"]
    assert "medical_history (safety status absent)" in ctx.uncertainty_output["missing_information"]
    out = ClarificationAgent().run(ctx).payload
    assert "medical_history" in out["target_information"], out
