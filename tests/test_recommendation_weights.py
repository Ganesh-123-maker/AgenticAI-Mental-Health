"""Tests for recommendation suitability weights (see sample/recommendation_weights.py).

The weights are relative match shares across retrieved options, computed
in code from retrieval cosine similarities. They are never clinical
probabilities, never success rates, and never 100%. These tests use
synthetic similarities only; the real held-out set is never touched.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")

from sample.backends.dummy_backend import DummyBackend  # noqa: E402
from sample.core.schemas import RuntimeConfig  # noqa: E402
from sample.io.config_loader import load_runtime_config  # noqa: E402
from sample.prompt_manager import PsychAgentPromptManager  # noqa: E402
from sample.recommendation_weights import (  # noqa: E402
    apply_weights_to_reply,
    build_weights_payload,
    find_percentages,
    find_violations,
    render_options_block,
    should_attach_weights,
    softmax_shares,
)
from sample.skill_manager import SkillManager  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def _skills(similarities):
    return [
        {
            "skill_id": str(i),
            "skill_name": f"Skill {i}",
            "skill_description": "desc",
            "when_to_use": "when",
            "trigger": "trigger",
            "similarity": sim,
        }
        for i, sim in enumerate(similarities)
    ]


# --- share arithmetic -----------------------------------------------------

def test_shares_sum_to_100_and_are_nonnegative_integers():
    for sims in (
        [0.85, 0.75, 0.70],
        [0.90, 0.75, 0.65],
        [0.80, 0.78, 0.77],
        [0.50, 0.49],
        [0.10, 0.09, 0.08, 0.07, 0.06],
    ):
        shares = softmax_shares(sims, 0.1)
        assert len(shares) == len(sims)
        assert sum(shares) == 100
        assert all(isinstance(s, int) and s >= 0 for s in shares)


def test_ordering_matches_similarity():
    shares = softmax_shares([0.90, 0.70, 0.80], 0.1)
    assert shares[0] > shares[2] > shares[1]


def test_deterministic():
    sims = [0.83, 0.71, 0.69, 0.40]
    assert softmax_shares(sims, 0.1) == softmax_shares(sims, 0.1)
    payload_a = build_weights_payload(_skills(sims))
    payload_b = build_weights_payload(_skills(sims))
    assert payload_a == payload_b


def test_top_share_never_100_with_multiple_options():
    # An extreme gap that would round to 100 without the cap.
    shares = softmax_shares([0.99, -1.0, -1.0], 0.1)
    assert sum(shares) == 100
    assert shares[0] < 100
    payload = build_weights_payload(_skills([0.99, -1.0, -1.0]))
    assert payload["mode"] == "semantic"
    assert sum(o["share"] for o in payload["options"]) == 100
    assert payload["options"][0]["share"] < 100
    assert "100%" not in render_options_block(payload)


def test_equal_scores_give_equal_shares():
    shares = softmax_shares([0.5, 0.5, 0.5], 0.1)
    assert sum(shares) == 100
    assert max(shares) - min(shares) <= 1


def test_invalid_temperature_rejected():
    with pytest.raises(ValueError):
        softmax_shares([0.5, 0.4], 0.0)
    with pytest.raises(ValueError):
        softmax_shares([0.5, 0.4], -1.0)


# --- payload modes --------------------------------------------------------

def test_empty_input_is_handled():
    payload = build_weights_payload([])
    assert payload == {"mode": "none", "options": []}
    assert render_options_block(payload) == ""


def test_single_option_gives_no_certainty_claim():
    payload = build_weights_payload(_skills([0.88]))
    assert payload["mode"] == "single"
    assert payload["options"][0]["share"] is None
    block = render_options_block(payload)
    assert "%" not in block
    assert "100" not in block


def test_offline_mode_does_not_fabricate_weights():
    # Zero-vector offline mode yields cosine -1.0 for every candidate;
    # the payload must still carry no semantic shares.
    payload = build_weights_payload(
        _skills([-1.0, -1.0, -1.0]), semantic_available=False
    )
    assert payload["mode"] == "unavailable"
    assert all(o["share"] is None for o in payload["options"])
    assert "%" not in render_options_block(payload)


def test_missing_similarity_falls_back_to_unavailable():
    skills = _skills([0.8, 0.7])
    del skills[1]["similarity"]
    payload = build_weights_payload(skills, semantic_available=True)
    assert payload["mode"] == "unavailable"
    assert all(o["share"] is None for o in payload["options"])


def test_disabled_mode():
    payload = build_weights_payload(_skills([0.8, 0.7]), enabled=False)
    assert payload == {"mode": "disabled", "options": []}
    text = "Try this exercise."
    assert apply_weights_to_reply(text, payload)[0] == text


# --- SkillManager wiring --------------------------------------------------

class _LiveBackendStub:
    is_offline = False

    async def chat_text(self, messages, **kwargs):
        return "ok"


def test_skill_manager_weights_live_and_offline():
    live_mgr = SkillManager(_LiveBackendStub(), RuntimeConfig())
    payload = live_mgr.suitability_weights(_skills([0.90, 0.75, 0.65]))
    assert payload["mode"] == "semantic"
    assert sum(o["share"] for o in payload["options"]) == 100
    assert payload["options"][0]["share"] < 100

    offline_mgr = SkillManager(DummyBackend(), RuntimeConfig())
    payload = offline_mgr.suitability_weights(_skills([-1.0, -1.0, -1.0]))
    assert payload["mode"] == "unavailable"
    assert all(o["share"] is None for o in payload["options"])


def test_config_defaults_and_yaml_override():
    cfg = RuntimeConfig()
    assert cfg.recommendation_weights_enabled is True
    assert cfg.recommendation_weights_temperature == 0.1
    assert cfg.recommendation_weights_max_options == 3
    yaml_cfg = load_runtime_config(
        REPO / "configs" / "runtime" / "psychagent_sglang_local.yaml"
    )
    assert yaml_cfg.recommendation_weights_enabled is True
    assert yaml_cfg.recommendation_weights_temperature == 0.1
    assert yaml_cfg.recommendation_weights_max_options == 3


# --- safety gates and post-check ------------------------------------------

def test_no_weights_on_high_risk_or_escalate():
    assert should_attach_weights("HIGH-RISK", "ALLOW", "some text") is False
    assert should_attach_weights("CLEAR", "ESCALATE", "some text") is False
    assert should_attach_weights("CLEAR", "ALLOW", "call Tele-MANAS 14416") is False
    assert should_attach_weights("CLEAR", "ALLOW", "some text") is True


def test_postcheck_catches_100_percent():
    payload = build_weights_payload(_skills([0.90, 0.75, 0.65]))
    shares = [o["share"] for o in payload["options"]]
    text = "This is the best option, 100% the right one. Let us begin."
    final, info = apply_weights_to_reply(text, payload)
    assert "100%" not in final
    assert info["applied"] == "deterministic"
    assert sorted(find_percentages(final)) == sorted(shares)
    assert "not predictions of outcome" in final


def test_postcheck_catches_outcome_probability_phrasing():
    payload = build_weights_payload(_skills([0.90, 0.75, 0.65]))
    shares = sorted(o["share"] for o in payload["options"])
    text = "This has an 80% chance it will work for you. Let us try it."
    assert find_violations(text), "test fixture must itself violate the rule"
    final, info = apply_weights_to_reply(text, payload)
    assert "chance it will work" not in final
    assert sorted(find_percentages(final)) == shares
    assert info["applied"] == "deterministic"


def test_model_correct_presentation_is_kept():
    payload = build_weights_payload(_skills([0.90, 0.75, 0.65]))
    shares = [o["share"] for o in payload["options"]]
    text = (
        f"Let us start with Skill 0 (about {shares[0]}%), "
        f"and keep Skill 1 (about {shares[1]}%) and Skill 2 (about {shares[2]}%) as alternatives."
    )
    final, info = apply_weights_to_reply(text, payload)
    assert final == text
    assert info["applied"] == "model"


def test_single_mode_strips_percentages():
    payload = build_weights_payload(_skills([0.88]))
    final, _info = apply_weights_to_reply("This one is 100% right.", payload)
    assert "%" not in final
    assert "without a percentage" in final


# --- prompt templates ------------------------------------------------------

EXAMPLE_SKILLS = [
    {
        "skill_name": "Box Breathing",
        "skill_description": "Slow breathing exercise.",
        "when_to_use": "When anxious.",
        "trigger": "Client reports anxiety.",
    },
    {
        "skill_name": "Grounding",
        "skill_description": "Grounding exercise.",
        "when_to_use": "When distressed.",
        "trigger": "Client reports distress.",
    },
]


@pytest.mark.parametrize("sect", ["bt", "cbt", "het", "pdt", "pmt"])
def test_each_school_template_renders_with_weights(sect):
    payload = build_weights_payload(_skills([0.90, 0.75]))
    # Titles must match the skill names the template lists.
    for option, skill in zip(payload["options"], EXAMPLE_SKILLS):
        option["title"] = skill["skill_name"]
    mgr = PsychAgentPromptManager(REPO / "prompts" / "psychagent", sect)
    rendered = mgr.render(
        "counselor_system",
        client_info={},
        history=[],
        session_stage="assessment",
        session_focus=[],
        homework_assigned_from_last_session=[],
        suggested_skills=EXAMPLE_SKILLS,
        recommendation_weights=payload,
    )
    for option in payload["options"]:
        assert option["title"] in rendered
        assert f"about {option['share']}%" in rendered
    # The prompt itself names the prohibition ("never present any option
    # as 100%") and the honest framing; those are instructions to the
    # model, not claims in a client-facing reply. The client-facing
    # 100% / outcome-probability bans are covered by the post-check tests.
    assert "not a prediction of outcome" in rendered
