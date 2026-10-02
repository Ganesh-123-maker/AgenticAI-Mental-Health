"""Base agent abstraction and shared communication schemas for PsychAgent.

Coding conventions
------------------
All schemas use plain ``@dataclass`` to stay consistent with the rest of
``src/sample/core/schemas.py``.  No Pydantic is introduced here.

Hierarchy
---------
AgentContext   — shared state object that flows through the agent pipeline
AgentMessage   — structured result produced by each agent
Agent          — base class; subclasses implement ``run(ctx) -> AgentMessage``
"""

from __future__ import annotations

import abc
import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# AgentContext — shared state passed between agents in the pipeline
# ---------------------------------------------------------------------------

@dataclass
class AgentContext:
    """Shared state passed through the agent pipeline.

    Fields are organised in layers so each agent can read what earlier
    agents produced and add its own result without coupling to every other
    agent directly.

    Required fields
    ~~~~~~~~~~~~~~~
    case_id         Stable case identifier (profile stem or benchmark id).
    modality        One of bt|cbt|het|pdt|pmt.

    Optional fields (populated progressively as agents run)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    therapy_stage       Current therapy stage string; None if not yet known.
    session_index       1-based session index; None for standalone evaluation.
    current_message     The client's latest utterance.
    prior_transcript    List of {"role":…, "content":…} turn dicts.
    history_list        Per-session summary dicts from runner state.
    obtain_client_info  Counselor-visible profile dict (obtain_client_info).
    homework_assigned   Last homework items from the runner state.
    public_memory       A ``PublicMemory`` instance (or None before loaded).
    full_profile        Full raw profile dict (from assets/profiles/).
    memory_output       Output dict from the Memory Agent.
    state_output        Output dict from the State Assessment Agent.
    uncertainty_output  Placeholder — populated by Uncertainty Agent (future).
    risk_output         Placeholder — populated by Risk Agent (future).
    routing_output      Placeholder — populated by Orchestrator (future).
    counseling_output   Placeholder — populated by Counseling Agent (future).
    safety_output       Placeholder — populated by Safety Supervisor (future).
    metadata            Free-form key/value bag for diagnostics.
    """

    # Required
    case_id: str
    modality: str

    # Session / stage context
    therapy_stage: Optional[str] = None
    session_index: Optional[int] = None

    # Conversation context
    current_message: Optional[str] = None
    prior_transcript: List[Dict[str, Any]] = field(default_factory=list)

    # Runner memory structures (populated from runner or benchmark loader)
    history_list: List[Dict[str, Any]] = field(default_factory=list)
    obtain_client_info: Dict[str, Any] = field(default_factory=dict)
    homework_assigned: List[str] = field(default_factory=list)

    # PublicMemory instance from core.schemas (None until Memory Agent runs)
    public_memory: Optional[Any] = None  # PublicMemory — kept as Any to avoid circular import

    # Full raw profile dict (assets/profiles/<mod>/sample/<id>.json or benchmark)
    full_profile: Optional[Dict[str, Any]] = None

    # Agent outputs (populated as each agent completes)
    memory_output: Optional[Dict[str, Any]] = None
    state_output: Optional[Dict[str, Any]] = None

    # Future agent output placeholders (data fields only — no agent logic)
    uncertainty_output: Optional[Dict[str, Any]] = None
    risk_output: Optional[Dict[str, Any]] = None
    routing_output: Optional[Dict[str, Any]] = None
    counseling_output: Optional[Dict[str, Any]] = None
    safety_output: Optional[Dict[str, Any]] = None
    safety_supervisor_output: Optional[Dict[str, Any]] = None
    final_reviewed_response: Optional[str] = None
    outcome_output: Optional[Dict[str, Any]] = None
    memory_update_output: Optional[Dict[str, Any]] = None

    # Diagnostics / free-form metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def copy(self) -> "AgentContext":
        """Return a shallow copy with list/dict fields deep-copied."""
        return copy.deepcopy(self)


# ---------------------------------------------------------------------------
# AgentMessage — structured result from one agent invocation
# ---------------------------------------------------------------------------

@dataclass
class AgentMessage:
    """Structured communication object produced by every agent.

    Every agent emits exactly one AgentMessage.  Fields that are irrelevant
    for a particular agent should be left at their defaults (None / []).

    Fields
    ------
    agent               Name/identifier of the emitting agent.
    status              "ok" | "partial" | "error" | "unavailable".
    evidence            List of evidence strings that support the output.
    confidence          0.0–1.0 confidence in the output; None if not applicable.
    missing_information Fields or facts that could not be determined.
    recommended_action  Short description of what the next agent/system should do.
    next_agent          Name of the next agent that should run (None = pipeline end).
    payload             Agent-specific structured output dict.
    error               Error message when status != "ok".
    """

    agent: str
    status: str = "ok"  # "ok" | "partial" | "error" | "unavailable"
    evidence: List[str] = field(default_factory=list)
    confidence: Optional[float] = None
    missing_information: List[str] = field(default_factory=list)
    recommended_action: Optional[str] = None
    next_agent: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status,
            "evidence": list(self.evidence),
            "confidence": self.confidence,
            "missing_information": list(self.missing_information),
            "recommended_action": self.recommended_action,
            "next_agent": self.next_agent,
            "payload": dict(self.payload),
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Agent — abstract base class
# ---------------------------------------------------------------------------

class Agent(abc.ABC):
    """Abstract base for all PsychAgent pipeline agents.

    Subclasses must implement ``run(ctx) -> AgentMessage``.

    Design notes
    ~~~~~~~~~~~~
    * Agents are read-only with respect to memory and stored state.
    * Agents must not modify ``ctx`` in-place; they return an ``AgentMessage``
      and the caller may update ``ctx`` with the result.
    * Agents should raise ``AgentError`` for irrecoverable failures.
    * Recoverable/partial failures should return status="partial" or "unavailable".
    """

    #: Each subclass must set a unique name used in AgentMessage.agent.
    name: str = "base"

    @abc.abstractmethod
    def run(self, ctx: AgentContext) -> AgentMessage:
        """Run the agent against the given context and return a message.

        Args:
            ctx: The shared agent context.  Must not be mutated.

        Returns:
            AgentMessage with the agent's structured result.
        """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"


# ---------------------------------------------------------------------------
# AgentError — standard exception type
# ---------------------------------------------------------------------------

class AgentError(RuntimeError):
    """Raised for irrecoverable agent failures.

    Use this instead of generic RuntimeError so callers can distinguish
    agent-level errors from infrastructure errors.
    """

    def __init__(self, agent_name: str, message: str) -> None:
        super().__init__(f"[{agent_name}] {message}")
        self.agent_name = agent_name
