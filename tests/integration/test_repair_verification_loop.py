"""W11 controlled repair and independent verification loop tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios_incident.agents.repair_agent import (
    RepairAgent,
    RepairVerificationLoop,
)
from aios_incident.agents.verifier_agent import VerifierAgent
from aios_incident.exceptions import RepairNotAllowedError
from aios_incident.models import (
    AllowedScope,
    Diagnosis,
    IncidentTarget,
    MessageType,
    RepairAction,
    RepairActionResult,
    RepairPlan,
    RepairResult,
    RiskLevel,
    RootCauseCandidate,
    RunContext,
    VerificationCheck,
)
from aios_incident.orchestrator.blackboard import Blackboard
from aios_incident.orchestrator.interaction_bus import InteractionBus
from aios_incident.orchestrator.planner import build_default_agent_cards
from aios_incident.orchestrator.trace import JsonlTraceStore
from aios_incident.state import WorkflowStatus
from aios_incident.tools.repair import ControlledRepairTool
from aios_incident.tools.verify import VERIFICATION_ORDER, ControlledVerificationTool

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
INCIDENT_ID = "inc-w11"


class ScriptedRepairBackend:
    def __init__(
        self,
        *,
        failed_attempts: set[int] | None = None,
        rollback_succeeds: bool = True,
    ) -> None:
        self.failed_attempts = failed_attempts or set()
        self.rollback_succeeds = rollback_succeeds
        self.executed_attempts: list[int] = []
        self.rollback_calls = 0

    def execute_action(
        self,
        context: RunContext,
        plan: RepairPlan,
        action: RepairAction,
        attempt_no: int,
    ) -> RepairActionResult:
        self.executed_attempts.append(attempt_no)
        success = attempt_no not in self.failed_attempts
        return RepairActionResult(
            action_id=action.action_id,
            success=success,
            return_code=0 if success else 1,
            output_summary="controlled action completed" if success else "controlled action failed",
            duration_ms=5,
        )

    def rollback(self, context: RunContext, plan: RepairPlan) -> str:
        if not self.rollback_succeeds:
            raise RuntimeError("rollback failed")
        self.rollback_calls += 1
        return "pre-repair state restored"


class ScriptedVerificationBackend:
    def __init__(self, *, passing_attempts: set[int]) -> None:
        self.passing_attempts = passing_attempts
        self.checked_names: list[str] = []

    def run_check(
        self,
        context: RunContext,
        repair_result: RepairResult,
        check_name: str,
    ) -> VerificationCheck:
        self.checked_names.append(check_name)
        passed = repair_result.attempt_no in self.passing_attempts
        return VerificationCheck(
            name=check_name,
            passed=passed,
            details={"reason": "controlled check passed" if passed else "controlled check failed"},
        )


def context() -> RunContext:
    return RunContext(
        run_id="run-w11",
        incident_id=INCIDENT_ID,
        objective="repair and verify",
        target=IncidentTarget(
            host="sandbox-01",
            service="web-app",
            environment="docker",
        ),
        allowed_scope=AllowedScope(
            read_paths=("/var/log", "/etc/web-app"),
            write_paths=("/etc/web-app",),
            allowed_services=("web-app",),
        ),
        time_budget_seconds=600,
        max_repair_attempts=2,
        success_criteria=("health_endpoint", "smoke_test", "regression_test"),
        workflow_status=WorkflowStatus.RUNNING,
    )


def diagnosis() -> Diagnosis:
    root = RootCauseCandidate(
        root_cause_id="rc-w11",
        description="database dependency unavailable",
        supporting_evidence=("evi-log", "evi-dependency"),
        confidence=0.9,
        repair_risk=RiskLevel.MEDIUM,
        required_scope=("web-app",),
    )
    return Diagnosis(
        diagnosis_id="diag-w11",
        incident_id=INCIDENT_ID,
        root_causes=(root,),
        selected_root_cause_ids=(root.root_cause_id,),
        repair_constraints=("allowed_service:web-app",),
        created_at=NOW,
    )


def make_loop(
    tmp_path: Path,
    *,
    repair_backend: ScriptedRepairBackend,
    verification_backend: ScriptedVerificationBackend,
) -> tuple[RepairVerificationLoop, Blackboard, JsonlTraceStore]:
    trace = JsonlTraceStore(tmp_path / "traces", INCIDENT_ID, "run-w11")
    blackboard = Blackboard()
    bus = InteractionBus(INCIDENT_ID, trace, blackboard)
    for card in build_default_agent_cards():
        bus.register_agent(card.agent_id, card.agent_type)
    repair_agent = RepairAgent(blackboard)
    verifier = VerifierAgent(blackboard)
    loop = RepairVerificationLoop(
        context=context(),
        diagnosis=diagnosis(),
        recommended_action="restart the database dependency",
        repair_agent=repair_agent,
        verifier=verifier,
        repair_executor=ControlledRepairTool(repair_backend),
        verification_probe=ControlledVerificationTool(verification_backend),
        trace=trace,
        bus=bus,
        max_attempts=2,
    )
    return loop, blackboard, trace


def test_successful_first_repair_completes_loop(tmp_path: Path) -> None:
    repair_backend = ScriptedRepairBackend()
    verification_backend = ScriptedVerificationBackend(passing_attempts={1})
    loop, blackboard, trace = make_loop(
        tmp_path,
        repair_backend=repair_backend,
        verification_backend=verification_backend,
    )
    result = loop.run()

    assert result.status is WorkflowStatus.SUCCESS
    assert len(result.attempts) == 1
    attempt = result.attempts[0]
    assert attempt.attempt_no == 1
    assert attempt.plan.attempt_no == 1
    assert attempt.repair_result.status.value == "SUCCEEDED"
    assert attempt.verification_result.passed is True
    assert attempt.verification_result.attempt_no == 1
    assert verification_backend.checked_names == list(VERIFICATION_ORDER)
    assert blackboard.list_ready(INCIDENT_ID)

    messages = loop.bus.messages()
    assert [message.type for message in messages] == [
        MessageType.REVIEW,
        MessageType.RESULT,
    ]
    assert messages[0].correlation_id == messages[1].correlation_id
    assert messages[1].reply_to == messages[0].message_id

    event_types = [event.event_type for event in trace.read_events()]
    assert "REPAIR_PLAN_CREATED" in event_types
    assert "REPAIR_FINISHED" in event_types
    assert "VERIFICATION_FINISHED" in event_types
    assert "REPAIR_LOOP_SUCCEEDED" in event_types


def test_two_verification_failures_end_unresolved(tmp_path: Path) -> None:
    repair_backend = ScriptedRepairBackend()
    verification_backend = ScriptedVerificationBackend(passing_attempts=set())
    loop, _, trace = make_loop(
        tmp_path,
        repair_backend=repair_backend,
        verification_backend=verification_backend,
    )
    result = loop.run()

    assert result.status is WorkflowStatus.UNRESOLVED
    assert len(result.attempts) == 2
    assert [attempt.attempt_no for attempt in result.attempts] == [1, 2]
    assert [attempt.plan.attempt_no for attempt in result.attempts] == [1, 2]
    assert [attempt.verification_result.attempt_no for attempt in result.attempts] == [1, 2]
    assert result.attempts[1].plan.previous_failure_id == (
        result.attempts[0].verification_result.verification_id
    )
    assert result.attempts[0].plan.actions[0].description != (
        result.attempts[1].plan.actions[0].description
    )

    messages = loop.bus.messages()
    assert [message.type for message in messages] == [
        MessageType.REVIEW,
        MessageType.FEEDBACK,
        MessageType.REVIEW,
        MessageType.FEEDBACK,
    ]
    event_types = [event.event_type for event in trace.read_events()]
    assert "REPAIR_RETRY_SCHEDULED" in event_types
    assert "REPAIR_LOOP_UNRESOLVED" in event_types


def test_failed_repair_action_is_rolled_back(tmp_path: Path) -> None:
    repair_backend = ScriptedRepairBackend(failed_attempts={1})
    verification_backend = ScriptedVerificationBackend(passing_attempts=set())
    loop, _, _ = make_loop(
        tmp_path,
        repair_backend=repair_backend,
        verification_backend=verification_backend,
    )
    result = loop.run()

    first = result.attempts[0].repair_result
    assert first.status.value == "ROLLED_BACK"
    assert first.rollback_performed is True
    assert first.attempt_no == 1
    assert repair_backend.rollback_calls >= 1


@pytest.mark.parametrize(
    "action",
    [
        RepairAction(
            action_id="unsafe-1",
            description="run shell",
            tool_name="shell",
            parameters={"command": "rm -rf /"},
            timeout_seconds=10,
        ),
        RepairAction(
            action_id="unsafe-2",
            description="write outside scope",
            tool_name="config_restore",
            parameters={"target_path": "/tmp/outside.conf"},
            timeout_seconds=10,
        ),
    ],
)
def test_repair_tool_rejects_unsafe_plans(action: RepairAction) -> None:
    plan = RepairPlan(
        repair_id="repair-unsafe",
        incident_id=INCIDENT_ID,
        root_cause_ids=("rc-w11",),
        actions=(action,),
        expected_effect="none",
        risk_level=RiskLevel.HIGH,
        rollback_plan=("restore",),
        timeout_seconds=10,
        created_at=NOW,
    )
    with pytest.raises(RepairNotAllowedError):
        ControlledRepairTool(ScriptedRepairBackend()).validate(context(), plan)
