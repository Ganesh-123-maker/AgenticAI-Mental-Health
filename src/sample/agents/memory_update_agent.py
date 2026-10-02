"""Memory Update Agent for PsychAgent.

Evaluates newly observed information from the Outcome Agent and separates
durable facts to persist in PublicMemory from transitory details to discard.

Constraints:
- Must write into the EXISTING PublicMemory structure from src/sample/core/schemas.py
  (known_static_traits, session_recaps, last_homework) — no parallel memory stores.
- Default to NOT persisting unless a fact is clearly durable (a stated goal,
  a recurring theme, a safety-relevant flag).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ..core.schemas import PublicMemory
from .base import Agent, AgentContext, AgentMessage

logger = logging.getLogger(__name__)

# Patterns indicating durable stated goals
_GOAL_PATTERNS = [
    r"(goal|aim to|plan to|want to improve|hope to improve|hope to|wants to improve|plans to|wants to achieve|striving to|hope to learn|hope to solve|committed to)",
]

# Patterns indicating recurring themes, enduring traits, or chronic issues
_THEME_PATTERNS = [
    r"(insomnia|chronic|perfectionism|perfectionist|recurring|long-standing|habitual|family|profession|always had|childhood|relationship)",
]

# Patterns indicating safety-relevant flags
_SAFETY_PATTERNS = [
    r"(suicide|self-harm|kill myself|end it all|crisis|hopelessness|wanting to die|harm myself|overdose)",
]

# Patterns indicating strictly temporary/momentary states
_TEMPORARY_PATTERNS = [
    r"(today|traffic|lunch|coffee|weather|a bit tired right now|busy today|noisy|this morning|just drank|on the road)",
]


class MemoryUpdateAgent(Agent):
    """Classifies outcome facts into persistent vs temporary and updates PublicMemory."""

    name: str = "memory_update_agent"

    def run(
        self,
        ctx: Optional[AgentContext] = None,
        outcome_output: Optional[Dict[str, Any]] = None,
        public_memory: Optional[PublicMemory] = None,
        candidate_facts: Optional[List[str]] = None,
    ) -> AgentMessage:
        """Classify candidate facts and determine updates for PublicMemory.

        Args:
            ctx: Optional AgentContext.
            outcome_output: Output dict from OutcomeAgent. Defaults to ctx.outcome_output.
            public_memory: Existing PublicMemory instance.
            candidate_facts: Optional explicit list of candidate facts to evaluate.

        Returns:
            AgentMessage with persistent vs temporary facts and structured updates.
        """
        # 1. Resolve outcome output & candidate facts
        resolved_outcome = outcome_output
        if resolved_outcome is None and ctx is not None:
            resolved_outcome = ctx.outcome_output or {}
        if resolved_outcome is None:
            resolved_outcome = {}

        facts_to_evaluate: List[str] = []
        if candidate_facts is not None:
            facts_to_evaluate.extend(candidate_facts)

        newly_observed = resolved_outcome.get("newly_observed_information", [])
        if isinstance(newly_observed, list):
            for item in newly_observed:
                if str(item).strip() and str(item).strip() not in facts_to_evaluate:
                    facts_to_evaluate.append(str(item).strip())

        # 2. Classify each fact into persistent vs temporary
        persistent_facts: List[Dict[str, Any]] = []
        temporary_facts: List[str] = []

        for fact in facts_to_evaluate:
            category, is_durable = self._classify_fact(fact)
            if is_durable:
                persistent_facts.append({
                    "fact": fact,
                    "category": category,  # "goal" | "recurring_theme" | "safety_flag" | "static_trait"
                })
            else:
                temporary_facts.append(fact)

        # 3. Build target field breakdown
        traits_to_add: Dict[str, Any] = {}
        safety_flags_to_add: List[str] = []
        goals_to_add: List[str] = []
        themes_to_add: List[str] = []

        for p in persistent_facts:
            cat = p["category"]
            f_text = p["fact"]
            if cat == "safety_flag":
                safety_flags_to_add.append(f_text)
            elif cat == "goal":
                goals_to_add.append(f_text)
            elif cat == "recurring_theme":
                themes_to_add.append(f_text)
            else:
                traits_to_add[f_text] = "confirmed"

        if goals_to_add:
            traits_to_add["stated_goals"] = goals_to_add
        if themes_to_add:
            traits_to_add["recurring_themes"] = themes_to_add
        if safety_flags_to_add:
            traits_to_add["safety_flags"] = safety_flags_to_add

        payload: Dict[str, Any] = {
            "persistent": persistent_facts,
            "temporary": temporary_facts,
            "target_fields": {
                "known_static_traits": traits_to_add,
                "session_recaps": [p["fact"] for p in persistent_facts if p["category"] == "recurring_theme"],
                "last_homework": [],
            },
        }

        evidence = [
            f"Evaluated {len(facts_to_evaluate)} candidate facts",
            f"Classified {len(persistent_facts)} durable facts to persist",
            f"Classified {len(temporary_facts)} transitory facts to discard",
        ]

        return AgentMessage(
            agent=self.name,
            status="ok",
            evidence=evidence,
            confidence=0.9,
            missing_information=[],
            recommended_action="merge_into_public_memory",
            next_agent=None,
            payload=payload,
        )

    def _classify_fact(self, fact: str) -> Tuple[str, bool]:
        """Classify a fact as durable (persistent) or transitory (temporary).

        Returns:
            (category, is_durable)
            Default to NOT persisting unless a fact is clearly durable.
        """
        fact_clean = fact.strip()
        if not fact_clean or len(fact_clean) < 4:
            return "filler", False

        # Check safety flag first (highest durability)
        for pattern in _SAFETY_PATTERNS:
            if re.search(pattern, fact_clean, re.IGNORECASE):
                return "safety_flag", True

        # Check stated goals
        for pattern in _GOAL_PATTERNS:
            if re.search(pattern, fact_clean, re.IGNORECASE):
                return "goal", True

        # Check recurring theme or chronic issue
        for pattern in _THEME_PATTERNS:
            if re.search(pattern, fact_clean, re.IGNORECASE):
                return "recurring_theme", True

        # Explicitly check temporary patterns
        for pattern in _TEMPORARY_PATTERNS:
            if re.search(pattern, fact_clean, re.IGNORECASE):
                return "transitory_state", False

        # Default rule: do NOT persist unless clearly durable
        return "conversational_detail", False

    def apply_update(
        self,
        *,
        public_memory: PublicMemory,
        persistent_facts: List[Dict[str, Any]],
        homework: Optional[List[str]] = None,
        session_summary: Optional[Dict[str, Any]] = None,
    ) -> PublicMemory:
        """Apply persistent facts directly into the existing PublicMemory instance.

        Modifies:
        - public_memory.known_static_traits
        - public_memory.session_recaps
        - public_memory.last_homework

        Does NOT create a new parallel memory store.
        """
        if not isinstance(public_memory, PublicMemory):
            return public_memory

        if not isinstance(public_memory.known_static_traits, dict):
            public_memory.known_static_traits = {}

        # Merge durable goals, themes, and safety flags into known_static_traits
        for item in persistent_facts:
            fact_text = item.get("fact") if isinstance(item, dict) else str(item)
            cat = item.get("category", "trait") if isinstance(item, dict) else "trait"

            if cat == "goal":
                goals = public_memory.known_static_traits.setdefault("stated_goals", [])
                if isinstance(goals, list) and fact_text not in goals:
                    goals.append(fact_text)
            elif cat == "recurring_theme":
                themes = public_memory.known_static_traits.setdefault("recurring_themes", [])
                if isinstance(themes, list) and fact_text not in themes:
                    themes.append(fact_text)
            elif cat == "safety_flag":
                flags = public_memory.known_static_traits.setdefault("safety_flags", [])
                if isinstance(flags, list) and fact_text not in flags:
                    flags.append(fact_text)
            else:
                public_memory.known_static_traits[fact_text] = "persisted"

        # Update last_homework if provided
        if homework is not None and isinstance(homework, list):
            public_memory.last_homework = list(homework)

        # Update session_recaps with summary if provided
        if session_summary is not None and isinstance(session_summary, dict):
            # If session_summary not already in session_recaps, append it
            s_idx = session_summary.get("session_index", len(public_memory.session_recaps) + 1)
            recap_entry = {
                "session_index": s_idx,
                "summary": session_summary.get("session_summary_abstract", ""),
                "homework": session_summary.get("homework", public_memory.last_homework),
                "static_traits": dict(public_memory.known_static_traits),
            }
            # Check if this session index already exists in recaps
            existing_idx = [r.get("session_index") for r in public_memory.session_recaps if isinstance(r, dict)]
            if s_idx not in existing_idx:
                public_memory.session_recaps.append(recap_entry)

        return public_memory
