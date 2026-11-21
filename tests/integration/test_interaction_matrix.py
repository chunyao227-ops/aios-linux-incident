"""W09 message bus and fixed bidirectional interaction matrix tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios_incident.agents.coordinator_agent import CoordinatorAgent
from aios_incident.exceptions import (
    InteractionParticipantUnavailableError,
    InteractionResponseTimeoutError,
)
from aios_incident.models import (
    AllowedScope,
    Evidence,
    EvidenceKind,
    IncidentTarget,
    Message,
    MessageType,
    RepairResult,
    RepairStatus,
    RunContext,
    VerificationCheck,
    VerificationResult,
)
from aios_incident.orchestrator.blackboard import ArtifactKind, Blackboard
from aios_incident.orchestrator.interaction_bus import InteractionBus
from aios_incident.orchestrator.planner import build_default_agent_cards
from aios_incident.orchestrator.trace import JsonlTraceStore

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
INCIDENT_ID = "inc-w09"


def evidence(
    *,
    evidence_id: str,
    producer: str,
    kind: EvidenceKind,
    summary: str,
    facts: dict[str, object],
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        incident_id=INCIDENT_ID,
        task_id="N1",
        producer_agent=producer,
        kind=kind,
        summary=summary,
        source_ref=f"source/{evidence_id}",
        observed_at=NOW,
        facts=facts,
        confidence=0.9,
    )


def repair_result() -> RepairResult:
    return RepairResult(
        repair_id="repair-001",
        incident_id=INCIDENT_ID,
        status=RepairStatus.SUCCEEDED,
        started_at=NOW,
        ended_at=NOW,
    )


def verification_result(*, passed: bool = True) -> VerificationResult:
    return VerificationResult(
        verification_id="verify-001",
        incident_id=INCIDENT_ID,
        repair_id="repair-001",
        passed=passed,
        checks=(VerificationCheck(name="health_endpoint", passed=passed),),
        failure_reasons=() if passed else ("health_endpoint: returned 503",),
        started_at=NOW,
        ended_at=NOW,
    )


def context_and_bus(tmp_path: Path) -> tuple[RunContext, InteractionBus, Blackboard]:
    context = RunContext(
        run_id="run-w09",
        incident_id=INCIDENT_ID,
        objective="coordinate evidence",
        target=IncidentTarget(
            host="sandbox-01",
            service="web-app",
            environment="docker",
        ),
        allowed_scope=AllowedScope(),
        time_budget_seconds=600,
        max_repair_attempts=2,
        success_criteria=("health_endpoint",),
    )
    trace = JsonlTraceStore(tmp_path / "traces", INCIDENT_ID, context.run_id)
    blackboard = Blackboard()
    bus = InteractionBus(INCIDENT_ID, trace, blackboard)
    for card in build_default_agent_cards():
        bus.register_agent(card.agent_id, card.agent_type)
    return context, bus, blackboard


def test_fixed_three_pairs_have_bidirectional_messages(tmp_path: Path) -> None:
    context, bus, blackboard = context_and_bus(tmp_path)
    graph = CoordinatorAgent().coordinate_required_interactions(
        context,
        bus,
        log_evidence=evidence(
            evidence_id="evi-log",
            producer="LogAgent",
            kind=EvidenceKind.LOG,
            summary="database connection refused",
            facts={"last_line": "database connection refused"},
        ),
        config_evidence=evidence(
            evidence_id="evi-config",
            producer="ConfigAgent",
            kind=EvidenceKind.CONFIG,
            summary="configuration read",
            facts={"sha256": "a" * 64, "content": "port: 8080"},
        ),
        metrics_evidence=evidence(
            evidence_id="evi-metrics",
            producer="MetricsAgent",
            kind=EvidenceKind.METRICS,
            summary="load increased",
            facts={"load_average": {"one_minute": 1.2}, "memory_kib": {"MemFree": 100}},
        ),
        dependency_evidence=evidence(
            evidence_id="evi-dependency",
            producer="DependencyAgent",
            kind=EvidenceKind.DEPENDENCY,
            summary="web-app process missing",
            facts={"processes": [{"pid": 12}], "ports": [{"port": 8080}]},
        ),
        repair_result=repair_result(),
        verification_result=verification_result(),
    )

    assert graph.message_count == 11
    assert graph.bidirectional_edge_count == 3
    assert set(graph.bidirectional_pairs) == {
        "ConfigAgent<->LogAgent",
        "DependencyAgent<->MetricsAgent",
        "RepairAgent<->VerifierAgent",
    }
    messages = bus.messages()
    assert all(message.from_agent != message.to_agent for message in messages)
    assert all(message.correlation_id for message in messages)

    queries = [
        message for message in messages if message.type in {MessageType.QUESTION, MessageType.QUERY}
    ]
    replies = {
        message.reply_to: message
        for message in messages
        if message.type in {MessageType.REPLY, MessageType.RESPONSE}
    }
    assert len(queries) == 4
    assert all(queries[index].message_id in replies for index in range(len(queries)))
    assert all(
        replies[query.message_id].correlation_id == query.correlation_id for query in queries
    )

    trace_events = bus.trace.read_events()
    sent_events = [event for event in trace_events if event.event_type == "MESSAGE_SENT"]
    received_events = [event for event in trace_events if event.event_type == "MESSAGE_RECEIVED"]
    assert len(sent_events) == 11
    assert len(received_events) == 11
    assert all(event.details.get("correlation_id") for event in sent_events)
    message_artifacts = blackboard.list_ready(INCIDENT_ID, kind=ArtifactKind.MESSAGE)
    assert len(message_artifacts) == 11


def test_failed_verification_returns_feedback_to_repair(tmp_path: Path) -> None:
    context, bus, _ = context_and_bus(tmp_path)
    graph = CoordinatorAgent().coordinate_required_interactions(
        context,
        bus,
        log_evidence=evidence(
            evidence_id="evi-log",
            producer="LogAgent",
            kind=EvidenceKind.LOG,
            summary="log",
            facts={},
        ),
        config_evidence=evidence(
            evidence_id="evi-config",
            producer="ConfigAgent",
            kind=EvidenceKind.CONFIG,
            summary="config",
            facts={},
        ),
        metrics_evidence=evidence(
            evidence_id="evi-metrics",
            producer="MetricsAgent",
            kind=EvidenceKind.METRICS,
            summary="metrics",
            facts={},
        ),
        dependency_evidence=evidence(
            evidence_id="evi-dependency",
            producer="DependencyAgent",
            kind=EvidenceKind.DEPENDENCY,
            summary="dependency",
            facts={},
        ),
        repair_result=repair_result(),
        verification_result=verification_result(passed=False),
    )

    assert graph.bidirectional_edge_count == 3
    feedback = [message for message in bus.messages() if message.type is MessageType.FEEDBACK]
    assert len(feedback) == 1
    assert feedback[0].from_agent == "verifier-agent-01"
    assert feedback[0].to_agent == "repair-agent-01"


def test_query_response_types_and_wait(tmp_path: Path) -> None:
    _, bus, _ = context_and_bus(tmp_path)
    question = bus.send_question(
        incident_id=INCIDENT_ID,
        task_id="N1",
        from_agent="metrics-agent-01",
        to_agent="dependency-agent-01",
        content="query dependency state",
        message_type=MessageType.QUERY,
    )
    reply = bus.send_reply(
        question,
        from_agent="dependency-agent-01",
        content="dependency state returned",
        message_type=MessageType.RESPONSE,
    )
    response = bus.wait_for_response(question.correlation_id, timeout_seconds=1)
    assert response == reply


def test_query_timeout_is_explicit_and_traced(tmp_path: Path) -> None:
    _, bus, _ = context_and_bus(tmp_path)
    question = bus.send_question(
        incident_id=INCIDENT_ID,
        task_id="N1",
        from_agent="log-agent-01",
        to_agent="config-agent-01",
        content="query without response",
    )
    with pytest.raises(InteractionResponseTimeoutError):
        bus.wait_for_response(question.correlation_id, timeout_seconds=0.001)

    timeout_event = bus.trace.read_events()[-1]
    assert timeout_event.event_type == "MESSAGE_RESPONSE_TIMEOUT"
    assert timeout_event.status == "TIMEOUT"


def test_disconnected_agent_send_failure_is_traced(tmp_path: Path) -> None:
    _, bus, _ = context_and_bus(tmp_path)
    bus.disconnect_agent("config-agent-01")
    message = Message(
        message_id="msg-offline",
        incident_id=INCIDENT_ID,
        task_id="N1",
        from_agent="log-agent-01",
        to_agent="config-agent-01",
        type=MessageType.QUESTION,
        content="cannot be delivered",
        correlation_id="corr-offline",
        timestamp=NOW,
    )
    with pytest.raises(InteractionParticipantUnavailableError):
        bus.send(message)

    failed_event = bus.trace.read_events()[-1]
    assert failed_event.event_type == "MESSAGE_SEND_FAILED"
    assert failed_event.status == "FAILED"
    assert failed_event.details["message_id"] == "msg-offline"


@pytest.mark.parametrize(
    "message_type",
    [MessageType.REVIEW, MessageType.FAILURE, MessageType.VERIFIED],
)
def test_extended_message_types_are_supported(
    tmp_path: Path,
    message_type: MessageType,
) -> None:
    _, bus, _ = context_and_bus(tmp_path)
    message = Message(
        message_id=f"msg-{message_type.value}",
        incident_id=INCIDENT_ID,
        task_id="N7.1",
        from_agent="verifier-agent-01",
        to_agent="repair-agent-01",
        type=message_type,
        content=f"message type {message_type.value}",
        correlation_id=f"corr-{message_type.value}",
        timestamp=NOW,
    )
    assert bus.send(message) == message
