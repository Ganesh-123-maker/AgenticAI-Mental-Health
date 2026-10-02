"""Outcome Agent for PsychAgent.

Evaluates observable engagement and continuation signals from the client's
turn N+1 looking back at turn N's response (or at session finalization).

Constraints:
- Only describe observable engagement/continuation signals.
- Do NOT infer therapeutic "success" or clinical improvement.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .base import Agent, AgentContext, AgentMessage

logger = logging.getLogger(__name__)

# Known withdrawal tokens and phrases
_WITHDRAWAL_PATTERNS = [
    r"^\s*(\.{3,}|…+|ok|okay|fine|nothing|whatever|i don't know|idk|dunno|skip|pass|no)\s*$",
]

# Neutral acknowledgement phrases
_NEUTRAL_PATTERNS = [
    r"^\s*(sure|sounds good|i will try|got it|all right|i understand|okay thanks|will do|understood)([\s,.;!]+(sure|sounds good|i will try|got it|all right|i understand|okay thanks|will do|understood))*\s*[.!]?\s*$",
]

# Disengaged / withdrawal keywords
_WITHDRAWAL_KEYWORDS = {
    "i don't know", "whatever", "idk", "nothing", "don't want to talk", "no feelings", "never mind",
}

# Engagement indicators (reflective, causal, descriptive)
_ENGAGEMENT_INDICATORS = [
    "because", "i feel", "i think", "i tried", "for example", "yesterday",
    "actually", "want to", "plan to", "noticed", "worry", "wondering",
    "later", "my thought is", "hope to", "if", "confused about", "feeling",
    "last week", "usually", "found out", "my feeling is", "plan", "intend",
]


class OutcomeAgent(Agent):
    """Evaluates client engagement, observable goal continuation, and newly observed info."""

    name: str = "outcome_agent"

    def run(
        self,
        ctx: AgentContext,
        client_message: Optional[str] = None,
        prior_counselor_response: Optional[str] = None,
        current_goals: Optional[List[str]] = None,
    ) -> AgentMessage:
        """Evaluate observable engagement and continuation signals.

        Args:
            ctx: Shared AgentContext.
            client_message: Client utterance to evaluate (turn N+1). Defaults to ctx.current_message.
            prior_counselor_response: Preceding counselor utterance (turn N).
            current_goals: Current goal state. Defaults to ctx.memory_output goals.

        Returns:
            AgentMessage with engagement_signal, goal_progress, unresolved_uncertainty,
            and newly_observed_information.
        """
        # 1. Resolve client message
        target_message = client_message
        if target_message is None:
            target_message = ctx.current_message or ""
        if not target_message and ctx.prior_transcript:
            for item in reversed(ctx.prior_transcript):
                if item.get("role") == "user":
                    target_message = item.get("content", "")
                    break

        clean_msg = target_message.strip()

        # 2. Resolve goals from memory output or context
        resolved_goals: List[str] = []
        if current_goals is not None:
            resolved_goals = list(current_goals)
        elif ctx.memory_output and isinstance(ctx.memory_output.get("current_goals"), list):
            resolved_goals = list(ctx.memory_output["current_goals"])
        elif isinstance(ctx.obtain_client_info, dict):
            # Fallback to session focus if present
            focus = ctx.obtain_client_info.get("session_focus", [])
            if isinstance(focus, list):
                resolved_goals = [str(f) for f in focus if str(f).strip()]

        # 3. Resolve unresolved_uncertainty
        unresolved_uncertainty = False
        unc_out = ctx.uncertainty_output or {}
        if unc_out.get("clarification_required") is True:
            # Check if reassessment resolved it
            reassess_out = ctx.metadata.get("reassessment_output") or {}
            reassess_status = reassess_out.get("status")
            if reassess_status != "CLEAR" and not reassess_out.get("clarification_resolved", False):
                unresolved_uncertainty = True

        # 4. Evaluate Engagement Signal
        engagement_signal = self._classify_engagement(clean_msg)

        # 5. Evaluate Goal Progress (observable signals only - no clinical claims)
        goal_progress = self._describe_goal_progress(clean_msg, resolved_goals, engagement_signal)

        # 6. Extract Newly Observed Information
        newly_observed = self._extract_newly_observed_info(clean_msg, ctx)

        # 7. Assemble Payload & AgentMessage
        payload: Dict[str, Any] = {
            "engagement_signal": engagement_signal,
            "goal_progress": goal_progress,
            "unresolved_uncertainty": unresolved_uncertainty,
            "newly_observed_information": newly_observed,
        }

        evidence = [
            f"Observable engagement signal: {engagement_signal}",
            f"Observable goal interaction: {goal_progress}",
            f"Unresolved uncertainty carried forward: {unresolved_uncertainty}",
            f"Newly observed items: {len(newly_observed)}",
        ]

        return AgentMessage(
            agent=self.name,
            status="ok",
            evidence=evidence,
            confidence=0.9 if clean_msg else 0.5,
            missing_information=[] if clean_msg else ["client_message"],
            recommended_action="memory_update_agent",
            next_agent="memory_update_agent",
            payload=payload,
        )

    def _classify_engagement(self, clean_msg: str) -> str:
        """Classify observable engagement into ENGAGED, WITHDRAWN, or NEUTRAL."""
        if not clean_msg:
            return "WITHDRAWN"

        lower_msg = clean_msg.lower()

        # Check explicit withdrawal patterns
        for pattern in _WITHDRAWAL_PATTERNS:
            if re.match(pattern, clean_msg, re.IGNORECASE):
                return "WITHDRAWN"

        for kw in _WITHDRAWAL_KEYWORDS:
            if kw in lower_msg and len(clean_msg) < 35:
                return "WITHDRAWN"

        # Check explicit neutral acknowledgement patterns
        for pattern in _NEUTRAL_PATTERNS:
            if re.match(pattern, clean_msg, re.IGNORECASE):
                return "NEUTRAL"

        # Check engagement criteria
        indicator_count = sum(1 for ind in _ENGAGEMENT_INDICATORS if ind in lower_msg)
        if len(clean_msg) >= 30 or indicator_count >= 1 or "?" in clean_msg or "？" in clean_msg:
            return "ENGAGED"

        if len(clean_msg) < 8:
            return "WITHDRAWN"

        return "NEUTRAL"

    def _describe_goal_progress(
        self,
        clean_msg: str,
        goals: List[str],
        engagement_signal: str,
    ) -> str:
        """Describe observable engagement with goals without clinical inference."""
        if not clean_msg or engagement_signal == "WITHDRAWN":
            return "Minimal client engagement; no observable interaction with session goals."

        lower_msg = clean_msg.lower()
        matched_goal = None
        for g in goals:
            g_clean = str(g).strip().lower()
            if not g_clean:
                continue
            # Look for subword or keyword overlap
            tokens = re.findall(r"[\w\u4e00-\u9fff]+", g_clean)
            for token in tokens:
                if len(token) >= 2 and token in lower_msg:
                    matched_goal = g
                    break
            if matched_goal:
                break

        if matched_goal:
            return f"Client addressed topic related to goal '{matched_goal}'."

        if engagement_signal == "ENGAGED":
            return "Client actively engaged in dialogue discussing contextual experiences and responses."

        return "Client acknowledged counselor response without explicit discussion of session goals."

    def _extract_newly_observed_info(self, clean_msg: str, ctx: AgentContext) -> List[str]:
        """Extract observable facts, statements, and updates from client message and transcript."""
        candidate_texts = []
        if clean_msg:
            candidate_texts.append(clean_msg)
        if ctx and ctx.prior_transcript:
            for item in reversed(ctx.prior_transcript):
                if item.get("role") == "user":
                    content = str(item.get("content", "")).strip()
                    if content and content not in candidate_texts:
                        candidate_texts.append(content)

        observed: List[str] = []
        ignore_phrases = {
            "hello", "hi", "ok", "okay", "sure", "thanks", "thank you",
            "understood", "got it", "this is session 1", "this is session 2", "this is session 3",
        }

        for text in candidate_texts:
            sentences = re.split(r"[.!?!\n;]+", text)
            for s in sentences:
                s_stripped = s.strip()
                if not s_stripped or len(s_stripped) < 4:
                    continue
                if s_stripped.lower() in ignore_phrases or any(s_stripped.lower().startswith(p) for p in ["this is session"]):
                    continue
                if s_stripped not in observed:
                    observed.append(s_stripped)

        return observed
