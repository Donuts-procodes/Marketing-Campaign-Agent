from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from orchestrator.schemas.state import StrategyState


@runtime_checkable
class AgentNodeProtocol(Protocol):
    """Structural protocol — any callable matching this signature is a valid agent node."""

    async def execute(self, state: StrategyState) -> dict: ...


class BaseAgentNode(ABC):
    """
    Abstract base for agent nodes requiring shared setup (logging, config injection, etc.).

    Subclass this for agents that need instance state (e.g. injected clients).
    For pure-function agents, simply implement a matching async callable instead.
    """

    @abstractmethod
    async def execute(self, state: StrategyState) -> dict:
        """
        Process the current graph state and return a partial state-update delta.

        The returned dict must contain ONLY the keys being updated;
        LangGraph merges it into the running StrategyState automatically.
        """
        ...
