"""W10 evidence fusion and diagnosis tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_incident.exceptions import DiagnosticEvidenceError
from aios_incident.models import (
    AllowedScope,
    Evidence,
    EvidenceKind,
    IncidentTarget,
    Message,
    MessageType,
    RunContext,
)
from aios_incident.orchestrator.diagnosis import DiagnosisFusionEngine

T0 = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
INCIDENT_ID = "inc-w10"


def context() -> RunContext:
    return RunContext(
        run_id="run-w10",
        incident_id=INCIDENT_ID,
        objective="fuse evidence",
        target=IncidentTarget(
            host="sandbox-01",
            service="web-app",
            environment="docker",
        ),
        allowed_scope=AllowedScope(
            read_paths=("/var/log", "/etc/web-app"),
            allowed_services=("web-app",),
        ),
        time_budget_seconds=600,
        max_repair_attempts=2,
        success_criteria=("health_endpoint",),
    )


def evidence(
    *,
    evidence_id: str,
    kind: EvidenceKind,
    producer: str,
    facts: dict[str, object],
    minute: int = 0,
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        incident_id=INCIDENT_ID,
        task_id=f"N{minute + 1}",
        producer_agent=producer,
        kind=kind,
        summary=f"{kind.value} evidence",
        source_ref=f"source/{evidence_id}",
        observed_at=T0 + timedelta(minutes=minute),
        facts=facts,
        confidence=0.9,
    )


def four_evidence() -> tuple[Evidence, ...]:
    return (
        evidence(
            evidence_id="evi-log",
            kind=EvidenceKind.LOG,
            producer="LogAgent",
            facts={
                "last_line": "database connection refused",
                "service": "web-app",
                "service_state": "stopped",
            },
            minute=3,
        ),
        evidence(
            evidence_id="evi-metrics",
            kind=EvidenceKind.METRICS,
            producer="MetricsAgent",
            facts={
                "load_average": {"one_minute": 0.5},
                "memory_kib": {"MemAvailable": 2048 * 1024},
                "service": "web-app",
            },
            minute=1,
        ),
        evidence(
            evidence_id="evi-config",
            kind=EvidenceKind.CONFIG,
            producer="ConfigAgent",
            facts={"content": "port: 8080", "truncated": False},
            minute=0,
        ),
        evidence(
            evidence_id="evi-dependency",
            kind=EvidenceKind.DEPENDENCY,
            producer="DependencyAgent",
            facts={"processes": [], "ports": [], "service": "web-app"},
            minute=2,
        ),
    )


def message(*, evidence_id: str) -> Message:
    return Message(
        message_id="msg-w10",
        incident_id=INCIDENT_ID,
        task_id="N1",
        from_agent="log-agent-01",
        to_agent="config-agent-01",
        type=MessageType.QUESTION,
        content="verify evidence",
        evidence_ids=(evidence_id,),
        correlation_id="corr-w10",
        timestamp=T0,
    )


def test_four_evidence_classes_fuse_into_supported_root_cause() -> None:
    engine = DiagnosisFusionEngine()
    result = engine.fuse(context(), four_evidence(), (message(evidence_id="evi-log"),))

    assert result.status == "READY"
    assert result.diagnosis.selected_root_cause_ids
    assert len(result.evidence_chain) == 4
    assert [entry.evidence_id for entry in result.evidence_chain] == [
        "evi-config",
        "evi-metrics",
        "evi-dependency",
        "evi-log",
    ]
    valid_ids = {item.evidence_id for item in four_evidence()}
    for root_cause in result.diagnosis.root_causes:
        assert root_cause.supporting_evidence
        assert set(root_cause.supporting_evidence) <= valid_ids
    assert result.evidence_chain[-1].linked_message_ids == ("msg-w10",)
    assert result.interaction_message_ids == ("msg-w10",)
    assert result.follow_up_requests == ()


def test_identical_facts_are_deduplicated_across_sources() -> None:
    result = DiagnosisFusionEngine().fuse(context(), four_evidence())
    service_facts = [fact for fact in result.merged_facts if fact.fact_key == "service"]
    assert len(service_facts) == 1
    assert set(service_facts[0].evidence_ids) == {
        "evi-log",
        "evi-metrics",
        "evi-dependency",
    }
    assert set(service_facts[0].source_kinds) == {
        EvidenceKind.LOG,
        EvidenceKind.METRICS,
        EvidenceKind.DEPENDENCY,
    }


def test_conflicting_fact_blocks_repair_and_requests_follow_up() -> None:
    items = list(four_evidence())
    items[3] = evidence(
        evidence_id="evi-dependency",
        kind=EvidenceKind.DEPENDENCY,
        producer="DependencyAgent",
        facts={
            "processes": [{"pid": 42}],
            "ports": [{"port": 8080}],
            "service": "web-app",
            "service_state": "running",
        },
        minute=2,
    )

    result = DiagnosisFusionEngine().fuse(context(), tuple(items))

    assert result.status == "BLOCKED"
    assert result.diagnosis.selected_root_cause_ids == ()
    assert any(conflict.fact_key == "service_state" for conflict in result.conflicts)
    assert result.follow_up_requests
    assert result.diagnosis.conflicting_evidence
    assert "repair_blocked_until_conflicts_resolved" in result.diagnosis.repair_constraints


@pytest.mark.parametrize(
    ("items", "message_pattern"),
    [
        ((), "at least four"),
        (four_evidence()[:3], "missing evidence kinds"),
        (
            four_evidence() + (four_evidence()[0],),
            "evidence IDs must be unique",
        ),
    ],
)
def test_missing_or_duplicate_evidence_fails_closed(
    items: tuple[Evidence, ...],
    message_pattern: str,
) -> None:
    with pytest.raises(DiagnosticEvidenceError, match=message_pattern):
        DiagnosisFusionEngine().fuse(context(), items)


def test_message_with_unknown_evidence_reference_fails_closed() -> None:
    with pytest.raises(DiagnosticEvidenceError, match="unknown evidence"):
        DiagnosisFusionEngine().fuse(
            context(),
            four_evidence(),
            (message(evidence_id="evi-missing"),),
        )


def test_candidate_evidence_references_are_always_valid() -> None:
    items = four_evidence()
    result = DiagnosisFusionEngine().fuse(context(), items)
    evidence_ids = {item.evidence_id for item in items}
    referenced = {
        evidence_id
        for root_cause in result.diagnosis.root_causes
        for evidence_id in root_cause.supporting_evidence
    }
    assert referenced
    assert referenced <= evidence_ids
