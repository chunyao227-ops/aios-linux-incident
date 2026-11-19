"""Minimal Agent boundary. Concrete behavior is implemented in later work orders."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentDescriptor:
    """Stable identity and capability declaration for an Agent."""

    name: str
    role: str
    capabilities: tuple[str, ...]


class BaseAgent(ABC):
    """Base class for the seven fixed Agents."""

    descriptor: AgentDescriptor

    @abstractmethod
    async def handle(self, task: Any) -> Any:
        """Handle one scheduled task without implementing business logic here."""
