"""W05 FastAPI incident API integration tests."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aios_incident.api import create_app
from aios_incident.config import load_config

INCIDENT_PAYLOAD = {
    "objective": "诊断并修复 web-app 不可用问题",
    "target": {
        "host": "sandbox-01",
        "service": "web-app",
        "environment": "docker",
    },
    "allowed_scope": {
        "read_paths": ["/var/log", "/etc/web-app"],
        "write_paths": ["/etc/web-app"],
        "allowed_services": ["web-app", "postgresql"],
    },
    "time_budget_seconds": 600,
    "max_repair_attempts": 2,
    "success_criteria": [
        "health_endpoint_returns_200",
        "smoke_test_passes",
    ],
}


@pytest.fixture
def api_client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(load_config(), trace_root=tmp_path)
    with TestClient(app) as client:
        yield client


def create_incident(client: TestClient) -> dict[str, object]:
    response = client.post("/api/v1/incidents", json=INCIDENT_PAYLOAD)
    assert response.status_code == 201
    return response.json()


def test_create_query_dag_events_and_result(api_client: TestClient, tmp_path: Path) -> None:
    created = create_incident(api_client)
    incident_id = str(created["incident_id"])
    run_id = str(created["run_id"])

    assert created["state"] == "CREATED"
    assert incident_id.startswith("inc-")
    assert run_id.startswith("run-")

    status_response = api_client.get(f"/api/v1/incidents/{incident_id}")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["incident_id"] == incident_id
    assert status["run_id"] == run_id
    assert status["state"] == "CREATED"
    assert status["current_tasks"] == []
    assert status["completed_tasks"] == []
    assert status["repair_attempt"] == 0
    assert status["final_report"] is None

    dag_response = api_client.get(f"/api/v1/incidents/{incident_id}/dag")
    assert dag_response.status_code == 200
    assert dag_response.json()["incident_id"] == incident_id
    assert len(dag_response.json()["nodes"]) == 10

    events_response = api_client.get(f"/api/v1/incidents/{incident_id}/events")
    assert events_response.status_code == 200
    events = events_response.json()["events"]
    assert [item["event_type"] for item in events] == [
        "INCIDENT_CREATED",
        "DAG_INSTANTIATED",
    ]

    result_response = api_client.get(f"/api/v1/incidents/{incident_id}/result")
    assert result_response.status_code == 200
    assert result_response.json()["final_report"] is None

    trace_path = tmp_path / incident_id / f"{run_id}.jsonl"
    assert trace_path.exists()
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_type"] == "INCIDENT_CREATED"


def test_incident_ids_and_run_ids_are_unique(api_client: TestClient) -> None:
    first = create_incident(api_client)
    second = create_incident(api_client)

    assert first["incident_id"] != second["incident_id"]
    assert first["run_id"] != second["run_id"]


def test_cancel_transitions_state_and_appends_trace(api_client: TestClient) -> None:
    created = create_incident(api_client)
    incident_id = str(created["incident_id"])

    cancelled = api_client.post(f"/api/v1/incidents/{incident_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "CANCELLED"

    repeated = api_client.post(f"/api/v1/incidents/{incident_id}/cancel")
    assert repeated.status_code == 200
    assert repeated.json()["state"] == "CANCELLED"

    events = api_client.get(f"/api/v1/incidents/{incident_id}/events").json()["events"]
    assert [item["event_type"] for item in events] == [
        "INCIDENT_CREATED",
        "DAG_INSTANTIATED",
        "INCIDENT_CANCELLED",
    ]


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {**INCIDENT_PAYLOAD, "unexpected": True},
        {**INCIDENT_PAYLOAD, "max_repair_attempts": 3},
        {
            **INCIDENT_PAYLOAD,
            "allowed_scope": {
                "read_paths": ["relative/path"],
                "write_paths": [],
                "allowed_services": [],
            },
        },
    ],
)
def test_invalid_incident_request_returns_structured_error(
    api_client: TestClient,
    invalid_payload: dict[str, object],
) -> None:
    response = api_client.post("/api/v1/incidents", json=invalid_payload)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "INVALID_INCIDENT_REQUEST"
    assert error["message"] == "request validation failed"
    assert error["details"]


def test_unknown_incident_returns_structured_404(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/incidents/inc-does-not-exist")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "INCIDENT_NOT_FOUND",
            "message": "incident not found: inc-does-not-exist",
            "details": [],
        }
    }
