"""W06 sandbox-backed read-only tool integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from aios_incident.exceptions import RepairDisabledError, ToolPathError
from aios_incident.models import AllowedScope
from aios_incident.orchestrator.trace import JsonlTraceStore
from aios_incident.tools.base import ToolName, ToolRequest
from aios_incident.tools.gateway import SandboxReadOnlyBackend, ToolGateway


def write_file(root: Path, target_path: str, content: str) -> None:
    path = root / target_path.lstrip("/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def isolated_gateway(
    tmp_path: Path,
) -> tuple[ToolGateway, JsonlTraceStore]:
    sandbox_root = tmp_path / "sandbox"
    write_file(
        sandbox_root,
        "/var/log/web-app/error.log",
        "2026-11-21T12:00:00Z connected\n2026-11-21T12:01:00Z database refused\n",
    )
    write_file(
        sandbox_root,
        "/etc/web-app/config.yaml",
        "service: web-app\nport: 8080\n",
    )
    write_file(sandbox_root, "/proc/loadavg", "0.10 0.20 0.30 1/100 123\n")
    write_file(
        sandbox_root,
        "/proc/meminfo",
        "MemTotal: 16384 kB\nMemFree: 8192 kB\nMemAvailable: 12000 kB\n",
    )
    write_file(sandbox_root, "/proc/stat", "cpu 1 2 3 4\ncpu0 1 2 3 4\ncpu1 1 2 3 4\n")
    write_file(
        sandbox_root,
        "/proc/net/dev",
        (
            "Inter-| Receive | Transmit\n"
            " face |bytes packets errs drop fifo frame compressed multicast|"
            "bytes packets errs drop fifo colls carrier compressed\n"
            " eth0: 100 2 0 0 0 0 0 0 200 3 0 0 0 0 0 0\n"
        ),
    )
    write_file(sandbox_root, "/proc/123/comm", "web-app\n")
    write_file(
        sandbox_root,
        "/proc/123/status",
        "Name:\tweb-app\nState:\tS (sleeping)\nPPid:\t1\n",
    )
    write_file(
        sandbox_root,
        "/proc/net/tcp",
        (
            "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   "
            "uid  timeout inode\n"
            "   0: 00000000:1F90 00000000:0000 0A 00000000:00000000 "
            "00:00000000 00000000     0        0 1\n"
        ),
    )
    write_file(
        sandbox_root,
        "/proc/net/tcp6",
        (
            "  sl  local_address                         remote_address                        "
            "st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        ),
    )

    scope = AllowedScope(
        read_paths=("/var/log", "/etc/web-app"),
        allowed_services=("web-app", "postgresql"),
    )
    trace = JsonlTraceStore(tmp_path / "traces", "inc-001", "run-001")
    gateway = ToolGateway(
        SandboxReadOnlyBackend(sandbox_root),
        scope_resolver=lambda _: scope,
        trace_resolver=lambda _: trace,
    )
    return gateway, trace


def request(
    tool_name: ToolName,
    *,
    agent_type: str,
    arguments: dict[str, object],
) -> ToolRequest:
    return ToolRequest(
        request_id=f"request-{tool_name.value}",
        incident_id="inc-001",
        task_id="N1",
        agent_id="agent-001",
        agent_type=agent_type,
        tool_name=tool_name,
        arguments=arguments,
    )


def test_four_read_only_tools_return_structured_data(
    isolated_gateway: tuple[ToolGateway, JsonlTraceStore],
) -> None:
    gateway, trace = isolated_gateway

    log_result = gateway.execute(
        request(
            ToolName.LOG_READ,
            agent_type="LogAgent",
            arguments={"path": "/var/log/web-app/error.log"},
        )
    )
    assert log_result.data["lines"][-1].endswith("database refused")

    metrics_result = gateway.execute(
        request(
            ToolName.METRICS_COLLECT,
            agent_type="MetricsAgent",
            arguments={"service": "web-app", "window_seconds": 60},
        )
    )
    assert metrics_result.data["load_average"]["one_minute"] == 0.1
    assert metrics_result.data["memory_kib"]["MemTotal"] == 16384
    assert metrics_result.data["cpu_entries"] == 2

    config_result = gateway.execute(
        request(
            ToolName.CONFIG_READ,
            agent_type="ConfigAgent",
            arguments={"path": "/etc/web-app/config.yaml"},
        )
    )
    assert "port: 8080" in config_result.data["content"]
    assert len(config_result.data["sha256"]) == 64

    dependency_result = gateway.execute(
        request(
            ToolName.DEPENDENCY_INSPECT,
            agent_type="DependencyAgent",
            arguments={"service": "web-app"},
        )
    )
    assert dependency_result.data["processes"][0]["pid"] == 123
    assert dependency_result.data["ports"][0]["port"] == 8080

    events = trace.read_events()
    assert len(events) == 8
    assert all(event.event_type in {"TOOL_CALL_STARTED", "TOOL_CALL_FINISHED"} for event in events)


def test_path_escape_is_rejected_before_filesystem_access(
    isolated_gateway: tuple[ToolGateway, JsonlTraceStore],
) -> None:
    gateway, trace = isolated_gateway
    with pytest.raises(ToolPathError):
        gateway.execute(
            request(
                ToolName.CONFIG_READ,
                agent_type="ConfigAgent",
                arguments={"path": "/etc/web-app/../../etc/passwd"},
            )
        )
    assert trace.read_events()[-1].status == "FAILED"


def test_repair_placeholder_cannot_write(
    isolated_gateway: tuple[ToolGateway, JsonlTraceStore],
) -> None:
    gateway, trace = isolated_gateway
    with pytest.raises(RepairDisabledError):
        gateway.execute(
            request(
                ToolName.REPAIR_APPLY,
                agent_type="RepairAgent",
                arguments={
                    "description": "rewrite configuration",
                    "target_path": "/etc/web-app/config.yaml",
                },
            )
        )
    assert trace.read_events()[-1].status == "FAILED"
