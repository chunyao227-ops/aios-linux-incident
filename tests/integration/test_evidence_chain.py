"""W10 integration of W08 evidence Agent outputs and W09 messages."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from aios_incident.agents.config_agent import ConfigAgent
from aios_incident.agents.coordinator_agent import CoordinatorAgent
from aios_incident.agents.dependency_agent import DependencyAgent
from aios_incident.agents.log_agent import LogAgent
from aios_incident.agents.metrics_agent import MetricsAgent
from aios_incident.models import (
    IncidentTarget,
    RepairResult,
    RepairStatus,
    RunContext,
    VerificationCheck,
    VerificationResult,
)
from aios_incident.orchestrator.blackboard import Blackboard
from aios_incident.orchestrator.diagnosis import DiagnosisFusionEngine
from aios_incident.orchestrator.interaction_bus import InteractionBus
from aios_incident.orchestrator.minimal_flow import seed_demo_target
from aios_incident.orchestrator.planner import build_default_agent_cards
from aios_incident.orchestrator.trace import JsonlTraceStore
from aios_incident.tools.gateway import SandboxReadOnlyBackend, ToolGateway

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
INCIDENT_ID = "inc-w10-chain"


def test_collected_four_evidence_and_three_pair_messages_form_chain(
    tmp_path: Path,
) -> None:
    root = tmp_path / "sandbox"
    log_path, scope = seed_demo_target(root)
    context = RunContext(
        run_id="run-w10-chain",
        incident_id=INCIDENT_ID,
        objective="diagnose web-app",
        target=IncidentTarget(
            host="sandbox-01",
            service="web-app",
            environment="docker",
        ),
        allowed_scope=scope,
        time_budget_seconds=600,
        max_repair_attempts=2,
        success_criteria=("health_endpoint",),
    )
    trace = JsonlTraceStore(tmp_path / "traces", INCIDENT_ID, context.run_id)
    blackboard = Blackboard()
    gateway = ToolGateway(
        SandboxReadOnlyBackend(root),
        scope_resolver=lambda _: scope,
        trace_resolver=lambda _: trace,
    )

    task = CoordinatorAgent().plan(context, log_path=log_path)
    log_evidence = LogAgent(gateway, blackboard).collect(context, task)
    metrics_evidence = MetricsAgent(gateway, blackboard).collect(context)
    config_evidence = ConfigAgent(gateway, blackboard).collect(
        context,
        config_path="/etc/web-app/config.yaml",
    )
    dependency_evidence = DependencyAgent(gateway, blackboard).collect(context)

    bus = InteractionBus(INCIDENT_ID, trace, blackboard)
    for card in build_default_agent_cards():
        bus.register_agent(card.agent_id, card.agent_type)
    repair_result = RepairResult(
        repair_id="repair-w10",
        incident_id=INCIDENT_ID,
        status=RepairStatus.SUCCEEDED,
        started_at=NOW,
        ended_at=NOW,
    )
    verification_result = VerificationResult(
        verification_id="verify-w10",
        incident_id=INCIDENT_ID,
        repair_id=repair_result.repair_id,
        passed=True,
        checks=(VerificationCheck(name="health_endpoint", passed=True),),
        started_at=NOW,
        ended_at=NOW,
    )
    messages = CoordinatorAgent().coordinate_required_interactions(
        context,
        bus,
        log_evidence=log_evidence,
        config_evidence=config_evidence,
        metrics_evidence=metrics_evidence,
        dependency_evidence=dependency_evidence,
        repair_result=repair_result,
        verification_result=verification_result,
    )
    bus_messages = bus.messages()

    result = DiagnosisFusionEngine().fuse(
        context,
        (
            log_evidence,
            metrics_evidence,
            config_evidence,
            dependency_evidence,
        ),
        bus_messages,
    )

    assert messages.bidirectional_edge_count == 3
    assert result.status in {"READY", "BLOCKED"}
    assert len(result.evidence_chain) == 4
    assert all(entry.linked_message_ids for entry in result.evidence_chain)
    assert result.interaction_message_ids == tuple(message.message_id for message in bus_messages)
    valid_evidence_ids = {
        log_evidence.evidence_id,
        metrics_evidence.evidence_id,
        config_evidence.evidence_id,
        dependency_evidence.evidence_id,
    }
    for root_cause in result.diagnosis.root_causes:
        assert set(root_cause.supporting_evidence) <= valid_evidence_ids
