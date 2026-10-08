"""Multi-agent pipeline for PsychAgent.

Chains:
Memory → State → Uncertainty + Risk (parallel) → Orchestrator
  → (Clarification → Reassessment → back to Orchestrator, if UNCERTAIN)
  → Counseling Agent (delegating to SkillManager & PromptManager)
  → Safety Supervisor (ALLOW / REVISE / RE-ROUTE / ESCALATE)

Caps:
- REVISE: at most 1 revision (counseling_agent called at most twice).
- RE-ROUTE: at most 1 re-route (orchestrator called at most twice).
- ESCALATE: replaced with safe fallback without fabricated resources.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from .base import AgentContext, AgentMessage
from .clarification_agent import ClarificationAgent
from .counseling_agent import CounselingAgent
from .memory_agent import MemoryAgent
from .orchestrator import Orchestrator
from .reassessment_agent import ReassessmentAgent
from .risk_agent import RiskAgent
from .safety_supervisor import SafetySupervisor
from .state_agent import StateAgent
from .uncertainty_agent import UncertaintyAgent

logger = logging.getLogger(__name__)


def _timed_run(agent: Any, ctx: AgentContext, **kwargs: Any) -> Tuple[AgentMessage, float]:
    """Run one agent and return (message, wall-clock duration in milliseconds).

    Latency instrumentation for the research question's cost half ("at what
    latency/token cost?"). The agents are rule-based/deterministic and make no
    LLM calls themselves, so this measures real agent compute time; token
    costs only arise in live-LLM runner/evaluation paths and are not
    estimated here.
    """
    start = time.perf_counter()
    msg = agent.run(ctx, **kwargs)
    duration_ms = round((time.perf_counter() - start) * 1000, 3)
    return msg, duration_ms


def _resolve_flags(
    flags: Optional[Dict[str, bool]] = None,
    ctx: Optional[AgentContext] = None,
    runner_instance: Any = None,
    **kwargs: Any,
) -> Dict[str, bool]:
    resolved = {
        "uncertainty_enabled": True,
        "risk_enabled": True,
        "clarification_enabled": True,
        "safety_supervisor_enabled": True,
        "longitudinal_enabled": True,
        "multi_agent_routing_enabled": True,
    }
    if runner_instance is not None:
        rc = getattr(runner_instance, "runtime_config", None)
        if rc is not None:
            for k in resolved:
                if hasattr(rc, k):
                    resolved[k] = bool(getattr(rc, k))
    if ctx is not None and isinstance(ctx.metadata, dict):
        ctx_flags = ctx.metadata.get("flags")
        if isinstance(ctx_flags, dict):
            for k in resolved:
                if k in ctx_flags:
                    resolved[k] = bool(ctx_flags[k])
        for k in resolved:
            if k in ctx.metadata:
                resolved[k] = bool(ctx.metadata[k])
    if flags is not None and isinstance(flags, dict):
        for k in resolved:
            if k in flags:
                resolved[k] = bool(flags[k])
    for k in resolved:
        if kwargs.get(k) is not None:
            resolved[k] = bool(kwargs[k])
    return resolved


_CARRIED_RISK_RANK = {"LOW": 0, "UNCERTAIN": 1, "MODERATE": 2, "HIGH": 3}


def _apply_carried_risk_floor(ctx: AgentContext) -> None:
    """Prevent risk downgrading across conversation turns.

    If the backend carried forward a HIGH/MODERATE severity from a previous
    turn (ctx.metadata["carried_risk_severity"]), the fresh RiskAgent
    assessment cannot downgrade below it merely because the latest message
    is benign. New evidence can still raise the severity. This is a
    max-severity floor, not a re-implementation of risk detection.
    """
    floor = (ctx.metadata or {}).get("carried_risk_severity")
    if not isinstance(floor, str) or not floor:
        return
    floor = floor.upper()
    if floor not in ("HIGH", "MODERATE"):
        return
    risk_payload = ctx.risk_output or {}
    if not isinstance(risk_payload, dict):
        return
    fresh = str(risk_payload.get("severity", "LOW")).upper()
    if _CARRIED_RISK_RANK.get(fresh, 0) < _CARRIED_RISK_RANK[floor]:
        risk_payload["severity"] = floor
        risk_payload["carried_from_prior_turn"] = True


def _normalize_answer_sequence(clarification_answer: Optional[Union[str, List[str]]]) -> List[str]:
    """Normalize the clarification answer(s) to a per-turn sequence.

    Backward compatible: a single string is treated as a one-turn sequence;
    None means no answers. Each turn consumes the next answer in order, so
    turn 2+ can process a genuinely new client response instead of replaying
    turn 1's. The pipeline never fabricates answers: when the sequence is
    exhausted, the loop breaks.
    """
    if clarification_answer is None:
        return []
    if isinstance(clarification_answer, str):
        return [clarification_answer]
    return [a for a in clarification_answer if isinstance(a, str)]


def _propagate_reassessment_state(ctx: AgentContext, reassess_payload: Dict[str, Any]) -> None:
    """Make the reassessment's refreshed assessments current for the next turn.

    State ownership: the ReassessmentAgent PRODUCES the updated uncertainty
    and risk state (payload["uncertainty"], payload["risk"]); the pipeline
    PROPAGATES them onto the context between clarification turns. Without
    this, the next ClarificationAgent invocation would reason from the
    original (stale) UncertaintyAgent output.
    """
    if not isinstance(reassess_payload, dict):
        return
    refreshed_unc = reassess_payload.get("uncertainty")
    if isinstance(refreshed_unc, dict) and refreshed_unc:
        ctx.uncertainty_output = refreshed_unc
    refreshed_risk = reassess_payload.get("risk")
    if isinstance(refreshed_risk, dict) and refreshed_risk:
        ctx.risk_output = refreshed_risk


def run_pipeline(
    ctx: AgentContext,
    clarification_answer: Optional[Union[str, List[str]]] = None,
    max_reassess_turns: int = 1,
    flags: Optional[Dict[str, bool]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Execute the multi-agent pipeline synchronously (for unit/offline testing).

    clarification_answer may be a single string (one answer, backward
    compatible) or a list of strings (one per clarification turn). Each turn
    consumes the next answer; ctx.current_message is updated to the latest
    client message before reassessment.

    Returns:
        Dict with "response", "route", "next_agent", "verdict", "trail", and "context".
    """
    active_flags = _resolve_flags(flags, ctx=ctx, **kwargs)
    trail: List[Dict[str, Any]] = []
    answer_sequence = _normalize_answer_sequence(clarification_answer)

    # 1. Memory Agent
    mem_agent = MemoryAgent()
    mem_msg, mem_ms = _timed_run(mem_agent, ctx)
    ctx.memory_output = mem_msg.payload
    trail.append({"agent": mem_agent.name, "status": mem_msg.status, "payload": mem_msg.payload, "duration_ms": mem_ms})

    # 2. State Assessment Agent
    state_agent = StateAgent()
    state_msg, state_ms = _timed_run(state_agent, ctx)
    ctx.state_output = state_msg.payload
    trail.append({"agent": state_agent.name, "status": state_msg.status, "payload": state_msg.payload, "duration_ms": state_ms})

    # 3. Uncertainty Agent & Risk Agent (parallel assessment)
    if active_flags["uncertainty_enabled"]:
        unc_agent = UncertaintyAgent()
        unc_msg, unc_ms = _timed_run(unc_agent, ctx)
        ctx.uncertainty_output = unc_msg.payload
        trail.append({"agent": unc_agent.name, "status": unc_msg.status, "payload": unc_msg.payload, "duration_ms": unc_ms})
    else:
        unc_payload = {
            "status": "CLEAR",
            "missing_information": [],
            "clarification_required": False,
            "priority": "LOW",
            "bypassed": True,
        }
        ctx.uncertainty_output = unc_payload
        trail.append({"agent": "uncertainty_agent", "status": "BYPASSED", "payload": unc_payload, "duration_ms": 0.0})

    if active_flags["risk_enabled"]:
        risk_agent = RiskAgent()
        risk_msg, risk_ms = _timed_run(risk_agent, ctx)
        ctx.risk_output = risk_msg.payload
        trail.append({"agent": risk_agent.name, "status": risk_msg.status, "payload": risk_msg.payload, "duration_ms": risk_ms})
    else:
        risk_payload = {
            "severity": "LOW",
            "risk_type": "NONE",
            "rationale": "Risk agent bypassed",
            "immediate_action_required": False,
            "bypassed": True,
        }
        ctx.risk_output = risk_payload
        trail.append({"agent": "risk_agent", "status": "BYPASSED", "payload": risk_payload, "duration_ms": 0.0})

    # Longitudinal floor: a carried HIGH/MODERATE from a prior turn cannot be
    # downgraded by a benign latest message.
    _apply_carried_risk_floor(ctx)

    # Orchestrator & Safety Supervisor loop with capped re-routes
    orchestrator = Orchestrator()
    clar_agent = ClarificationAgent()
    reassess_agent = ReassessmentAgent()
    counseling_agent = CounselingAgent()
    supervisor = SafetySupervisor()

    reroute_count = 0
    max_reroutes = 1
    final_response = ""
    supervisor_verdict = "ALLOW"
    current_route = "CLEAR"
    reassess_count = 0
    orch_msg = None

    while reroute_count <= max_reroutes:
        # 4. Orchestrator Routing
        if active_flags["multi_agent_routing_enabled"]:
            orch_msg, orch_ms = _timed_run(orchestrator, ctx)
            ctx.routing_output = orch_msg.payload
            current_route = orch_msg.payload.get("route", "UNCERTAIN")
            trail.append({
                "agent": orchestrator.name,
                "step": f"routing_turn_{reroute_count}",
                "route": current_route,
                "payload": orch_msg.payload, "duration_ms": orch_ms,
            })
        else:
            orch_msg = None
            current_route = "CLEAR"
            trail.append({
                "agent": "orchestrator",
                "step": f"routing_turn_{reroute_count}",
                "route": "CLEAR",
                "payload": {"route": "CLEAR", "next_agent": "counseling_agent", "bypassed": True}, "duration_ms": 0.0,
            })

        # 5. Clarify -> Reassess Loop (if UNCERTAIN, clarification permitted, and re-evaluation permitted)
        while current_route == "UNCERTAIN" and active_flags["clarification_enabled"] and reassess_count < max_reassess_turns:
            reassess_count += 1
            clar_msg, clar_ms = _timed_run(clar_agent, ctx)
            ctx.clarification_output = clar_msg.payload
            ctx.metadata["clarification_output"] = clar_msg.payload
            trail.append({"agent": clar_agent.name, "turn": reassess_count, "payload": clar_msg.payload, "duration_ms": clar_ms})

            # This turn's client answer (None when the sequence is exhausted).
            turn_answer = answer_sequence[reassess_count - 1] if reassess_count - 1 < len(answer_sequence) else None
            if turn_answer is not None:
                # The latest client message is this turn's answer.
                ctx.current_message = turn_answer
                reassess_msg, reassess_ms = _timed_run(reassess_agent, ctx, clarification_answer=turn_answer)
                ctx.reassessment_output = reassess_msg.payload
                ctx.metadata["reassessment_output"] = reassess_msg.payload
                # Refresh ctx state for the next clarification turn (if any).
                _propagate_reassessment_state(ctx, reassess_msg.payload)
                trail.append({"agent": reassess_agent.name, "turn": reassess_count, "payload": reassess_msg.payload,
                              "clarification_answer": turn_answer, "duration_ms": reassess_ms})

                if active_flags["multi_agent_routing_enabled"]:
                    orch_msg, orch_ms = _timed_run(orchestrator, ctx)
                    ctx.routing_output = orch_msg.payload
                    current_route = orch_msg.payload.get("route", "UNCERTAIN")
                    trail.append({"agent": orchestrator.name, "step": f"reassessment_routing_{reassess_count}", "route": current_route, "payload": orch_msg.payload, "duration_ms": orch_ms})
                else:
                    current_route = "CLEAR"
            else:
                break

        # 6. Counseling Agent Draft
        counsel_msg, counseling_ms = _timed_run(counseling_agent, ctx)
        draft_response = counsel_msg.payload.get("response_text", "")
        ctx.counseling_output = counsel_msg.payload
        trail.append({"agent": counseling_agent.name, "step": "initial_draft", "payload": counsel_msg.payload, "duration_ms": counseling_ms})

        # 7. Safety Supervisor Evaluation
        if active_flags["safety_supervisor_enabled"]:
            sup_msg, sup_ms = _timed_run(supervisor, ctx, draft_response=draft_response)
            sup_payload = sup_msg.payload
            supervisor_verdict = sup_payload.get("verdict", "ALLOW")
            trail.append({
                "agent": supervisor.name,
                "step": f"supervision_turn_{reroute_count}",
                "verdict": supervisor_verdict,
                "rationale": sup_payload.get("rationale"),
                "payload": sup_payload, "duration_ms": sup_ms,
            })

            if supervisor_verdict == "ALLOW":
                final_response = draft_response
                break
            elif supervisor_verdict == "ESCALATE":
                final_response = sup_payload.get("safe_fallback") or draft_response
                trail.append({"agent": supervisor.name, "action": "escalate_fallback_applied", "duration_ms": 0.0})
                break
            elif supervisor_verdict == "REVISE":
                # The supervisor already produced a revised_response addressing
                # the flagged issues. Use it directly: the counseling agent
                # does not consume revision rationales, so re-running it
                # would return the identical flagged draft. Fall back to a
                # counseling re-run only if no structured revision exists.
                revised_response = sup_payload.get("revised_response") or sup_payload.get("suggested_revision")
                if revised_response:
                    final_response = revised_response
                    trail.append({"agent": supervisor.name, "action": "supervisor_revision_applied", "duration_ms": 0.0})
                else:
                    ctx.metadata["supervisor_revision_rationale"] = sup_payload.get("rationale")
                    revised_counsel_msg, counseling_rev_ms = _timed_run(counseling_agent, ctx)
                    final_response = revised_counsel_msg.payload.get("response_text", draft_response)
                    trail.append({"agent": counseling_agent.name, "step": "revision", "payload": revised_counsel_msg.payload, "duration_ms": counseling_rev_ms})
                break
            elif supervisor_verdict == "RE-ROUTE":
                reroute_count += 1
                if reroute_count <= max_reroutes:
                    # Keep the human-readable rationale for traceability.
                    ctx.metadata["supervisor_reroute_rationale"] = sup_payload.get("rationale")
                    # Structured risk/route mismatch signal (not rationale text
                    # parsing). If the supervisor flagged risk_consistency=False
                    # and our assessed risk is HIGH, ensure the orchestrator
                    # sees HIGH on re-route. Fail closed: missing/invalid
                    # risk_consistency -> no escalation.
                    if sup_payload.get("risk_consistency") is False:
                        if str((ctx.risk_output or {}).get("severity", "LOW")).upper() == "HIGH":
                            ctx.risk_output["severity"] = "HIGH"
                    continue
                else:
                    # Retry exhausted with the mismatch unresolved: never
                    # silently deliver the flagged draft. Prefer the
                    # supervisor's safe fallback/revision; fail closed to
                    # ESCALATE with a neutral safe message otherwise.
                    # sup_payload here is from the latest supervisor run.
                    # Guard: the supervisor's "revision" must differ from the
                    # flagged draft (its suggester can echo the input).
                    safe_text = None
                    if isinstance(sup_payload, dict):
                        for key in ("safe_fallback", "revised_response", "suggested_revision"):
                            candidate = sup_payload.get(key)
                            if isinstance(candidate, str) and candidate.strip() \
                                    and candidate.strip() != draft_response.strip():
                                safe_text = candidate
                                break
                    if safe_text:
                        final_response = safe_text
                        trail.append({
                            "agent": supervisor.name,
                            "action": "reroute_exhausted_safe_fallback_applied",
                            "verdict": supervisor_verdict,
                            "duration_ms": 0.0,
                        })
                    else:
                        final_response = (
                            "I want to make sure I support you safely and accurately. "
                            "Let's pause here for now — if you need immediate support, "
                            "please reach out to a trusted person, a mental health "
                            "professional, or a crisis helpline (Tele-MANAS 14416 in "
                            "India, 988 in the US)."
                        )
                        supervisor_verdict = "ESCALATE"
                        trail.append({
                            "agent": supervisor.name,
                            "action": "reroute_exhausted_escalated",
                            "verdict": "ESCALATE",
                            "duration_ms": 0.0,
                        })
                    break
        else:
            supervisor_verdict = "ALLOW"
            trail.append({
                "agent": "safety_supervisor",
                "step": f"supervision_turn_{reroute_count}",
                "verdict": "ALLOW",
                "payload": {"verdict": "ALLOW", "bypassed": True}, "duration_ms": 0.0,
            })
            final_response = draft_response
            break

    return {
        "response": final_response,
        "route": current_route,
        "next_agent": orch_msg.payload.get("next_agent") if orch_msg else "counseling_agent",
        "verdict": supervisor_verdict,
        "reason": orch_msg.payload.get("reason") if orch_msg else "Routing bypassed",
        "reassess_count": reassess_count,
        "reroute_count": reroute_count,
        "trail": trail,
        "context": ctx,
    }


async def run_pipeline_async(
    ctx: AgentContext,
    *,
    runner_instance: Any,
    transcript: List[Dict[str, Any]],
    counselor_messages: List[Dict[str, str]],
    session_goals: Dict[str, Any],
    stage: str,
    candidate_skills: List[Dict[str, Any]],
    case_id: str,
    turn_tag: str,
    render_counselor_system: Any,
    each_turn_system: Optional[List[str]] = None,
    clarification_answer: Optional[Union[str, List[str]]] = None,
    max_reassess_turns: int = 1,
    flags: Optional[Dict[str, bool]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Execute the multi-agent pipeline asynchronously in the live runner.

    Calls Memory → State → Uncertainty + Risk → Orchestrator
      → (Clarify/Reassess if UNCERTAIN)
      → Counseling Agent (SkillManager & PromptManager)
      → Safety Supervisor (ALLOW / REVISE / RE-ROUTE / ESCALATE)

    Returns:
        Dict with "response" (c_resp_pure, c_resp_raw), "route", "verdict", "trail", and "context".
    """
    active_flags = _resolve_flags(flags, ctx=ctx, runner_instance=runner_instance, **kwargs)
    trail: List[Dict[str, Any]] = []
    answer_sequence = _normalize_answer_sequence(clarification_answer)

    # 1. Memory Agent
    mem_agent = MemoryAgent()
    mem_msg, mem_ms = _timed_run(mem_agent, ctx)
    ctx.memory_output = mem_msg.payload
    trail.append({"agent": mem_agent.name, "status": mem_msg.status, "payload": mem_msg.payload, "duration_ms": mem_ms})

    # 2. State Assessment Agent
    state_agent = StateAgent()
    state_msg, state_ms = _timed_run(state_agent, ctx)
    ctx.state_output = state_msg.payload
    trail.append({"agent": state_agent.name, "status": state_msg.status, "payload": state_msg.payload, "duration_ms": state_ms})

    # 3. Uncertainty Agent & Risk Agent (parallel assessment)
    if active_flags["uncertainty_enabled"]:
        unc_agent = UncertaintyAgent()
        unc_msg, unc_ms = _timed_run(unc_agent, ctx)
        ctx.uncertainty_output = unc_msg.payload
        trail.append({"agent": unc_agent.name, "status": unc_msg.status, "payload": unc_msg.payload, "duration_ms": unc_ms})
    else:
        unc_payload = {
            "status": "CLEAR",
            "missing_information": [],
            "clarification_required": False,
            "priority": "LOW",
            "bypassed": True,
        }
        ctx.uncertainty_output = unc_payload
        trail.append({"agent": "uncertainty_agent", "status": "BYPASSED", "payload": unc_payload, "duration_ms": 0.0})

    if active_flags["risk_enabled"]:
        risk_agent = RiskAgent()
        risk_msg, risk_ms = _timed_run(risk_agent, ctx)
        ctx.risk_output = risk_msg.payload
        trail.append({"agent": risk_agent.name, "status": risk_msg.status, "payload": risk_msg.payload, "duration_ms": risk_ms})
    else:
        risk_payload = {
            "severity": "LOW",
            "risk_type": "NONE",
            "rationale": "Risk agent bypassed",
            "immediate_action_required": False,
            "bypassed": True,
        }
        ctx.risk_output = risk_payload
        trail.append({"agent": "risk_agent", "status": "BYPASSED", "payload": risk_payload, "duration_ms": 0.0})

    # Longitudinal floor: a carried HIGH/MODERATE from a prior turn cannot be
    # downgraded by a benign latest message.
    _apply_carried_risk_floor(ctx)

    orchestrator = Orchestrator()
    clar_agent = ClarificationAgent()
    reassess_agent = ReassessmentAgent()
    counseling_agent = CounselingAgent()
    supervisor = SafetySupervisor()

    reroute_count = 0
    max_reroutes = 1
    final_pure = ""
    final_raw = ""
    supervisor_verdict = "ALLOW"
    current_route = "CLEAR"
    reassess_count = 0
    orch_msg = None

    while reroute_count <= max_reroutes:
        # 4. Orchestrator Routing
        if active_flags["multi_agent_routing_enabled"]:
            orch_msg, orch_ms = _timed_run(orchestrator, ctx)
            ctx.routing_output = orch_msg.payload
            current_route = orch_msg.payload.get("route", "UNCERTAIN")
            trail.append({
                "agent": orchestrator.name,
                "step": f"routing_turn_{reroute_count}",
                "route": current_route,
                "payload": orch_msg.payload, "duration_ms": orch_ms,
            })
        else:
            orch_msg = None
            current_route = "CLEAR"
            trail.append({
                "agent": "orchestrator",
                "step": f"routing_turn_{reroute_count}",
                "route": "CLEAR",
                "payload": {"route": "CLEAR", "next_agent": "counseling_agent", "bypassed": True}, "duration_ms": 0.0,
            })

        # 5. Clarify -> Reassess Loop (if UNCERTAIN and answer provided)
        while current_route == "UNCERTAIN" and active_flags["clarification_enabled"] and reassess_count < max_reassess_turns:
            reassess_count += 1
            clar_msg, clar_ms = _timed_run(clar_agent, ctx)
            ctx.clarification_output = clar_msg.payload
            ctx.metadata["clarification_output"] = clar_msg.payload
            trail.append({"agent": clar_agent.name, "turn": reassess_count, "payload": clar_msg.payload, "duration_ms": clar_ms})

            # This turn's client answer (None when the sequence is exhausted).
            turn_answer = answer_sequence[reassess_count - 1] if reassess_count - 1 < len(answer_sequence) else None
            if turn_answer is not None:
                # The latest client message is this turn's answer.
                ctx.current_message = turn_answer
                reassess_msg, reassess_ms = _timed_run(reassess_agent, ctx, clarification_answer=turn_answer)
                ctx.reassessment_output = reassess_msg.payload
                ctx.metadata["reassessment_output"] = reassess_msg.payload
                # Refresh ctx state for the next clarification turn (if any).
                _propagate_reassessment_state(ctx, reassess_msg.payload)
                trail.append({"agent": reassess_agent.name, "turn": reassess_count, "payload": reassess_msg.payload,
                              "clarification_answer": turn_answer, "duration_ms": reassess_ms})

                if active_flags["multi_agent_routing_enabled"]:
                    orch_msg, orch_ms = _timed_run(orchestrator, ctx)
                    ctx.routing_output = orch_msg.payload
                    current_route = orch_msg.payload.get("route", "UNCERTAIN")
                    trail.append({"agent": orchestrator.name, "step": f"reassessment_routing_{reassess_count}", "route": current_route, "payload": orch_msg.payload, "duration_ms": orch_ms})
                else:
                    current_route = "CLEAR"
            else:
                break

        # 6. Counseling Agent Draft (via existing SkillManager & PromptManager)
        _counsel_start = time.perf_counter()
        c_resp_pure, c_resp_raw = await counseling_agent.generate_response(
            ctx,
            runner_instance=runner_instance,
            transcript=transcript,
            counselor_messages=counselor_messages,
            session_goals=session_goals,
            stage=stage,
            candidate_skills=candidate_skills,
            case_id=case_id,
            turn_tag=turn_tag,
            render_counselor_system=render_counselor_system,
            each_turn_system=each_turn_system,
        )
        counseling_ms = round((time.perf_counter() - _counsel_start) * 1000, 3)
        ctx.counseling_output = {"response": c_resp_pure, "route": current_route}
        trail.append({"agent": counseling_agent.name, "step": "initial_draft", "route": current_route, "duration_ms": counseling_ms})

        # 7. Safety Supervisor Evaluation
        if active_flags["safety_supervisor_enabled"]:
            sup_msg, sup_ms = _timed_run(supervisor, ctx, draft_response=c_resp_pure)
            sup_payload = sup_msg.payload
            supervisor_verdict = sup_payload.get("verdict", "ALLOW")
            trail.append({
                "agent": supervisor.name,
                "step": f"supervision_turn_{reroute_count}",
                "verdict": supervisor_verdict,
                "rationale": sup_payload.get("rationale"),
                "payload": sup_payload, "duration_ms": sup_ms,
            })

            if supervisor_verdict == "ALLOW":
                final_pure, final_raw = c_resp_pure, c_resp_raw
                break
            elif supervisor_verdict == "ESCALATE":
                safe_text = sup_payload.get("safe_fallback") or c_resp_pure
                final_pure, final_raw = safe_text, safe_text
                trail.append({"agent": supervisor.name, "action": "escalate_fallback_applied", "duration_ms": 0.0})
                break
            elif supervisor_verdict == "REVISE":
                # Prefer the supervisor's structured revision: the counseling
                # agent does not consume revision rationales, so regenerating
                # without it returns the identical flagged draft.
                revised_response = sup_payload.get("revised_response") or sup_payload.get("suggested_revision")
                if revised_response:
                    final_pure, final_raw = revised_response, revised_response
                    trail.append({"agent": supervisor.name, "action": "supervisor_revision_applied", "duration_ms": 0.0})
                else:
                    # No structured revision: re-generate with revision rationale guidance
                    ctx.metadata["supervisor_revision_rationale"] = sup_payload.get("rationale")
                    _rev_start = time.perf_counter()
                    rev_pure, rev_raw = await counseling_agent.generate_response(
                        ctx,
                        runner_instance=runner_instance,
                        transcript=transcript,
                        counselor_messages=counselor_messages,
                        session_goals=session_goals,
                        stage=stage,
                        candidate_skills=candidate_skills,
                        case_id=case_id,
                        turn_tag=f"{turn_tag}_revision",
                        render_counselor_system=render_counselor_system,
                        each_turn_system=each_turn_system,
                    )
                    counseling_rev_ms = round((time.perf_counter() - _rev_start) * 1000, 3)
                    final_pure, final_raw = rev_pure, rev_raw
                    trail.append({"agent": counseling_agent.name, "step": "revision", "duration_ms": counseling_rev_ms})
                break
            elif supervisor_verdict == "RE-ROUTE":
                reroute_count += 1
                if reroute_count <= max_reroutes:
                    # Keep the human-readable rationale for traceability.
                    ctx.metadata["supervisor_reroute_rationale"] = sup_payload.get("rationale")
                    # Structured risk/route mismatch signal (not rationale text
                    # parsing). If the supervisor flagged risk_consistency=False
                    # and our assessed risk is HIGH, ensure the orchestrator
                    # sees HIGH on re-route. Fail closed: missing/invalid
                    # risk_consistency -> no escalation.
                    if sup_payload.get("risk_consistency") is False:
                        if str((ctx.risk_output or {}).get("severity", "LOW")).upper() == "HIGH":
                            ctx.risk_output["severity"] = "HIGH"
                    continue
                else:
                    # Retry exhausted with the mismatch unresolved: never
                    # silently deliver the flagged draft. Prefer the
                    # supervisor's safe fallback/revision; fail closed to
                    # ESCALATE with a neutral safe message otherwise.
                    # Guard: the "revision" must differ from the flagged draft
                    # (the supervisor's suggester can echo the input).
                    safe_text = None
                    if isinstance(sup_payload, dict):
                        for key in ("safe_fallback", "revised_response", "suggested_revision"):
                            candidate = sup_payload.get(key)
                            if isinstance(candidate, str) and candidate.strip() \
                                    and candidate.strip() != c_resp_pure.strip():
                                safe_text = candidate
                                break
                    if safe_text:
                        final_pure, final_raw = safe_text, safe_text
                        trail.append({
                            "agent": supervisor.name,
                            "action": "reroute_exhausted_safe_fallback_applied",
                            "verdict": supervisor_verdict,
                            "duration_ms": 0.0,
                        })
                    else:
                        final_pure = final_raw = (
                            "I want to make sure I support you safely and accurately. "
                            "Let's pause here for now — if you need immediate support, "
                            "please reach out to a trusted person, a mental health "
                            "professional, or a crisis helpline (Tele-MANAS 14416 in "
                            "India, 988 in the US)."
                        )
                        supervisor_verdict = "ESCALATE"
                        trail.append({
                            "agent": supervisor.name,
                            "action": "reroute_exhausted_escalated",
                            "verdict": "ESCALATE",
                            "duration_ms": 0.0,
                        })
                    break
        else:
            supervisor_verdict = "ALLOW"
            final_pure, final_raw = c_resp_pure, c_resp_raw
            trail.append({
                "agent": "safety_supervisor",
                "step": f"supervision_turn_{reroute_count}",
                "verdict": "ALLOW",
                "payload": {"verdict": "ALLOW", "bypassed": True}, "duration_ms": 0.0,
            })
            break

    return {
        "response": (final_pure, final_raw),
        "route": current_route,
        "next_agent": orch_msg.payload.get("next_agent") if orch_msg else "counseling_agent",
        "verdict": supervisor_verdict,
        "reason": orch_msg.payload.get("reason") if orch_msg else "Routing bypassed",
        "reassess_count": reassess_count,
        "reroute_count": reroute_count,
        "trail": trail,
        "context": ctx,
    }

