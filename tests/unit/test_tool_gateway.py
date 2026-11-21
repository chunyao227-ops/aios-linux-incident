"""W06 tool permission, limit and trace tests."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from aios_incident.exceptions import (
    RepairDisabledError,
    ToolArgumentError,
    ToolOutputLimitError,
    ToolPathError,
    ToolPermissionError,
    ToolTimeoutError,
)
from aios_incident.models import AllowedScope
from aios_incident.orchestrator.trace import JsonlTraceStore
from aios_incident.tools.base import ToolName, ToolRequest
from aios_incident.tools.gateway import ToolGateway


class FakeBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.delay_seconds = 0.0
        self.log_data = {
            "path": "/var/log/web-app/error.log",
            "lines": ["database connection refused"],
            "truncated": False,
        }

    def read_log(
        self,
        target_path: str,
        *,
        max_lines: int,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "read_log",
                {
                    "target_path": target_path,
                    "max_lines": max_lines,
                    "max_output_bytes": max_output_bytes,
                },
            )
        )
        time.sleep(self.delay_seconds)
        return self.log_data

    def collect_metrics(
        self,
        *,
        service: str | None,
        window_seconds: int | None,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "collect_metrics",
                {
                    "service": service,
                    "window_seconds": window_seconds,
                    "max_output_bytes": max_output_bytes,
                },
            )
        )
        return {"cpu": 0.25, "service": service, "window_seconds": window_seconds}

    def read_config(self, target_path: str, *, max_output_bytes: int) -> dict[str, Any]:
        self.calls.append(
            ("read_config", {"target_path": target_path, "max_output_bytes": max_output_bytes})
        )
        return {"path": target_path, "content": "port: 8080", "truncated": False}

    def inspect_dependencies(
        self,
        *,
        service: str,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "inspect_dependencies",
                {"service": service, "max_output_bytes": max_output_bytes},
            )
        )
        return {"service": service, "processes": [{"pid": 12, "name": service}]}


def make_request(
    tool_name: ToolName,
    *,
    agent_type: str,
    arguments: dict[str, Any] | None = None,
    max_output_bytes: int = 4096,
    timeout_seconds: float = 2,
) -> ToolRequest:
    return ToolRequest(
        request_id="tool-request-001",
        incident_id="inc-001",
        task_id="N1",
        agent_id="agent-001",
        agent_type=agent_type,
        tool_name=tool_name,
        arguments=arguments or {},
        max_output_bytes=max_output_bytes,
        timeout_seconds=timeout_seconds,
    )


@pytest.fixture
def gateway(tmp_path: Path) -> tuple[ToolGateway, FakeBackend, JsonlTraceStore]:
    backend = FakeBackend()
    scope = AllowedScope(
        read_paths=("/var/log", "/etc/web-app"),
        allowed_services=("web-app", "postgresql"),
    )
    trace = JsonlTraceStore(tmp_path / "traces", "inc-001", "run-001")
    client = ToolGateway(
        backend,
        scope_resolver=lambda _: scope,
        trace_resolver=lambda _: trace,
    )
    return client, backend, trace


def test_log_tool_returns_structured_result_and_traces_start_finish(
    gateway: tuple[ToolGateway, FakeBackend, JsonlTraceStore],
) -> None:
    client, backend, trace = gateway
    request = make_request(
        ToolName.LOG_READ,
        agent_type="LogAgent",
        arguments={"path": "/var/log/web-app/error.log", "max_lines": 50},
    )
    result = client.execute(request)

    assert result.success is True
    assert result.data["lines"] == ["database connection refused"]
    assert backend.calls[0][0] == "read_log"
    assert backend.calls[0][1]["max_lines"] == 50
    assert [event.event_type for event in trace.read_events()] == [
        "TOOL_CALL_STARTED",
        "TOOL_CALL_FINISHED",
    ]
    assert [event.tool_calls for event in trace.read_events()] == [0, 1]
    assert trace.read_events()[1].status == "SUCCEEDED"


def test_unauthorized_agent_is_rejected_and_traced(
    gateway: tuple[ToolGateway, FakeBackend, JsonlTraceStore],
) -> None:
    client, backend, trace = gateway
    request = make_request(
        ToolName.CONFIG_READ,
        agent_type="LogAgent",
        arguments={"path": "/etc/web-app/config.yaml"},
    )
    with pytest.raises(ToolPermissionError, match="not authorized"):
        client.execute(request)

    assert backend.calls == []
    assert [event.status for event in trace.read_events()] == ["RUNNING", "FAILED"]


def test_unknown_argument_is_rejected(
    gateway: tuple[ToolGateway, FakeBackend, JsonlTraceStore],
) -> None:
    client, _, _ = gateway
    with pytest.raises(ToolArgumentError, match="unsupported"):
        client.execute(
            make_request(
                ToolName.LOG_READ,
                agent_type="LogAgent",
                arguments={"path": "/var/log/web-app/error.log", "shell": "whoami"},
            )
        )


@pytest.mark.parametrize(
    "path",
    [
        "/var/log/../../etc/passwd",
        "/etc/passwd",
        "relative/path.log",
    ],
)
def test_path_escape_or_out_of_scope_is_rejected(
    gateway: tuple[ToolGateway, FakeBackend, JsonlTraceStore],
    path: str,
) -> None:
    client, backend, _ = gateway
    with pytest.raises(ToolPathError):
        client.execute(
            make_request(
                ToolName.LOG_READ,
                agent_type="LogAgent",
                arguments={"path": path},
            )
        )
    assert backend.calls == []


def test_repair_tool_fails_closed_even_for_authorized_agent(
    gateway: tuple[ToolGateway, FakeBackend, JsonlTraceStore],
) -> None:
    client, backend, _ = gateway
    with pytest.raises(RepairDisabledError):
        client.execute(
            make_request(
                ToolName.REPAIR_APPLY,
                agent_type="RepairAgent",
                arguments={
                    "description": "restart postgresql",
                    "target_path": "/etc/web-app/config.yaml",
                },
            )
        )
    assert backend.calls == []


def test_output_limit_is_enforced(
    gateway: tuple[ToolGateway, FakeBackend, JsonlTraceStore],
) -> None:
    client, backend, _ = gateway
    backend.log_data = {"lines": ["x" * 200], "truncated": False}
    with pytest.raises(ToolOutputLimitError):
        client.execute(
            make_request(
                ToolName.LOG_READ,
                agent_type="LogAgent",
                arguments={"path": "/var/log/web-app/error.log"},
                max_output_bytes=32,
            )
        )


def test_timeout_is_enforced(
    gateway: tuple[ToolGateway, FakeBackend, JsonlTraceStore],
) -> None:
    client, backend, _ = gateway
    backend.delay_seconds = 0.02
    with pytest.raises(ToolTimeoutError):
        client.execute(
            make_request(
                ToolName.LOG_READ,
                agent_type="LogAgent",
                arguments={"path": "/var/log/web-app/error.log"},
                timeout_seconds=0.001,
            )
        )


def test_effective_limits_are_capped_by_policy(
    gateway: tuple[ToolGateway, FakeBackend, JsonlTraceStore],
) -> None:
    client, backend, _ = gateway
    client.execute(
        make_request(
            ToolName.LOG_READ,
            agent_type="LogAgent",
            arguments={"path": "/var/log/web-app/error.log"},
            max_output_bytes=10_000_000,
            timeout_seconds=60,
        )
    )
    assert backend.calls[0][1]["max_output_bytes"] == 64 * 1024
