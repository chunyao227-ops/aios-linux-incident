"""Capture the six Docker scenario lifecycle results without scenario answers."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "docs" / "submission" / "evidence" / "scenarios"
SCENARIO_IDS = ("f1", "f2", "f3", "f4", "f5", "f6")
FONT = "Segoe UI, Microsoft YaHei, sans-serif"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    remainder = str(resolved)[len(resolved.drive) :].replace("\\", "/")
    return f"/mnt/{drive}{remainder}"


def run_script(
    scenario_id: str,
    action: str,
    *,
    expected_status: int = 0,
) -> dict[str, Any]:
    script = ROOT / "scenarios" / scenario_id / f"{action}.sh"
    started = time.perf_counter()
    result = subprocess.run(
        ["wsl", "-d", "Ubuntu-22.04", "bash", wsl_path(script)],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=120,
        check=False,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    if result.returncode != expected_status:
        raise RuntimeError(
            f"{scenario_id}/{action} returned {result.returncode}; "
            f"stderr={result.stderr[-1000:]}"
        )
    return {
        "action": action,
        "return_code": result.returncode,
        "expected_return_code": expected_status,
        "passed": result.returncode == expected_status,
        "duration_ms": elapsed_ms,
        "stdout_sha256": hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
    }


def capture_scenario(scenario_id: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    checks: dict[str, bool] = {}
    try:
        steps.append(run_script(scenario_id, "destroy"))
        steps.append(run_script(scenario_id, "start"))
        initial_hash = subprocess.run(
            [
                "wsl",
                "-d",
                "Ubuntu-22.04",
                "bash",
                wsl_path(ROOT / "scenarios" / scenario_id / "hash.sh"),
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=120,
            check=False,
        )
        if initial_hash.returncode != 0:
            raise RuntimeError(f"{scenario_id}/hash failed")
        initial_hash_value = initial_hash.stdout.strip()
        baseline_verify = run_script(scenario_id, "verify")
        steps.append(baseline_verify)
        checks["baseline_healthy"] = baseline_verify["passed"]
        steps.append(run_script(scenario_id, "inject"))
        fault_verify = run_script(scenario_id, "verify", expected_status=1)
        steps.append(fault_verify)
        checks["fault_rejected"] = fault_verify["passed"]
        steps.append(run_script(scenario_id, "repair"))
        repaired_verify = run_script(scenario_id, "verify")
        steps.append(repaired_verify)
        checks["repaired_healthy"] = repaired_verify["passed"]
        pressure = run_script(scenario_id, "pressure")
        steps.append(pressure)
        checks["pressure_passed"] = pressure["passed"]
        steps.append(run_script(scenario_id, "reset"))
        reset_hash = subprocess.run(
            [
                "wsl",
                "-d",
                "Ubuntu-22.04",
                "bash",
                wsl_path(ROOT / "scenarios" / scenario_id / "hash.sh"),
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=120,
            check=False,
        )
        if reset_hash.returncode != 0:
            raise RuntimeError(f"{scenario_id}/hash after reset failed")
        reset_hash_value = reset_hash.stdout.strip()
        hash_match = initial_hash_value == reset_hash_value
        checks["hash_match"] = hash_match
        if not hash_match:
            raise RuntimeError(f"{scenario_id} reset hash mismatch")
        return {
            "scenario_id": scenario_id,
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "initial_hash": initial_hash_value,
            "reset_hash": reset_hash_value,
            "hash_match": hash_match,
            "steps": steps,
        }
    finally:
        destroy = run_script(scenario_id, "destroy")
        steps.append(destroy)


def render_summary(results: list[dict[str, Any]]) -> None:
    parts = [
        f'<text x="38" y="38" font-family="{FONT}" font-size="24" '
        'font-weight="700" fill="#142433">W12 六场景生命周期证据</text>',
        f'<text x="38" y="62" font-family="{FONT}" font-size="13" '
        'fill="#657887">基线验证、故障失败、修复验证、压力、重置哈希和销毁</text>',
        f'<text x="38" y="102" font-family="{FONT}" font-size="13" '
        f'fill="#31546d">场景总数 {len(results)} · 通过 '
        f'{sum(item["status"] == "PASS" for item in results)}</text>',
    ]
    headers = ("场景", "基线", "故障", "修复", "压力", "哈希", "销毁")
    header_positions = (55, 250, 390, 530, 670, 810, 960)
    for header, x in zip(headers, header_positions, strict=True):
        parts.append(
            f'<text x="{x}" y="145" font-family="{FONT}" font-size="13" '
            f'font-weight="700" fill="#657887">{header}</text>'
        )
    for index, result in enumerate(results):
        y = 180 + index * 62
        checks = result["checks"]
        cells = (
            result["scenario_id"].upper(),
            "PASS" if checks["baseline_healthy"] else "FAIL",
            "EXPECTED FAIL" if checks["fault_rejected"] else "FAIL",
            "PASS" if checks["repaired_healthy"] else "FAIL",
            "PASS" if checks["pressure_passed"] else "FAIL",
            "PASS" if checks["hash_match"] else "FAIL",
            "PASS",
        )
        parts.append(
            f'<rect x="38" y="{y - 25}" width="980" height="44" rx="7" '
            f'fill="{"#ffffff" if index % 2 == 0 else "#eef3f5"}" '
            'stroke="#d9e1e6"/>'
        )
        for cell, x in zip(cells, header_positions, strict=True):
            color = "#b54b4b" if cell == "FAIL" else "#175f70"
            if cell == "EXPECTED FAIL":
                color = "#657887"
            parts.append(
                f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="13" '
                f'font-weight="{700 if x == 55 else 500}" fill="{color}">'
                f"{html_escape(str(cell))}</text>"
            )
    body = "".join(parts)
    content = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1060" height="580" '
        'viewBox="0 0 1060 580">'
        '<rect width="100%" height="100%" fill="#f5f7f9"/>'
        f"{body}</svg>\n"
    )
    (OUTPUT_DIR / "W12_scenario_matrix.svg").write_text(
        content,
        encoding="utf-8",
        newline="\n",
    )


def html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for scenario_id in SCENARIO_IDS:
        result = capture_scenario(scenario_id)
        results.append(result)
        (OUTPUT_DIR / f"W12_{scenario_id}_lifecycle.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"{scenario_id}: {result['status']}")
    (OUTPUT_DIR / "W12_lifecycle_summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    render_summary(results)
    print("captured six Docker scenario lifecycles")


if __name__ == "__main__":
    main()
