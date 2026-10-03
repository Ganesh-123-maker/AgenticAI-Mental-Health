"""Memory/Context Agent for PsychAgent.

This agent is READ-ONLY with respect to memory.  It gathers context from
the existing PsychAgent memory structures (PublicMemory, history_list,
obtain_client_info, homework_assigned) and presents it in a form suitable
for the State Assessment Agent.

It does NOT:
- write to any memory store
- create a new parallel memory store
- replace the existing PublicMemory architecture
- require a live LLM call

The existing runner's ``_build_public_memory`` method is the authoritative
source of PublicMemory construction.  This agent reads from an already-built
PublicMemory (or constructs one locally from the runner state fields carried
in AgentContext) to avoid any dependency on the runner itself.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

from ..core.schemas import PublicMemory
from .base import Agent, AgentContext, AgentError, AgentMessage

logger = logging.getLogger(__name__)


class MemoryAgent(Agent):
    """Gathers and structures longitudinal context from existing memory stores.

    Input (from AgentContext)
    -------------------------
    ctx.public_memory       PublicMemory instance, if already built by caller.
    ctx.history_list        Session summary dicts (runner state).
    ctx.obtain_client_info  Counselor-visible profile dict (runner state).
    ctx.homework_assigned   Current homework list (runner state).
    ctx.full_profile        Full raw profile (assets/profiles/ or benchmark).
    ctx.current_message     Latest client utterance (optional).
    ctx.therapy_stage       Current therapy stage (optional).
    ctx.session_index       Current session index (optional).

    Output (AgentMessage.payload)
    -----------------------------
    known_static_traits     Static client info (age, occupation, …).
    session_recaps          List of prior-session summaries.
    last_homework           Most recent homework items.
    current_session_index   Session number, or None.
    current_stage           Therapy stage, or "(unknown)".
    previous_interventions  List of strings extracted from session summaries.
    current_goals           List of strings from the latest session plan.
    prior_outcomes          List of strings extracted from summaries.
    newly_observed          Any content from the current message worth noting.
    source                  Which memory fields were populated ("public_memory"
                            | "runner_state" | "full_profile" | "none").
    """

    name = "memory_agent"

    def run(self, ctx: AgentContext) -> AgentMessage:  # noqa: C901
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
                missing_information=["all context (unexpected error)"],
            )

    def _run(self, ctx: AgentContext) -> AgentMessage:
        # -------------------------------------------------------------------
        # Step 1: resolve PublicMemory — prefer already-built instance,
        #         fall back to building one from runner-state fields.
        # -------------------------------------------------------------------
        source_flags: List[str] = []

        if isinstance(ctx.public_memory, PublicMemory):
            mem = ctx.public_memory
            source_flags.append("public_memory")
        elif ctx.history_list or ctx.obtain_client_info or ctx.homework_assigned:
            mem = self._build_from_runner_state(ctx)
            source_flags.append("runner_state")
        else:
            mem = PublicMemory()  # empty but structurally valid
            source_flags.append("none")

        # -------------------------------------------------------------------
        # Step 2: extract static profile info from full_profile if available
        # -------------------------------------------------------------------
        raw_basic_info: Dict[str, Any] = {}
        raw_theory_info: Dict[str, Any] = {}
        if isinstance(ctx.full_profile, dict):
            source_flags.append("full_profile")
            raw_basic_info = ctx.full_profile.get("basic_info", {}) or {}
            raw_theory_info = (
                ctx.full_profile.get("theory", {}) or {}
            ).get(ctx.modality, {}) or {}
        elif isinstance(ctx.obtain_client_info, dict) and ctx.obtain_client_info:
            # No raw profile (e.g. live web sessions): use the counselor-visible
            # profile carried in runner/web state. Placeholder values are dropped
            # so that genuinely unknown fields stay unknown.
            raw_basic_info = _basic_info_from_client_info(ctx.obtain_client_info)

        # Merge known_static_traits: public_memory wins over raw profile
        known_static_traits: Dict[str, Any] = {}
        if isinstance(raw_basic_info.get("static_traits"), dict):
            known_static_traits.update(raw_basic_info["static_traits"])
        if isinstance(mem.known_static_traits, dict) and mem.known_static_traits:
            known_static_traits.update(
                {k: v for k, v in mem.known_static_traits.items() if not _is_placeholder(v)}
            )

        # -------------------------------------------------------------------
        # Step 3: extract previous interventions and outcomes from summaries
        # -------------------------------------------------------------------
        previous_interventions: List[str] = []
        prior_outcomes: List[str] = []
        current_goals: List[str] = []

        for recap in mem.session_recaps:
            if not isinstance(recap, dict):
                continue
            summary_text = str(recap.get("summary", "") or "")
            if summary_text.strip():
                previous_interventions.append(
                    f"[Session {recap.get('session_index', '?')}] {summary_text.strip()}"
                )
            hw = recap.get("homework", [])
            if isinstance(hw, list):
                for item in hw:
                    s = str(item).strip()
                    if s:
                        prior_outcomes.append(s)

        # Current goals from full_profile or latest session plan
        core_demands = str(raw_basic_info.get("core_demands", "") or "").strip()
        if core_demands:
            current_goals.append(core_demands)

        # Extract goals from history_list's latest next_session_plan
        if ctx.history_list:
            last_summary = ctx.history_list[-1]
            if isinstance(last_summary, dict):
                nsp = last_summary.get("next_session_plan", {})
                if isinstance(nsp, dict):
                    focus = nsp.get("next_session_focus", [])
                    if isinstance(focus, list):
                        current_goals.extend(str(f) for f in focus if str(f).strip())

        # -------------------------------------------------------------------
        # Step 4: newly observed content from current message
        # -------------------------------------------------------------------
        newly_observed: List[str] = []
        if ctx.current_message and ctx.current_message.strip():
            newly_observed.append(ctx.current_message.strip())

        # -------------------------------------------------------------------
        # Step 5: evidence summary
        # -------------------------------------------------------------------
        evidence: List[str] = []
        if mem.session_recaps:
            evidence.append(f"{len(mem.session_recaps)} historical session recap(s) loaded")
        if mem.last_homework:
            evidence.append(f"{len(mem.last_homework)} assigned homework task(s)")
        if known_static_traits:
            evidence.append(f"{len(known_static_traits)} known static trait(s)")
        if raw_basic_info.get("main_problem"):
            evidence.append("Chief complaint loaded")
        if raw_basic_info.get("growth_experiences"):
            ge = raw_basic_info["growth_experiences"]
            if isinstance(ge, list) and ge:
                evidence.append(f"{len(ge)} developmental milestone(s) loaded")

        missing: List[str] = []
        if not mem.session_recaps:
            missing.append("prior_session_recaps (first session or no history)")
        if not mem.last_homework:
            missing.append("last_homework (not yet assigned)")
        if not current_goals:
            missing.append("current_goals (not available from profile or history)")
        if not ctx.current_message:
            missing.append("current_message (no client utterance provided)")

        # -------------------------------------------------------------------
        # Step 6: assemble payload
        # -------------------------------------------------------------------
        payload: Dict[str, Any] = {
            "known_static_traits": copy.deepcopy(known_static_traits),
            "session_recaps": copy.deepcopy(mem.session_recaps),
            "last_homework": list(mem.last_homework),
            "current_session_index": ctx.session_index,
            "current_stage": ctx.therapy_stage or "(unknown)",
            "previous_interventions": previous_interventions,
            "current_goals": current_goals,
            "prior_outcomes": prior_outcomes,
            "newly_observed": newly_observed,
            "main_problem": str(raw_basic_info.get("main_problem", "") or ""),
            "core_demands": str(raw_basic_info.get("core_demands", "") or ""),
            "growth_experiences": copy.deepcopy(
                raw_basic_info.get("growth_experiences", []) or []
            ),
            "theory_info": copy.deepcopy(raw_theory_info),
            "source": "|".join(source_flags),
        }

        status = "ok" if source_flags != ["none"] else "unavailable"

        return AgentMessage(
            agent=self.name,
            status=status,
            evidence=evidence,
            confidence=None,  # Memory is factual, not probabilistic
            missing_information=missing,
            recommended_action="state_agent" if status == "ok" else None,
            next_agent="state_agent",
            payload=payload,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_from_runner_state(self, ctx: AgentContext) -> PublicMemory:
        """Reconstruct PublicMemory from runner-state fields in AgentContext.

        Mirrors the logic in ``runner.PsychAgentRunner._build_public_memory``
        without importing the runner (avoids circular dependencies).
        """
        obtain_client_info = ctx.obtain_client_info or {}
        homework_assigned = list(ctx.homework_assigned or [])

        recaps: List[Dict[str, Any]] = []
        for idx, item in enumerate(ctx.history_list or [], start=1):
            if not isinstance(item, dict):
                continue
            recaps.append(
                {
                    "session_index": idx,
                    "summary": item.get("session_summary_abstract", ""),
                    "homework": item.get("homework", []),
                    "static_traits": obtain_client_info.get("static_traits", {}),
                }
            )

        known_static_traits: Dict[str, Any] = {}
        if isinstance(obtain_client_info, dict):
            static_traits = obtain_client_info.get("static_traits", {})
            if isinstance(static_traits, dict):
                known_static_traits = dict(static_traits)

        return PublicMemory(
            known_static_traits=known_static_traits,
            session_recaps=recaps,
            last_homework=homework_assigned,
        )


# Values the web/runner layers use as "not yet known" placeholders.
_PLACEHOLDER_VALUES = {
    "", "unknown", "unmentioned", "not_mentioned", "not mentioned", "n/a", "none",
    "to be clarified", "current concern", "client", "(unavailable)",
}


def _is_placeholder(value: Any) -> bool:
    return str(value or "").strip().lower() in _PLACEHOLDER_VALUES


def _basic_info_from_client_info(client_info: Dict[str, Any]) -> Dict[str, Any]:
    """Build a ``basic_info``-shaped dict from obtain_client_info without placeholders."""
    basic: Dict[str, Any] = {}
    traits = client_info.get("static_traits")
    if isinstance(traits, dict):
        clean_traits = {k: v for k, v in traits.items() if not _is_placeholder(v)}
        if clean_traits:
            basic["static_traits"] = clean_traits
    for key in ("main_problem", "core_demands", "topic"):
        value = client_info.get(key)
        if isinstance(value, str) and not _is_placeholder(value):
            basic[key] = value.strip()
    growth = client_info.get("growth_experiences")
    if isinstance(growth, list):
        clean_growth = [str(g).strip() for g in growth if not _is_placeholder(g)]
        if clean_growth:
            basic["growth_experiences"] = clean_growth
    return basic
