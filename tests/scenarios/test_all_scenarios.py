"""W12 Docker scenario lifecycle tests."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from aios_incident.agents.coordinator_agent import CoordinatorAgent
from aios_incident.models import (
    AllowedScope,
    Evidence,
    EvidenceKind,
    IncidentTarget,
    RepairResult,
    RepairStatus,
    RunContext,
    VerificationCheck,
    VerificationResult,
)
from aios_incident.orchestrator.interaction_bus import InteractionBus
from aios_incident.orchestrator.planner import build_default_agent_cards
from aios_incident.orchestrator.trace import JsonlTraceStore

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DOCKER_SCENARIOS") != "1",
    reason="set RUN_DOCKER_SCENARIOS=1 to execute Docker scenarios",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_IDS = ("f1", "f2", "f3", "f4", "f5", "f6")
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    remainder = str(resolved)[len(resolved.drive) :].replace("\\", "/")
    return f"/mnt/{drive}{remainder}"


def run_script(script: Path, *, expected_status: int = 0) -> subprocess.CompletedProcess[str]:
    if os.name == "nt":
        command = ["wsl", "-d", "Ubuntu-22.04", "bash", wsl_path(script)]
    else:
        command = ["bash", str(script)]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == expected_status, (
        f"{script} returned {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    return result


def scenario_script(scenario_id: str, name: str) -> Path:
    return PROJECT_ROOT / "scenarios" / scenario_id / f"{name}.sh"


def scenario_manifest(scenario_id: str) -> dict[str, object]:
    path = PROJECT_ROOT / "scenarios" / scenario_id / "scenario.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def assert_three_interaction_pairs(
    scenario_id: str,
    tmp_path: Path,
) -> None:
    incident_id = f"inc-{scenario_id}"
    run_id = f"run-{scenario_id}"
    trace = JsonlTraceStore(tmp_path / "interactions", incident_id, run_id)
    bus = InteractionBus(incident_id, trace)
    for card in build_default_agent_cards():
        bus.register_agent(card.agent_id, card.agent_type)
    context = RunContext(
        run_id=run_id,
        incident_id=incident_id,
        objective=f"validate interactions for {scenario_id}",
        target=IncidentTarget(host="sandbox-01", service="web-app", environment="docker"),
        allowed_scope=AllowedScope(),
        time_budget_seconds=600,
        max_repair_attempts=2,
        success_criteria=("health_endpoint",),
    )
    evidence = (
        Evidence(
            evidence_id=f"evi-{scenario_id}-log",
            incident_id=incident_id,
            task_id="N1",
            producer_agent="LogAgent",
            kind=EvidenceKind.LOG,
            summary=f"{scenario_id} log evidence",
            source_ref=f"/var/log/web-app/{scenario_id}.log",
            observed_at=NOW,
            facts={"last_line": f"{scenario_id} service failure"},
            confidence=0.9,
        ),
        Evidence(
            evidence_id=f"evi-{scenario_id}-metrics",
            incident_id=incident_id,
            task_id="N2",
            producer_agent="MetricsAgent",
            kind=EvidenceKind.METRICS,
            summary=f"{scenario_id} metrics evidence",
            source_ref="/proc",
            observed_at=NOW,
            facts={"service": "web-app"},
            confidence=0.9,
        ),
        Evidence(
            evidence_id=f"evi-{scenario_id}-config",
            incident_id=incident_id,
            task_id="N3",
            producer_agent="ConfigAgent",
            kind=EvidenceKind.CONFIG,
            summary=f"{scenario_id} config evidence",
            source_ref="/etc/web-app/config.json",
            observed_at=NOW,
            facts={"scenario_id": scenario_id},
            confidence=0.9,
        ),
        Evidence(
            evidence_id=f"evi-{scenario_id}-dependency",
            incident_id=incident_id,
            task_id="N4",
            producer_agent="DependencyAgent",
            kind=EvidenceKind.DEPENDENCY,
            summary=f"{scenario_id} dependency evidence",
            source_ref="/proc",
            observed_at=NOW,
            facts={"service": "web-app", "processes": [], "ports": []},
            confidence=0.9,
        ),
    )
    repair_result = RepairResult(
        repair_id=f"repair-{scenario_id}",
        incident_id=incident_id,
        status=RepairStatus.SUCCEEDED,
        started_at=NOW,
        ended_at=NOW,
    )
    verification_result = VerificationResult(
        verification_id=f"verify-{scenario_id}",
        incident_id=incident_id,
        repair_id=repair_result.repair_id,
        passed=True,
        checks=(VerificationCheck(name="health_endpoint", passed=True),),
        started_at=NOW,
        ended_at=NOW,
    )
    graph = CoordinatorAgent().coordinate_required_interactions(
        context,
        bus,
        log_evidence=evidence[0],
        config_evidence=evidence[2],
        metrics_evidence=evidence[1],
        dependency_evidence=evidence[3],
        repair_result=repair_result,
        verification_result=verification_result,
    )
    assert graph.bidirectional_edge_count == 3
    assert len(graph.bidirectional_pairs) == 3


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_failure_success_and_reset_hash(
    scenario_id: str,
    tmp_path: Path,
) -> None:
    manifest = scenario_manifest(scenario_id)
    assert manifest["required_interactions"] == [
        "LogAgent<->ConfigAgent",
        "MetricsAgent<->DependencyAgent",
        "RepairAgent<->VerifierAgent",
    ]

    run_script(scenario_script(scenario_id, "destroy"))
    try:
        run_script(scenario_script(scenario_id, "start"))
        initial_hash = run_script(scenario_script(scenario_id, "hash")).stdout.strip()
        run_script(scenario_script(scenario_id, "verify"))

        run_script(scenario_script(scenario_id, "inject"))
        run_script(scenario_script(scenario_id, "verify"), expected_status=1)

        run_script(scenario_script(scenario_id, "repair"))
        run_script(scenario_script(scenario_id, "verify"))
        run_script(scenario_script(scenario_id, "pressure"))

        run_script(scenario_script(scenario_id, "reset"))
        reset_hash = run_script(scenario_script(scenario_id, "hash")).stdout.strip()
        assert reset_hash == initial_hash
        assert len(reset_hash) == 64

        assert_three_interaction_pairs(scenario_id, tmp_path)
    finally:
        run_script(scenario_script(scenario_id, "destroy"))
