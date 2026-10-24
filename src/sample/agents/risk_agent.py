"""Risk Agent for PsychAgent.

This agent evaluates safety and crisis signals across the client message,
state assessment output, and memory output.

IMPORTANT design constraints
-----------------------------
* It ONLY identifies safety and crisis signals.
* It must NOT output clinical diagnosis labels (e.g. depression, PTSD, borderline).
* It must NOT choose counseling skills or change what gets generated.
* It keeps NO EVIDENCE / UNCERTAIN / EVIDENCE OF RISK genuinely distinct.
* Evidence MUST contain specific signals (e.g., exact keywords, absent safety fields),
  NOT clinical reasoning or interpretive narratives.

Output (AgentMessage):
---------------------
status:                 "ok"
confidence:             0.0–1.0
evidence:               List of specific detected signals (not reasoning)
payload:
    severity:           "LOW" | "MODERATE" | "HIGH" | "UNCERTAIN"
    risk_status:        "NO_EVIDENCE" | "UNCERTAIN" | "EVIDENCE_OF_RISK"
    evidence:           List of specific signal strings
    confidence:         0.0–1.0
    signals_detected:   List of specific tokens or condition strings
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from .base import Agent, AgentContext, AgentError, AgentMessage

logger = logging.getLogger(__name__)


class RiskSignal(NamedTuple):
    """A language-independent risk concept with surface forms per language.

    Grouping surface forms under one concept (instead of flat per-language
    keyword lists) keeps severity in one place: adding a language means adding
    forms to existing concepts, not maintaining a parallel list. Each concept
    carries a stable id used in evidence strings.
    """
    id: str
    severity: str
    en: Tuple[str, ...]
    zh: Tuple[str, ...]


RISK_SIGNALS: Tuple[RiskSignal, ...] = (
    RiskSignal(
        id="suicidal_ideation", severity="HIGH",
        en=("suicide", "suicidal", "want to die", "kill myself", "killing myself",
            "take my own life", "end my life", "ending my life", "end life",
            "ending life", "end it all", "ending it all", "don't want to live",
            "don't want to be alive", "want to disappear", "wish I could disappear",
            "don't want to exist", "stop existing", "goodbye note",
            "end everything", "give up on life", "not being here anymore",
            "tired of living", "unalive myself",
            # Passive / indirect ideation: hedged or negated wishes to not
            # continue living, existence-negation, and worthlessness forms.
            # (Development-set class fix, 2026-10-23; forms containing a
            # negation cue are affirmed unless a denial-of-thought cue in
            # the preceding window negates them, see _find_signal.)
            "not sure I want to keep going", "not sure I want to go on",
            "tired of existing",
            "wish I didn't exist", "wish I just didn't exist", "just not exist",
            "wouldn't matter to anyone", "would not matter to anyone",
            "nobody would miss me", "no one would miss me", "wouldn't be missed"),
        zh=("suicide", "want to die", "do not want to live", "end my life", "end one's own life"),
    ),
    RiskSignal(
        id="self_harm", severity="HIGH",
        en=("self-harm", "self harm", "self-injury", "hurt myself", "hurting myself",
            "harm myself", "harming myself", "slit wrists", "slit my wrists",
            "cut my wrists", "cutting my wrists"),
        zh=("self-mutilation", "self-injury", "hurt oneself", "slit wrists"),
    ),
    RiskSignal(
        id="hopeless_despair", severity="HIGH",
        en=("can't go on", "hopeless want to die", "leave this world",
            "cannot survive", "better off dead", "better off without me",
            "not waking up", "don't want to wake up", "don't wake up",
            "never wake up", "not wake up", "wouldn't wake up",
            "never been born", "wish I was dead", "wish I were dead",
            # Passive-ideation facets: inability to continue, pointlessness
            # of self/life, and sleep-as-escape constructions.
            "can't keep going", "cannot keep going",
            "not sure I can keep going", "don't know if I can keep going",
            "what's the point of me", "what is the point of me",
            "what's the point of living", "no point in living",
            "no point in going on", "no reason to live",
            "no reason to go on", "no reason to keep going",
            "don't see any reason to go on", "don't see a reason to go on",
            "see no reason to go on",
            # Sleep-as-escape, hope-anchored AND morning-anchored: the
            # hope/wish framing alone does NOT separate these from benign
            # alarm-clock talk ("hope I won't wake up late for my alarm"
            # also contains it, verified 2026-10-24). The "in the morning"
            # anchor is what keeps alarm talk out. Trade-off, documented:
            # a bare "hope I won't wake up tomorrow" (no "in the morning")
            # is missed by these forms.
            "hoping I won't wake up in the morning", "hope I won't wake up in the morning",
            "fall asleep and not", "fall asleep and never wake up"),
        zh=("cannot go on living", "better off dead", "end it all once and for all", "do not want to wake up"),
    ),
    RiskSignal(
        id="acute_psychiatric_crisis", severity="HIGH",
        en=("psychiatric emergency", "involuntary hospitalization",
            "severe mental disorder", "severe violence", "jump off building"),
        zh=("jump off a building", "psychiatric emergency", "severe mental disorder", "severe violent behavior"),
    ),
    RiskSignal(
        id="insomnia", severity="MODERATE",
        en=("insomnia all night", "severe insomnia", "cannot sleep", "can't sleep",
            "unable to fall asleep"),
        zh=("awake all night with insomnia", "severe insomnia", "insomnia", "unable to fall asleep", "cannot sleep"),
    ),
    RiskSignal(
        id="functional_impairment", severity="MODERATE",
        en=("unable to work", "cannot work"),
        zh=("unable to work", "cannot work", "unable to get to work"),
    ),
    RiskSignal(
        id="panic", severity="MODERATE",
        en=("extreme panic", "panic attack"),
        zh=("panic attack", "extreme panic", "panic episode"),
    ),
    RiskSignal(
        id="collapse", severity="MODERATE",
        en=("verge of collapse", "feeling broken"),
        zh=("on the verge of collapse", "about to collapse", "on the edge of collapse", "mentally and physically exhausted"),
    ),
    RiskSignal(
        id="hopelessness", severity="MODERATE",
        en=("completely hopeless", "no hope"),
        zh=("completely hopeless", "despair", "utterly hopeless", "no hope"),
    ),
    RiskSignal(
        id="overwhelm", severity="MODERATE",
        en=("unbearable", "can't bear it", "cannot bear it", "overwhelmed"),
        zh=("overwhelmed", "cannot bear the strain", "hard to bear", "cannot hold on any longer"),
    ),
    RiskSignal(
        id="destruction", severity="MODERATE",
        en=("perishing", "destruction"),
        zh=("destruction",),
    ),
)

ZH_HIGH_CRISIS_FORMS: Tuple[str, ...] = tuple(
    form for _s in RISK_SIGNALS if _s.severity == "HIGH" for form in _s.zh
)

_NEGATION_CUES = (
    "no", "not", "never", "without", "denies", "denied", "deny", "don't", "do not", "didn't",
    "haven't", "have not", "hasn't", "wouldn't", "won't", "none", "nor",
)
# Conjunctions join independent clauses, so a negation in one conjunct
# must not leak into the next: "I am not suicidal and I don't want to
# die." is two denials, and "I don't care and want to die" is an
# affirmation. Without "and"/"or" as clause breaks, the 6-word window
# counted cues across the conjunction and misread both cases.
_CLAUSE_BREAK = re.compile(r"[.,;!?]|\bbut\b|\bhowever\b|\balthough\b|\band\b|\bor\b", re.IGNORECASE)
_NEGATION_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in _NEGATION_CUES) + r")\b", re.IGNORECASE)

# Denial-of-thought constructions: the only preceding-window cues that can
# negate a risk form which itself carries a negation cue (e.g. "not waking
# up"). A cue from any other statement in the same clause ("not happy, I
# don't want to live") is incidental and must NOT negate the form.
_DENIAL_OF_THOUGHT_PATTERNS = (
    "never thought", "never think", "never imagined", "never considered",
    "didn't think", "did not think", "don't think", "do not think",
    "not thought", "no thought", "no thoughts", "deny", "denied", "denies",
)


def _find_signal(text: str, signal: str) -> Optional[str]:
    """Return "affirmed", "negated" or None for a signal in text (case-insensitive).

    A mention counts as negated only if exactly one negation cue appears
    earlier in the same clause (up to 6 words before the signal).
    Ambiguous cases are resolved towards "affirmed" (i.e. towards flagging
    risk).

    Two or more negation cues in the window form a double negation and count
    as affirmed, not negated: "It's not like I haven't thought about ending
    it all" discloses the thought rather than denying it.

    Forms that themselves contain a negation cue (e.g. "don't want to
    live", "not waking up") are affirmed by default, because the cue inside
    the form is part of the wish. The single exception is a denial of the
    thought itself in the preceding window ("never thought about not
    waking up"): exactly one cue there, and that cue must belong to a
    denial-of-thought construction. Zero cues, two or more cues, or an
    incidental cue all stay affirmed.
    """
    lowered = text.lower()
    sig = signal.lower()
    found_negated = False
    start = lowered.find(sig)
    while start != -1:
        prefix = lowered[:start]
        breaks = list(_CLAUSE_BREAK.finditer(prefix))
        clause = prefix[breaks[-1].end():] if breaks else prefix
        window = " ".join(clause.split()[-6:])
        cue_count = len(_NEGATION_RE.findall(window))
        if _NEGATION_RE.search(sig):
            if cue_count == 1 and any(p in window for p in _DENIAL_OF_THOUGHT_PATTERNS):
                found_negated = True
            else:
                return "affirmed"
        elif cue_count != 1:
            return "affirmed"
        else:
            found_negated = True
        start = lowered.find(sig, start + len(sig))
    return "negated" if found_negated else None


_ZH_NEGATION_CUES = ("have not", "deny", "negate", "never", "never have", "not", "not yet", "do not", "without", "not")
_ZH_CLAUSE_BREAK = re.compile(r"[.,;!?]|but|however|but|although")
_ZH_NEG_WINDOW_CHARS = 8


def _find_signal_zh(text: str, form: str) -> Optional[str]:
    """Return "affirmed", "negated" or None for a Chinese signal form in text.

    Mirrors _find_signal's semantics for Chinese: a mention counts as negated
    only if a negation cue appears shortly before the form within the same
    clause. Uses a character window since Chinese has no word boundaries.
    Ambiguous cases resolve towards "affirmed".
    """
    if not text or not form:
        return None
    found_negated = False
    start = text.find(form)
    while start != -1:
        prefix = text[:start]
        breaks = list(_ZH_CLAUSE_BREAK.finditer(prefix))
        clause = prefix[breaks[-1].end():] if breaks else prefix
        window = clause[-_ZH_NEG_WINDOW_CHARS:]
        if not any(cue in window for cue in _ZH_NEGATION_CUES):
            return "affirmed"
        found_negated = True
        start = text.find(form, start + len(form))
    return "negated" if found_negated else None


_LEET_TRANS = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
_LEET_CHARS = frozenset("013457@$")
_SPACED_LETTERS_RE = re.compile(r"\b(?:[A-Za-z][ .]){2,}[A-Za-z]\b")


def _normalize_for_matching(text: str) -> str:
    """Return a de-obfuscated copy of text for signal matching.

    Two general obfuscations are undone:
    - letter-spaced or letter-dotted words ("s u i c i d e", "s.u.i.c.i.d.e")
      are joined back into single words;
    - leetspeak substitutions inside mixed letter/digit tokens ("k1lling",
      "su1cide", "mys3lf") are mapped back to letters.

    The original text is always matched as well; this copy only adds matches,
    it never removes one, so it cannot loosen any existing rule.
    """
    def _join(m: "re.Match") -> str:
        return re.sub(r"[ .]", "", m.group(0))

    norm = _SPACED_LETTERS_RE.sub(_join, text)
    out = []
    for tok in norm.split(" "):
        if any(c.isalpha() for c in tok) and any(c in _LEET_CHARS for c in tok):
            out.append(tok.translate(_LEET_TRANS))
        else:
            out.append(tok)
    return " ".join(out)


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _match_signal(text: str, signal: RiskSignal) -> Tuple[Optional[str], Optional[str]]:
    """Match a language-independent risk concept against text.

    Tries the concept's English forms with _find_signal and its Chinese forms
    with _find_signal_zh (when the text contains CJK characters, covering
    mixed-language input). Returns (matched_form, "affirmed" | "negated") or
    (None, None). An affirmed match in either language wins over negated-only
    matches, preserving the fail-towards-flagging behavior.
    """
    if not text:
        return None, None
    negated_form: Optional[str] = None
    en_texts = [text]
    normalized = _normalize_for_matching(text)
    if normalized != text:
        en_texts.append(normalized)
    for form in signal.en:
        for candidate in en_texts:
            hit = _find_signal(candidate, form)
            if hit == "affirmed":
                return form, "affirmed"
            if hit == "negated" and negated_form is None:
                negated_form = form
    if _CJK_RE.search(text):
        for form in signal.zh:
            hit = _find_signal_zh(text, form)
            if hit == "affirmed":
                return form, "affirmed"
            if hit == "negated" and negated_form is None:
                negated_form = form
    if negated_form is not None:
        return negated_form, "negated"
    return None, None


class RiskAgent(Agent):
    """Detects explicit safety and crisis signals without diagnostic labeling."""

    name = "risk_agent"

    def __init__(self, backend: Optional[Any] = None) -> None:
        self.backend = backend

    def run(self, ctx: AgentContext) -> AgentMessage:
        try:
            return self._run(ctx)
        except AgentError:
            raise
        except Exception as exc:
            logger.exception("[%s] unexpected error: %s", self.name, exc)
            return AgentMessage(
                agent=self.name,
                status="error",
                confidence=0.0,
                missing_information=[],
                evidence=[f"Agent error: {exc}"],
                payload={
                    "severity": "UNCERTAIN",
                    "risk_status": "UNCERTAIN",
                    "evidence": [f"Error during risk assessment: {exc}"],
                    "confidence": 0.0,
                    "signals_detected": [],
                },
                error=str(exc),
            )

    def _run(self, ctx: AgentContext) -> AgentMessage:
        state_payload = ctx.state_output or {}
        if not isinstance(state_payload, dict):
            state_payload = {}

        mem_payload = ctx.memory_output or {}
        if not isinstance(mem_payload, dict):
            mem_payload = {}

        raw_message = str(ctx.current_message or "").strip()
        current_concern = str(state_payload.get("current_concern", "")).strip()
        main_problem = str(mem_payload.get("main_problem", "")).strip()
        static_traits = mem_payload.get("known_static_traits", {}) or {}
        medical_history = str(static_traits.get("medical_history", "")).strip()
        unknown_info = state_payload.get("unknown_information", []) or []

        high_signals: List[str] = []
        negated_signals: List[str] = []
        for signal in RISK_SIGNALS:
            if signal.severity != "HIGH":
                continue
            for label, text in (("client_message", raw_message), ("current_concern", current_concern), ("main_problem", main_problem)):
                if not text:
                    continue
                form, hit = _match_signal(text, signal)
                if hit == "affirmed":
                    high_signals.append(f"{label}:'{form}'")
                elif hit == "negated":
                    negated_signals.append(f"negated:{label}:'{form}'")
            if medical_history:
                form, hit = _match_signal(medical_history, signal)
                if hit == "affirmed":
                    high_signals.append(f"medical_history:'{form}'")

        if high_signals:
            evidence = [f"Direct crisis signal detected: {s}" for s in high_signals]
            payload = {
                "severity": "HIGH",
                "risk_status": "EVIDENCE_OF_RISK",
                "evidence": evidence,
                "confidence": 0.95,
                "signals_detected": high_signals,
            }
            _validate_risk_payload(payload)
            return AgentMessage(
                agent=self.name,
                status="HIGH",
                evidence=evidence,
                confidence=0.95,
                missing_information=[],
                payload=payload,
            )

        safety_status_missing = False
        for item in unknown_info:
            item_str = str(item).lower()
            if "medical_history" in item_str or "safety" in item_str:
                safety_status_missing = True
                break

        if not medical_history or medical_history.lower() in ("(unavailable)", "not mentioned", "unknown"):
            if any("medical_history" in str(x) for x in unknown_info) or any("medical_history" in str(x) for x in (ctx.metadata.get("missing_information") or [])):
                safety_status_missing = True

        moderate_signals: List[str] = []
        for signal in RISK_SIGNALS:
            if signal.severity != "MODERATE":
                continue
            for label, text in (("client_message", raw_message), ("current_concern", current_concern), ("main_problem", main_problem)):
                if not text:
                    continue
                form, hit = _match_signal(text, signal)
                if hit == "affirmed":
                    moderate_signals.append(f"{label}:'{form}'")

        if safety_status_missing:
            evidence = ["Safety status unverified: medical/psychiatric history missing from intake evidence"]
            if moderate_signals:
                evidence.extend([f"Distress signal: {s}" for s in moderate_signals])
            payload = {
                "severity": "UNCERTAIN",
                "risk_status": "UNCERTAIN",
                "evidence": evidence,
                "confidence": 0.60,
                "signals_detected": moderate_signals + ["missing_safety_status"],
            }
            _validate_risk_payload(payload)
            return AgentMessage(
                agent=self.name,
                status="UNCERTAIN",
                evidence=evidence,
                confidence=0.60,
                missing_information=["medical_history"],
                payload=payload,
            )

        if moderate_signals:
            evidence = [f"Functional distress signal detected: {s}" for s in moderate_signals]
            payload = {
                "severity": "MODERATE",
                "risk_status": "UNCERTAIN",
                "evidence": evidence,
                "confidence": 0.75,
                "signals_detected": moderate_signals,
            }
            _validate_risk_payload(payload)
            return AgentMessage(
                agent=self.name,
                status="MODERATE",
                evidence=evidence,
                confidence=0.75,
                missing_information=[],
                payload=payload,
            )

        evidence = ["NO EVIDENCE: No risk or crisis signals detected in current message, state, or memory context"]
        if negated_signals:
            evidence.append(
                "Safety-related terms appeared only in explicitly negated form and were not treated as risk: "
                + ", ".join(sorted(set(negated_signals)))
            )
        payload = {
            "severity": "LOW",
            "risk_status": "NO_EVIDENCE",
            "evidence": evidence,
            "confidence": 0.90,
            "signals_detected": sorted(set(negated_signals)),
        }
        _validate_risk_payload(payload)
        return AgentMessage(
            agent=self.name,
            status="LOW",
            evidence=evidence,
            confidence=0.90,
            missing_information=[],
            payload=payload,
        )


def _validate_risk_payload(payload: Dict[str, Any]) -> None:
    """Validate risk output schema."""
    valid_severities = ("LOW", "MODERATE", "HIGH", "UNCERTAIN")
    valid_statuses = ("NO_EVIDENCE", "UNCERTAIN", "EVIDENCE_OF_RISK")
    if payload.get("severity") not in valid_severities:
        raise AgentError("risk_agent", f"Invalid severity: {payload.get('severity')}")
    if payload.get("risk_status") not in valid_statuses:
        raise AgentError("risk_agent", f"Invalid risk_status: {payload.get('risk_status')}")
    conf = payload.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
        raise AgentError("risk_agent", f"Invalid confidence: {conf}")
    if not isinstance(payload.get("evidence"), list):
        raise AgentError("risk_agent", "evidence must be a list")
