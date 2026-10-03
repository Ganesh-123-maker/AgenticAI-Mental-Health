"""Dummy backend for dry-run and tests."""

from __future__ import annotations

import asyncio
import json
from typing import List

from .base import Message


class DummyBackend:
    """Deterministic text backend that can emit an end token."""

    def __init__(self, *, default_end_after_turn: int = 2) -> None:
        self._default_end_after_turn = default_end_after_turn

    async def chat_text(self, messages: List[Message], **kwargs: object) -> str:
        await asyncio.sleep(0)
        end_after_turn = int(kwargs.get("dummy_end_after_turn", self._default_end_after_turn))
        end_token = str(kwargs.get("end_token", "</end>"))
        if messages:
            system_text = str(messages[0].get("content", "")).lower()
            if "client simulator" in system_text or "simulator" in system_text:
                return (
                    "I still get anxious and self-critical about what happened at the shelter. "
                    "Your question helps me keep talking."
                )
            if "session_summary_abstract" in system_text:
                state_analysis = {
                    "affective_state": "Anxious but cooperative",
                    "behavioral_patterns": "Actively seeking help",
                    "therapeutic_alliance": "Good",
                    "unresolved_points_or_tensions": "Self-blame",
                }
                if "target_behavior" in system_text:
                    state_analysis["target_behavior"] = "Emotional avoidance"
                elif "existentialism_topic" in system_text:
                    state_analysis["existentialism_topic"] = "Existential anxiety"
                elif "subconscious_manifestation" in system_text:
                    state_analysis["subconscious_manifestation"] = "Subconscious resistance"
                elif "personal_agency" in system_text:
                    state_analysis["personal_agency"] = "Personal agency"
                else:
                    state_analysis["cognitive_patterns"] = "Self-critical"

                payload = {
                    "session_summary_abstract": "The session focused on current distress and a practical next step.",
                    "goal_assessment": {
                        "objective_recap": "Establish session goals",
                        "completion_status": "Partially achieved",
                        "evidence_and_analysis": "Client agreed to track emotional triggers."
                    },
                    "client_state_analysis": state_analysis,
                    "next_session_plan": {
                        "next_session_stage": "Core cognitive and behavioral interventions",
                        "next_session_focus": ["Identify automatic thoughts"]
                    },
                    "homework": ["Track one trigger this week and note thoughts and feelings."]
                }
                return f"<response>\n{json.dumps(payload, ensure_ascii=False)}\n</response>"

            if "profile merging and update" in system_text:
                static_traits = {
                    "name": "Alex", "age": "25", "gender": "Male", "occupation": "Engineer",
                    "educational_background": "Bachelor", "marital_status": "Single",
                    "family_status": "Good", "social_status": "Moderate", "medical_history": "None"
                }
                base_profile = {
                    "static_traits": static_traits,
                    "main_problem": "Primary emotional distress and anxiety",
                    "topic": "Emotion regulation",
                    "core_demands": "Wants to improve emotion regulation skills",
                    "growth_experiences": ["High stress since graduating college"]
                }
                if "targetbehavioritem" in system_text or "target_behavior" in system_text:
                    base_profile["target_behavior"] = [{
                        "behavior": "Avoid communicating with others",
                        "antecedent": ["High work stress"],
                        "core_reason": "Fear of criticism",
                        "function": "Self-protection",
                        "consequence": "Emotional suppression"
                    }]
                elif "existentialismtopicitem" in system_text or "existentialism_topic" in system_text or "contact_model" in system_text:
                    base_profile["existentialism_topic"] = [{
                        "theme": "Existential anxiety",
                        "manifestations": ["Feeling lost"],
                        "outcomes": ["Seeking meaning"]
                    }]
                    base_profile["contact_model"] = [{
                        "mode": "Withdrawal",
                        "definition": "Reducing social interactions",
                        "manifestations": ["Solitude"]
                    }]
                elif "core_conflict" in system_text or "object_relations" in system_text:
                    base_profile["core_conflict"] = {
                        "wish": "Gain acceptance",
                        "fear": "Being rejected",
                        "defense_goal": ["Suppressing expression"]
                    }
                    base_profile["object_relations"] = [{
                        "self_representation": "Imperfect self",
                        "object_representation": "Demanding others",
                        "linking_affect": "Anxiety"
                    }]
                    base_profile["behavioral_response_patterns"] = [{
                        "trigger_condition": "Being criticized",
                        "interpretation": "I am not good enough",
                        "defense_mechanism": "Intellectualization",
                        "response_instruction": "Stay calm and keep notes"
                    }]
                elif "exception_events" in system_text or "force_field" in system_text:
                    base_profile["exception_events"] = [{
                        "target_problem": "Losing emotional control",
                        "unique_outcome": "Successfully practiced deep breathing relaxation",
                        "reason": "Recognized emotional signals early"
                    }]
                    base_profile["force_field"] = {
                        "positive_force": ["Actively seeking help"],
                        "negative_force": ["Overwork"]
                    }
                else:
                    base_profile["core_beliefs"] = ["I must perform perfectly to be accepted"]
                    base_profile["special_situations"] = [{
                        "event": "Work presentation fell short of expectations",
                        "conditional_assumptions": "If I am not perfect, I fail",
                        "compensatory_strategies": "Over-preparation",
                        "automatic_thoughts": "I can't do this well",
                        "cognitive_pattern": "Catastrophizing",
                        "progress": "Pending resolution",
                        "analysis": ["Examine differences between automatic thoughts and reality"]
                    }]
                return f"<response>\n{json.dumps(base_profile, ensure_ascii=False)}\n</response>"

        counselor_turn = sum(1 for m in messages if m.get("role") == "assistant") + 1
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = msg.get("content", "")
                break

        # Opening generation path: avoid echoing meta task instructions.
        if counselor_turn == 1 and ("opening" in last_user.lower() or "session opening" in last_user.lower()):
            return (
                "Welcome. Before we start, I'd like to hear what has felt most difficult lately, "
                "and we can set one small focus for today."
            )

        if counselor_turn >= end_after_turn:
            return f"I hear your progress. Let's pause here for today. {end_token}"

        clipped = last_user.replace("\n", " ")[:140]
        return f"Thanks for sharing. I heard: '{clipped}'. Let's explore one concrete coping step for this week."
