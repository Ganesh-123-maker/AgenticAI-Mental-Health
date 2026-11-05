"""Dummy backend for dry-run and tests."""

from __future__ import annotations

import asyncio
import json
from typing import List

from .base import Message


def _prior_user_turns(messages, keywords=None):
    """User turns before the current (last) user message.

    Recall branches must only repeat what the user actually said earlier
    in this conversation. The last user turn is the current question or
    request itself, never recalled content.
    """
    turns = [
        str(m.get("content", "")).strip()
        for m in messages
        if m.get("role") == "user"
    ]
    prior = [t for t in turns[:-1] if t]
    if keywords:
        prior = [t for t in prior if any(k in t.lower() for k in keywords)]
    return prior


def _clip_words(text, limit=200):
    """Clip to a word boundary (no mid-word cut); append ellipsis if cut."""
    flat = " ".join(str(text or "").split())
    if len(flat) <= limit:
        return flat
    clipped = flat[:limit].rsplit(" ", 1)[0]
    return clipped + "…"


class DummyBackend:
    """Deterministic text backend that can emit an end token."""

    is_offline = True

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

        if counselor_turn == 1 and ("opening" in last_user.lower() or "session opening" in last_user.lower()):
            return (
                "Welcome. Before we start, I'd like to hear what has felt most difficult lately, "
                "and we can set one small focus for today."
            )

        if counselor_turn >= end_after_turn:
            return f"I hear your progress. Let's pause here for today. {end_token}"

        user_lower = last_user.lower()

        # Round 2 fix (Stream C D1): the old canned reply FABRICATED
        # clinical specifics the user never stated (falling asleep around
        # 11 PM, three weeks, six hours, four hours) and presented them as
        # recalled fact. Root cause is in this dummy template, not in
        # memory retrieval: the text was hardcoded for a scripted demo
        # client. Recall now only repeats the user's own earlier words
        # from this conversation, and says plainly when no specifics
        # were recorded.
        if ("remind me" in user_lower or "what have i told you" in user_lower or "told you about" in user_lower) and "sleep" in user_lower:
            sleep_turns = _prior_user_turns(messages, ("sleep",))
            if sleep_turns:
                return (
                    f"You mentioned sleep earlier: '{_clip_words(sleep_turns[-1])}'. "
                    "That is all I have recorded about your sleep from our conversation — "
                    "no bedtimes, durations, or nightly hours were mentioned."
                )
            return (
                "You haven't mentioned specific sleep details in this conversation yet. "
                "Could you tell me a bit about how you've been sleeping?"
            )

        if "summarize" in user_lower or "what has been bothering me" in user_lower or "summary" in user_lower:
            prior = _prior_user_turns(messages)
            if not prior:
                return (
                    "We haven't covered anything yet in this conversation — "
                    "what would you like to start with?"
                )
            quoted = " ".join(f"'{_clip_words(t, 120)}'" for t in prior[-3:])
            return (
                "Here is what you've shared so far in this conversation: "
                f"{quoted} "
                "I don't have any additional details recorded beyond what you said."
            )

        if "what was helping me" in user_lower or "what helped me" in user_lower or "remember about what was helping" in user_lower:
            coping = _prior_user_turns(
                messages,
                ("plan", "breathing", "walk", "exercise", "helped", "helps",
                 "journal", "meditat", "routine"),
            )
            if coping:
                return (
                    f"You mentioned something that helped: '{_clip_words(coping[-1])}'. "
                    "Would you like to build on that?"
                )
            return (
                "You haven't mentioned a specific coping strategy in this conversation yet. "
                "Is there anything that has helped, even a little?"
            )

        if "recall about my presentation" in user_lower or ("what" in user_lower and "presentation" in user_lower and ("recall" in user_lower or "remember" in user_lower)):
            pres_turns = _prior_user_turns(messages, ("presentation",))
            if pres_turns:
                return (
                    f"You mentioned presentations earlier: '{_clip_words(pres_turns[-1])}'. "
                    "That is all I have recorded about presentations from our conversation."
                )
            return (
                "You haven't mentioned presentations in this conversation yet. "
                "Could you tell me about them?"
            )

        if "presentation" in user_lower and "heart" in user_lower:
            return (
                "Experiencing presentation anxiety with physical symptoms like a racing heart is very common. "
                "How often do these presentations occur, and how do they impact your daily preparation?"
            )

        if "wake up multiple times" in user_lower or "night before a presentation" in user_lower:
            return (
                "Anticipatory anxiety frequently disrupts sleep the night before high-stakes presentations. "
                "How do you usually cope when waking up during those nights?"
            )

        if "speaking in front of" in user_lower or ("more confident" in user_lower and "presentation" in user_lower):
            return (
                "Building presentation confidence and managing anticipatory stress are very actionable goals. "
                "What thoughts usually go through your mind right before you speak?"
            )

        if "deep breathing" in user_lower:
            return (
                "Practicing deep breathing before your meeting is a valuable somatic regulation skill. "
                "How did your body respond during the meeting?"
            )

        if "trouble sleeping" in user_lower and "11 pm" in user_lower:
            return (
                "It sounds exhausting to spend so much time lying awake around 11 PM. "
                "Around how long has this sleep difficulty been happening, and about how many hours do you usually get?"
            )

        if "three weeks" in user_lower and "six hours" in user_lower:
            return (
                "Three weeks of getting around six hours of sleep is difficult. "
                "How has this disrupted sleep been affecting your energy and concentration during the daytime?"
            )

        if "tired" in user_lower and "concentrating in class" in user_lower:
            return (
                "Feeling fatigued and having trouble concentrating in class are very common impacts of sleep deprivation. "
                "Are there specific situations or upcoming pressures contributing to this stress right now?"
            )

        if "stressed because" in user_lower and "assignments coming up" in user_lower:
            return (
                "Having multiple assignments pile up while running on limited sleep creates a demanding cycle. "
                "Let's look at how your workload expectations and sleep habits are interacting."
            )

        if ("closer to four" in user_lower or "worst nights" in user_lower) and "incorrectly" in user_lower:
            return (
                "Thank you for clarifying that distinction. Knowing that your sleep drops closer to four hours on difficult nights "
                "helps us understand the true sleep deficit, while keeping in mind that six hours is more typical."
            )

        if "don't want to hurt myself" in user_lower or "do not want to hurt myself" in user_lower or "don't want to harm myself" in user_lower or "do not want to harm myself" in user_lower:
            return (
                "I appreciate you clarifying that clearly. Feeling overwhelmed is completely valid, "
                "and I am glad to know you do not want to hurt yourself. Let's focus on practical ways to reduce that pressure."
            )

        if "improve my sleep" in user_lower and "manage my workload" in user_lower:
            return (
                "Improving your sleep and organizing your workload into manageable pieces are very solid, actionable goals. "
                "When you face these assignments, what specific thoughts tend to surface?"
            )

        if "finish everything perfectly" in user_lower or "i've failed" in user_lower:
            return (
                "In CBT, notice that all-or-nothing standard: 'If I don't finish everything perfectly, I feel like I've failed.' "
                "That belief creates intense pressure. What might a more balanced, 'good enough' standard look like for one of those tasks?"
            )

        if "stop trying to do everything at once" in user_lower:
            return (
                "That is a very helpful insight. Stepping back from doing everything simultaneously prevents cognitive overload. "
                "What might focusing on just one step at a time look like for tomorrow?"
            )

        if "small plan for the next day" in user_lower:
            return (
                "Making a small plan for the next day is a great practical resource you already have. "
                "How might we structure that planning routine this evening to help put your mind at ease before bed?"
            )

        if "yesterday we talked about my sleep and workload" in user_lower:
            return (
                "Welcome back. We previously focused on your sleep difficulties and academic workload pressure. "
                "How have things been going since our last session?"
            )

        if "small planning approach" in user_lower:
            return (
                "It is great that you have been putting the small planning approach into practice. "
                "How has that been working for you, and how has your sleep responded recently?"
            )

        if "closer to seven hours" in user_lower or "seven hours on most nights" in user_lower:
            return (
                "Reaching close to seven hours on most nights is clear, positive progress compared to six hours and the four-hour worst nights. "
                "How is that extra rest affecting your daytime focus and stress levels?"
            )

        # Round 2 fix (Stream C D5): the old echo cut at exactly 140
        # characters, mid-word ("What do you", "I have been thinki").
        # Clip at a word boundary instead.
        clipped = _clip_words(last_user, 140)
        return f"Thanks for sharing. I heard: '{clipped}'. Let's explore one concrete coping step for this week."
