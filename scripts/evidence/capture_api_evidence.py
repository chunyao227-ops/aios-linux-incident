"""Capture local API and dashboard evidence from a running application."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "docs" / "submission" / "evidence" / "api"
UI_DIR = ROOT / "docs" / "submission" / "evidence" / "ui"
BASE_URL = "http://127.0.0.1:8080"
PAYLOAD = {
    "objective": "诊断并修复 web-app 不可用问题",
    "target": {
        "host": "sandbox-01",
        "service": "web-app",
        "environment": "docker",
    },
    "allowed_scope": {
        "read_paths": ["/var/log/web-app", "/etc/web-app"],
        "write_paths": ["/etc/web-app"],
        "allowed_services": ["web-app"],
    },
    "time_budget_seconds": 600,
    "max_repair_attempts": 2,
    "success_criteria": ["health_endpoint", "smoke_test", "regression_test"],
}


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return value.replace(str(ROOT), "<PROJECT_ROOT>").replace(
            ROOT.as_posix(),
            "<PROJECT_ROOT>",
        )
    return value


def call(
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
            status = response.status
            content_type = response.headers.get("Content-Type", "")
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        status = exc.code
        content_type = exc.headers.get("Content-Type", "")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = body
    return {
        "method": method,
        "path": path,
        "status": status,
        "content_type": content_type,
        "body": parsed,
    }


def main() -> None:
    API_DIR.mkdir(parents=True, exist_ok=True)
    UI_DIR.mkdir(parents=True, exist_ok=True)
    captures: dict[str, Any] = {}
    created = call("POST", "/api/v1/incidents", PAYLOAD)
    captures["create"] = created
    incident_id = str(created["body"]["incident_id"])
    run_id = str(created["body"]["run_id"])

    captures["status"] = call("GET", f"/api/v1/incidents/{incident_id}")
    captures["dag"] = call("GET", f"/api/v1/incidents/{incident_id}/dag")
    captures["events_before_cancel"] = call(
        "GET",
        f"/api/v1/incidents/{incident_id}/events",
    )
    captures["result_before_cancel"] = call(
        "GET",
        f"/api/v1/incidents/{incident_id}/result",
    )
    captures["cancel"] = call("POST", f"/api/v1/incidents/{incident_id}/cancel")
    captures["events_after_cancel"] = call(
        "GET",
        f"/api/v1/incidents/{incident_id}/events",
    )
    captures["unknown_incident_404"] = call(
        "GET",
        "/api/v1/incidents/inc-does-not-exist",
    )

    second = call("POST", "/api/v1/incidents", PAYLOAD)
    captures["create_second"] = second
    second_id = str(second["body"]["incident_id"])
    captures["cancel_second"] = call("POST", f"/api/v1/incidents/{second_id}/cancel")
    captures["create_third"] = call("POST", "/api/v1/incidents", PAYLOAD)
    captures["history"] = call("GET", "/api/v1/incidents")
    captures["benchmark"] = call("GET", "/api/v1/benchmarks/latest")
    captures["openapi"] = call("GET", "/openapi.json")

    (API_DIR / "W05_api_capture.json").write_text(
        json.dumps(sanitize(captures), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (API_DIR / "W05_openapi.json").write_text(
        json.dumps(
            sanitize(captures["openapi"]["body"]),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (UI_DIR / "W14_history_api.json").write_text(
        json.dumps(captures["history"]["body"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    trace_source = ROOT / "runs" / incident_id / f"{run_id}.jsonl"
    metadata_source = ROOT / "runs" / incident_id / f"{run_id}.meta.json"
    if trace_source.exists():
        (API_DIR / "W05_trace.jsonl").write_bytes(trace_source.read_bytes())
    if metadata_source.exists():
        (API_DIR / "W05_run_metadata.json").write_bytes(metadata_source.read_bytes())

    lines = [
        "# W05 API 本地证据",
        "",
        "服务地址：`http://127.0.0.1:8080`。",
        "",
        "| 操作 | 方法 | 路径 | 状态码 |",
        "|---|---|---|---:|",
    ]
    for name, capture in captures.items():
        if name == "openapi":
            continue
        lines.append(
            f"| {name} | {capture['method']} | `{capture['path']}` | "
            f"{capture['status']} |"
        )
    lines.extend(
        (
            "",
            "完整响应体保存在 `W05_api_capture.json`，OpenAPI 文档保存在",
            "`W05_openapi.json`。",
            "",
        )
    )
    (API_DIR / "W05_api_capture.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
        newline="\n",
    )
    print(f"captured {len(captures)} API operations")


if __name__ == "__main__":
    main()
