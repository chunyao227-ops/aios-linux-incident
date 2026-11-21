"""Allowlisted repair execution without arbitrary shell strings."""

from __future__ import annotations

from typing import Protocol

from ..exceptions import RepairNotAllowedError
from ..models import (
    RepairAction,
    RepairActionResult,
    RepairPlan,
    RepairResult,
    RepairStatus,
    RunContext,
)
from ..utils import utc_now

ALLOWED_REPAIR_PARAMETERS: dict[str, frozenset[str]] = {
    "simulated_repair": frozenset({"service", "strategy_attempt", "previous_failure_id"}),
    "service_start": frozenset({"service", "container_id"}),
    "service_restart": frozenset({"service", "container_id"}),
    "config_restore": frozenset({"target_path", "container_id", "source_ref"}),
}

FORBIDDEN_PARAMETER_NAMES = frozenset({"command", "shell", "script", "cmd", "sudo", "rm", "mkfs"})


class RepairBackend(Protocol):
    def execute_action(
        self,
        context: RunContext,
        plan: RepairPlan,
        action: RepairAction,
        attempt_no: int,
    ) -> RepairActionResult:
        """Execute one fixed, non-shell repair action."""

    def rollback(
        self,
        context: RunContext,
        plan: RepairPlan,
    ) -> str:
        """Restore the pre-repair state and return a bounded summary."""


class ControlledRepairTool:
    """Validate and execute one typed RepairPlan."""

    def __init__(self, backend: RepairBackend) -> None:
        self.backend = backend

    def execute(self, context: RunContext, plan: RepairPlan) -> RepairResult:
        self.validate(context, plan)
        started_at = utc_now()
        action_results: list[RepairActionResult] = []
        failure: RepairActionResult | None = None
        for action in plan.actions:
            result = self.backend.execute_action(
                context,
                plan,
                action,
                plan.attempt_no,
            )
            action_results.append(result)
            if not result.success and action.critical:
                failure = result
                break

        rollback_performed = False
        rollback_summary = ""
        if failure is not None:
            try:
                rollback_summary = self.backend.rollback(context, plan)
                rollback_performed = True
            except Exception:
                rollback_performed = False
        status = (
            RepairStatus.SUCCEEDED
            if failure is None
            else RepairStatus.ROLLED_BACK
            if rollback_performed
            else RepairStatus.FAILED
        )
        return RepairResult(
            repair_id=plan.repair_id,
            incident_id=context.incident_id,
            attempt_no=plan.attempt_no,
            status=status,
            action_results=tuple(action_results),
            rollback_performed=rollback_performed,
            error=(
                None
                if failure is None
                else f"{failure.action_id} failed; {rollback_summary or 'rollback unavailable'}"
            ),
            started_at=started_at,
            ended_at=utc_now(),
        )

    @staticmethod
    def validate(context: RunContext, plan: RepairPlan) -> None:
        if plan.incident_id != context.incident_id:
            raise RepairNotAllowedError("repair plan belongs to another incident")
        if not plan.root_cause_ids:
            raise RepairNotAllowedError("repair plan has no diagnosed root cause")
        if not plan.rollback_plan:
            raise RepairNotAllowedError("repair plan has no rollback plan")
        if plan.attempt_no > 1 and plan.previous_failure_id is None:
            raise RepairNotAllowedError("retry repair must reference previous failure")

        allowed_services = set(context.allowed_scope.allowed_services)
        write_paths = tuple(context.allowed_scope.write_paths)
        for action in plan.actions:
            if action.tool_name not in ALLOWED_REPAIR_PARAMETERS:
                raise RepairNotAllowedError(f"repair tool is not allowlisted: {action.tool_name}")
            keys = set(action.parameters)
            if keys & FORBIDDEN_PARAMETER_NAMES:
                raise RepairNotAllowedError("repair parameters contain a shell or destructive key")
            unknown = keys - ALLOWED_REPAIR_PARAMETERS[action.tool_name]
            if unknown:
                raise RepairNotAllowedError(
                    f"unsupported repair parameters for {action.tool_name}: {sorted(unknown)}"
                )
            service = action.parameters.get("service")
            if service is not None and service != context.target.service:
                raise RepairNotAllowedError("repair service is outside the incident target")
            if allowed_services and context.target.service not in allowed_services:
                raise RepairNotAllowedError("target service is outside allowed_services")
            container_id = action.parameters.get("container_id")
            if container_id is not None and container_id != context.target.host:
                raise RepairNotAllowedError("repair target container does not match the incident")
            target_path = action.parameters.get("target_path")
            if target_path is not None:
                if not isinstance(target_path, str) or not target_path.startswith("/"):
                    raise RepairNotAllowedError("repair target_path must be absolute")
                if ".." in target_path:
                    raise RepairNotAllowedError("repair target_path cannot contain '..'")
                if not any(
                    target_path == root or target_path.startswith(root.rstrip("/") + "/")
                    for root in write_paths
                ):
                    raise RepairNotAllowedError("repair target_path is outside write scope")
