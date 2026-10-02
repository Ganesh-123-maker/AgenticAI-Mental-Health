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
from typing import Any, Dict, List, Optional, Tuple

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


def run_pipeline(
    ctx: AgentContext,
    clarification_answer: Optional[str] = None,
    max_reassess_turns: int = 1,
    flags: Optional[Dict[str, bool]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Execute the multi-agent pipeline synchronously (for unit/offline testing).

    Returns:
        Dict with "response", "route", "next_agent", "verdict", "trail", and "context".
    """
    active_flags = _resolve_flags(flags, ctx=ctx, **kwargs)
    trail: List[Dict[str, Any]] = []

    # 1. Memory Agent
    mem_agent = MemoryAgent()
    mem_msg = mem_agent.run(ctx)
    ctx.memory_output = mem_msg.payload
    trail.append({"agent": mem_agent.name, "status": mem_msg.status, "payload": mem_msg.payload})

    # 2. State Assessment Agent
    state_agent = StateAgent()
    state_msg = state_agent.run(ctx)
    ctx.state_output = state_msg.payload
    trail.append({"agent": state_agent.name, "status": state_msg.status, "payload": state_msg.payload})

    # 3. Uncertainty Agent & Risk Agent (parallel assessment)
    if active_flags["uncertainty_enabled"]:
        unc_agent = UncertaintyAgent()
        unc_msg = unc_agent.run(ctx)
        ctx.uncertainty_output = unc_msg.payload
        trail.append({"agent": unc_agent.name, "status": unc_msg.status, "payload": unc_msg.payload})
    else:
        unc_payload = {
            "status": "CLEAR",
            "missing_information": [],
            "clarification_required": False,
            "priority": "LOW",
            "bypassed": True,
        }
        ctx.uncertainty_output = unc_payload
        trail.append({"agent": "uncertainty_agent", "status": "BYPASSED", "payload": unc_payload})

    if active_flags["risk_enabled"]:
        risk_agent = RiskAgent()
        risk_msg = risk_agent.run(ctx)
        ctx.risk_output = risk_msg.payload
        trail.append({"agent": risk_agent.name, "status": risk_msg.status, "payload": risk_msg.payload})
    else:
        risk_payload = {
            "severity": "LOW",
            "risk_type": "NONE",
            "rationale": "Risk agent bypassed",
            "immediate_action_required": False,
            "bypassed": True,
        }
        ctx.risk_output = risk_payload
        trail.append({"agent": "risk_agent", "status": "BYPASSED", "payload": risk_payload})

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
            orch_msg = orchestrator.run(ctx)
            current_route = orch_msg.payload.get("route", "UNCERTAIN")
            trail.append({
                "agent": orchestrator.name,
                "step": f"routing_turn_{reroute_count}",
                "route": current_route,
                "payload": orch_msg.payload,
            })
        else:
            orch_msg = None
            current_route = "CLEAR"
            trail.append({
                "agent": "orchestrator",
                "step": f"routing_turn_{reroute_count}",
                "route": "CLEAR",
                "payload": {"route": "CLEAR", "next_agent": "counseling_agent", "bypassed": True},
            })

        # 5. Clarify -> Reassess Loop (if UNCERTAIN, clarification permitted, and re-evaluation permitted)
        while current_route == "UNCERTAIN" and active_flags["clarification_enabled"] and reassess_count < max_reassess_turns:
            reassess_count += 1
            clar_msg = clar_agent.run(ctx)
            ctx.clarification_output = clar_msg.payload
            ctx.metadata["clarification_output"] = clar_msg.payload
            trail.append({"agent": clar_agent.name, "turn": reassess_count, "payload": clar_msg.payload})

            if clarification_answer is not None:
                reassess_msg = reassess_agent.run(ctx, clarification_answer=clarification_answer)
                ctx.reassessment_output = reassess_msg.payload
                ctx.metadata["reassessment_output"] = reassess_msg.payload
                trail.append({"agent": reassess_agent.name, "turn": reassess_count, "payload": reassess_msg.payload})

                if active_flags["multi_agent_routing_enabled"]:
                    orch_msg = orchestrator.run(ctx)
                    current_route = orch_msg.payload.get("route", "UNCERTAIN")
                    trail.append({"agent": orchestrator.name, "step": f"reassessment_routing_{reassess_count}", "route": current_route, "payload": orch_msg.payload})
                else:
                    current_route = "CLEAR"
            else:
                break

        # 6. Counseling Agent Draft
        counsel_msg = counseling_agent.run(ctx)
        draft_response = counsel_msg.payload.get("response_text", "")
        ctx.counseling_output = counsel_msg.payload
        trail.append({"agent": counseling_agent.name, "step": "initial_draft", "payload": counsel_msg.payload})

        # 7. Safety Supervisor Evaluation
        if active_flags["safety_supervisor_enabled"]:
            sup_msg = supervisor.run(ctx, draft_response=draft_response)
            sup_payload = sup_msg.payload
            supervisor_verdict = sup_payload.get("verdict", "ALLOW")
            trail.append({
                "agent": supervisor.name,
                "step": f"supervision_turn_{reroute_count}",
                "verdict": supervisor_verdict,
                "rationale": sup_payload.get("rationale"),
                "payload": sup_payload,
            })

            if supervisor_verdict == "ALLOW":
                final_response = draft_response
                break
            elif supervisor_verdict == "ESCALATE":
                final_response = sup_payload.get("safe_fallback") or draft_response
                trail.append({"agent": supervisor.name, "action": "escalate_fallback_applied"})
                break
            elif supervisor_verdict == "REVISE":
                # Cap at 1 revision: send back to counseling agent once with rationale
                ctx.metadata["supervisor_revision_rationale"] = sup_payload.get("rationale")
                revised_counsel_msg = counseling_agent.run(ctx)
                final_response = revised_counsel_msg.payload.get("response_text", draft_response)
                trail.append({"agent": counseling_agent.name, "step": "revision", "payload": revised_counsel_msg.payload})
                break
            elif supervisor_verdict == "RE-ROUTE":
                reroute_count += 1
                if reroute_count <= max_reroutes:
                    # Update context with safety findings and re-route
                    ctx.metadata["supervisor_reroute_rationale"] = sup_payload.get("rationale")
                    if "High risk" in sup_payload.get("rationale", ""):
                        ctx.risk_output["severity"] = "HIGH"
                    continue
                else:
                    final_response = draft_response
                    break
        else:
            supervisor_verdict = "ALLOW"
            trail.append({
                "agent": "safety_supervisor",
                "step": f"supervision_turn_{reroute_count}",
                "verdict": "ALLOW",
                "payload": {"verdict": "ALLOW", "bypassed": True},
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
    clarification_answer: Optional[str] = None,
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

    # 1. Memory Agent
    mem_agent = MemoryAgent()
    mem_msg = mem_agent.run(ctx)
    ctx.memory_output = mem_msg.payload
    trail.append({"agent": mem_agent.name, "status": mem_msg.status, "payload": mem_msg.payload})

    # 2. State Assessment Agent
    state_agent = StateAgent()
    state_msg = state_agent.run(ctx)
    ctx.state_output = state_msg.payload
    trail.append({"agent": state_agent.name, "status": state_msg.status, "payload": state_msg.payload})

    # 3. Uncertainty Agent & Risk Agent (parallel assessment)
    if active_flags["uncertainty_enabled"]:
        unc_agent = UncertaintyAgent()
        unc_msg = unc_agent.run(ctx)
        ctx.uncertainty_output = unc_msg.payload
        trail.append({"agent": unc_agent.name, "status": unc_msg.status, "payload": unc_msg.payload})
    else:
        unc_payload = {
            "status": "CLEAR",
            "missing_information": [],
            "clarification_required": False,
            "priority": "LOW",
            "bypassed": True,
        }
        ctx.uncertainty_output = unc_payload
        trail.append({"agent": "uncertainty_agent", "status": "BYPASSED", "payload": unc_payload})

    if active_flags["risk_enabled"]:
        risk_agent = RiskAgent()
        risk_msg = risk_agent.run(ctx)
        ctx.risk_output = risk_msg.payload
        trail.append({"agent": risk_agent.name, "status": risk_msg.status, "payload": risk_msg.payload})
    else:
        risk_payload = {
            "severity": "LOW",
            "risk_type": "NONE",
            "rationale": "Risk agent bypassed",
            "immediate_action_required": False,
            "bypassed": True,
        }
        ctx.risk_output = risk_payload
        trail.append({"agent": "risk_agent", "status": "BYPASSED", "payload": risk_payload})

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
            orch_msg = orchestrator.run(ctx)
            current_route = orch_msg.payload.get("route", "UNCERTAIN")
            trail.append({
                "agent": orchestrator.name,
                "step": f"routing_turn_{reroute_count}",
                "route": current_route,
                "payload": orch_msg.payload,
            })
        else:
            orch_msg = None
            current_route = "CLEAR"
            trail.append({
                "agent": "orchestrator",
                "step": f"routing_turn_{reroute_count}",
                "route": "CLEAR",
                "payload": {"route": "CLEAR", "next_agent": "counseling_agent", "bypassed": True},
            })

        # 5. Clarify -> Reassess Loop (if UNCERTAIN and answer provided)
        while current_route == "UNCERTAIN" and active_flags["clarification_enabled"] and reassess_count < max_reassess_turns:
            reassess_count += 1
            clar_msg = clar_agent.run(ctx)
            ctx.clarification_output = clar_msg.payload
            ctx.metadata["clarification_output"] = clar_msg.payload
            trail.append({"agent": clar_agent.name, "turn": reassess_count, "payload": clar_msg.payload})

            if clarification_answer is not None:
                reassess_msg = reassess_agent.run(ctx, clarification_answer=clarification_answer)
                ctx.reassessment_output = reassess_msg.payload
                ctx.metadata["reassessment_output"] = reassess_msg.payload
                trail.append({"agent": reassess_agent.name, "turn": reassess_count, "payload": reassess_msg.payload})

                if active_flags["multi_agent_routing_enabled"]:
                    orch_msg = orchestrator.run(ctx)
                    current_route = orch_msg.payload.get("route", "UNCERTAIN")
                    trail.append({"agent": orchestrator.name, "step": f"reassessment_routing_{reassess_count}", "route": current_route, "payload": orch_msg.payload})
                else:
                    current_route = "CLEAR"
            else:
                break

        # 6. Counseling Agent Draft (via existing SkillManager & PromptManager)
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
        ctx.counseling_output = {"response": c_resp_pure, "route": current_route}
        trail.append({"agent": counseling_agent.name, "step": "initial_draft", "route": current_route})

        # 7. Safety Supervisor Evaluation
        if active_flags["safety_supervisor_enabled"]:
            sup_msg = supervisor.run(ctx, draft_response=c_resp_pure)
            sup_payload = sup_msg.payload
            supervisor_verdict = sup_payload.get("verdict", "ALLOW")
            trail.append({
                "agent": supervisor.name,
                "step": f"supervision_turn_{reroute_count}",
                "verdict": supervisor_verdict,
                "rationale": sup_payload.get("rationale"),
                "payload": sup_payload,
            })

            if supervisor_verdict == "ALLOW":
                final_pure, final_raw = c_resp_pure, c_resp_raw
                break
            elif supervisor_verdict == "ESCALATE":
                safe_text = sup_payload.get("safe_fallback") or c_resp_pure
                final_pure, final_raw = safe_text, safe_text
                trail.append({"agent": supervisor.name, "action": "escalate_fallback_applied"})
                break
            elif supervisor_verdict == "REVISE":
                # Cap at 1 revision: re-generate with revision rationale guidance
                ctx.metadata["supervisor_revision_rationale"] = sup_payload.get("rationale")
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
                final_pure, final_raw = rev_pure, rev_raw
                trail.append({"agent": counseling_agent.name, "step": "revision"})
                break
            elif supervisor_verdict == "RE-ROUTE":
                reroute_count += 1
                if reroute_count <= max_reroutes:
                    ctx.metadata["supervisor_reroute_rationale"] = sup_payload.get("rationale")
                    if "High risk" in sup_payload.get("rationale", ""):
                        ctx.risk_output["severity"] = "HIGH"
                    continue
                else:
                    final_pure, final_raw = c_resp_pure, c_resp_raw
                    break
        else:
            supervisor_verdict = "ALLOW"
            final_pure, final_raw = c_resp_pure, c_resp_raw
            trail.append({
                "agent": "safety_supervisor",
                "step": f"supervision_turn_{reroute_count}",
                "verdict": "ALLOW",
                "payload": {"verdict": "ALLOW", "bypassed": True},
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

