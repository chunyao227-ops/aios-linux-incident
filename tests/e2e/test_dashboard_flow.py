"""W14 dashboard, history persistence and observability tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from aios_incident.api import create_app
from aios_incident.config import load_config
from aios_incident.models import TraceEvent
from aios_incident.state import WorkflowStatus

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


def create_incident(client: TestClient) -> dict[str, object]:
    response = client.post("/api/v1/incidents", json=PAYLOAD)
    assert response.status_code == 201
    return response.json()


def append_replay_events(app: object, incident_id: str) -> None:
    service = app.state.incident_service
    record = service._get_record(incident_id)
    now = datetime.now(timezone.utc)
    events = (
        TraceEvent(
            trace_id=f"trace-{incident_id}-flow",
            incident_id=incident_id,
            task_id="N0",
            agent_id="CoordinatorAgent",
            event_type="MINIMAL_FLOW_STARTED",
            status="RUNNING",
            timestamp=now,
        ),
        TraceEvent(
            trace_id=f"trace-{incident_id}-message",
            incident_id=incident_id,
            task_id="N1",
            agent_id="log-agent-01",
            event_type="MESSAGE_SENT",
            status="DELIVERED",
            timestamp=now,
            details={
                "message_id": "msg-dashboard-001",
                "message_type": "QUESTION",
                "from_agent": "log-agent-01",
                "to_agent": "config-agent-01",
                "from_agent_type": "LogAgent",
                "to_agent_type": "ConfigAgent",
                "correlation_id": "corr-dashboard-001",
            },
        ),
        TraceEvent(
            trace_id=f"trace-{incident_id}-repair",
            incident_id=incident_id,
            task_id="N6.1",
            agent_id="repair-agent-01",
            event_type="REPAIR_FINISHED",
            status="SUCCEEDED",
            timestamp=now,
            duration_ms=150,
        ),
        TraceEvent(
            trace_id=f"trace-{incident_id}-verify",
            incident_id=incident_id,
            task_id="N7.1",
            agent_id="verifier-agent-01",
            event_type="VERIFICATION_FINISHED",
            status="SUCCEEDED",
            timestamp=now,
            duration_ms=100,
        ),
    )
    for event in events:
        record.trace.append(event)
    record.context = record.context.model_copy(update={"workflow_status": WorkflowStatus.SUCCESS})
    record.repair_attempt = 1
    record.final_report = {
        "incident_id": incident_id,
        "final_status": "SUCCESS",
        "source": "dashboard-e2e",
    }
    service._persist_record(record)


def test_dashboard_assets_and_real_benchmark_data(tmp_path: Path) -> None:
    app = create_app(load_config(), trace_root=tmp_path)
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert 'id="dag-grid"' in page.text
        assert 'id="benchmark-rows"' in page.text

        script = client.get("/ui-assets/app.js")
        assert script.status_code == 200
        assert "/api/v1/incidents" in script.text
        assert "/api/v1/benchmarks/latest" in script.text

        benchmark = client.get("/api/v1/benchmarks/latest")
        assert benchmark.status_code == 200
        assert benchmark.json()["available"] is True
        assert benchmark.json()["summary"]["average_speedup"] > 0.2


def test_history_and_full_replay_survive_new_app_instance(tmp_path: Path) -> None:
    app = create_app(load_config(), trace_root=tmp_path)
    with TestClient(app) as client:
        created = create_incident(client)
        incident_id = str(created["incident_id"])
        append_replay_events(app, incident_id)

    restarted_app = create_app(load_config(), trace_root=tmp_path)
    with TestClient(restarted_app) as client:
        history = client.get("/api/v1/incidents")
        assert history.status_code == 200
        assert history.json()["incidents"][0]["incident_id"] == incident_id

        status = client.get(f"/api/v1/incidents/{incident_id}").json()
        assert status["state"] == "SUCCESS"
        assert status["repair_attempt"] == 1

        dag = client.get(f"/api/v1/incidents/{incident_id}/dag").json()
        assert len(dag["nodes"]) == 10

        events = client.get(f"/api/v1/incidents/{incident_id}/events").json()["events"]
        event_types = [event["event_type"] for event in events]
        assert "MINIMAL_FLOW_STARTED" in event_types
        assert "MESSAGE_SENT" in event_types
        assert "REPAIR_FINISHED" in event_types
        assert "VERIFICATION_FINISHED" in event_types

        result = client.get(f"/api/v1/incidents/{incident_id}/result").json()
        assert result["final_report"]["final_status"] == "SUCCESS"


def test_cancel_updates_state_and_history(tmp_path: Path) -> None:
    app = create_app(load_config(), trace_root=tmp_path)
    with TestClient(app) as client:
        created = create_incident(client)
        incident_id = str(created["incident_id"])
        cancelled = client.post(f"/api/v1/incidents/{incident_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["state"] == "CANCELLED"

        history = client.get("/api/v1/incidents").json()["incidents"]
        item = next(item for item in history if item["incident_id"] == incident_id)
        assert item["state"] == "CANCELLED"
