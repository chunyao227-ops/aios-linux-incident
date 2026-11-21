"""Deterministic web-app target used by the six Docker scenarios."""

from __future__ import annotations

import json
import os
import shutil
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("/etc/demo/config.json")
STATE_PATH = Path("/var/lib/demo/state.json")
APP_DIR = Path("/var/lib/demo")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def dependency_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def health_snapshot() -> dict[str, Any]:
    try:
        config = read_json(CONFIG_PATH)
        state = read_json(STATE_PATH)
        state_readable = True
    except (OSError, ValueError, json.JSONDecodeError):
        return {
            "healthy": False,
            "reason": "configuration_or_state_unreadable",
            "state_readable": False,
        }

    disk_usage = shutil.disk_usage(APP_DIR)
    disk_ratio = disk_usage.used / disk_usage.total if disk_usage.total else 1.0
    dependency_ok = dependency_reachable(
        str(config.get("db_host", "127.0.0.1")),
        int(config.get("db_port", 6379)),
    )
    checks = {
        "state_readable": state_readable,
        "port_matches": config.get("port") == 8080,
        "mode_matches": state.get("mode") == config.get("mode"),
        "dependency_reachable": dependency_ok,
        "disk_below_threshold": disk_ratio < 0.9,
    }
    return {
        "healthy": all(checks.values()),
        "reason": next((name for name, passed in checks.items() if not passed), "ok"),
        "scenario_id": os.getenv("SCENARIO_ID", "unknown"),
        "checks": checks,
        "disk_ratio": round(disk_ratio, 4),
        "config": config,
        "state_mode": state.get("mode"),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ScenarioWebApp/1.0"

    def do_GET(self) -> None:
        if self.path == "/health":
            snapshot = health_snapshot()
            self._json(200 if snapshot["healthy"] else 503, snapshot)
            return
        if self.path == "/api":
            snapshot = health_snapshot()
            self._json(
                200 if snapshot["healthy"] else 503,
                {"status": "ok" if snapshot["healthy"] else "unavailable"},
            )
            return
        if self.path == "/version":
            self._json(200, {"version": "1.0", "build": "scenario-fixture"})
            return
        self._json(404, {"error": "not_found"})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, value: dict[str, Any]) -> None:
        payload = json.dumps(value, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8080), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
