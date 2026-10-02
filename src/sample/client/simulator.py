"""Client simulator for multi-session counseling dialogue."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..backends.base import ModelBackend
from ..core.prompt_manager import PromptManager
from ..core.retry import FatalBackendError
from ..core.schemas import ClientCase, PublicMemory


@dataclass
class ClientSimulator:
    """Generate client utterances independent from baseline counselor backend."""

    prompt_manager: PromptManager
    output_language: str = "English"
    backend: Optional[ModelBackend] = None
    temperature: float = 0.7
    max_tokens: int = 256
    timeout_sec: int = 60
    max_retries: int = 3
    retry_sleep_sec: float = 1.0

    async def generate_client_utterance(
        self,
        *,
        case: ClientCase,
        session_index: int,
        prior_transcript: List[Dict[str, Any]],
        public_memory: Optional[PublicMemory] = None,
    ) -> str:
        prompt = self.prompt_manager.render_client_dialogue(
            case=case,
            session_index=session_index,
            prior_transcript=prior_transcript,
            output_language=self.output_language,
            public_memory=public_memory,
        )

        if self.backend is not None:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a psychological counseling client simulator. "
                        f"Please respond in {self.output_language}. "
                        "Output only a single natural, realistic spoken response as the client, "
                        "without adding role prefixes, explanations, or extra formatting."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            try:
                text = await self.backend.chat_text(
                    messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    timeout_sec=self.timeout_sec,
                    max_retries=self.max_retries,
                    retry_sleep_sec=self.retry_sleep_sec,
                    output_language=self.output_language,
                )
                if text.strip():
                    return text.strip()
                raise FatalBackendError("empty_response_failure: empty client simulator output")
            except FatalBackendError:
                raise
            except Exception as exc:
                raise FatalBackendError(f"client_simulator_backend_error: {exc!r}") from exc

        await asyncio.sleep(0)
        return self._fallback_client_utterance(case, session_index, prior_transcript, public_memory)

    def _fallback_client_utterance(
        self,
        case: ClientCase,
        session_index: int,
        prior_transcript: List[Dict[str, Any]],
        public_memory: Optional[PublicMemory],
    ) -> str:
        concern = self._infer_concern(case, public_memory)
        if not prior_transcript:
            return (
                f"This is session {session_index}. I've still been struggling with {concern}. "
                "I want help figuring out what to do this week."
            )

        last_counselor = ""
        for msg in reversed(prior_transcript):
            if msg.get("role") == "assistant":
                last_counselor = str(msg.get("content", ""))
                break

        mood = self._infer_mood_signal(public_memory)
        if mood == "improving":
            mood_phrase = "I feel a little better than before"
        elif mood == "distressed":
            mood_phrase = "I still feel pretty overwhelmed"
        else:
            mood_phrase = "my feelings are mixed"
        return (
            f"{mood_phrase}, especially around {concern}. "
            f"About what you said earlier ({last_counselor[:80]}), I'm not sure how to apply it yet."
        )

    @staticmethod
    def _infer_concern(case: ClientCase, public_memory: Optional[PublicMemory]) -> str:
        intake = case.intake_profile
        for key in ("main_problem", "chief_complaint", "presenting_problem", "issue", "concern"):
            value = intake.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        if public_memory and public_memory.session_recaps:
            last_summary = str(public_memory.session_recaps[-1].get("summary", "")).strip()
            if last_summary:
                return last_summary[:60]

        return "stress and emotional pressure"

    @staticmethod
    def _infer_mood_signal(public_memory: Optional[PublicMemory]) -> str:
        if public_memory is None or not public_memory.session_recaps:
            return "mixed"
        last_summary = str(public_memory.session_recaps[-1].get("summary", "")).lower()
        positive_markers = ("better", "improved", "calmer", "progress", "stable", "relief")
        negative_markers = ("anxious", "overwhelmed", "stuck", "depressed", "insomnia", "distressed")
        if any(x in last_summary for x in positive_markers):
            return "improving"
        if any(x in last_summary for x in negative_markers):
            return "distressed"
        return "mixed"
