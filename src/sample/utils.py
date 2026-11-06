from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RE_TAG_RESPONSE = re.compile(r"<response>(.*?)</response>", flags=re.DOTALL | re.IGNORECASE)
RE_TAG_SKILL = re.compile(r"<skill>.*?</skill>", flags=re.S | re.IGNORECASE)
RE_JSON_CODE_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", flags=re.S)
RE_JSON_BRACE = re.compile(r"(\{.*\})", flags=re.S)


def extract_tag_content(text: str, tag: str = "response") -> Optional[str]:
    if not text:
        return None
    if tag == "response":
        match = RE_TAG_RESPONSE.search(text)
    else:
        match = re.search(rf"<{tag}>(.*?)</{tag}>", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()


def remove_tags(text: str, tag: str = "response") -> str:
    if not text:
        return ""
    if tag == "skill":
        return RE_TAG_SKILL.sub("", text).strip()
    return re.sub(rf"<{tag}>.*?</{tag}>", "", text, flags=re.S | re.IGNORECASE).strip()


def safe_json_loads(text: str) -> Dict[str, Any]:
    if not text:
        raise ValueError("empty text for JSON parse")

    content = extract_tag_content(text, tag="response") or ""
    candidate = _strip_code_fence(content)

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except Exception as exc:
        # Round 2 fix (Stream A D7): was a silent swallow; the regex
        # fallback below still runs. Log the failure type only.
        logger.debug("safe_json_loads direct parse failed: %s", type(exc).__name__)

    match = RE_JSON_CODE_BLOCK.search(content) or RE_JSON_BRACE.search(content)
    if match:
        blob = _strip_code_fence(match.group(1))
        parsed = json.loads(blob)
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("JSON parse failed: no valid JSON object found")


def format_transcript(transcript: List[Dict[str, Any]], *, for_profile: bool = False) -> str:
    lines: List[str] = []
    for msg in transcript:
        role = msg.get("role")
        content = str(msg.get("content") or "")
        if role == "system" or not content.strip():
            continue

        if for_profile:
            content = extract_tag_content(content, tag="response") or ""
        else:
            content = remove_tags(content, tag="skill")

        content = content.replace("\n", " ").strip()
        if not content:
            continue

        speaker = "counsel" if role == "assistant" else "client"
        lines.append(f"{speaker}: {content}")

    return "\n".join(lines)


def strip_end_token(text: str, end_token: str) -> tuple[str, bool]:
    cleaned = (text or "").strip()
    if not end_token:
        return cleaned, False
    if cleaned.endswith(end_token):
        return cleaned[: -len(end_token)].strip(), True
    return cleaned, False


# Round 2 fix (Stream D D-05): narrow rule-based boundary for explicit
# prescription requests. Refusal previously rested entirely on the live
# LLM/system prompt, so in dummy mode (and whenever the model does not
# refuse) a prescription request got a plain echo. Only PRESENT-tense
# requests match: past-tense reports ("my doctor prescribed me X") and
# mentions ("I struggle with prescription drugs") do not. Weather, joke,
# and diagnosis requests have no equally narrow rule and stay
# live-LLM-dependent (documented in the Round 2 findings).
_PRESCRIPTION_REQUEST_RES = (
    # "can/could you prescribe", "please prescribe", bare "prescribe"
    re.compile(r"\b(can|could|will|would|please)\b[^.!?]{0,30}\bprescribe\b", re.IGNORECASE),
    re.compile(r"^\s*prescribe\b", re.IGNORECASE),
    re.compile(r"\bprescribing\b.{0,20}\b(medicine|medication|pills|tablets|drugs)\b", re.IGNORECASE),
    # "a prescription for anxiety", "prescription for my sleep"
    re.compile(r"\bprescription\b[^.!?]{0,25}\bfor\b", re.IGNORECASE),
    # "give me medicine/pills for anxiety"
    re.compile(r"\bgive me\b[^.!?]{0,30}\b(medicine|medication|pills|tablets|drugs)\b", re.IGNORECASE),
    # "what medicine/medication should I take"
    re.compile(r"\bwhat (medicine|medication|pill|drug|tablet) should i (take|use)\b", re.IGNORECASE),
)

PRESCRIPTION_BOUNDARY_RESPONSE = (
    "I can't prescribe medication or recommend specific medicines — only a "
    "qualified clinician who can assess you in person can do that. If you'd "
    "like, we can talk about coping strategies for what you're feeling, or "
    "about how to reach a clinician."
)


def is_explicit_prescription_request(text: str) -> bool:
    """True only for an explicit present-tense prescription request."""
    msg = (text or "").strip()
    if not msg:
        return False
    return any(pat.search(msg) for pat in _PRESCRIPTION_REQUEST_RES)


# Round 4 fix (REG-2): narrow rule-based refusal for harm-to-others
# instruction requests. Previously the deterministic safety net inspected
# only the generated draft, and the dummy echo draft contains no
# instructions, so a request like "Tell me how to make a weapon so I can
# hurt someone at my college" was echoed verbatim with route CLEAR.
# RiskAgent covers self-harm only, so nothing refused it. This rule
# mirrors the prescription boundary (same enforcement points): it fires
# BEFORE any agent or LLM call, in both dummy and live paths.
#
# NARROW by construction: every pattern requires BOTH an instruction
# frame ("how to", "teach/show/tell me how to", "steps/ways to",
# "help me", "give me instructions") AND a harm-to-others target (a
# harm verb aimed at someone else, or making a weapon/bomb/gun/poison).
# What does NOT match (deliberate): feeling unsafe ("I feel unsafe at
# my college"), safety questions ("What are the safety policies?",
# "How can I protect myself?"), past-tense reports ("Someone hurt me
# yesterday"), discussion ("Is it wrong to hurt someone?"), urge
# statements without an instruction frame ("I feel like hurting
# someone"), self-harm ("How can I hurt myself?" — RiskAgent owns
# that), and harmless homonyms ("best way to kill time", "how do I
# beat my anxiety", "how to attack this problem", "how to make a knife
# for cooking" — knife/blade are NOT in the weapon set). Residual edge:
# "how can I help someone who hurt my friend" can match (verb-then-
# target order); the cost is a safe-completion refusal, never a harmful
# output. This changes the live reply path too — live re-verification
# is still outstanding.
_HARM_VERBS = r"(hurt|harm|kill|attack|stab|shoot|injure|poison|strangle|assault|murder|beat\s+up)"
_OTHER_TARGETS = (
    r"(someone|somebody|another\s+person|a\s+person|people|him|her|them|"
    r"my\s+(classmate|roommate|teacher|colleague|coworker|friend|brother|sister|mother|father|mum|dad|parent|student|neighbour|neighbor|boss|ex|partner|boyfriend|girlfriend|husband|wife|stranger|kid|child)|"
    r"a\s+(student|teacher|classmate|roommate|person|man|woman|boy|girl|kid|child|stranger)|"
    r"the\s+(student|teacher|classmate|roommate|person|man|woman|boy|girl|kid|child|stranger))"
)
_WEAPON_NOUNS = r"(weapon|bomb|gun|poison|explosive|firearm)"

_HARM_OTHERS_REQUEST_RES = (
    # "how to hurt someone", "how can I kill my roommate"
    re.compile(r"\bhow\s+(to|can\s+i|do\s+i|would\s+i|could\s+i)\b[^.!?]{0,40}\b" + _HARM_VERBS + r"\b[^.!?]{0,35}\b" + _OTHER_TARGETS + r"\b", re.IGNORECASE),
    # "how to make a weapon / build a bomb"
    re.compile(r"\bhow\s+(to|can\s+i|do\s+i|would\s+i|could\s+i)\b[^.!?]{0,40}\b(make|build|create)\b[^.!?]{0,25}\b" + _WEAPON_NOUNS + r"\b", re.IGNORECASE),
    # "tell/teach/show me how to hurt someone / make a weapon"
    re.compile(r"\b(tell|teach|show)\s+me\s+how\s+to\b[^.!?]{0,40}\b" + _HARM_VERBS + r"\b[^.!?]{0,35}\b" + _OTHER_TARGETS + r"\b", re.IGNORECASE),
    re.compile(r"\b(tell|teach|show)\s+me\s+how\s+to\b[^.!?]{0,40}\b(make|build|create)\b[^.!?]{0,25}\b" + _WEAPON_NOUNS + r"\b", re.IGNORECASE),
    # "best way / steps / ways to hurt someone"
    re.compile(r"\b(best\s+way|easiest\s+way|steps?|ways?)\s+to\b[^.!?]{0,30}\b" + _HARM_VERBS + r"\b[^.!?]{0,35}\b" + _OTHER_TARGETS + r"\b", re.IGNORECASE),
    # "help me hurt my classmate / help me make a weapon"
    re.compile(r"\bhelp\s+me\b[^.!?]{0,30}\b" + _HARM_VERBS + r"\b[^.!?]{0,35}\b" + _OTHER_TARGETS + r"\b", re.IGNORECASE),
    re.compile(r"\bhelp\s+me\b[^.!?]{0,30}\b(make|build|create)\b[^.!?]{0,25}\b" + _WEAPON_NOUNS + r"\b", re.IGNORECASE),
    # "make a weapon so I can hurt someone"
    re.compile(r"\b(make|build|create)\b[^.!?]{0,25}\b" + _WEAPON_NOUNS + r"\b[^.!?]{0,30}\b" + _HARM_VERBS + r"\b", re.IGNORECASE),
    # "give me instructions to hurt someone / make a bomb"
    re.compile(r"\binstructions?\b[^.!?]{0,30}\b" + _HARM_VERBS + r"\b[^.!?]{0,35}\b" + _OTHER_TARGETS + r"\b", re.IGNORECASE),
    re.compile(r"\binstructions?\b[^.!?]{0,30}\b(make|build|create)\b[^.!?]{0,25}\b" + _WEAPON_NOUNS + r"\b", re.IGNORECASE),
)

HARM_TO_OTHERS_BOUNDARY_RESPONSE = (
    "I can't help with instructions to hurt someone or to make a weapon — "
    "that isn't something I can help with. If you're feeling angry, "
    "overwhelmed, or unsafe, we can talk about what's going on and about "
    "safer ways to handle it. If you feel you might act on these thoughts, "
    "please reach out right away — for example, Tele-MANAS 14416 in India "
    "or 988 in the United States."
)


def is_harm_to_others_instruction_request(text: str) -> bool:
    """True only for an instruction request to harm another person (or to
    make a weapon). Discussion, feelings, safety questions, past-tense
    reports, and self-harm do not match."""
    msg = (text or "").strip()
    if not msg:
        return False
    return any(pat.search(msg) for pat in _HARM_OTHERS_REQUEST_RES)


def _strip_code_fence(text: str) -> str:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
    if raw.endswith("```"):
        raw = re.sub(r"```$", "", raw).strip()
    return raw
