"""Task and workflow state machines defined by the frozen specification."""

from __future__ import annotations

from enum import Enum

from .exceptions import InvalidStateTransitionError


class TaskStatus(str, Enum):
    """Lifecycle states for a task DAG node."""

    CREATED = "CREATED"
    BLOCKED = "BLOCKED"
    READY = "READY"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    CANCELLED = "CANCELLED"


class WorkflowStatus(str, Enum):
    """Incident-level terminal and execution states."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    UNRESOLVED = "UNRESOLVED"
    BLOCKED = "BLOCKED"
    ABORTED = "ABORTED"
    CANCELLED = "CANCELLED"


TASK_TERMINAL_STATUSES = frozenset(
    {
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED_FINAL,
        TaskStatus.CANCELLED,
    }
)

WORKFLOW_TERMINAL_STATUSES = frozenset(
    {
        WorkflowStatus.SUCCESS,
        WorkflowStatus.UNRESOLVED,
        WorkflowStatus.BLOCKED,
        WorkflowStatus.ABORTED,
        WorkflowStatus.CANCELLED,
    }
)

TASK_ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.CREATED: frozenset({TaskStatus.BLOCKED, TaskStatus.READY}),
    TaskStatus.BLOCKED: frozenset({TaskStatus.READY}),
    TaskStatus.READY: frozenset({TaskStatus.ASSIGNED}),
    TaskStatus.ASSIGNED: frozenset({TaskStatus.RUNNING}),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.VERIFYING,
            TaskStatus.FAILED_RETRYABLE,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.VERIFYING: frozenset(
        {
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED_RETRYABLE,
            TaskStatus.FAILED_FINAL,
        }
    ),
    TaskStatus.FAILED_RETRYABLE: frozenset(
        {
            TaskStatus.READY,
            TaskStatus.FAILED_FINAL,
        }
    ),
    TaskStatus.SUCCEEDED: frozenset(),
    TaskStatus.FAILED_FINAL: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

WORKFLOW_ALLOWED_TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.CREATED: frozenset(
        {
            WorkflowStatus.RUNNING,
            WorkflowStatus.BLOCKED,
            WorkflowStatus.ABORTED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.RUNNING: frozenset(
        {
            WorkflowStatus.SUCCESS,
            WorkflowStatus.UNRESOLVED,
            WorkflowStatus.BLOCKED,
            WorkflowStatus.ABORTED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.SUCCESS: frozenset(),
    WorkflowStatus.UNRESOLVED: frozenset(),
    WorkflowStatus.BLOCKED: frozenset(),
    WorkflowStatus.ABORTED: frozenset(),
    WorkflowStatus.CANCELLED: frozenset(),
}


def is_task_terminal(status: TaskStatus) -> bool:
    """Return whether a task cannot transition again."""

    return status in TASK_TERMINAL_STATUSES


def is_workflow_terminal(status: WorkflowStatus) -> bool:
    """Return whether an incident workflow cannot transition again."""

    return status in WORKFLOW_TERMINAL_STATUSES


def transition_task(
    current: TaskStatus,
    target: TaskStatus,
    *,
    dependencies_satisfied: bool | None = None,
    retry_available: bool | None = None,
) -> TaskStatus:
    """Validate a task transition and return the target state."""

    if target not in TASK_ALLOWED_TRANSITIONS[current]:
        raise InvalidStateTransitionError(f"task transition not allowed: {current} -> {target}")

    if current == TaskStatus.CREATED:
        if dependencies_satisfied is True and target is not TaskStatus.READY:
            raise InvalidStateTransitionError(
                "CREATED with satisfied dependencies must become READY"
            )
        if dependencies_satisfied is False and target is not TaskStatus.BLOCKED:
            raise InvalidStateTransitionError("CREATED with unmet dependencies must become BLOCKED")
        if dependencies_satisfied is None:
            raise InvalidStateTransitionError("CREATED transition requires dependency evaluation")

    if current == TaskStatus.BLOCKED and dependencies_satisfied is not True:
        raise InvalidStateTransitionError(
            "BLOCKED can become READY only after dependencies are met"
        )

    if current == TaskStatus.FAILED_RETRYABLE:
        if retry_available is None:
            raise InvalidStateTransitionError("retry transition requires retry availability")
        if retry_available and target is not TaskStatus.READY:
            raise InvalidStateTransitionError("available retry must return the task to READY")
        if not retry_available and target is not TaskStatus.FAILED_FINAL:
            raise InvalidStateTransitionError("exhausted retry must finish as FAILED_FINAL")

    return target


def transition_workflow(current: WorkflowStatus, target: WorkflowStatus) -> WorkflowStatus:
    """Validate a workflow transition and return the target state."""

    if target not in WORKFLOW_ALLOWED_TRANSITIONS[current]:
        raise InvalidStateTransitionError(f"workflow transition not allowed: {current} -> {target}")
    return target
