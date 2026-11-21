"""DAG validation and deterministic capability matching."""

from __future__ import annotations

from collections.abc import Iterable
from threading import RLock

from ..exceptions import DAGValidationError
from ..models import AgentCard, AgentStatus, TaskDAG, TaskNode

DEFAULT_AGENT_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "CoordinatorAgent": ("planning", "fusion"),
    "LogAgent": ("log_analysis",),
    "MetricsAgent": ("metrics_analysis",),
    "ConfigAgent": ("config_analysis",),
    "DependencyAgent": ("dependency_analysis",),
    "RepairAgent": ("repair",),
    "VerifierAgent": ("verification",),
}

DEFAULT_AGENT_IDS: dict[str, str] = {
    "CoordinatorAgent": "coordinator-01",
    "LogAgent": "log-agent-01",
    "MetricsAgent": "metrics-agent-01",
    "ConfigAgent": "config-agent-01",
    "DependencyAgent": "dependency-agent-01",
    "RepairAgent": "repair-agent-01",
    "VerifierAgent": "verifier-agent-01",
}


def build_default_agent_cards() -> tuple[AgentCard, ...]:
    """Create one deterministic registry card for each fixed Agent type."""

    return tuple(
        AgentCard(
            agent_id=DEFAULT_AGENT_IDS[agent_type],
            agent_type=agent_type,
            capabilities=capabilities,
            max_concurrency=2,
        )
        for agent_type, capabilities in DEFAULT_AGENT_CAPABILITIES.items()
    )


class CapabilityMatcher:
    """Match ready tasks to least-loaded capable Agents deterministically."""

    def __init__(self, cards: Iterable[AgentCard]) -> None:
        self._cards = list(cards)
        self._lock = RLock()

    @property
    def cards(self) -> tuple[AgentCard, ...]:
        return tuple(self._cards)

    def capable_cards(self, node: TaskNode) -> tuple[AgentCard, ...]:
        required = set(node.required_capabilities)
        return tuple(
            card
            for card in self._cards
            if card.agent_type == node.agent_type and required.issubset(card.capabilities)
        )

    def reserve(self, node: TaskNode) -> AgentCard:
        with self._lock:
            candidates = [
                card
                for card in self.capable_cards(node)
                if card.status is not AgentStatus.OFFLINE
                and card.current_task_count < card.max_concurrency
            ]
            if not candidates:
                raise DAGValidationError(
                    f"no available {node.agent_type} with {sorted(node.required_capabilities)}"
                )
            selected = min(
                candidates,
                key=lambda card: (card.current_task_count, card.agent_id),
            )
            selected.current_task_count += 1
            selected.status = AgentStatus.BUSY
            return selected

    def release(self, card: AgentCard) -> None:
        with self._lock:
            if card.current_task_count > 0:
                card.current_task_count -= 1
            card.status = AgentStatus.IDLE if card.current_task_count == 0 else AgentStatus.BUSY


class TaskPlanner:
    """Validate a TaskDAG against the registered Agent capability matrix."""

    def __init__(self, cards: Iterable[AgentCard] | None = None) -> None:
        self.matcher = CapabilityMatcher(cards or build_default_agent_cards())

    def validate(self, dag: TaskDAG) -> None:
        node_ids = [node.task_id for node in dag.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise DAGValidationError("task IDs must be unique")
        dag.topological_order()
        for node in dag.nodes:
            if not self.matcher.capable_cards(node):
                raise DAGValidationError(
                    f"no registered Agent can execute {node.task_id}: "
                    f"{node.agent_type} {sorted(node.required_capabilities)}"
                )
