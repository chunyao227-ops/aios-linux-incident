"""W07 end-to-end minimal incident flow tests."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from aios_incident.adapters.aios_client import AiosClient
from aios_incident.adapters.llm_adapter import (
    ChatMessage,
    LlmAdapter,
    LLMResponse,
    StructuredLLMResponse,
)
from aios_incident.agents.coordinator_agent import (
    CoordinatorAgent,
    MinimalDiagnosisOutput,
)
from aios_incident.agents.log_agent import LogAgent
from aios_incident.agents.repair_agent import RepairAgent
from aios_incident.agents.verifier_agent import VerifierAgent
from aios_incident.config import load_config
from aios_incident.models import (
    AllowedScope,
    FinalReport,
    IncidentTarget,
    RunContext,
    TokenUsage,
)
from aios_incident.orchestrator.blackboard import ArtifactKind, Blackboard
from aios_incident.orchestrator.minimal_flow import (
    MinimalFlowResult,
    MinimalFlowRunner,
    SimulatedFaultScenario,
    SimulatedRepairExecutor,
    SimulatedScenarioVerifier,
    seed_demo_target,
)
from aios_incident.orchestrator.trace import JsonlTraceStore
from aios_incident.tools.gateway import SandboxReadOnlyBackend, ToolGateway
from aios_incident.validation import model_from_json, model_to_json


class FakeDiagnosisClient:
    def __init__(self, root_cause: str = "database service stopped") -> None:
        self.root_cause = root_cause
        self.calls = 0

    def chat_json(
        self,
        messages: Sequence[ChatMessage],
        *,
        output_model: type[Any],
        agent_name: str = "CoordinatorAgent",
        temperature: float | None = None,
        max_new_tokens: int | None = None,
        user_id: str | None = None,
    ) -> StructuredLLMResponse[Any]:
        self.calls += 1
        assert output_model is MinimalDiagnosisOutput
        assert messages
        data = MinimalDiagnosisOutput(
            root_cause=self.root_cause,
            confidence=0.9,
            repair_action="restart the database dependency",
        )
        response = LLMResponse(
            response_message=data.model_dump_json(),
            json_output=data.model_dump(mode="json"),
            finished=True,
            status_code=200,
            token_usage=TokenUsage(prompt=20, completion=10, source="reported"),
            duration_ms=5,
            attempts=1,
        )
        return StructuredLLMResponse(response=response, data=data)


def build_context(incident_id: str, allowed_scope: AllowedScope) -> RunContext:
    return RunContext(
        run_id=f"run-{incident_id}",
        incident_id=incident_id,
        objective="诊断并修复 web-app 不可用问题",
        target=IncidentTarget(
            host="sandbox-01",
            service="web-app",
            environment="docker",
        ),
        allowed_scope=allowed_scope,
        time_budget_seconds=600,
        max_repair_attempts=2,
        success_criteria=(
            "process_and_port_check",
            "health_endpoint",
            "smoke_test",
            "regression_test",
        ),
    )


def run_flow(
    tmp_path: Path,
    *,
    incident_id: str,
    repair_succeeds: bool,
    llm: Any,
) -> tuple[MinimalFlowResult, Blackboard, JsonlTraceStore]:
    root = tmp_path / "sandbox"
    log_path, scope = seed_demo_target(root)
    context = build_context(incident_id, scope)
    trace = JsonlTraceStore(tmp_path / "traces", incident_id, context.run_id)
    blackboard = Blackboard()
    gateway = ToolGateway(
        SandboxReadOnlyBackend(root),
        scope_resolver=lambda _: scope,
        trace_resolver=lambda _: trace,
    )
    scenario = SimulatedFaultScenario(
        service="web-app",
        repair_succeeds=repair_succeeds,
    )
    runner = MinimalFlowRunner(
        coordinator=CoordinatorAgent(),
        log_agent=LogAgent(gateway, blackboard),
        repair_agent=RepairAgent(blackboard),
        verifier=VerifierAgent(blackboard),
        llm=llm,
        blackboard=blackboard,
        trace=trace,
        repair_executor=SimulatedRepairExecutor(scenario),
        verification_probe=SimulatedScenarioVerifier(scenario),
    )
    return runner.run(context, log_path=log_path), blackboard, trace


def test_minimal_flow_success_path(tmp_path: Path) -> None:
    llm = FakeDiagnosisClient()
    result, blackboard, trace = run_flow(
        tmp_path,
        incident_id="inc-w07-success",
        repair_succeeds=True,
        llm=llm,
    )

    assert result.context.workflow_status.value == "SUCCESS"
    assert result.final_report.final_status.value == "SUCCESS"
    restored_report = model_from_json(model_to_json(result.final_report), FinalReport)
    assert restored_report == result.final_report
    assert result.verification_result.passed is True
    assert result.repair_result.status.value == "SUCCEEDED"
    assert result.final_report.evidence[0].kind.value == "log"
    assert llm.calls == 1

    event_types = [event.event_type for event in trace.read_events()]
    assert event_types[0] == "MINIMAL_FLOW_STARTED"
    assert {
        "MINIMAL_PLAN_CREATED",
        "TOOL_CALL_STARTED",
        "TOOL_CALL_FINISHED",
        "LOG_EVIDENCE_COLLECTED",
        "DIAGNOSIS_COMPLETED",
        "REPAIR_PLAN_CREATED",
        "REPAIR_FINISHED",
        "VERIFICATION_FINISHED",
        "FINAL_REPORT_CREATED",
        "MINIMAL_FLOW_FINISHED",
    } <= set(event_types)
    assert event_types[-1] == "MINIMAL_FLOW_FINISHED"

    artifact_kinds = {artifact.kind for artifact in blackboard.list_ready("inc-w07-success")}
    assert {
        ArtifactKind.EVIDENCE,
        ArtifactKind.ROOT_CAUSE,
        ArtifactKind.REPAIR_PLAN,
        ArtifactKind.REPAIR_EXECUTION,
        ArtifactKind.VERIFICATION_RESULT,
        ArtifactKind.FINAL_REPORT,
    } <= artifact_kinds


def test_minimal_flow_failure_path_is_not_reported_as_success(tmp_path: Path) -> None:
    result, _, trace = run_flow(
        tmp_path,
        incident_id="inc-w07-failure",
        repair_succeeds=False,
        llm=FakeDiagnosisClient(),
    )

    assert result.repair_result.status.value == "FAILED"
    assert result.verification_result.passed is False
    assert result.final_report.final_status.value == "UNRESOLVED"
    assert result.context.workflow_status.value == "UNRESOLVED"
    assert result.verification_result.failure_reasons

    verification_event = next(
        event for event in trace.read_events() if event.event_type == "VERIFICATION_FINISHED"
    )
    assert verification_event.status == "FAILED"


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_AIOS_INTEGRATION") != "1",
    reason="set RUN_AIOS_INTEGRATION=1 to use the real local AIOS model",
)
def test_minimal_flow_with_real_aios_model(tmp_path: Path) -> None:
    config = load_config()
    llm = LlmAdapter(AiosClient(config.aios), config.model)
    result, _, _ = run_flow(
        tmp_path,
        incident_id="inc-w07-aios",
        repair_succeeds=True,
        llm=llm,
    )

    assert result.final_report.final_status.value == "SUCCESS"
    assert result.diagnosis.root_causes
