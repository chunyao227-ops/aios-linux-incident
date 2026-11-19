"""W03 task and workflow transition tests."""

import pytest

from aios_incident.exceptions import InvalidStateTransitionError
from aios_incident.state import (
    TaskStatus,
    WorkflowStatus,
    is_task_terminal,
    is_workflow_terminal,
    transition_task,
    transition_workflow,
)


@pytest.mark.parametrize(
    ("current", "target", "kwargs"),
    [
        (TaskStatus.CREATED, TaskStatus.READY, {"dependencies_satisfied": True}),
        (TaskStatus.CREATED, TaskStatus.BLOCKED, {"dependencies_satisfied": False}),
        (TaskStatus.BLOCKED, TaskStatus.READY, {"dependencies_satisfied": True}),
        (TaskStatus.READY, TaskStatus.ASSIGNED, {}),
        (TaskStatus.ASSIGNED, TaskStatus.RUNNING, {}),
        (TaskStatus.RUNNING, TaskStatus.VERIFYING, {}),
        (TaskStatus.RUNNING, TaskStatus.FAILED_RETRYABLE, {}),
        (TaskStatus.RUNNING, TaskStatus.CANCELLED, {}),
        (TaskStatus.VERIFYING, TaskStatus.SUCCEEDED, {}),
        (TaskStatus.VERIFYING, TaskStatus.FAILED_RETRYABLE, {}),
        (TaskStatus.VERIFYING, TaskStatus.FAILED_FINAL, {}),
        (
            TaskStatus.FAILED_RETRYABLE,
            TaskStatus.READY,
            {"retry_available": True},
        ),
        (
            TaskStatus.FAILED_RETRYABLE,
            TaskStatus.FAILED_FINAL,
            {"retry_available": False},
        ),
    ],
)
def test_legal_task_transitions(
    current: TaskStatus,
    target: TaskStatus,
    kwargs: dict[str, bool],
) -> None:
    assert transition_task(current, target, **kwargs) is target


def test_running_cannot_skip_verification() -> None:
    with pytest.raises(InvalidStateTransitionError, match="RUNNING -> SUCCEEDED"):
        transition_task(TaskStatus.RUNNING, TaskStatus.SUCCEEDED)


def test_dependency_guards_are_required() -> None:
    with pytest.raises(InvalidStateTransitionError, match="requires dependency evaluation"):
        transition_task(TaskStatus.CREATED, TaskStatus.READY)
    with pytest.raises(InvalidStateTransitionError, match="unmet dependencies"):
        transition_task(
            TaskStatus.CREATED,
            TaskStatus.READY,
            dependencies_satisfied=False,
        )
    with pytest.raises(InvalidStateTransitionError, match="only after dependencies are met"):
        transition_task(
            TaskStatus.BLOCKED,
            TaskStatus.READY,
            dependencies_satisfied=False,
        )


def test_retry_guard_is_required() -> None:
    with pytest.raises(InvalidStateTransitionError, match="requires retry availability"):
        transition_task(TaskStatus.FAILED_RETRYABLE, TaskStatus.READY)
    with pytest.raises(InvalidStateTransitionError, match="available retry"):
        transition_task(
            TaskStatus.FAILED_RETRYABLE,
            TaskStatus.FAILED_FINAL,
            retry_available=True,
        )


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (WorkflowStatus.CREATED, WorkflowStatus.RUNNING),
        (WorkflowStatus.CREATED, WorkflowStatus.CANCELLED),
        (WorkflowStatus.RUNNING, WorkflowStatus.SUCCESS),
        (WorkflowStatus.RUNNING, WorkflowStatus.UNRESOLVED),
        (WorkflowStatus.RUNNING, WorkflowStatus.BLOCKED),
        (WorkflowStatus.RUNNING, WorkflowStatus.ABORTED),
        (WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED),
    ],
)
def test_legal_workflow_transitions(
    current: WorkflowStatus,
    target: WorkflowStatus,
) -> None:
    assert transition_workflow(current, target) is target


def test_workflow_cannot_restart_after_terminal_state() -> None:
    with pytest.raises(InvalidStateTransitionError, match="workflow transition not allowed"):
        transition_workflow(WorkflowStatus.SUCCESS, WorkflowStatus.RUNNING)


def test_terminal_state_helpers() -> None:
    assert is_task_terminal(TaskStatus.SUCCEEDED)
    assert is_task_terminal(TaskStatus.FAILED_FINAL)
    assert is_task_terminal(TaskStatus.CANCELLED)
    assert not is_task_terminal(TaskStatus.FAILED_RETRYABLE)
    assert is_workflow_terminal(WorkflowStatus.UNRESOLVED)
    assert not is_workflow_terminal(WorkflowStatus.RUNNING)
