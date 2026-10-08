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
    id: str          # e.g. "suicidal_ideation"
    severity: str    # "HIGH" | "MODERATE"
    en: Tuple[str, ...]  # English surface forms
    zh: Tuple[str, ...]  # Chinese surface forms


RISK_SIGNALS: Tuple[RiskSignal, ...] = (
    # ---- HIGH severity ----
    RiskSignal(
        id="suicidal_ideation", severity="HIGH",
        en=("suicide", "suicidal", "want to die", "kill myself", "killing myself",
            "take my own life", "end my life", "ending my life", "end life",
            "ending life", "end it all", "ending it all", "don't want to live"),
        zh=("自杀", "想死", "不想活", "结束生命", "了结生命"),
    ),
    RiskSignal(
        id="self_harm", severity="HIGH",
        en=("self-harm", "self harm", "self-injury", "hurt myself", "hurting myself",
            "harm myself", "harming myself", "slit wrists"),
        zh=("自残", "自伤", "伤害自己", "割腕"),
    ),
    RiskSignal(
        id="hopeless_despair", severity="HIGH",
        en=("can't go on", "hopeless want to die", "leave this world",
            "cannot survive", "better off dead", "better off without me",
            "not waking up", "don't want to wake up"),
        # Note: 撑不下去 ("can't cope") is deliberately MODERATE, not HIGH:
        # it appears in LOW-risk benchmark cases as general overwhelm.
        zh=("活不下去", "不如死了", "一了百了", "不想醒来"),
    ),
    RiskSignal(
        id="acute_psychiatric_crisis", severity="HIGH",
        en=("psychiatric emergency", "involuntary hospitalization",
            "severe mental disorder", "severe violence", "jump off building"),
        zh=("跳楼", "精神急诊", "严重精神障碍", "严重暴力行为"),
    ),
    # ---- MODERATE severity ----
    RiskSignal(
        id="insomnia", severity="MODERATE",
        en=("insomnia all night", "severe insomnia"),
        zh=("整夜失眠", "严重失眠", "失眠", "睡不着觉", "睡不着"),
    ),
    RiskSignal(
        id="functional_impairment", severity="MODERATE",
        en=("unable to work", "cannot work"),
        zh=("无法工作", "不能工作", "上不了班"),
    ),
    RiskSignal(
        id="panic", severity="MODERATE",
        en=("extreme panic", "panic attack"),
        zh=("惊恐发作", "极度恐慌", "恐慌发作"),
    ),
    RiskSignal(
        id="collapse", severity="MODERATE",
        en=("verge of collapse", "feeling broken"),
        zh=("濒临崩溃", "快要崩溃", "崩溃边缘", "心力交瘁"),
    ),
    RiskSignal(
        id="hopelessness", severity="MODERATE",
        en=("completely hopeless", "no hope"),
        zh=("完全绝望", "绝望", "毫无希望", "没有希望"),
    ),
    RiskSignal(
        id="overwhelm", severity="MODERATE",
        en=("unbearable", "can't bear it", "cannot bear it"),
        zh=("不堪重负", "承受不住", "难以承受", "撑不下去"),
    ),
    RiskSignal(
        id="destruction", severity="MODERATE",
        en=("perishing", "destruction"),
        zh=("毁灭",),
    ),
)

# Chinese surface forms of all HIGH-severity concepts, derived from the
# concept table above (single source of truth). Exported for consumers that
# perform their own language-aware crisis checks on utterances or on the
# signal labels in `signals_detected` (e.g. SafetySupervisor.is_acute_crisis).
ZH_HIGH_CRISIS_FORMS: Tuple[str, ...] = tuple(
    form for _s in RISK_SIGNALS if _s.severity == "HIGH" for form in _s.zh
)

# Negation cues that, when they precede a signal within the same clause, mark the
# mention as explicitly denied (e.g. "I have never had thoughts of suicide").
_NEGATION_CUES = (
    "no", "not", "never", "without", "denies", "denied", "deny", "don't", "do not", "didn't",
    "haven't", "have not", "hasn't", "wouldn't", "won't", "none", "nor",
)
_CLAUSE_BREAK = re.compile(r"[.,;!?]|\bbut\b|\bhowever\b|\balthough\b", re.IGNORECASE)
_NEGATION_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in _NEGATION_CUES) + r")\b", re.IGNORECASE)


def _find_signal(text: str, signal: str) -> Optional[str]:
    """Return "affirmed", "negated" or None for a signal in text (case-insensitive).

    A mention counts as negated only if a negation cue appears earlier in the
    same clause (up to 6 words before the signal) and the signal itself does
    not already contain a negation (e.g. "don't want to live"). Ambiguous
    cases are resolved towards "affirmed" (i.e. towards flagging risk).
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
        if _NEGATION_RE.search(sig) or not _NEGATION_RE.search(window):
            return "affirmed"
        found_negated = True
        start = lowered.find(sig, start + len(sig))
    return "negated" if found_negated else None


# Chinese negation cues for the character-window negation check below.
_ZH_NEGATION_CUES = ("没有", "否认", "否定", "从未", "不曾", "没", "未", "别", "无", "不")
# Clause boundaries for Chinese text (Chinese + ASCII punctuation, plus
# common contrast conjunctions).
_ZH_CLAUSE_BREAK = re.compile(r"[。，；！？、,.!?;]|但是|然而|不过|虽然")
# Number of characters before a Chinese signal form examined for negation.
# Chinese is denser than English; this mirrors the 6-word English window.
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
    for form in signal.en:
        hit = _find_signal(text, form)
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
        # Extract inputs from state, memory, and raw message
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

        # 1. Scan for explicit HIGH-RISK signals (language-aware concept matching;
        #    negation-aware per language for client-authored text)
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
            # Note: in medical_history, check if it's an affirmative risk (e.g. past attempt)
            # rather than a negated mention (e.g. "no prior attempts"). Uses the same
            # language-aware concept matching so Chinese histories are not blind.
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

        # 2. Check for UNCERTAIN safety status (safety status missing / unverified)
        safety_status_missing = False
        for item in unknown_info:
            item_str = str(item).lower()
            if "medical_history" in item_str or "safety" in item_str:
                safety_status_missing = True
                break

        if not medical_history or medical_history.lower() in ("(unavailable)", "not mentioned", "unknown"):
            # If medical history is explicitly not populated or unknown in the context
            if any("medical_history" in str(x) for x in unknown_info) or any("medical_history" in str(x) for x in (ctx.metadata.get("missing_information") or [])):
                safety_status_missing = True

        # 3. Scan for MODERATE distress / functional impairment signals
        #    (language-aware concept matching; affirmed matches only)
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

        # 4. NO EVIDENCE
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
