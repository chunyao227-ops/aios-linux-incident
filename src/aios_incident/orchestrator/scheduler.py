"""Concurrent task DAG dispatcher with bounded retries."""

from __future__ import annotations

import time
from collections.abc import Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import RLock
from typing import Any, Protocol

from ..exceptions import AdapterInvocationError
from ..models import AgentCard, RunContext, TaskDAG, TaskNode, TraceEvent
from ..state import TaskStatus, transition_task
from ..utils import generate_id, utc_now
from .planner import TaskPlanner
from .trace import JsonlTraceStore


@dataclass(frozen=True, slots=True)
class TaskOutcome:
    success: bool
    result_ref: str | None = None
    error: str | None = None
    retryable: bool = True
    details: dict[str, Any] = field(default_factory=dict)


class NodeExecutor(Protocol):
    def __call__(
        self,
        context: RunContext,
        node: TaskNode,
        agent: AgentCard,
    ) -> TaskOutcome:
        """Execute one DAG node with the assigned Agent."""


@dataclass(frozen=True, slots=True)
class DispatchReport:
    gate_task_id: str
    gate_ready: bool
    ready_tasks: tuple[str, ...]
    failed_tasks: tuple[str, ...]
    retry_counts: dict[str, int]
    outcomes: dict[str, TaskOutcome]


class Scheduler:
    """Dispatch all currently ready nodes before waiting for their completion."""

    def __init__(
        self,
        *,
        dag: TaskDAG,
        context: RunContext,
        trace: JsonlTraceStore,
        executors: Mapping[str, NodeExecutor],
        max_concurrency: int,
        max_retries: int = 1,
        planner: TaskPlanner | None = None,
        gate_task_id: str = "N5",
    ) -> None:
        if max_concurrency < 4:
            raise ValueError("max_concurrency must be at least 4")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.dag = dag
        self.context = context
        self.trace = trace
        self.executors = dict(executors)
        self.max_concurrency = max_concurrency
        self.max_retries = max_retries
        self.planner = planner or TaskPlanner()
        self.gate_task_id = gate_task_id
        self._nodes = {node.task_id: node for node in dag.nodes}
        self._outcomes: dict[str, TaskOutcome] = {}
        self._retry_counts: dict[str, int] = {}
        self._trace_lock = RLock()
        self._last_timestamp: datetime | None = None
        self.planner.validate(dag)

    def run(self) -> DispatchReport:
        pending: dict[Future[TaskOutcome], tuple[TaskNode, AgentCard]] = {}
        with ThreadPoolExecutor(
            max_workers=self.max_concurrency,
            thread_name_prefix="incident-dag",
        ) as pool:
            while True:
                self._refresh_ready_nodes()
                gate = self._nodes[self.gate_task_id]
                if gate.status is TaskStatus.READY and self.gate_task_id not in self.executors:
                    break
                if self._has_failed_collection() and not pending:
                    break

                submit_capacity = self.max_concurrency - len(pending)
                candidates = [
                    node
                    for node in self._nodes.values()
                    if node.status is TaskStatus.READY and node.task_id in self.executors
                ]
                if submit_capacity > 0 and candidates:
                    dispatch_batch_id = generate_id("dispatch")
                    for node in candidates[:submit_capacity]:
                        agent = self.planner.matcher.reserve(node)
                        node.status = transition_task(node.status, TaskStatus.ASSIGNED)
                        self._event(
                            node,
                            agent.agent_id,
                            "TASK_ASSIGNED",
                            TaskStatus.ASSIGNED.value,
                            details={"dispatch_batch_id": dispatch_batch_id},
                        )
                        future = pool.submit(
                            self._run_node,
                            node,
                            agent,
                            self.executors[node.task_id],
                            dispatch_batch_id,
                        )
                        pending[future] = (node, agent)

                if not pending:
                    break
                completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in completed:
                    node, agent = pending.pop(future)
                    try:
                        outcome = future.result()
                    except Exception as exc:
                        outcome = TaskOutcome(
                            success=False,
                            error=f"scheduler worker failure: {exc}",
                            retryable=False,
                        )
                    self.planner.matcher.release(agent)
                    self._apply_outcome(node, agent, outcome)

        ready = tuple(
            node.task_id for node in self._nodes.values() if node.status is TaskStatus.READY
        )
        failed = tuple(
            node.task_id for node in self._nodes.values() if node.status is TaskStatus.FAILED_FINAL
        )
        return DispatchReport(
            gate_task_id=self.gate_task_id,
            gate_ready=self._nodes[self.gate_task_id].status is TaskStatus.READY,
            ready_tasks=ready,
            failed_tasks=failed,
            retry_counts=dict(self._retry_counts),
            outcomes=dict(self._outcomes),
        )

    def _refresh_ready_nodes(self) -> None:
        changed = True
        while changed:
            changed = False
            for node in self.dag.nodes:
                if node.status not in {TaskStatus.CREATED, TaskStatus.BLOCKED}:
                    continue
                dependencies_satisfied = all(
                    self._nodes[dependency].status is TaskStatus.SUCCEEDED
                    for dependency in node.depends_on
                )
                if dependencies_satisfied:
                    node.status = transition_task(
                        node.status,
                        TaskStatus.READY,
                        dependencies_satisfied=True,
                    )
                    self._event(
                        node,
                        "scheduler",
                        "TASK_READY",
                        TaskStatus.READY.value,
                    )
                    changed = True
                elif node.status is TaskStatus.CREATED:
                    node.status = transition_task(
                        node.status,
                        TaskStatus.BLOCKED,
                        dependencies_satisfied=False,
                    )

    def _run_node(
        self,
        node: TaskNode,
        agent: AgentCard,
        executor: NodeExecutor,
        dispatch_batch_id: str,
    ) -> TaskOutcome:
        node.status = transition_task(node.status, TaskStatus.RUNNING)
        started = time.perf_counter()
        self._event(
            node,
            agent.agent_id,
            "TASK_STARTED",
            TaskStatus.RUNNING.value,
            details={"dispatch_batch_id": dispatch_batch_id},
        )
        try:
            outcome = executor(self.context, node, agent)
        except AdapterInvocationError as exc:
            outcome = TaskOutcome(success=False, error=str(exc), retryable=exc.retryable)
        except Exception as exc:
            outcome = TaskOutcome(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                retryable=False,
            )

        node.status = transition_task(node.status, TaskStatus.VERIFYING)
        self._event(
            node,
            agent.agent_id,
            "TASK_VERIFYING",
            TaskStatus.VERIFYING.value,
            duration_ms=_elapsed_ms(started),
        )
        if outcome.success:
            node.status = transition_task(node.status, TaskStatus.SUCCEEDED)
            status = TaskStatus.SUCCEEDED
        elif outcome.retryable:
            node.status = transition_task(node.status, TaskStatus.FAILED_RETRYABLE)
            status = TaskStatus.FAILED_RETRYABLE
        else:
            node.status = transition_task(node.status, TaskStatus.FAILED_FINAL)
            status = TaskStatus.FAILED_FINAL
        self._event(
            node,
            agent.agent_id,
            "TASK_FINISHED",
            status.value,
            duration_ms=_elapsed_ms(started),
            details=outcome.details,
        )
        return outcome

    def _apply_outcome(
        self,
        node: TaskNode,
        agent: AgentCard,
        outcome: TaskOutcome,
    ) -> None:
        self._outcomes[node.task_id] = outcome
        if node.status is not TaskStatus.FAILED_RETRYABLE:
            return
        if node.attempt <= self.max_retries:
            node.attempt += 1
            self._retry_counts[node.task_id] = node.attempt - 1
            node.status = transition_task(
                node.status,
                TaskStatus.READY,
                retry_available=True,
            )
            self._event(
                node,
                agent.agent_id,
                "TASK_RETRY_SCHEDULED",
                TaskStatus.READY.value,
                details={"attempt": node.attempt},
            )
        else:
            node.status = transition_task(
                node.status,
                TaskStatus.FAILED_FINAL,
                retry_available=False,
            )
            self._event(
                node,
                agent.agent_id,
                "TASK_FAILED_FINAL",
                TaskStatus.FAILED_FINAL.value,
            )

    def _has_failed_collection(self) -> bool:
        return any(
            self._nodes[task_id].status is TaskStatus.FAILED_FINAL
            for task_id in ("N1", "N2", "N3", "N4")
        )

    def _event(
        self,
        node: TaskNode,
        agent_id: str,
        event_type: str,
        status: str,
        *,
        duration_ms: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self._trace_lock:
            timestamp = utc_now()
            if self._last_timestamp is not None and timestamp <= self._last_timestamp:
                timestamp = self._last_timestamp + timedelta(microseconds=1)
            self._last_timestamp = timestamp
        self.trace.append(
            TraceEvent(
                trace_id=generate_id("trace"),
                incident_id=self.context.incident_id,
                task_id=node.task_id,
                agent_id=agent_id,
                event_type=event_type,
                status=status,
                timestamp=timestamp,
                duration_ms=duration_ms,
                details=details or {},
            )
        )


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
