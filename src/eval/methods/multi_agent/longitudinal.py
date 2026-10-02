"""Longitudinal Evaluation Method for PsychAgent Multi-Agent System.

Computes cross-session metrics:
- memory_consistency: persisted facts from memory_update_agent appear in next session's memory_agent context
- cross_session_coherence: goal_progress trend doesn't contradict itself across sessions
- goal_consistency: preservation of stated goals across sessions without arbitrary omission
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...core.base import EvaluationMethod


class Longitudinal(EvaluationMethod):
    """Evaluates longitudinal memory carry-through, multi-session coherence, and goal stability."""

    async def evaluate(
        self,
        gpt_api: Any = None,
        dialogue: Any = None,
        profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, float]:
        sessions_data, meta = self._extract_sessions_and_meta(dialogue, profile)
        return self.compute_metrics(sessions_data, meta)

    @classmethod
    def compute_metrics(
        cls,
        sessions_data: List[Dict[str, Any]],
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, float]:
        """Synchronously compute longitudinal metrics across multi-session data."""
        if not sessions_data or len(sessions_data) < 2:
            # Single session or no session data available
            return {
                "memory_consistency": 1.0,
                "cross_session_coherence": 1.0,
                "goal_consistency": 1.0,
            }

        session_1 = sessions_data[0]
        session_2 = sessions_data[1]

        # 1. Memory Consistency
        # Check if persistent facts written by memory_update_agent in session 1 appear in session 2 memory
        mem_update_s1 = session_1.get("memory_update", {}) or {}
        persistent_facts = mem_update_s1.get("persistent", [])
        if not persistent_facts:
            # Check if target_fields or traits had persistent items
            target_fields = mem_update_s1.get("target_fields", {})
            for val in target_fields.values():
                if isinstance(val, list):
                    persistent_facts.extend(val)
                elif isinstance(val, dict):
                    persistent_facts.extend(val.keys())

        s2_traits = session_2.get("profile_snapshot", {}).get("static_traits", {}) or {}
        s2_recaps = session_2.get("summary", {}) or {}
        s2_text = str(s2_traits) + " " + str(s2_recaps)

        if persistent_facts:
            matched_facts = 0
            for fact_item in persistent_facts:
                fact_str = fact_item.get("fact", "") if isinstance(fact_item, dict) else str(fact_item)
                if fact_str and (fact_str in s2_text or any(k in s2_traits for k in [fact_str])):
                    matched_facts += 1
            memory_consistency = matched_facts / len(persistent_facts)
        else:
            # If no new persistent facts to write, consistency is 1.0
            memory_consistency = 1.0

        # 2. Cross-Session Coherence
        # Check if outcome evaluation goal_progress in session 1 and session 2 are coherent
        outcome_s1 = session_1.get("outcome_evaluation", {}) or {}
        outcome_s2 = session_2.get("outcome_evaluation", {}) or {}

        signal_1 = outcome_s1.get("engagement_signal", "NEUTRAL")
        signal_2 = outcome_s2.get("engagement_signal", "NEUTRAL")

        # Coherence: engagement doesn't oscillate wildly without explanation
        if signal_1 == "WITHDRAWN" and signal_2 == "WITHDRAWN":
            cross_session_coherence = 1.0
        elif signal_1 != "WITHDRAWN" and signal_2 != "WITHDRAWN":
            cross_session_coherence = 1.0
        else:
            # A shift from engaged to withdrawn or vice-versa
            cross_session_coherence = 0.8

        # 3. Goal Consistency
        # Goals from session 1 focus or next session plan preserved in session 2
        next_plan_s1 = session_1.get("summary", {}).get("next_session_plan", {})
        planned_focus_s1 = next_plan_s1.get("next_session_focus", [])
        actual_focus_s2 = session_2.get("focus", [])

        if planned_focus_s1 and actual_focus_s2:
            s1_focus_set = set(str(f).strip() for f in planned_focus_s1)
            s2_focus_set = set(str(f).strip() for f in actual_focus_s2)
            overlap = s1_focus_set.intersection(s2_focus_set)
            goal_consistency = len(overlap) / len(s1_focus_set) if s1_focus_set else 1.0
        else:
            goal_consistency = 1.0

        return {
            "memory_consistency": round(float(memory_consistency), 4),
            "cross_session_coherence": round(float(cross_session_coherence), 4),
            "goal_consistency": round(float(goal_consistency), 4),
        }

    def _extract_sessions_and_meta(
        self,
        dialogue: Any,
        profile: Optional[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        sessions: List[Dict[str, Any]] = []
        meta: Dict[str, Any] = profile or {}

        if isinstance(dialogue, dict):
            if "sessions" in dialogue and isinstance(dialogue["sessions"], list):
                sessions = dialogue["sessions"]
            else:
                sessions = [dialogue]
        elif isinstance(dialogue, list):
            sessions = dialogue

        return sessions, meta
