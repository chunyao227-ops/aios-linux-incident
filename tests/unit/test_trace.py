"""W05 append-only JSONL trace tests."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios_incident.exceptions import TraceStoreError
from aios_incident.models import TraceEvent
from aios_incident.orchestrator.trace import JsonlTraceStore

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def event(
    trace_id: str,
    *,
    incident_id: str = "inc-001",
    event_type: str = "TASK_FINISHED",
) -> TraceEvent:
    return TraceEvent(
        trace_id=trace_id,
        incident_id=incident_id,
        task_id="N1",
        agent_id="log-agent-01",
        event_type=event_type,
        status="SUCCEEDED",
        timestamp=NOW,
        duration_ms=120,
    )


def test_trace_is_appended_and_read_back(tmp_path: Path) -> None:
    trace = JsonlTraceStore(tmp_path, "inc-001", "run-001")
    first = event("trace-001")
    second = event("trace-002")
    trace.append(first)
    trace.append(second)

    assert trace.read_events() == (first, second)
    assert trace.path == (tmp_path / "inc-001" / "run-001.jsonl").resolve()
    lines = trace.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["trace_id"] == "trace-001"


def test_duplicate_trace_id_is_rejected_without_overwriting(tmp_path: Path) -> None:
    trace = JsonlTraceStore(tmp_path, "inc-001", "run-001")
    trace.append(event("trace-001"))

    with pytest.raises(TraceStoreError, match="already exists"):
        trace.append(event("trace-001", event_type="REPLACEMENT"))
    assert [item.event_type for item in trace.read_events()] == ["TASK_FINISHED"]


def test_existing_trace_ids_are_loaded_for_restart_safety(tmp_path: Path) -> None:
    first_store = JsonlTraceStore(tmp_path, "inc-001", "run-001")
    first_store.append(event("trace-001"))

    restarted = JsonlTraceStore(tmp_path, "inc-001", "run-001")
    with pytest.raises(TraceStoreError, match="already exists"):
        restarted.append(event("trace-001"))


def test_trace_rejects_wrong_incident(tmp_path: Path) -> None:
    trace = JsonlTraceStore(tmp_path, "inc-001", "run-001")
    with pytest.raises(TraceStoreError, match="incident mismatch"):
        trace.append(event("trace-001", incident_id="inc-002"))


@pytest.mark.parametrize(
    ("incident_id", "run_id"),
    [
        ("../incident", "run-001"),
        ("inc-001", "../run"),
        ("", "run-001"),
        ("inc 001", "run-001"),
    ],
)
def test_trace_rejects_unsafe_path_components(
    tmp_path: Path,
    incident_id: str,
    run_id: str,
) -> None:
    with pytest.raises(TraceStoreError, match="unsafe path characters"):
        JsonlTraceStore(tmp_path, incident_id, run_id)


def test_missing_trace_file_reads_as_empty(tmp_path: Path) -> None:
    trace = JsonlTraceStore(tmp_path, "inc-001", "run-empty")
    assert trace.read_events() == ()


def test_malformed_existing_trace_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "inc-001" / "run-001.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("{invalid-json}\n", encoding="utf-8")

    with pytest.raises(TraceStoreError, match="invalid existing trace"):
        JsonlTraceStore(tmp_path, "inc-001", "run-001")
