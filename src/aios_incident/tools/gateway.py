"""Permissioned, bounded and traced tool gateway for incident Agents."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from ..exceptions import (
    AIOSIncidentError,
    RepairDisabledError,
    ToolArgumentError,
    ToolExecutionError,
    ToolNotAllowedError,
    ToolOutputLimitError,
    ToolPathError,
    ToolPermissionError,
    ToolTimeoutError,
)
from ..models import AllowedScope, TraceEvent
from ..orchestrator.trace import JsonlTraceStore
from ..utils import generate_id, utc_now
from .base import (
    TOOL_POLICIES,
    ReadOnlyBackend,
    ToolName,
    ToolRequest,
    ToolResult,
)

ScopeResolver = Callable[[str], AllowedScope]
TraceResolver = Callable[[str], JsonlTraceStore]


class ToolGateway:
    """Validate, execute and trace every tool request."""

    def __init__(
        self,
        backend: ReadOnlyBackend,
        *,
        scope_resolver: ScopeResolver,
        trace_resolver: TraceResolver,
    ) -> None:
        self.backend = backend
        self._scope_resolver = scope_resolver
        self._trace_resolver = trace_resolver

    def execute(self, request: ToolRequest) -> ToolResult:
        """Execute one allowlisted read-only tool call or fail closed."""

        policy = TOOL_POLICIES.get(request.tool_name)
        if policy is None:
            raise ToolNotAllowedError(f"tool is not allowlisted: {request.tool_name.value}")
        trace = self._trace_resolver(request.incident_id)
        self._append_trace(
            trace,
            request,
            event_type="TOOL_CALL_STARTED",
            status="RUNNING",
            tool_calls=0,
        )
        started = time.perf_counter()
        try:
            result = self._execute_checked(request, started)
        except AIOSIncidentError as exc:
            self._append_trace(
                trace,
                request,
                event_type="TOOL_CALL_FINISHED",
                status="FAILED",
                duration_ms=_elapsed_ms(started),
                tool_calls=1,
                extra={"error_type": type(exc).__name__, "error": str(exc)},
            )
            raise
        except Exception as exc:
            normalized = ToolExecutionError(f"tool backend failed: {exc}")
            self._append_trace(
                trace,
                request,
                event_type="TOOL_CALL_FINISHED",
                status="FAILED",
                duration_ms=_elapsed_ms(started),
                tool_calls=1,
                extra={"error_type": type(exc).__name__, "error": str(exc)},
            )
            raise normalized from exc

        self._append_trace(
            trace,
            request,
            event_type="TOOL_CALL_FINISHED",
            status="SUCCEEDED",
            duration_ms=result.duration_ms,
            tool_calls=1,
            extra={"output_bytes": result.output_bytes, "truncated": result.truncated},
        )
        return result

    def _execute_checked(self, request: ToolRequest, started: float) -> ToolResult:
        policy = TOOL_POLICIES[request.tool_name]
        if request.agent_type not in policy.allowed_agent_types:
            raise ToolPermissionError(
                f"{request.agent_type} is not authorized for {request.tool_name.value}"
            )

        arguments = request.arguments
        required = policy.required_arguments
        allowed = required | policy.optional_arguments
        missing = required - set(arguments)
        unknown = set(arguments) - allowed
        if missing:
            raise ToolArgumentError(f"missing tool arguments: {sorted(missing)}")
        if unknown:
            raise ToolArgumentError(f"unsupported tool arguments: {sorted(unknown)}")

        scope = self._scope_resolver(request.incident_id)
        effective_timeout = min(request.timeout_seconds, policy.max_timeout_seconds)
        effective_output_limit = min(request.max_output_bytes, policy.max_output_bytes)

        if request.tool_name is ToolName.REPAIR_APPLY:
            raise RepairDisabledError("repair.apply is disabled until controlled write review")

        if request.tool_name is ToolName.LOG_READ:
            path = _required_string(arguments, "path")
            _validate_read_path(scope, path)
            max_lines = _optional_int(
                arguments,
                "max_lines",
                default=200,
                minimum=1,
                maximum=1000,
            )
            data = self.backend.read_log(
                path,
                max_lines=max_lines,
                max_output_bytes=effective_output_limit,
            )
        elif request.tool_name is ToolName.CONFIG_READ:
            path = _required_string(arguments, "path")
            _validate_read_path(scope, path)
            data = self.backend.read_config(
                path,
                max_output_bytes=effective_output_limit,
            )
        elif request.tool_name is ToolName.METRICS_COLLECT:
            service = _optional_string(arguments, "service")
            window_seconds = _optional_int(
                arguments,
                "window_seconds",
                default=None,
                minimum=1,
                maximum=3600,
            )
            data = self.backend.collect_metrics(
                service=service,
                window_seconds=window_seconds,
                max_output_bytes=effective_output_limit,
            )
        elif request.tool_name is ToolName.DEPENDENCY_INSPECT:
            service = _required_string(arguments, "service")
            data = self.backend.inspect_dependencies(
                service=service,
                max_output_bytes=effective_output_limit,
            )
        else:
            raise ToolNotAllowedError(f"unsupported tool: {request.tool_name.value}")

        encoded = json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        if len(encoded) > effective_output_limit:
            raise ToolOutputLimitError(f"tool output exceeds {effective_output_limit} bytes")
        duration_ms = _elapsed_ms(started)
        if duration_ms / 1000 > effective_timeout:
            raise ToolTimeoutError(f"tool exceeded {effective_timeout:g}s timeout")
        return ToolResult(
            request_id=request.request_id,
            incident_id=request.incident_id,
            task_id=request.task_id,
            agent_id=request.agent_id,
            tool_name=request.tool_name,
            data=data,
            truncated=bool(data.get("truncated", False)),
            output_bytes=len(encoded),
            duration_ms=duration_ms,
        )

    def _append_trace(
        self,
        trace: JsonlTraceStore,
        request: ToolRequest,
        *,
        event_type: str,
        status: str,
        duration_ms: int | None = None,
        tool_calls: int,
        extra: dict[str, Any] | None = None,
    ) -> None:
        details: dict[str, Any] = {
            "request_id": request.request_id,
            "tool_name": request.tool_name.value,
            "agent_type": request.agent_type,
        }
        if extra:
            details.update(extra)
        trace.append(
            TraceEvent(
                trace_id=generate_id("trace"),
                incident_id=request.incident_id,
                task_id=request.task_id,
                agent_id=request.agent_id,
                event_type=event_type,
                status=status,
                timestamp=utc_now(),
                duration_ms=duration_ms,
                tool_calls=tool_calls,
                details=details,
            )
        )


class SandboxReadOnlyBackend:
    """Read-only backend rooted at one filesystem snapshot of a Linux target."""

    def __init__(self, sandbox_root: Path) -> None:
        self.sandbox_root = sandbox_root.resolve()

    def read_log(
        self,
        target_path: str,
        *,
        max_lines: int,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        path = self._sandbox_path(target_path)
        try:
            size_bytes = path.stat().st_size
            read_limit = min(max(size_bytes, max_output_bytes * 2), 512 * 1024)
            with path.open("rb") as stream:
                if size_bytes > read_limit:
                    stream.seek(-read_limit, 2)
                raw = stream.read(read_limit)
        except OSError as exc:
            raise ToolExecutionError(f"cannot read log file {target_path}: {exc}") from exc

        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()[-max_lines:]
        selected: list[str] = []
        selected_bytes = 0
        for line in reversed(lines):
            line_bytes = len((line + "\n").encode("utf-8"))
            if selected_bytes + line_bytes > max_output_bytes:
                break
            selected.append(line)
            selected_bytes += line_bytes
        selected.reverse()
        return {
            "path": target_path,
            "size_bytes": size_bytes,
            "max_lines": max_lines,
            "lines": selected,
            "truncated": size_bytes > read_limit or len(selected) < len(lines),
        }

    def collect_metrics(
        self,
        *,
        service: str | None,
        window_seconds: int | None,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        proc_root = self._sandbox_path("/proc")
        loadavg = self._optional_text(proc_root / "loadavg")
        meminfo = self._optional_text(proc_root / "meminfo")
        netdev = self._optional_text(proc_root / "net" / "dev")
        stat_text = self._optional_text(proc_root / "stat")
        return {
            "source": "sandbox-proc",
            "available": any(value is not None for value in (loadavg, meminfo, netdev)),
            "service": service,
            "window_seconds": window_seconds,
            "load_average": _parse_loadavg(loadavg),
            "memory_kib": _parse_meminfo(meminfo),
            "network_interfaces": _parse_netdev(netdev),
            "cpu_entries": _count_cpu_entries(stat_text),
            "max_output_bytes": max_output_bytes,
        }

    def read_config(self, target_path: str, *, max_output_bytes: int) -> dict[str, Any]:
        path = self._sandbox_path(target_path)
        try:
            size_bytes = path.stat().st_size
            with path.open("rb") as stream:
                raw = stream.read(max_output_bytes + 1)
        except OSError as exc:
            raise ToolExecutionError(f"cannot read config file {target_path}: {exc}") from exc
        truncated = len(raw) > max_output_bytes
        content_bytes = raw[:max_output_bytes]
        return {
            "path": target_path,
            "size_bytes": size_bytes,
            "content": content_bytes.decode("utf-8", errors="replace"),
            "sha256": hashlib.sha256(content_bytes).hexdigest(),
            "truncated": truncated,
        }

    def inspect_dependencies(
        self,
        *,
        service: str,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        proc_root = self._sandbox_path("/proc")
        processes: list[dict[str, Any]] = []
        if proc_root.is_dir():
            process_dirs = sorted(
                (item for item in proc_root.iterdir() if item.is_dir() and item.name.isdigit()),
                key=lambda item: int(item.name),
            )
            for process_dir in process_dirs[:1000]:
                name = self._optional_text(process_dir / "comm")
                if name is None:
                    continue
                status = self._optional_text(process_dir / "status") or ""
                service_lower = service.lower()
                if (
                    service_lower not in name.strip().lower()
                    and service_lower not in status.lower()
                ):
                    continue
                processes.append(
                    {
                        "pid": int(process_dir.name),
                        "name": name.strip(),
                        "status": _parse_process_status(status),
                    }
                )
        ports = self._parse_proc_net(
            proc_root / "net" / "tcp",
            proc_root / "net" / "tcp6",
        )
        return {
            "source": "sandbox-proc",
            "service": service,
            "processes": processes,
            "ports": ports,
            "available": proc_root.is_dir(),
            "max_output_bytes": max_output_bytes,
        }

    def _sandbox_path(self, target_path: str) -> Path:
        normalized = _normalize_absolute_path(target_path)
        relative = Path(*normalized.parts[1:])
        candidate = (self.sandbox_root / relative).resolve()
        if candidate != self.sandbox_root and self.sandbox_root not in candidate.parents:
            raise ToolPathError(f"path escapes sandbox root: {target_path}")
        return candidate

    @staticmethod
    def _optional_text(path: Path) -> str | None:
        try:
            if not path.is_file():
                return None
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    @staticmethod
    def _parse_proc_net(tcp_path: Path, tcp6_path: Path) -> list[dict[str, Any]]:
        ports: list[dict[str, Any]] = []
        for path in (tcp_path, tcp6_path):
            text = SandboxReadOnlyBackend._optional_text(path)
            if text is None:
                continue
            for line in text.splitlines()[1:]:
                fields = line.split()
                if len(fields) < 4:
                    continue
                address, port_hex = _split_proc_address(fields[1])
                ports.append(
                    {
                        "address": address,
                        "port": int(port_hex, 16),
                        "state": fields[3],
                    }
                )
        return ports[:500]


def _validate_read_path(scope: AllowedScope, target_path: str) -> None:
    normalized = _normalize_absolute_path(target_path)
    allowed = tuple(_normalize_absolute_path(path) for path in scope.read_paths)
    if not any(normalized == root or normalized.is_relative_to(root) for root in allowed):
        raise ToolPathError(f"path is outside allowed read scope: {target_path}")


def _normalize_absolute_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts or "\x00" in value:
        raise ToolPathError(f"unsafe target path: {value}")
    return path


def _required_string(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolArgumentError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_string(arguments: dict[str, Any], key: str) -> str | None:
    if key not in arguments or arguments[key] is None:
        return None
    return _required_string(arguments, key)


def _optional_int(
    arguments: dict[str, Any],
    key: str,
    *,
    default: int | None,
    minimum: int,
    maximum: int,
) -> int | None:
    value = arguments.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolArgumentError(f"{key} must be an integer")
    if value < minimum or value > maximum:
        raise ToolArgumentError(f"{key} must be between {minimum} and {maximum}")
    return value


def _parse_loadavg(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    fields = text.split()
    if len(fields) < 3:
        return None
    try:
        return {
            "one_minute": float(fields[0]),
            "five_minutes": float(fields[1]),
            "fifteen_minutes": float(fields[2]),
        }
    except ValueError:
        return None


def _parse_meminfo(text: str | None) -> dict[str, int] | None:
    if not text:
        return None
    values: dict[str, int] = {}
    for line in text.splitlines():
        key, _, remainder = line.partition(":")
        if key not in {"MemTotal", "MemFree", "MemAvailable", "SwapTotal", "SwapFree"}:
            continue
        fields = remainder.split()
        if fields and fields[0].isdigit():
            values[key] = int(fields[0])
    return values


def _parse_netdev(text: str | None) -> list[dict[str, Any]]:
    if not text:
        return []
    interfaces: list[dict[str, Any]] = []
    for line in text.splitlines()[2:]:
        name, _, values = line.partition(":")
        fields = values.split()
        if len(fields) < 16:
            continue
        interfaces.append(
            {
                "name": name.strip(),
                "rx_bytes": int(fields[0]),
                "rx_packets": int(fields[1]),
                "tx_bytes": int(fields[8]),
                "tx_packets": int(fields[9]),
            }
        )
    return interfaces


def _count_cpu_entries(text: str | None) -> int:
    if not text:
        return 0
    return sum(
        1
        for line in text.splitlines()
        if line.startswith("cpu") and len(line) > 3 and line[3].isdigit()
    )


def _parse_process_status(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator and key in {"Name", "State", "PPid", "VmRSS"}:
            values[key] = value.strip()
    return values


def _split_proc_address(value: str) -> tuple[str, str]:
    address, _, port = value.partition(":")
    return address, port or "0"


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
