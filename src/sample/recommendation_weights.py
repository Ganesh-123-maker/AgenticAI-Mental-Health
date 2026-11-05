"""Suitability weights for exercise / feedback recommendations.

What these numbers are
----------------------
The retrieval step scores retrieved skills by cosine similarity to the
client's current message (``skill["similarity"]`` in
``SkillManager.retrive``). This module converts those scores into whole
percentages that sum to exactly 100 across the options shown. The result
is a *relative suitability weight*: how well each option matches the
client's current message, session goals and stage *compared with the
other retrieved options*.

What these numbers are not
---------------------------
They are NOT clinical probabilities, NOT success rates and NOT
predictions of outcome. The system is uncalibrated: no outcome data
backs these shares, and they have never been validated against real
outcomes or expert ratings. Client-facing wording must say so, and must
never phrase a share as "X% chance this will work", "X% effective", or
any cure claim. No "cure" or "improvement" detector exists in this
module, and no recommendation is ever shown as 100%.

How the shares are computed
---------------------------
Softmax over the similarities with a configurable temperature
(default 0.1; see ``DEFAULT_TEMPERATURE``), then largest-remainder
rounding to whole percentages. The ranking is deterministic: ties keep
retrieval order, and equal similarities give equal shares (within one
rounding point). When two or more options are shown, the top share is
capped at 99, so a rounded 100 can never appear. When only one option
is retrieved, no percentage is shown at all. When semantic similarities
are unavailable (offline / dummy embedding mode returns zero vectors
and cosine falls back to -1.0 for every candidate), no semantic shares
are produced: the payload reports mode ``"unavailable"`` and the reply
shows the options in rank order with no percentages.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Sequence, Tuple

DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_OPTIONS = 3

# Rank labels used by the deterministic options block. They describe fit
# order only; the numbers beside them are the relative match weights.
_RANK_LABELS = ("best match", "also a good fit", "another option")

_PERCENT_RE = re.compile(r"(\d{1,3})\s*%")
# A sentence is an outcome-probability claim if it attaches a percentage
# to a chance / effectiveness / success word, or if it states a 100%
# claim at all. Standalone cure / guarantee claims about a recommendation
# are forbidden with or without a percentage.
_OUTCOME_WORDS_RE = re.compile(
    r"\b(chance|probability|likelihood|effective|success)\b", re.IGNORECASE
)
_HUNDRED_RE = re.compile(r"\b100\s*%", re.IGNORECASE)
_CURE_GUARANTEE_RE = re.compile(
    r"\bwill\s+cure\b|\bguaranteed\s+to\b", re.IGNORECASE
)
_CRISIS_MARKERS = ("Tele-MANAS", "988 Suicide")


def softmax_shares(similarities: Sequence[float], temperature: float) -> List[int]:
    """Convert similarities to whole percentages summing to exactly 100.

    Softmax with ``temperature`` (must be finite and positive), then
    largest-remainder rounding. Ties in fractional remainders break
    toward the higher similarity, then toward the earlier option, so the
    result is deterministic. With two or more options the top share is
    capped at 99: a rounded 100 is moved down by one point in favour of
    the second option.
    """
    sims = [float(s) for s in similarities]
    if not sims:
        return []
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("temperature must be finite and positive")
    if len(sims) == 1:
        return [100]
    finite = [s for s in sims if math.isfinite(s)]
    top = max(finite) if finite else 0.0
    exps: List[float] = []
    for s in sims:
        if math.isfinite(s):
            exps.append(math.exp((s - top) / temperature))
        else:
            exps.append(0.0)
    total = sum(exps)
    if total <= 0:
        # No usable signal (all similarities non-finite): split evenly.
        raw = [100.0 / len(sims)] * len(sims)
    else:
        raw = [e / total * 100.0 for e in exps]
    floors = [int(math.floor(v)) for v in raw]
    remainder = 100 - sum(floors)
    order = sorted(
        range(len(sims)),
        key=lambda i: (-(raw[i] - floors[i]), -sims[i], i),
    )
    shares = list(floors)
    for i in order[:remainder]:
        shares[i] += 1
    if len(shares) >= 2 and shares[0] == 100:
        shares[0] -= 1
        shares[1] += 1
    return shares


def build_weights_payload(
    skills: Sequence[Dict[str, Any]],
    *,
    temperature: float = DEFAULT_TEMPERATURE,
    max_options: int = DEFAULT_MAX_OPTIONS,
    semantic_available: bool = True,
    enabled: bool = True,
) -> Dict[str, Any]:
    """Build the weights payload for a list of retrieved skills.

    Returns ``{"mode": ..., "options": [...]}`` where mode is one of:
    ``"disabled"`` (feature off), ``"none"`` (no skills retrieved),
    ``"unavailable"`` (skills exist but no semantic similarities, e.g.
    offline mode or a missing similarity value: options in rank order,
    no shares), ``"single"`` (exactly one option: no share, never 100%),
    ``"semantic"`` (2+ options with shares summing to 100, top at most
    99). Options carry ``rank``, ``title`` and ``share`` (int or None).
    """
    if not enabled:
        return {"mode": "disabled", "options": []}
    items = list(skills or [])
    if not items:
        return {"mode": "none", "options": []}
    try:
        limit = int(max_options)
    except (TypeError, ValueError):
        limit = DEFAULT_MAX_OPTIONS
    limit = max(1, limit)

    def _similarity(skill: Dict[str, Any]) -> float:
        value = skill.get("similarity")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return float("nan")
        return float(value)

    def _sort_key(pair: Tuple[int, Dict[str, Any]]) -> Tuple[float, int]:
        # Missing or non-finite similarities sort last (key +inf), so
        # retrieval order is preserved for the unavailable path; the
        # numeric check below decides the mode.
        sim = _similarity(pair[1])
        return (-sim if math.isfinite(sim) else float("inf"), pair[0])

    ranked = sorted(enumerate(items), key=_sort_key)
    chosen = ranked[:limit]
    titles: List[str] = []
    for _, skill in chosen:
        title = skill.get("skill_name") or skill.get("skill_id") or "Option"
        titles.append(str(title))
    sims = [_similarity(skill) for _, skill in chosen]
    if not semantic_available or any(not math.isfinite(s) for s in sims):
        return {
            "mode": "unavailable",
            "options": [
                {"rank": i + 1, "title": title, "share": None}
                for i, title in enumerate(titles)
            ],
        }
    if len(chosen) == 1:
        return {
            "mode": "single",
            "options": [{"rank": 1, "title": titles[0], "share": None}],
        }
    shares = softmax_shares(sims, temperature)
    options = [
        {"rank": i + 1, "title": titles[i], "share": shares[i]}
        for i in range(len(titles))
    ]
    # A rounded share of 0 means negligible match next to the others;
    # drop it from what is shown (dropping a 0 keeps the sum at 100).
    shown = [o for o in options if o["share"] and o["share"] > 0]
    if len(shown) < 2:  # pragma: no cover - defensive; cap guarantees >= 2
        shown = options[:2]
        shown[0] = dict(shown[0], share=99)
        shown[1] = dict(shown[1], share=1)
    for i, option in enumerate(shown):
        option["rank"] = i + 1
    return {"mode": "semantic", "options": shown}


def render_options_block(payload: Dict[str, Any]) -> str:
    """Deterministic client-facing rendering of a weights payload.

    Semantic mode renders the options with their shares and the honest
    label. Single mode renders the plain no-percentage sentence. Every
    other mode renders nothing: no percentages are ever invented.
    """
    mode = (payload or {}).get("mode")
    options = (payload or {}).get("options") or []
    if mode == "semantic" and options:
        lines = [
            "",
            "",
            "Options we considered, by how well each matches what you shared. "
            "These are relative match weights, not predictions of outcome:",
        ]
        for option in options:
            rank = int(option.get("rank", 1))
            label = _RANK_LABELS[0] if rank == 1 else (
                _RANK_LABELS[1] if rank == 2 else _RANK_LABELS[2]
            )
            lines.append(
                f"- {option.get('title')} — {label} (about {option.get('share')}%)"
            )
        return "\n".join(lines)
    if mode == "single" and options:
        return (
            "\n\nOnly one matching option came up for this turn, so here it "
            "is on its own, without a percentage."
        )
    return ""


def find_percentages(text: str) -> List[int]:
    """All whole percentages mentioned in ``text`` (e.g. ``80`` for 80%)."""
    return [int(m.group(1)) for m in _PERCENT_RE.finditer(text or "")]


def find_violations(text: str) -> List[str]:
    """Forbidden claims in ``text``: 100% claims and outcome-probability phrasing."""
    violations: List[str] = []
    if not text:
        return violations
    if _HUNDRED_RE.search(text):
        violations.append("presents a recommendation as 100%")
    if _CURE_GUARANTEE_RE.search(text):
        violations.append("states a cure or guarantee claim")
    for sentence in _split_sentences(text):
        if _PERCENT_RE.search(sentence) and _OUTCOME_WORDS_RE.search(sentence):
            violations.append(
                "states weights as an outcome probability: " + sentence.strip()[:80]
            )
    return violations


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p for p in parts if p]


def _sentence_is_forbidden(sentence: str) -> bool:
    if _HUNDRED_RE.search(sentence) or _CURE_GUARANTEE_RE.search(sentence):
        return True
    return bool(_PERCENT_RE.search(sentence) and _OUTCOME_WORDS_RE.search(sentence))


def strip_percentage_tokens(text: str) -> str:
    """Remove percentage tokens (e.g. 'about 80%') from model text."""
    cleaned = re.sub(r"\s*(?:about|around|approximately)\s*\d{1,3}\s*%", "", text or "")
    cleaned = re.sub(r"\s*\d{1,3}\s*%", "", cleaned)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def drop_forbidden_sentences(text: str) -> str:
    """Drop sentences carrying forbidden claims; keep everything else."""
    kept = [s for s in _split_sentences(text) if not _sentence_is_forbidden(s)]
    return " ".join(kept).strip()


def should_attach_weights(route: Any, verdict: Any, text: str) -> bool:
    """False on the HIGH-RISK route, on an ESCALATE verdict, and for crisis text.

    Crisis responses and helplines stay exactly as they are: no exercise
    percentages are ever attached to them.
    """
    if str(route or "").upper() == "HIGH-RISK":
        return False
    if str(verdict or "").upper() == "ESCALATE":
        return False
    if any(marker in (text or "") for marker in _CRISIS_MARKERS):
        return False
    return True


def apply_weights_to_reply(
    text: str, payload: Dict[str, Any]
) -> Tuple[str, Dict[str, Any]]:
    """Verify a counselor reply against computed weights; repair if needed.

    - Semantic mode: if the reply already states exactly the computed
      shares and carries no forbidden claim, it is kept as-is.
      Otherwise forbidden sentences are dropped first (while their
      percentages are still visible to the check), remaining percentage
      tokens are stripped, and the deterministic options block is
      appended.
    - Single mode: any percentage is stripped and the plain
      no-percentage sentence is appended (unless already present).
    - Unavailable mode: any percentage is stripped (it would be
      fabricated); nothing is appended.
    - Disabled / none: the reply is returned unchanged.
    """
    mode = (payload or {}).get("mode")
    options = (payload or {}).get("options") or []
    if mode == "semantic" and options:
        violations = find_violations(text)
        percentages = find_percentages(text)
        shares = sorted(int(o["share"]) for o in options)
        if not violations and percentages and sorted(percentages) == shares:
            return text, {"applied": "model", "violations": []}
        cleaned = strip_percentage_tokens(drop_forbidden_sentences(text))
        if not cleaned:
            cleaned = "Let me share a few options that fit what you described."
        return cleaned + render_options_block(payload), {
            "applied": "deterministic",
            "violations": violations,
        }
    if mode == "single" and options:
        percentages = find_percentages(text)
        violations = find_violations(text)
        if not percentages and not violations:
            return text, {"applied": "model", "violations": []}
        cleaned = strip_percentage_tokens(drop_forbidden_sentences(text))
        if "only one matching option" not in cleaned.lower():
            cleaned = (cleaned + render_options_block(payload)) if cleaned else (
                "Here is the option that fits what you described."
                + render_options_block(payload)
            )
        return cleaned, {"applied": "deterministic", "violations": violations}
    if mode == "unavailable":
        percentages = find_percentages(text)
        violations = find_violations(text)
        if not percentages and not violations:
            return text, {"applied": "none", "violations": []}
        cleaned = strip_percentage_tokens(drop_forbidden_sentences(text))
        return cleaned, {"applied": "cleaned", "violations": violations}
    return text, {"applied": "none", "violations": []}
