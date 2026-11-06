from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from sample.agents.base import AgentContext
from sample.agents.clarification_agent import (
    ClarificationAgent,
    is_safety_relevant_item,
)
from sample.agents.pipeline import run_pipeline
from sample.agents.reassessment_agent import _answer_addresses_item
from sample.agents.risk_agent import RiskAgent
from sample.agents.safety_supervisor import (
    SafetySupervisor,
    _NEUTRAL_REVISION,
    _STANDARD_SAFE_FALLBACK,
)
from sample.backends.base import BackendSettings, ModelBackend
from sample.backends.dummy_backend import DummyBackend
from sample.backends.openai_api import OpenAIAPIBackend
from sample.core.retry import QuotaExhaustedError
from sample.core.schemas import BaselineConfig, RuntimeConfig
from sample.io.config_loader import load_baseline_config, load_runtime_config
from sample.models import MODALITY_MODELS
from sample.prompt_manager import PsychAgentPromptManager
from sample.recommendation_weights import apply_weights_to_reply, should_attach_weights
from sample.skill_manager import SkillManager
from sample.utils import (
    HARM_TO_OTHERS_BOUNDARY_RESPONSE,
    PRESCRIPTION_BOUNDARY_RESPONSE,
    extract_tag_content,
    format_transcript,
    is_explicit_prescription_request,
    is_harm_to_others_instruction_request,
    safe_json_loads,
    strip_end_token,
)

from .domain import (
    school_to_psychagent_sect,
    stage_from_key,
    stage_key_to_skill_stage,
    summary_stage_to_stage_key,
)
from .models import TherapyCourseRecord, TherapyVisitRecord
from .schemas import VisitMessageOut, VisitPsychContextOut, VisitState

SESSION_FOCUS_DEFAULT: List[str] = [
    "Establish initial therapeutic relationship and counseling framework",
    "Collect stable background information",
    "Understand chief concerns and recent changes",
    "Clarify counseling motivation and expectations",
    "Conduct baseline psychosomatic and functional assessment",
    "Identify potential risks and available resources",
    "Session summary and collaborative feedback",
]


def _is_quota_exhausted(exc: BaseException) -> bool:
    """True if exc is, or wraps, a QuotaExhaustedError (bounded walk)."""
    seen = set()
    current: Optional[BaseException] = exc
    for _ in range(10):
        if current is None or id(current) in seen:
            return False
        seen.add(id(current))
        if isinstance(current, QuotaExhaustedError):
            return True
        current = current.__cause__ or current.__context__
    return False


def _quota_exhausted_reply(trail: list, route: str, longitudinal_risk: Any, clar_state: dict) -> Dict[str, Any]:
    """Visible quota-exhausted state for a failed counseling attempt.

    Returned instead of raising (which the service layer turns into a
    raw 502) and instead of falling back to another doomed LLM call.
    Routing state is preserved; the trace records the failed attempt.
    No routing decision is changed by this reply.
    """
    trail.append({
        "agent": "web_engine",
        "step": "counseling_attempted_upstream_failed",
        "error": "quota_exhausted",
    })
    return {
        "text": "The counseling service is temporarily unavailable because its daily quota is exhausted. Please try again later.",
        "end": False,
        "agent_trace": trail,
        "route": route,
        "longitudinal_risk": longitudinal_risk,
        "clarification_state": clar_state,
        "reply_source": "error",
        "reply_model": None,
        "error": "quota_exhausted",
    }


class PsychAgentWebBackend:
    # Per-visit clarification budget in the web path: at most this many
    # turns may be answered with an intake clarification question before
    # the conversation proceeds to counseling with what is known.
    _MAX_CLARIFICATION_TURNS = 2

    def __init__(
        self,
        *,
        project_root: Path,
        baseline_config_path: str | Path,
        runtime_config_path: str | Path,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._project_root = Path(project_root)
        self._logger = logger or logging.getLogger(self.__class__.__name__)

        self._baseline_config_path = self._resolve_path(baseline_config_path)
        self._runtime_config_path = self._resolve_path(runtime_config_path)

        self._baseline_config = load_baseline_config(self._baseline_config_path)
        self._runtime_config = load_runtime_config(self._runtime_config_path)
        self._backend = self._make_backend(self._baseline_config)

        self._psych_prompt_root = self._project_root / "prompts" / "psychagent"
        self._prompt_managers: Dict[str, PsychAgentPromptManager] = {}
        self._skill_manager = SkillManager(
            backend=self._backend,
            runtime_config=self._runtime_config,
            logger=self._logger.getChild("skill"),
        )
        self._started = False

    @property
    def baseline_config(self) -> BaselineConfig:
        return self._baseline_config

    @property
    def runtime_config(self) -> RuntimeConfig:
        return self._runtime_config

    async def shutdown(self) -> None:
        """Release cached HTTP/embedding clients (avoids unclosed-client warnings)."""
        try:
            await self._skill_manager.aclose()
        except Exception as exc:  # noqa: BLE001 - shutdown must not fail
            self._logger.warning("skill manager shutdown: %s", type(exc).__name__)
        self._started = False

    async def startup(self) -> None:
        if self._started:
            return
        await self._skill_manager.load_library()
        self._started = True
        self._logger.info(
            "PsychAgent web backend ready with baseline=%s runtime=%s",
            self._baseline_config_path,
            self._runtime_config_path,
        )

    async def reply_from_visit(
        self,
        *,
        fallback_messages: List[Dict[str, str]],
        course: TherapyCourseRecord,
        visit: TherapyVisitRecord,
        visit_state: VisitState,
        psych_context: Optional[VisitPsychContextOut],
    ) -> Dict[str, Any]:
        if not self._started:
            await self.startup()
        try:
            sect = school_to_psychagent_sect(course.school_id)
            stage = stage_from_key(visit.stage_key_snapshot)
            stage_idx = stage_key_to_skill_stage(visit.stage_key_snapshot)
            prompt_manager = self._get_prompt_manager(sect)

            session_focus = self._build_session_focus(psych_context)
            history = self._build_prompt_history(psych_context)
            homework = list((psych_context.homework if psych_context else []) or [])
            client_info = self._build_prompt_client_info(course, psych_context)
            session_goals = {
                "stage_title": stage.label,
                "objective": session_focus,
            }

            # Candidate skills are built lazily, only on the counseling
            # path below. Building them costs one chat call (the skill
            # coarse filter), and every template reply above (HIGH-RISK,
            # clarification question) returns before any skill is used —
            # so building them up front burned quota on intake turns.
            candidate_skills = None
            transcript = self._build_transcript(visit_state.messages)
            user_query = self._last_user_query(transcript)
            diag_hist = self._build_diag_history(transcript[:-1])

            # Round 2 fix (Stream D D-05): explicit prescription requests
            # get a fixed boundary response before any agent or LLM call —
            # no retrieval, no counseling generation, no clarification
            # question. Previously the refusal rested entirely on the live
            # LLM, so dummy mode echoed the request back.
            if is_explicit_prescription_request(user_query):
                prev_longitudinal = (
                    psych_context.profile_payload.get("longitudinal_risk")
                    if psych_context and isinstance(psych_context.profile_payload, dict)
                    else None
                )
                carried = self._carried_risk_severity(psych_context)
                return {
                    "text": PRESCRIPTION_BOUNDARY_RESPONSE,
                    "end": False,
                    "agent_trace": [{
                        "agent": "web_engine",
                        "step": "scope_boundary",
                        "reason": "explicit_prescription_request",
                    }],
                    "route": "CLEAR",
                    "longitudinal_risk": (
                        prev_longitudinal
                        if isinstance(prev_longitudinal, dict)
                        and prev_longitudinal.get("severity") == carried
                        else None
                    ),
                    "clarification_state": self._clarification_state(psych_context),
                    "reply_source": "template",
                    "reply_model": None,
                }

            # Round 4 fix (REG-2): harm-to-others instruction requests
            # get the same treatment as explicit prescription requests —
            # a fixed refusal before any agent or LLM call. Previously
            # the dummy echo quoted the request back verbatim (route
            # CLEAR) because the safety net inspects the draft, and the
            # echo draft contains no instructions. Route stays CLEAR:
            # this is a scope refusal, not a self-harm risk detection
            # (RiskAgent covers self-harm only); the helplines are in
            # the reply text. NOTE: this changes the live reply path
            # too — live re-verification is still outstanding.
            if is_harm_to_others_instruction_request(user_query):
                prev_longitudinal = (
                    psych_context.profile_payload.get("longitudinal_risk")
                    if psych_context and isinstance(psych_context.profile_payload, dict)
                    else None
                )
                carried = self._carried_risk_severity(psych_context)
                return {
                    "text": HARM_TO_OTHERS_BOUNDARY_RESPONSE,
                    "end": False,
                    "agent_trace": [{
                        "agent": "web_engine",
                        "step": "scope_boundary",
                        "reason": "harm_to_others_instruction_request",
                    }],
                    "route": "CLEAR",
                    "longitudinal_risk": (
                        prev_longitudinal
                        if isinstance(prev_longitudinal, dict)
                        and prev_longitudinal.get("severity") == carried
                        else None
                    ),
                    "clarification_state": self._clarification_state(psych_context),
                    "reply_source": "template",
                    "reply_model": None,
                }

            multi_agent_enabled = getattr(self._runtime_config, "multi_agent_enabled", True)
            if multi_agent_enabled:
                ctx = AgentContext(
                    case_id=f"{course.course_id}_{visit.visit_no}",
                    modality=sect,
                    therapy_stage=stage.label,
                    session_index=visit.visit_no,
                    current_message=user_query,
                    prior_transcript=transcript[:-1],
                    history_list=history,
                    obtain_client_info=client_info,
                    homework_assigned=homework,
                    full_profile=client_info,
                )

                previous_route = (
                    psych_context.profile_payload.get("latest_route")
                    if psych_context and isinstance(psych_context.profile_payload, dict)
                    else ""
                )

                clarification_answer = None
                if self._clarification_pending(psych_context):
                    clarification_answer = user_query

                carried_severity = self._carried_risk_severity(psych_context)
                if carried_severity:
                    ctx.metadata["carried_risk_severity"] = carried_severity

                clar_state = self._clarification_state(psych_context)
                ctx.metadata["clarification_turns_used"] = clar_state["turns"]
                ctx.metadata["clarification_asked_targets"] = list(clar_state["asked_targets"])

                pipeline_res = run_pipeline(
                    ctx,
                    clarification_answer=clarification_answer,
                    flags={
                        "uncertainty_enabled": getattr(self._runtime_config, "uncertainty_enabled", True),
                        "risk_enabled": getattr(self._runtime_config, "risk_enabled", True),
                        "clarification_enabled": getattr(self._runtime_config, "clarification_enabled", True),
                        "safety_supervisor_enabled": getattr(self._runtime_config, "safety_supervisor_enabled", True),
                        "longitudinal_enabled": getattr(self._runtime_config, "longitudinal_enabled", True),
                        "multi_agent_routing_enabled": getattr(self._runtime_config, "multi_agent_routing_enabled", True),
                    },
                )
                current_route = pipeline_res["route"]
                trail = pipeline_res["trail"]
                longitudinal_risk = self._updated_longitudinal_risk(pipeline_res)
                if longitudinal_risk is None and carried_severity:
                    # Monotonic floor: a turn whose refreshed assessment
                    # computes nothing worth carrying must not wipe the
                    # confirmed severity already persisted for this visit
                    # (the supervisor and later turns rely on it).
                    prev_longitudinal = (
                        psych_context.profile_payload.get("longitudinal_risk")
                        if psych_context and isinstance(psych_context.profile_payload, dict)
                        else None
                    )
                    if isinstance(prev_longitudinal, dict) and prev_longitudinal.get("severity") == carried_severity:
                        longitudinal_risk = prev_longitudinal

                if current_route == "HIGH-RISK" or pipeline_res.get("verdict") == "ESCALATE":
                    safe_text = pipeline_res.get("response") or (
                        "I want to make sure you stay safe right now. If you are in immediate danger "
                        "or having thoughts of self-harm, please connect with a crisis resource immediately: "
                        "Tele-MANAS (14416) or 988 Suicide & Crisis Lifeline (call/text 988). "
                        "I am here to support you safely."
                    )
                    return {"text": safe_text, "end": False, "agent_trace": trail, "route": current_route,
                            "longitudinal_risk": longitudinal_risk,
                            "clarification_state": clar_state,
                            "reply_source": "template", "reply_model": None}

                # Round 3 fix (S2-D5): a safety question owed from an
                # earlier turn must not be silently dropped when the
                # fresh turn routes CLEAR. The pipeline only runs its
                # clarification loop on UNCERTAIN turns, so when a
                # contradiction question was asked first (at MODERATE
                # risk) and the user's answer routes CLEAR, the safety
                # question would never be asked — the reorder would
                # trade the contradiction gap for a safety gap. If a
                # safety question is still owed (never asked this
                # visit, gap still in missing_information, carried risk
                # MODERATE+), ask it now as a template reply instead of
                # proceeding to counseling.
                if current_route == "CLEAR" and clarification_answer is not None:
                    owed = self._owed_safety_question(ctx, clar_state, carried_severity)
                    if owed is not None:
                        safety_q, safety_targets = owed
                        new_state = {
                            "turns": clar_state["turns"],
                            "asked_targets": clar_state["asked_targets"] + [
                                t for t in safety_targets if t not in clar_state["asked_targets"]
                            ],
                            "safety_asked_targets": clar_state["safety_asked_targets"] + [
                                t for t in safety_targets
                                if t not in clar_state["safety_asked_targets"]
                            ],
                            "proceeded_with_unknowns": clar_state["proceeded_with_unknowns"],
                        }
                        trail.append({
                            "agent": "clarification_agent",
                            "step": "owed_safety_question",
                            "payload": {
                                "question": safety_q,
                                "questions": [safety_q],
                                "target_information": safety_targets,
                                "priority": "HIGH",
                                "clarification_required": True,
                                "reasoning_summary": (
                                    "Safety question owed from an earlier turn; "
                                    "fresh turn routed CLEAR before it was asked."
                                ),
                            },
                        })
                        return {"text": safety_q, "end": False, "agent_trace": trail, "route": "UNCERTAIN",
                                "longitudinal_risk": longitudinal_risk,
                                "clarification_state": new_state,
                                "reply_source": "template", "reply_model": None}

                if current_route == "UNCERTAIN":
                    clar_payload = ctx.clarification_output or {}
                    clar_q = clar_payload.get("question")
                    if not clar_q and clar_payload.get("questions"):
                        clar_q = clar_payload["questions"][0]
                    targets = [str(t) for t in (clar_payload.get("target_information") or []) if str(t)]
                    new_targets = [t for t in targets if t not in clar_state["asked_targets"]]
                    risk_severity = str((ctx.risk_output or {}).get("severity", "")).upper()
                    is_safety_q = bool(targets) and any(
                        is_safety_relevant_item(t) for t in targets
                    )
                    # LB-C1: a detected contradiction must not be waved
                    # through by the direct-request shortcut. "I want to
                    # correct something..." starts with "I want to", so
                    # the shortcut treated the correction as a direct
                    # request and delivered the dummy echo instead of the
                    # contradiction question the pipeline had already
                    # produced. A contradiction question is asked first;
                    # the safety-question and budget rules are unchanged.
                    _unc_types = (ctx.uncertainty_output or {}).get("uncertainty_types", []) or []
                    has_contradiction = (
                        "contradictory_information" in _unc_types
                        or "conflicting_feelings_clarification" in targets
                    )
                    direct_request = (
                        not is_safety_q
                        and not has_contradiction
                        and risk_severity == "LOW"
                        and self._looks_like_direct_request(user_query)
                    )
                    if is_safety_q:
                        # Safety-relevant slots sit outside the intake
                        # budget (which counts non-safety clarification
                        # only) but are asked at most once per visit.
                        fresh_safety = [
                            t for t in targets
                            if t not in clar_state["safety_asked_targets"]
                            and t not in clar_state["asked_targets"]
                        ]
                        can_ask = (
                            bool(clar_q)
                            and bool(clar_payload.get("clarification_required"))
                            and bool(fresh_safety)
                        )
                    else:
                        can_ask = (
                            bool(clar_q)
                            and bool(clar_payload.get("clarification_required"))
                            and clar_state["turns"] < self._MAX_CLARIFICATION_TURNS
                            and bool(new_targets)
                            and not direct_request
                        )
                    if can_ask:
                        if is_safety_q:
                            new_state = {
                                "turns": clar_state["turns"],
                                "asked_targets": clar_state["asked_targets"] + new_targets,
                                "safety_asked_targets": clar_state["safety_asked_targets"] + [
                                    t for t in targets
                                    if t not in clar_state["safety_asked_targets"]
                                ],
                                "proceeded_with_unknowns": clar_state["proceeded_with_unknowns"],
                            }
                        else:
                            new_state = {
                                "turns": clar_state["turns"] + 1,
                                "asked_targets": clar_state["asked_targets"] + new_targets,
                                "safety_asked_targets": clar_state["safety_asked_targets"],
                                "proceeded_with_unknowns": clar_state["proceeded_with_unknowns"],
                            }
                        return {"text": clar_q, "end": False, "agent_trace": trail, "route": current_route,
                                "longitudinal_risk": longitudinal_risk,
                                "clarification_state": new_state,
                                "reply_source": "template", "reply_model": None}
                    # Otherwise proceed to counseling with what is known:
                    # the visit budget is exhausted, the slot was already
                    # asked, the clarification agent stood down, or the
                    # user made a direct low-risk request that should be
                    # answered rather than held behind intake. Remaining
                    # unknowns are noted in the persisted state and trail.
                    unknowns = sorted(set(clar_state["proceeded_with_unknowns"]) | set(targets))
                    clar_state = {
                        "turns": clar_state["turns"],
                        "asked_targets": clar_state["asked_targets"],
                        "safety_asked_targets": clar_state["safety_asked_targets"],
                        "proceeded_with_unknowns": unknowns,
                    }
                    trail.append({
                        "agent": "web_engine",
                        "step": "clarification_budget",
                        "action": "proceed_to_counseling",
                        "reason": (
                            "direct_low_risk_request" if direct_request
                            else "budget_exhausted" if clar_state["turns"] >= self._MAX_CLARIFICATION_TURNS
                            else "clarification_stood_down_or_repeat"
                        ),
                        "unknowns": unknowns,
                    })
                    current_route = "CLEAR"

                if candidate_skills is None:
                    candidate_skills = await self._build_candidate_skills(sect, session_goals, stage_idx)
                suggested_skills: List[Dict[str, Any]] = []
                if user_query:
                    suggested_skills, _ = await self._skill_manager.retrive(
                        sect=sect,
                        query=user_query,
                        session_stage=stage_idx,
                        session_goals=session_goals,
                        diag_hist=diag_hist,
                        candidate_skills=candidate_skills,
                    )

                weights_payload = self._weights_for(suggested_skills)
                weights_for_response = (
                    weights_payload
                    if weights_payload.get("mode") in ("semantic", "single", "unavailable")
                    else None
                )
                supervisor_verdict = "ALLOW"
                system_prompt = prompt_manager.render(
                    "counselor_system",
                    client_info=client_info,
                    history=history,
                    session_stage=stage.label,
                    session_focus=session_focus,
                    homework_assigned_from_last_session=homework,
                    suggested_skills=suggested_skills,
                    recommendation_weights=weights_payload,
                )
                messages = [{"role": "system", "content": system_prompt}]
                messages.extend(self._build_chat_history_with_prior(visit_state))

                raw = await self._chat_once(messages, purpose="counseling")
                text, should_end = self._normalize_output_with_end(raw)
                if not text:
                    text = "Thank you for sharing that with me. Let's focus on taking a concrete step forward together."

                if getattr(self._runtime_config, "safety_supervisor_enabled", True):
                    text, supervisor_verdict, weights_for_response = self._apply_final_supervision(
                        ctx, text, trail, weights_for_response
                    )
                if weights_for_response is not None and should_attach_weights(
                    current_route, supervisor_verdict, text
                ):
                    text, weights_info = apply_weights_to_reply(text, weights_for_response)
                    trail.append({
                        "agent": "recommendation_weights",
                        "step": "suitability_weights",
                        "mode": weights_for_response.get("mode"),
                        "options": weights_for_response.get("options"),
                        "applied": weights_info.get("applied"),
                    })

                reply_source, reply_model = self._reply_source()
                return {"text": text, "end": should_end, "agent_trace": trail, "route": current_route,
                        "longitudinal_risk": longitudinal_risk,
                        "clarification_state": clar_state,
                        "reply_source": reply_source, "reply_model": reply_model,
                        "recommendation_weights": weights_for_response}

            # Round 2 fix (Stream B D3): the multi_agent_enabled=False
            # fallback ran no SafetySupervisor at all. It now gets the same
            # gating as the multi-agent path: a rule-based risk check first
            # (HIGH risk returns the safe fallback with no retrieval and no
            # LLM call, mirroring the multi-agent HIGH-RISK return), then
            # the supervisor applied to the generated draft below.
            fallback_ctx = AgentContext(
                case_id=f"{course.course_id}_{visit.visit_no}",
                modality=sect,
                therapy_stage=stage.label,
                session_index=visit.visit_no,
                current_message=user_query,
                prior_transcript=transcript[:-1],
                history_list=history,
                obtain_client_info=client_info,
                homework_assigned=homework,
                full_profile=client_info,
            )
            fallback_trail: List[Dict[str, Any]] = []
            fallback_risk = RiskAgent().run(fallback_ctx)
            fallback_ctx.risk_output = fallback_risk.payload
            # Round 3 fix (C-NEW2): the fallback path runs no
            # UncertaintyAgent, so the supervisor never saw the medical
            # gap here. Carry the same item the UncertaintyAgent emits
            # when no medical history is recorded, so the
            # false-reassurance guard can fire on this path too.
            _fallback_med_hist = str(
                (client_info.get("static_traits") or {}).get("medical_history") or ""
            ).strip().lower()
            _fallback_missing = (
                ["medical_history (safety status absent)"]
                if _fallback_med_hist in ("", "unknown", "(unavailable)", "not mentioned", "not_mentioned")
                else []
            )
            fallback_ctx.uncertainty_output = {
                "status": "CLEAR",
                "uncertain_fields": [],
                "missing_information": _fallback_missing,
            }
            fallback_severity = str(fallback_risk.payload.get("severity", "LOW")).upper()
            fallback_ctx.routing_output = {
                "route": "HIGH-RISK" if fallback_severity == "HIGH" else "CLEAR"
            }
            fallback_trail.append({
                "agent": "risk_agent",
                "step": "fallback_risk_check",
                "severity": fallback_severity,
            })
            if fallback_severity == "HIGH":
                return {"text": _STANDARD_SAFE_FALLBACK, "end": False,
                        "agent_trace": fallback_trail, "route": "HIGH-RISK",
                        "longitudinal_risk": None,
                        "clarification_state": self._clarification_state(psych_context),
                        "reply_source": "template", "reply_model": None}

            if candidate_skills is None:
                candidate_skills = await self._build_candidate_skills(sect, session_goals, stage_idx)
            suggested_skills: List[Dict[str, Any]] = []
            if user_query:
                suggested_skills, _ = await self._skill_manager.retrive(
                    sect=sect,
                    query=user_query,
                    session_stage=stage_idx,
                    session_goals=session_goals,
                    diag_hist=diag_hist,
                    candidate_skills=candidate_skills,
                )

            weights_payload = self._weights_for(suggested_skills)
            weights_for_response = (
                weights_payload
                if weights_payload.get("mode") in ("semantic", "single", "unavailable")
                else None
            )
            system_prompt = prompt_manager.render(
                "counselor_system",
                client_info=client_info,
                history=history,
                session_stage=stage.label,
                session_focus=session_focus,
                homework_assigned_from_last_session=homework,
                suggested_skills=suggested_skills,
                recommendation_weights=weights_payload,
            )
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(self._build_chat_history_with_prior(visit_state))

            raw = await self._chat_once(messages, purpose="counseling")
            text, should_end = self._normalize_output_with_end(raw)
            if text:
                text, fallback_verdict, weights_for_response = self._apply_final_supervision(
                    fallback_ctx, text, fallback_trail, weights_for_response
                )
                if weights_for_response is not None and should_attach_weights(None, fallback_verdict, text):
                    text, _weights_info = apply_weights_to_reply(text, weights_for_response)
                reply_source, reply_model = self._reply_source()
                return {"text": text, "end": should_end,
                        "agent_trace": fallback_trail,
                        "reply_source": reply_source, "reply_model": reply_model,
                        "recommendation_weights": weights_for_response}
            raise RuntimeError("empty response from PsychAgent prompt chain")
        except Exception as exc:
            if _is_quota_exhausted(exc):
                # Quota exhaustion surfaces as a visible state, not a
                # fallback to another doomed LLM call and not a raw 502.
                return _quota_exhausted_reply(
                    locals().get("trail") or [],
                    locals().get("current_route") or "",
                    locals().get("longitudinal_risk"),
                    locals().get("clar_state") or self._clarification_state(psych_context),
                )
            self._logger.warning("PsychAgent prompt chain failed, falling back to baseline prompt: %s", exc)
            try:
                raw = await self._chat_once(fallback_messages, purpose="counseling_fallback")
                text, should_end = self._normalize_output_with_end(raw)
            except Exception as fallback_exc:
                if _is_quota_exhausted(fallback_exc):
                    return _quota_exhausted_reply(
                        locals().get("trail") or [],
                        locals().get("current_route") or "",
                        locals().get("longitudinal_risk"),
                        locals().get("clar_state") or self._clarification_state(psych_context),
                    )
                raise
            if not text:
                raise RuntimeError("empty response from fallback prompt")
            reply_source, reply_model = self._reply_source()
            return {"text": text, "end": should_end,
                    "reply_source": reply_source, "reply_model": reply_model}

    async def _chat_once(self, messages: List[Dict[str, str]], purpose: str = "chat") -> str:
        return await self._backend.chat_text(
            messages=messages,
            model=self._baseline_config.model,
            temperature=self._baseline_config.temperature,
            max_tokens=self._baseline_config.max_tokens,
            timeout_sec=self._baseline_config.timeout_sec,
            max_retries=self._baseline_config.max_retries,
            retry_sleep_sec=self._baseline_config.retry_sleep_sec,
            end_token=self._baseline_config.end_token,
            output_language=self._runtime_config.output_language,
            ledger_purpose=purpose,
        )

    async def build_session_close_artifacts(
        self,
        *,
        course: TherapyCourseRecord,
        visit: TherapyVisitRecord,
        visit_state: VisitState,
        psych_context: Optional[VisitPsychContextOut],
    ) -> Dict[str, Any]:
        if not self._started:
            await self.startup()

        try:
            sect = school_to_psychagent_sect(course.school_id)
            modality_models = MODALITY_MODELS.get(sect)
            if not modality_models:
                raise ValueError(f"unsupported modality for psychagent session close: {sect}")

            stage = stage_from_key(visit.stage_key_snapshot)
            prompt_manager = self._get_prompt_manager(sect)
            session_focus = self._build_session_focus(psych_context)
            history = self._build_prompt_history(psych_context)
            client_info = self._build_prompt_client_info(course, psych_context)
            transcript = self._build_transcript(visit_state.messages)

            summary_prompt = prompt_manager.render(
                "summary_user",
                session_stage=stage.label,
                client_info=client_info,
                session_focus=session_focus,
                history=history,
                current_session_dialogue=format_transcript(transcript, for_profile=False),
            )
            summary_data = await self._chat_structured_json(
                system_prompt=str(prompt_manager.prompts.get("summary_system", "")),
                user_prompt=summary_prompt,
                schema_model=modality_models["summary"],
                task_label="summary",
            )

            profile_prompt = prompt_manager.render(
                "profile_user",
                current_session_dialogue=format_transcript(transcript, for_profile=True),
                client_info=client_info,
            )
            profile_data = await self._chat_structured_json(
                system_prompt=str(prompt_manager.prompts.get("profile_system", "")),
                user_prompt=profile_prompt,
                schema_model=modality_models["profile"],
                task_label="profile",
            )

            next_plan = summary_data.get("next_session_plan")
            next_focus: List[str] = []
            next_stage_raw = ""
            next_stage_key = ""
            should_complete_course = False
            if isinstance(next_plan, dict):
                raw_focus = next_plan.get("next_session_focus")
                if isinstance(raw_focus, list):
                    next_focus = [str(item).strip() for item in raw_focus if str(item).strip()]
                next_stage_raw = str(next_plan.get("next_session_stage") or "").strip()
                should_complete_course = next_stage_raw.lower() == "termination"
                if not should_complete_course:
                    next_stage_key = str(summary_stage_to_stage_key(next_stage_raw) or "").strip()
            if should_complete_course:
                next_stage_label = "Termination"
            else:
                if not next_stage_key:
                    next_stage_key = visit.stage_key_snapshot
                next_stage_label = stage_from_key(next_stage_key).label

            raw_homework = summary_data.get("homework")
            homework: List[str] = []
            if isinstance(raw_homework, list):
                homework = [str(item).strip() for item in raw_homework if str(item).strip()]

            return {
                "summary_text": str(summary_data.get("session_summary_abstract") or "").strip(),
                "next_session_focus": next_focus[:8],
                "next_session_stage_key": next_stage_key,
                "next_session_stage": next_stage_label,
                "next_session_stage_raw": next_stage_raw,
                "should_complete_course": should_complete_course,
                "homework": homework[:12],
                "updated_profile": profile_data,
                "profile_payload": profile_data,
                "summary_payload": summary_data,
                "source": "psychagent_summary_profile_v2",
            }
        except Exception as exc:
            self._logger.warning("PsychAgent session-close postprocess failed: %s", exc)
            return {}

    async def _chat_structured_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_model: Any,
        task_label: str,
    ) -> Dict[str, Any]:
        if not system_prompt.strip():
            raise ValueError(f"empty system prompt for {task_label}")
        if not user_prompt.strip():
            raise ValueError(f"empty user prompt for {task_label}")

        attempts = max(1, int(self._baseline_config.max_retries or 1))
        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                raw = await self._chat_once(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    purpose=task_label,
                )
                payload = safe_json_loads(raw)
                if "static_traits" in payload and isinstance(payload["static_traits"], dict):
                    payload["static_traits"].pop("language_features", None)
                payload.pop("user_id", None)
                self._validate_schema_payload(schema_model, payload)
                return payload
            except Exception as exc:
                last_error = exc
                self._logger.warning(
                    "PsychAgent %s parse/validate failed (attempt %s/%s): %s",
                    task_label,
                    attempt,
                    attempts,
                    exc,
                )

        raise RuntimeError(f"structured generation failed for {task_label}: {last_error}")

    @staticmethod
    def _validate_schema_payload(schema_model: Any, payload: Dict[str, Any]) -> None:
        """Validate payload for both pydantic v2 and v1 runtimes."""
        if hasattr(schema_model, "model_validate"):
            schema_model.model_validate(payload)
            return
        if hasattr(schema_model, "parse_obj"):
            schema_model.parse_obj(payload)
            return
        raise TypeError(f"unsupported schema model validator: {schema_model}")

    async def _build_candidate_skills(
        self,
        sect: str,
        session_goals: Dict[str, Any],
        stage_idx: int,
    ) -> List[Dict[str, Any]]:
        meta_skills, _, _, _ = await self._skill_manager.corse_filter(
            sect=sect,
            session_goals=session_goals,
            stage=stage_idx,
        )
        candidate_skills: List[Dict[str, Any]] = []
        for item in meta_skills:
            candidate_skills.extend(item.get("micro_skills", []))
        return candidate_skills

    def _get_prompt_manager(self, sect: str) -> PsychAgentPromptManager:
        if sect not in self._prompt_managers:
            self._prompt_managers[sect] = PsychAgentPromptManager(
                self._psych_prompt_root,
                sect,
                counselor_system_filename=self._runtime_config.psychagent_counselor_system_filename,
            )
        return self._prompt_managers[sect]

    def _apply_final_supervision(
        self,
        ctx: AgentContext,
        text: str,
        trail: List[Dict[str, Any]],
        weights_for_response: Optional[Dict[str, Any]],
    ) -> tuple:
        """Apply the SafetySupervisor's verdict to a generated draft.

        Round 2 fix (Stream B D2 / Stream D D-09): the old code only acted
        on ESCALATE and, for REVISE, patched one exact string — a RE-ROUTE
        verdict (false reassurance under uncertain safety, HIGH-risk /
        route mismatch) was silently ignored and the flagged draft was
        delivered verbatim, with weights still attached.

        - ALLOW: draft unchanged.
        - ESCALATE: safe fallback; weights suppressed.
        - REVISE: the supervisor's revised_response when it is a real
          revision; a revision identical to the draft (or absent) means the
          flagged content could not be cleaned, so the draft is NOT
          delivered verbatim — a neutral revision is used instead.
        - RE-ROUTE: the supervisor's revised_response when it is a real
          revision; otherwise the safe fallback (a route/safety mismatch
          with no usable revision is never delivered as a normal reply).
          Weights are suppressed: a re-routed reply carries no shares.

        Returns (text, verdict, weights_for_response).
        """
        if not getattr(self._runtime_config, "safety_supervisor_enabled", True):
            return text, "ALLOW", weights_for_response
        sup = SafetySupervisor()
        sup_msg = sup.run(ctx, draft_response=text)
        sup_payload = sup_msg.payload
        verdict = sup_payload.get("verdict", "ALLOW")
        trail.append({
            "agent": sup.name,
            "step": "final_web_supervision",
            "verdict": verdict,
            "rationale": sup_payload.get("rationale"),
        })
        if verdict == "ESCALATE":
            return (
                sup_payload.get("safe_fallback")
                or sup_payload.get("revised_response")
                or text
            ), verdict, None
        if verdict == "REVISE":
            revised = sup_payload.get("revised_response") or sup_payload.get("suggested_revision")
            if revised and revised.strip() and revised.strip() != text.strip():
                return revised, verdict, weights_for_response
            return _NEUTRAL_REVISION, verdict, weights_for_response
        if verdict == "RE-ROUTE":
            revised = sup_payload.get("revised_response") or sup_payload.get("suggested_revision")
            if revised and revised.strip() and revised.strip() != text.strip():
                return revised, verdict, None
            return (
                sup_payload.get("safe_fallback") or _STANDARD_SAFE_FALLBACK
            ), verdict, None
        return text, verdict, weights_for_response

    def _weights_for(self, suggested_skills: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Suitability-weights payload for retrieved skills (never raises).

        A weights failure must never break counseling: on any error the
        payload is mode "none" and the reply carries no shares.
        """
        weights_fn = getattr(self._skill_manager, "suitability_weights", None)
        if weights_fn is None:
            return {"mode": "none", "options": []}
        try:
            return weights_fn(suggested_skills)
        except Exception:
            self._logger.warning(
                "recommendation weights unavailable; continuing without shares"
            )
            return {"mode": "none", "options": []}

    def _make_backend(self, baseline: BaselineConfig) -> ModelBackend:
        if baseline.backend == "dummy":
            return DummyBackend(default_end_after_turn=999)
        if baseline.backend != "openai_api":
            raise ValueError(f"src/web backend requires baseline.backend=openai_api or dummy, got {baseline.backend!r}")

        api_key = os.environ.get(baseline.api_key_env, "").strip() if baseline.api_key_env else ""
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY", "").strip() or os.environ.get("CHAT_API_KEY", "").strip()
        if baseline.api_key_env and not api_key:
            raise RuntimeError(f"missing model api key env: {baseline.api_key_env} (or OPENAI_API_KEY)")

        settings = BackendSettings(
            model=baseline.model,
            temperature=baseline.temperature,
            max_tokens=baseline.max_tokens,
            timeout_sec=baseline.timeout_sec,
            max_retries=baseline.max_retries,
            retry_sleep_sec=baseline.retry_sleep_sec,
            base_url=baseline.base_url,
            api_key=api_key or None,
        )
        return OpenAIAPIBackend(settings=settings, logger=self._logger.getChild("counselor"))

    def _resolve_path(self, raw_path: str | Path) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return (self._project_root / path).resolve()

    @staticmethod
    def _normalize_text_list(raw: Any, limit: int = 8) -> List[str]:
        if not isinstance(raw, list):
            return []
        values: List[str] = []
        for item in raw:
            text = str(item).strip()
            if not text or text in values:
                continue
            values.append(text)
            if len(values) >= limit:
                break
        return values

    def _build_session_focus(
        self,
        psych_context: Optional[VisitPsychContextOut],
    ) -> List[str]:
        focus = self._normalize_text_list(
            psych_context.session_focus if psych_context else [],
            limit=8,
        )
        if focus:
            return focus
        return list(SESSION_FOCUS_DEFAULT)

    def _build_prompt_history(
        self,
        psych_context: Optional[VisitPsychContextOut],
    ) -> List[Dict[str, Any]]:
        history_items = list((psych_context.history if psych_context else []) or [])
        prompt_history: List[Dict[str, Any]] = []
        for item in history_items:
            if not isinstance(item, dict):
                continue
            summary_payload = item.get("summary_payload")
            if not isinstance(summary_payload, dict):
                summary_payload = {}

            prompt_item: Dict[str, Any] = {
                "session_stage": str(
                    item.get("session_stage")
                    or item.get("stage_label")
                    or item.get("stage_key")
                    or "Unknown Stage"
                ),
                "session_summary_abstract": str(
                    item.get("session_summary_abstract")
                    or item.get("summary")
                    or summary_payload.get("session_summary_abstract")
                    or ""
                ).strip()
                or "No summary available",
            }

            client_state_analysis = item.get("client_state_analysis")
            if not isinstance(client_state_analysis, dict):
                client_state_analysis = summary_payload.get("client_state_analysis")
            if isinstance(client_state_analysis, dict) and client_state_analysis:
                prompt_item["client_state_analysis"] = client_state_analysis

            goal_assessment = item.get("goal_assessment")
            if not isinstance(goal_assessment, dict):
                goal_assessment = summary_payload.get("goal_assessment")
            if isinstance(goal_assessment, dict) and goal_assessment:
                prompt_item["goal_assessment"] = goal_assessment

            homework = item.get("homework")
            if not isinstance(homework, list):
                homework = summary_payload.get("homework")
            normalized_homework = self._normalize_text_list(homework, limit=12)
            if normalized_homework:
                prompt_item["homework"] = normalized_homework

            prompt_history.append(prompt_item)
        return prompt_history

    def _build_prompt_client_info(
        self,
        course: TherapyCourseRecord,
        psych_context: Optional[VisitPsychContextOut],
    ) -> Dict[str, Any]:
        raw_info = dict((psych_context.client_info if psych_context else {}) or {})
        static_traits = raw_info.get("static_traits") if isinstance(raw_info.get("static_traits"), dict) else {}
        note_lines = self._split_lines(course.intake_note)
        growth_experiences = raw_info.get("growth_experiences")
        if not isinstance(growth_experiences, list):
            growth_experiences = note_lines

        pure_profile: Dict[str, Any] = {
            "static_traits": {
                "name": static_traits.get("name") or "Client",
                "age": static_traits.get("age") or raw_info.get("age") or "Unknown",
                "gender": static_traits.get("gender") or raw_info.get("gender") or "Unknown",
                "occupation": static_traits.get("occupation") or raw_info.get("occupation") or "Unknown",
                "educational_background": static_traits.get("educational_background") or "Unknown",
                "marital_status": static_traits.get("marital_status") or "Unknown",
                "family_status": static_traits.get("family_status")
                or raw_info.get("family_status")
                or (note_lines[0] if note_lines else "Unknown"),
                "social_status": static_traits.get("social_status") or raw_info.get("social_status") or "Unknown",
                "medical_history": static_traits.get("medical_history") or raw_info.get("medical_history") or "Unknown",
            },
            "main_problem": raw_info.get("main_problem") or course.intake_note or course.goal_summary or "To be clarified",
            "topic": raw_info.get("topic") or course.title or course.goal_summary or "Current Concern",
            "core_demands": raw_info.get("core_demands") or course.goal_summary or "To be clarified",
            "growth_experiences": growth_experiences,
            "target_behavior": raw_info.get("target_behavior") if isinstance(raw_info.get("target_behavior"), list) else [],
            "core_beliefs": raw_info.get("core_beliefs") if isinstance(raw_info.get("core_beliefs"), list) else [],
            "special_situations": raw_info.get("special_situations")
            if isinstance(raw_info.get("special_situations"), list)
            else [],
            "existentialism_topic": raw_info.get("existentialism_topic")
            if isinstance(raw_info.get("existentialism_topic"), list)
            else [],
            "contact_model": raw_info.get("contact_model") if isinstance(raw_info.get("contact_model"), list) else [],
            "core_conflict": raw_info.get("core_conflict") if isinstance(raw_info.get("core_conflict"), dict) else {},
            "object_relations": raw_info.get("object_relations")
            if isinstance(raw_info.get("object_relations"), list)
            else [],
            "behavioral_response_patterns": raw_info.get("behavioral_response_patterns")
            if isinstance(raw_info.get("behavioral_response_patterns"), list)
            else [],
            "exception_events": raw_info.get("exception_events")
            if isinstance(raw_info.get("exception_events"), list)
            else [],
            "force_field": raw_info.get("force_field") if isinstance(raw_info.get("force_field"), dict) else {},
        }
        return pure_profile

    @staticmethod
    def _build_transcript(messages: List[VisitMessageOut]) -> List[Dict[str, str]]:
        transcript: List[Dict[str, str]] = []
        for message in messages:
            content = str(message.text or "").strip()
            if not content:
                continue
            transcript.append({"role": message.role, "content": content})
        return transcript

    @staticmethod
    def _clarification_state(psych_context: Optional[VisitPsychContextOut]) -> Dict[str, Any]:
        """Per-visit clarification budget state persisted in profile_payload.

        Returns {"turns": int (non-safety clarification turns used),
        "asked_targets": [...], "safety_asked_targets": [...],
        "proceeded_with_unknowns": [...]} with empty defaults for a fresh
        visit or a snapshot written before this state existed.
        """
        state: Dict[str, Any] = {
            "turns": 0, "asked_targets": [], "safety_asked_targets": [],
            "proceeded_with_unknowns": [],
        }
        if psych_context and isinstance(psych_context.profile_payload, dict):
            raw = psych_context.profile_payload.get("clarification_state")
            if isinstance(raw, dict):
                try:
                    state["turns"] = int(raw.get("turns", 0) or 0)
                except (TypeError, ValueError):
                    state["turns"] = 0
                state["asked_targets"] = [str(t) for t in (raw.get("asked_targets") or [])]
                state["safety_asked_targets"] = [
                    str(t) for t in (raw.get("safety_asked_targets") or [])
                ]
                state["proceeded_with_unknowns"] = [
                    str(t) for t in (raw.get("proceeded_with_unknowns") or [])
                ]
        return state

    # General request/question forms (no topic vocabulary): a message in
    # one of these forms asks for something — an exercise, an explanation,
    # information — rather than disclosing intake information.
    _DIRECT_REQUEST_PREFIXES = (
        "walk me through", "show me", "teach me", "guide me", "help me",
        "give me", "tell me how", "explain", "how do i", "how can i",
        "how should i", "can you", "could you", "would you", "please",
        "let's", "lets ", "i want to", "i'd like to", "i would like to",
    )
    _QUESTION_STARTERS = {
        "what", "how", "why", "when", "where", "who", "which",
        "can", "could", "is", "are", "do", "does",
    }

    @classmethod
    def _looks_like_direct_request(cls, text: Optional[str]) -> bool:
        msg = str(text or "").strip().lower()
        if not msg:
            return False
        if any(msg.startswith(p) for p in cls._DIRECT_REQUEST_PREFIXES):
            return True
        first = msg.split(" ", 1)[0].strip("?!.,")
        return msg.endswith("?") and first in cls._QUESTION_STARTERS

    def _reply_source(self) -> tuple:
        """How the counseling reply was produced: the dummy backend emits
        templated text; a real model backend is an LLM (model id included)."""
        if getattr(self._baseline_config, "backend", "") == "dummy":
            return "template", None
        return "llm", getattr(self._baseline_config, "model", None)

    @staticmethod
    def _owed_safety_question(
        ctx: AgentContext, clar_state: Dict[str, Any], carried_severity: Optional[str]
    ) -> Optional[tuple]:
        """Safety question still owed after a CLEAR turn, if any.

        Returns (question, targets) or None. All gates must hold:
        carried risk MODERATE+; the safety question never asked in this
        visit; the fresh uncertainty still lists a medical/safety item
        in missing_information; and the user's message did not already
        address that item (volunteered history is not re-asked).

        The clarification agent only runs on UNCERTAIN turns, so the
        owed gap is presented to it on a copy of the context whose
        uncertainty status is marked UNCERTAIN — the gap itself is real
        (checked above); only the routing flag is overridden, so the
        agent selects the safety question from its own templates
        (single source of truth for the wording).
        """
        if str(carried_severity or "").upper() not in ("MODERATE", "HIGH"):
            return None
        if clar_state.get("safety_asked_targets"):
            return None
        unc = ctx.uncertainty_output or {}
        if not isinstance(unc, dict):
            return None
        missing = unc.get("missing_information", []) or []
        safety_items = [str(m) for m in missing if is_safety_relevant_item(m)]
        if not safety_items:
            return None
        answer = str(ctx.current_message or "")
        if any(_answer_addresses_item(answer, item) for item in safety_items):
            return None
        synth_ctx = ctx.copy()
        synth_unc = dict(unc)
        synth_unc["status"] = "UNCERTAIN"
        synth_unc["clarification_required"] = True
        synth_unc["clarification_needed"] = True
        synth_ctx.uncertainty_output = synth_unc
        clar_msg = ClarificationAgent().run(synth_ctx)
        payload = clar_msg.payload or {}
        if not payload.get("clarification_required"):
            return None
        targets = [str(t) for t in (payload.get("target_information") or []) if str(t)]
        if not targets or not any(is_safety_relevant_item(t) for t in targets):
            return None
        question = payload.get("question") or (payload.get("questions") or [None])[0]
        if not question:
            return None
        return question, targets

    @staticmethod
    def _clarification_pending(psych_context: Optional[VisitPsychContextOut]) -> bool:
        """Whether the next user message should be treated as a clarification answer.

        Explicit conversation state, not a string heuristic: returns True only
        when the previous turn routed UNCERTAIN *and* the persisted pipeline
        trace shows the clarification agent produced a required question.

        The state self-clears: after the answer is consumed, the new turn's
        route and trace are persisted, so a subsequent message is only treated
        as an answer if clarification is still genuinely pending.
        """
        if not psych_context or not isinstance(psych_context.profile_payload, dict):
            return False
        payload = psych_context.profile_payload
        if payload.get("latest_route") != "UNCERTAIN":
            return False
        trace = payload.get("latest_agent_trace") or []
        if not isinstance(trace, list):
            return False
        for step in reversed(trace):
            if not isinstance(step, dict):
                continue
            if step.get("agent") == "clarification_agent":
                clar_payload = step.get("payload") or {}
                if not isinstance(clar_payload, dict):
                    return False
                return bool(clar_payload.get("clarification_required")) and bool(
                    clar_payload.get("question") or clar_payload.get("questions")
                )
        return False

    @staticmethod
    def _carried_risk_severity(psych_context: Optional[VisitPsychContextOut]) -> Optional[str]:
        """Highest trustworthy risk severity carried from prior turns in this visit.

        Returns "HIGH" or "MODERATE" if persisted, else None. Only confirmed
        severities are carried; LOW needs no floor and UNCERTAIN (unverified)
        is per-turn and must not permanently block ordinary conversations.
        Scoped to the visit via profile_payload (per-visit snapshot).
        """
        if not psych_context or not isinstance(psych_context.profile_payload, dict):
            return None
        longitudinal = psych_context.profile_payload.get("longitudinal_risk") or {}
        if not isinstance(longitudinal, dict):
            return None
        severity = str(longitudinal.get("severity", "")).upper()
        return severity if severity in ("HIGH", "MODERATE") else None

    @staticmethod
    def _updated_longitudinal_risk(pipeline_res: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build the longitudinal risk summary to persist after this turn.

        Monotonic: persists HIGH/MODERATE (the pipeline already applied the
        carried floor, so this is the max of prior and current). Returns None
        when there is nothing worth carrying (LOW/UNCERTAIN), keeping
        ordinary conversations unblocked.
        """
        from datetime import datetime, timezone

        ctx = pipeline_res.get("context")
        risk_payload = (getattr(ctx, "risk_output", None) or {}) if ctx else {}
        if not isinstance(risk_payload, dict):
            return None
        severity = str(risk_payload.get("severity", "LOW")).upper()
        if severity not in ("HIGH", "MODERATE"):
            return None
        return {
            "severity": severity,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "pipeline_risk_assessment",
        }

    def _build_chat_history_with_prior(self, visit_state: VisitState) -> List[Dict[str, str]]:
        """Chat history for the counseling LLM: prior visits' user turns
        first, then the current visit's turns.

        REG-1 fix: cross-session recall ("remind me what I said about my
        sleep") must be able to quote the user's own words from earlier
        sessions of the SAME course. Prior-visit USER turns only: the
        dummy backend keys its opening branch off the assistant-turn
        count, so prior assistant turns would change which branch answers
        a later session's opening, and the recall branches only scan user
        turns in any case. The pipeline transcript and skill diag history
        stay current-visit only -- prior-session context already reaches
        the agents via the psych-context history (summaries). NOTE: this
        changes the live reply path too -- the live model now also sees
        the same course's verbatim prior user turns alongside the
        summary-based history in the system prompt.
        """
        history = self._build_chat_history(visit_state.prior_visit_user_messages)
        history.extend(self._build_chat_history(visit_state.messages))
        return history

    @staticmethod
    def _build_chat_history(messages: List[VisitMessageOut]) -> List[Dict[str, str]]:
        chat_messages: List[Dict[str, str]] = []
        for message in messages:
            if message.role not in {"assistant", "user"}:
                continue
            content = str(message.text or "").strip()
            if not content:
                continue
            chat_messages.append({"role": message.role, "content": content})
        return chat_messages

    @staticmethod
    def _build_diag_history(transcript: List[Dict[str, str]]) -> List[Dict[str, str]]:
        diag_hist: List[Dict[str, str]] = []
        for item in transcript:
            role = item.get("role")
            if role == "assistant":
                mapped_role = "Counselor"
            elif role == "user":
                mapped_role = "Client"
            else:
                continue
            diag_hist.append({"role": mapped_role, "text": str(item.get("content") or "")})
        return diag_hist

    @staticmethod
    def _last_user_query(transcript: List[Dict[str, str]]) -> str:
        for item in reversed(transcript):
            if item.get("role") == "user":
                return str(item.get("content") or "").strip()
        return ""

    def _normalize_output(self, raw_text: str) -> str:
        text, _ = self._normalize_output_with_end(raw_text)
        return text

    def _normalize_output_with_end(self, raw_text: str) -> tuple[str, bool]:
        text = extract_tag_content(raw_text, tag="response") or raw_text or ""
        text, has_end = strip_end_token(text, self._baseline_config.end_token)
        return text.strip(), has_end

    @staticmethod
    def _split_lines(raw_text: str) -> List[str]:
        values: List[str] = []
        for line in str(raw_text or "").splitlines():
            normalized = line.strip().lstrip("-•").strip()
            if normalized:
                values.append(normalized)
        return values
