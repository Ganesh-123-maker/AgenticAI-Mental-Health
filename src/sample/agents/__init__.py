"""Multi-agent foundation for PsychAgent.

Exports:
    Agent          — base class all agents inherit
    AgentMessage   — structured inter-agent communication object
    AgentContext   — shared state object passed between agents
"""

from .base import Agent, AgentMessage, AgentContext
from .outcome_agent import OutcomeAgent
from .memory_update_agent import MemoryUpdateAgent

__all__ = ["Agent", "AgentMessage", "AgentContext", "OutcomeAgent", "MemoryUpdateAgent"]
