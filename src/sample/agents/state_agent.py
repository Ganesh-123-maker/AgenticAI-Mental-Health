"""State Assessment Agent for PsychAgent.

This agent consumes the Memory Agent's output and the current AgentContext
and produces a structured description of the current client state.

IMPORTANT design constraints
-----------------------------
* This is NOT a diagnosis agent.
* This is NOT an uncertainty agent.
* This is NOT a risk/routing agent.
* It must NOT output clinical labels, DSM/ICD categories, or severity ratings.
* It must NOT decide CLEAR vs UNCERTAIN vs HIGH-RISK.
* It must NOT decide whether clarification is needed.
* It must NOT decide whether crisis intervention is needed.

What it DOES
------------
It describes, in structured form, what IS and IS NOT known from the
current evidence — the profile, the memory output, and the current message —
without fabricating missing information.

All fields that cannot be evidenced are recorded as "(unavailable)" or
placed in ``unknown_information`` rather than guessed.

Output (AgentMessage.payload)
------------------------------
current_concern         Client's currently expressed concern (string or
                        "(unavailable)").
expressed_needs         What the client has explicitly said they want.
current_session_focus   The agreed session focus/goal for this session.
known_information       List of facts explicitly supported by the evidence.
unknown_information     List of facts that are absent from the evidence.
context                 Dict of additional structured context (stage, session,
                        modality, static traits).
longitudinal_relevance  String describing how prior sessions relate to now.
confidence              Fraction of expected fields that could be populated
                        from evidence (0.0–1.0).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import Agent, AgentContext, AgentError, AgentMessage

logger = logging.getLogger(__name__)

# Fields we expect to know in a well-populated case; used for confidence
_EXPECTED_KNOWN_FIELDS = (
    "main_problem",
    "core_demands",
    "known_static_traits",
    "growth_experiences",
    "current_stage",
    "session_index",
    "prior_session_recaps",
    "theory_info",
    "last_homework",
)


class StateAgent(Agent):
    """Structures what is known and unknown from the current evidence.

    Does not require a live LLM call — it operates deterministically on
    the structured data already gathered by the Memory Agent.
    """

    name = "state_agent"

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
                error=str(exc),
                missing_information=["all state fields (unexpected error)"],
            )

    def _run(self, ctx: AgentContext) -> AgentMessage:
        # -------------------------------------------------------------------
        # Step 1: pull Memory Agent payload from ctx or memory_output
        # -------------------------------------------------------------------
        mem_payload: Dict[str, Any] = {}
        if isinstance(ctx.memory_output, dict):
            mem_payload = ctx.memory_output

        # Convenience extractors with safe defaults
        def _str(key: str, default: str = "(unavailable)") -> str:
            val = mem_payload.get(key) or default
            return str(val).strip() or default

        def _list(key: str) -> List[Any]:
            val = mem_payload.get(key)
            if isinstance(val, list):
                return list(val)
            if isinstance(val, str) and val.strip() and val.strip() != "(unavailable)":
                return [val.strip()]
            return []

        def _dict(key: str) -> Dict[str, Any]:
            val = mem_payload.get(key)
            return dict(val) if isinstance(val, dict) else {}

        # -------------------------------------------------------------------
        # Step 2: determine current concern
        # -------------------------------------------------------------------
        # Use the latest client utterance first; fall back to main_problem
        current_concern: str
        if ctx.current_message and ctx.current_message.strip():
            current_concern = ctx.current_message.strip()
        else:
            mp = _str("main_problem")
            current_concern = mp

        # -------------------------------------------------------------------
        # Step 3: expressed needs — from core_demands in the profile
        # -------------------------------------------------------------------
        expressed_needs: str = _str("core_demands")

        # -------------------------------------------------------------------
        # Step 4: current session focus
        # -------------------------------------------------------------------
        goals = _list("current_goals")
        current_session_focus: str = goals[0] if goals else "(unavailable)"

        # -------------------------------------------------------------------
        # Step 5: build known_information list
        # -------------------------------------------------------------------
        known_information: List[str] = []

        static_traits = _dict("known_static_traits")
        if static_traits:
            for key, val in static_traits.items():
                if val and str(val).strip() not in ("not_mentioned", "unknown", "unmentioned", "unknown", ""):
                    known_information.append(f"[Basic Info] {key}: {val}")

        main_problem = _str("main_problem")
        if main_problem != "(unavailable)":
            known_information.append(f"[Chief Complaint] {main_problem}")

        core_demands = _str("core_demands")
        if core_demands != "(unavailable)":
            known_information.append(f"[Core Demands] {core_demands}")

        for ge in _list("growth_experiences"):
            s = str(ge).strip()
            if s:
                known_information.append(f"[Growth Experience] {s}")

        theory_info = _dict("theory_info")
        if theory_info:
            for key, val in theory_info.items():
                if val:
                    known_information.append(f"[{ctx.modality.upper()} Theory] {key}: Recorded")

        recaps = _list("session_recaps")
        for recap in recaps:
            if isinstance(recap, dict):
                summary = str(recap.get("summary", "")).strip()
                idx = recap.get("session_index", "?")
                if summary:
                    known_information.append(f"[Session {idx} Summary] {summary}")

        if mem_payload.get("last_homework"):
            for hw in _list("last_homework"):
                s = str(hw).strip()
                if s:
                    known_information.append(f"[Previous Homework] {s}")

        prev_interventions = _list("previous_interventions")
        for intv in prev_interventions:
            s = str(intv).strip()
            if s:
                known_information.append(f"[Past Intervention] {s}")

        if ctx.current_message and ctx.current_message.strip():
            known_information.append(f"[Current Statement] {ctx.current_message.strip()}")

        # -------------------------------------------------------------------
        # Step 6: build unknown_information list
        # -------------------------------------------------------------------
        unknown_information: List[str] = list(mem_payload.get("missing_information", []))
        # Also propagate missing_information from the memory agent message
        # (if stored on ctx.memory_output as a separate key)
        extra_missing = mem_payload.get("_missing_from_memory_agent", [])
        if isinstance(extra_missing, list):
            for item in extra_missing:
                if item not in unknown_information:
                    unknown_information.append(str(item))

        # Structural checks: add items missing from known_information
        if not static_traits or all(
            str(v).strip() in ("not_mentioned", "unknown", "") for v in static_traits.values()
        ):
            _add_if_absent(unknown_information, "known_static_traits (not populated)")

        if main_problem == "(unavailable)":
            _add_if_absent(unknown_information, "main_problem (not in profile or context)")

        if core_demands == "(unavailable)":
            _add_if_absent(unknown_information, "core_demands (not in profile or context)")

        if not _list("growth_experiences"):
            _add_if_absent(unknown_information, "growth_experiences (empty or not provided)")

        if not theory_info:
            _add_if_absent(unknown_information, "theory_info (not available for this modality)")

        if not recaps:
            _add_if_absent(unknown_information, "prior_session_recaps (first session or no history)")

        if not ctx.current_message or not ctx.current_message.strip():
            _add_if_absent(unknown_information, "current_message (no client utterance)")

        # -------------------------------------------------------------------
        # Step 7: context dict
        # -------------------------------------------------------------------
        context_dict: Dict[str, Any] = {
            "modality": ctx.modality,
            "therapy_stage": ctx.therapy_stage or _str("current_stage"),
            "session_index": ctx.session_index,
            "source": mem_payload.get("source", "none"),
        }

        # -------------------------------------------------------------------
        # Step 8: longitudinal relevance (descriptive, not evaluative)
        # -------------------------------------------------------------------
        longitudinal_relevance: str
        if recaps:
            last_recap = recaps[-1]
            last_idx = last_recap.get("session_index", "?") if isinstance(last_recap, dict) else len(recaps)
            longitudinal_relevance = (
                f"Total of {len(recaps)} historical session records. "
                f"Most recent is Session {last_idx}."
            )
            if prev_interventions:
                longitudinal_relevance += f" Recorded {len(prev_interventions)} past intervention steps."
        else:
            longitudinal_relevance = "No historical session records found (initial session or standalone evaluation)."

        # -------------------------------------------------------------------
        # Step 9: confidence — fraction of expected fields populated
        # -------------------------------------------------------------------
        populated = 0
        if static_traits:
            populated += 1
        if main_problem != "(unavailable)":
            populated += 1
        if core_demands != "(unavailable)":
            populated += 1
        if _list("growth_experiences"):
            populated += 1
        if context_dict.get("therapy_stage") and context_dict["therapy_stage"] != "(unavailable)":
            populated += 1
        if ctx.session_index is not None:
            populated += 1
        if recaps:
            populated += 1
        if theory_info:
            populated += 1
        if _list("last_homework"):
            populated += 1

        confidence = populated / len(_EXPECTED_KNOWN_FIELDS)

        # -------------------------------------------------------------------
        # Step 10: evidence and missing lists for AgentMessage wrapper
        # -------------------------------------------------------------------
        evidence: List[str] = [
            f"{len(known_information)} known information items",
            f"{len(unknown_information)} items requiring clarification",
        ]
        if recaps:
            evidence.append(f"Based on {len(recaps)} historical sessions")

        # -------------------------------------------------------------------
        # Step 11: assemble payload
        # -------------------------------------------------------------------
        payload: Dict[str, Any] = {
            "current_concern": current_concern,
            "expressed_needs": expressed_needs,
            "current_session_focus": current_session_focus,
            "known_information": known_information,
            "unknown_information": unknown_information,
            "context": context_dict,
            "longitudinal_relevance": longitudinal_relevance,
            "confidence": confidence,
        }

        status = "ok" if known_information else "partial"

        return AgentMessage(
            agent=self.name,
            status=status,
            evidence=evidence,
            confidence=confidence,
            missing_information=unknown_information,
            recommended_action=None,  # routing is a later agent's responsibility
            next_agent=None,
            payload=payload,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_if_absent(lst: List[str], item: str) -> None:
    if item not in lst:
        lst.append(item)
