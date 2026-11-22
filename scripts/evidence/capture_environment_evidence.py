"""Capture a sanitized local runtime snapshot for submission evidence."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "docs" / "submission" / "evidence" / "environment"


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


def command(*args: str) -> dict[str, Any]:
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return {
        "command": list(args),
        "return_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def get_json(url: str) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=5) as response:
            return {
                "url": url,
                "status": response.status,
                "body": json.loads(response.read().decode("utf-8")),
            }
    except (OSError, URLError, json.JSONDecodeError) as exc:
        return {
            "url": url,
            "status": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config_paths = (
        ROOT / "config" / "app.example.yaml",
        ROOT / "config" / "aios.kernel.local.yaml",
        ROOT / "config" / "model.local.yaml",
        ROOT / "config" / "model.remote.yaml.example",
    )
    docker = command(
        "wsl",
        "-d",
        "Ubuntu-22.04",
        "--",
        "docker",
        "info",
        "--format",
        "{{json .}}",
    )
    docker_summary: dict[str, Any] = {}
    if docker["return_code"] == 0:
        try:
            payload = json.loads(docker["stdout"])
            docker_summary = {
                key: payload.get(key)
                for key in (
                    "ServerVersion",
                    "OperatingSystem",
                    "Driver",
                    "CgroupDriver",
                    "NCPU",
                    "MemTotal",
                )
            }
        except json.JSONDecodeError:
            docker_summary = {"raw": docker["stdout"]}

    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": command("git", "rev-parse", "HEAD")["stdout"],
        "host": {
            "platform": platform.platform(),
            "python": sys.version,
            "python_executable": str(Path(sys.executable).relative_to(ROOT))
            if Path(sys.executable).is_relative_to(ROOT)
            else "<EXTERNAL_PYTHON>",
        },
        "wsl": command("wsl", "-d", "Ubuntu-22.04", "--", "bash", "-lc", "uname -a"),
        "api": get_json("http://127.0.0.1:8080/openapi.json"),
        "aios": get_json("http://127.0.0.1:8000/status"),
        "aios_core": get_json("http://127.0.0.1:8000/core/status"),
        "ollama": get_json("http://127.0.0.1:11434/api/version"),
        "ollama_models": get_json("http://127.0.0.1:11434/api/tags"),
        "docker": {
            "probe": docker,
            "summary": docker_summary,
        },
        "config_sha256": {
            str(path.relative_to(ROOT)): sha256(path)
            for path in config_paths
            if path.exists()
        },
    }
    (OUTPUT_DIR / "local_runtime_snapshot.json").write_text(
        json.dumps(sanitize(snapshot), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# 本地运行时环境快照",
        "",
        f"- 采集时间：{snapshot['captured_at']}",
        f"- Git 提交：`{snapshot['git_commit']}`",
        f"- 平台：`{snapshot['host']['platform']}`",
        f"- Python：`{snapshot['host']['python'].splitlines()[0]}`",
        f"- AIOS：`{snapshot['aios'].get('body', {}).get('status', 'unavailable')}`",
        f"- Ollama：`{snapshot['ollama'].get('body', {}).get('version', 'unavailable')}`",
        f"- Docker：`{docker_summary.get('ServerVersion', 'unavailable')}`",
        "",
        "完整探测结果和配置文件 SHA-256 见 `local_runtime_snapshot.json`。",
        "",
        "本快照不包含账号、密码、API Key 或 SSH 私钥。",
        "",
    ]
    (OUTPUT_DIR / "local_runtime_snapshot.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
        newline="\n",
    )
    print("local environment snapshot captured")


if __name__ == "__main__":
    main()
