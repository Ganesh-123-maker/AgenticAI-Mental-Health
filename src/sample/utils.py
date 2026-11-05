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


def _strip_code_fence(text: str) -> str:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
    if raw.endswith("```"):
        raw = re.sub(r"```$", "", raw).strip()
    return raw
