"""Fixture control for deterministic Docker scenario lifecycle operations."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("/etc/demo/config.json")
STATE_PATH = Path("/var/lib/demo/state.json")
FAULT_PATH = Path("/var/lib/demo/fault.bin")
DEPENDENCY_PID = Path("/run/demo/dependency.pid")


def config_for(scenario_id: str) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "service": "web-app",
        "port": 8080,
        "db_host": "127.0.0.1",
        "db_port": 6379,
        "mode": "healthy",
        "version": "1.0",
    }


def state_for(scenario_id: str) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "service": "web-app",
        "mode": "healthy",
        "revision": 1,
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def initialize(scenario_id: str) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(CONFIG_PATH, config_for(scenario_id))
    write_json(STATE_PATH, state_for(scenario_id))
    STATE_PATH.chmod(0o640)
    if FAULT_PATH.exists():
        FAULT_PATH.unlink()


def inject(scenario_id: str) -> None:
    config = read_json(CONFIG_PATH)
    state = read_json(STATE_PATH)
    if scenario_id == "f1":
        config["port"] = 9090
        write_json(CONFIG_PATH, config)
    elif scenario_id == "f2":
        STATE_PATH.chmod(0)
    elif scenario_id == "f3":
        stop_dependency()
    elif scenario_id == "f4":
        config["db_port"] = 6399
        write_json(CONFIG_PATH, config)
    elif scenario_id == "f5":
        with FAULT_PATH.open("wb") as stream:
            block = b"x" * (1024 * 1024)
            for _ in range(15):
                stream.write(block)
    elif scenario_id == "f6":
        state["mode"] = "degraded"
        write_json(STATE_PATH, state)
    else:
        raise ValueError(f"unknown scenario: {scenario_id}")


def repair(scenario_id: str) -> None:
    if scenario_id == "f1":
        config = read_json(CONFIG_PATH)
        config["port"] = 8080
        write_json(CONFIG_PATH, config)
    elif scenario_id == "f2":
        STATE_PATH.chmod(0o640)
    elif scenario_id == "f3":
        start_dependency()
    elif scenario_id == "f4":
        config = read_json(CONFIG_PATH)
        config["db_port"] = 6379
        write_json(CONFIG_PATH, config)
    elif scenario_id == "f5":
        if FAULT_PATH.exists():
            FAULT_PATH.unlink()
    elif scenario_id == "f6":
        state = read_json(STATE_PATH)
        state["mode"] = "healthy"
        write_json(STATE_PATH, state)
    else:
        raise ValueError(f"unknown scenario: {scenario_id}")


def stop_dependency() -> None:
    if not DEPENDENCY_PID.is_file():
        return
    try:
        os.kill(int(DEPENDENCY_PID.read_text(encoding="utf-8").strip()), signal.SIGTERM)
    except (OSError, ValueError):
        pass


def start_dependency() -> None:
    if port_open():
        return
    process = subprocess.Popen(
        [sys.executable, "/opt/demo/dependency.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    DEPENDENCY_PID.write_text(str(process.pid), encoding="utf-8")
    for _ in range(30):
        if port_open():
            return
        time.sleep(0.05)
    raise RuntimeError("dependency did not start")


def port_open() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 6379), timeout=0.2):
            return True
    except OSError:
        return False


def http_status(path: str) -> int:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:8080{path}", timeout=2) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except OSError:
        return 0


def verify() -> int:
    checks = {
        "health": http_status("/health") == 200,
        "smoke": http_status("/api") == 200,
        "regression": http_status("/version") == 200,
    }
    print(json.dumps({"passed": all(checks.values()), "checks": checks}, sort_keys=True))
    return 0 if all(checks.values()) else 1


def pressure() -> int:
    successes = 0
    for _ in range(20):
        successes += int(http_status("/health") == 200)
    passed = successes >= 19
    print(json.dumps({"passed": passed, "successes": successes, "total": 20}, sort_keys=True))
    return 0 if passed else 1


def environment_hash() -> str:
    import hashlib

    state: dict[str, Any] = {
        "config_mode": oct(CONFIG_PATH.stat().st_mode & 0o777),
        "state_mode": oct(STATE_PATH.stat().st_mode & 0o777),
    }
    for name, path in (("config", CONFIG_PATH), ("state", STATE_PATH)):
        try:
            state[name] = path.read_text(encoding="utf-8")
        except PermissionError:
            state[name] = "<unreadable>"
    state["fault_file"] = FAULT_PATH.exists()
    state["dependency_port"] = port_open()
    payload = json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices={
            "initialize",
            "inject",
            "repair",
            "verify",
            "pressure",
            "hash",
            "wait",
        },
    )
    parser.add_argument("--scenario", default=os.getenv("SCENARIO_ID", "f1"))
    args = parser.parse_args()

    if args.command == "initialize":
        initialize(args.scenario)
    elif args.command == "inject":
        inject(args.scenario)
    elif args.command == "repair":
        repair(args.scenario)
    elif args.command == "verify":
        return verify()
    elif args.command == "pressure":
        return pressure()
    elif args.command == "hash":
        print(environment_hash())
    elif args.command == "wait":
        for _ in range(100):
            if http_status("/version") == 200:
                return 0
            time.sleep(0.05)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
