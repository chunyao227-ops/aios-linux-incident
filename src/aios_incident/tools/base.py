"""Tool protocol, permissions and size limits."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from pydantic import Field

from ..models import NonEmptyStr, StrictModel


class ToolName(str, Enum):
    LOG_READ = "log.read"
    METRICS_COLLECT = "metrics.collect"
    CONFIG_READ = "config.read"
    DEPENDENCY_INSPECT = "dependency.inspect"
    REPAIR_APPLY = "repair.apply"


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    name: ToolName
    allowed_agent_types: frozenset[str]
    read_only: bool
    max_timeout_seconds: float
    max_output_bytes: int
    required_arguments: frozenset[str] = frozenset()
    optional_arguments: frozenset[str] = frozenset()


TOOL_POLICIES: dict[ToolName, ToolPolicy] = {
    ToolName.LOG_READ: ToolPolicy(
        name=ToolName.LOG_READ,
        allowed_agent_types=frozenset({"LogAgent"}),
        read_only=True,
        max_timeout_seconds=10,
        max_output_bytes=64 * 1024,
        required_arguments=frozenset({"path"}),
        optional_arguments=frozenset({"max_lines"}),
    ),
    ToolName.METRICS_COLLECT: ToolPolicy(
        name=ToolName.METRICS_COLLECT,
        allowed_agent_types=frozenset({"MetricsAgent"}),
        read_only=True,
        max_timeout_seconds=10,
        max_output_bytes=64 * 1024,
        optional_arguments=frozenset({"service", "window_seconds"}),
    ),
    ToolName.CONFIG_READ: ToolPolicy(
        name=ToolName.CONFIG_READ,
        allowed_agent_types=frozenset({"ConfigAgent"}),
        read_only=True,
        max_timeout_seconds=10,
        max_output_bytes=64 * 1024,
        required_arguments=frozenset({"path"}),
    ),
    ToolName.DEPENDENCY_INSPECT: ToolPolicy(
        name=ToolName.DEPENDENCY_INSPECT,
        allowed_agent_types=frozenset({"DependencyAgent"}),
        read_only=True,
        max_timeout_seconds=10,
        max_output_bytes=96 * 1024,
        required_arguments=frozenset({"service"}),
    ),
    ToolName.REPAIR_APPLY: ToolPolicy(
        name=ToolName.REPAIR_APPLY,
        allowed_agent_types=frozenset({"RepairAgent"}),
        read_only=False,
        max_timeout_seconds=5,
        max_output_bytes=16 * 1024,
        required_arguments=frozenset({"description"}),
        optional_arguments=frozenset({"target_path"}),
    ),
}


class ToolRequest(StrictModel):
    request_id: NonEmptyStr
    incident_id: NonEmptyStr
    task_id: NonEmptyStr
    agent_id: NonEmptyStr
    agent_type: NonEmptyStr
    tool_name: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=10, gt=0, le=60)
    max_output_bytes: int = Field(default=32 * 1024, gt=0)


class ToolResult(StrictModel):
    request_id: NonEmptyStr
    incident_id: NonEmptyStr
    task_id: NonEmptyStr
    agent_id: NonEmptyStr
    tool_name: ToolName
    success: bool = True
    data: dict[str, Any]
    truncated: bool = False
    output_bytes: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


class ReadOnlyBackend(Protocol):
    """Trusted backend that executes only fixed read-only operations."""

    def read_log(
        self,
        target_path: str,
        *,
        max_lines: int,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        """Read bounded log lines from an allowed target path."""

    def collect_metrics(
        self,
        *,
        service: str | None,
        window_seconds: int | None,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        """Collect bounded CPU, memory, disk and network metrics."""

    def read_config(self, target_path: str, *, max_output_bytes: int) -> dict[str, Any]:
        """Read one bounded configuration file."""

    def inspect_dependencies(
        self,
        *,
        service: str,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        """Return structured process, service and port relationships."""
