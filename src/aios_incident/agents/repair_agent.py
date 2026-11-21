"""Minimal RepairAgent plan and controlled simulation executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..exceptions import RepairNotAllowedError
from ..models import (
    Diagnosis,
    Message,
    MessageType,
    RepairAction,
    RepairPlan,
    RepairResult,
    RiskLevel,
    RunContext,
    TraceEvent,
    VerificationResult,
)
from ..orchestrator.blackboard import ArtifactKind, Blackboard, BlackboardArtifact
from ..orchestrator.interaction_bus import InteractionBus
from ..orchestrator.trace import JsonlTraceStore
from ..state import WorkflowStatus, transition_workflow
from ..utils import generate_id, utc_now
from .verifier_agent import VerificationProbe, VerifierAgent


class RepairExecutor(Protocol):
    def execute(self, context: RunContext, plan: RepairPlan) -> RepairResult:
        """Execute a reviewed or simulated repair plan."""


class RepairAgent:
    """Generate a rollback-aware plan and delegate its execution."""

    def __init__(self, blackboard: Blackboard, *, agent_id: str = "repair-agent-01") -> None:
        self.blackboard = blackboard
        self.agent_id = agent_id

    def repair(
        self,
        context: RunContext,
        diagnosis: Diagnosis,
        *,
        recommended_action: str,
        executor: RepairExecutor,
    ) -> tuple[RepairPlan, RepairResult]:
        plan = self.create_plan(
            context,
            diagnosis,
            recommended_action=recommended_action,
        )
        result = self.execute_plan(context, plan, executor=executor)
        return plan, result

    def create_plan(
        self,
        context: RunContext,
        diagnosis: Diagnosis,
        *,
        recommended_action: str,
        attempt_no: int = 1,
        previous_failure_id: str | None = None,
    ) -> RepairPlan:
        if attempt_no > 1 and previous_failure_id is None:
            raise ValueError("later repair attempts must reference the previous failure")
        root_cause_ids = diagnosis.selected_root_cause_ids or tuple(
            root.root_cause_id for root in diagnosis.root_causes
        )
        strategy_action = (
            recommended_action
            if attempt_no == 1
            else f"{recommended_action}; alternate strategy from verifier feedback"
        )
        action = RepairAction(
            action_id=generate_id("action"),
            description=strategy_action,
            tool_name="simulated_repair",
            parameters={
                "service": context.target.service,
                "strategy_attempt": attempt_no,
                "previous_failure_id": previous_failure_id,
            },
            timeout_seconds=30,
            critical=True,
        )
        plan = RepairPlan(
            repair_id=generate_id("repair"),
            incident_id=context.incident_id,
            attempt_no=attempt_no,
            previous_failure_id=previous_failure_id,
            root_cause_ids=root_cause_ids,
            actions=(action,),
            preconditions=("diagnosis_contains_supporting_evidence",),
            expected_effect=f"{context.target.service} passes health and smoke checks",
            risk_level=RiskLevel.MEDIUM,
            rollback_plan=("restore the pre-repair simulated service state",),
            timeout_seconds=60,
            created_at=utc_now(),
        )
        self.blackboard.put(
            BlackboardArtifact(
                artifact_id=generate_id("art"),
                incident_id=context.incident_id,
                producer_agent="RepairAgent",
                kind=ArtifactKind.REPAIR_PLAN,
                content_ref=f"{plan.repair_id}:plan",
                created_at=utc_now(),
            )
        )
        return plan

    def execute_plan(
        self,
        context: RunContext,
        plan: RepairPlan,
        *,
        executor: RepairExecutor,
    ) -> RepairResult:
        result = executor.execute(context, plan)
        self.blackboard.put(
            BlackboardArtifact(
                artifact_id=generate_id("art"),
                incident_id=context.incident_id,
                producer_agent="RepairAgent",
                kind=ArtifactKind.REPAIR_EXECUTION,
                content_ref=f"{plan.repair_id}:result",
                created_at=utc_now(),
            )
        )
        return result


@dataclass(frozen=True, slots=True)
class RepairAttemptRecord:
    attempt_no: int
    plan: RepairPlan
    repair_result: RepairResult
    verification_result: VerificationResult
    review_message_id: str
    outcome_message_id: str


@dataclass(frozen=True, slots=True)
class RepairLoopResult:
    context: RunContext
    status: WorkflowStatus
    attempts: tuple[RepairAttemptRecord, ...]


class RepairVerificationLoop:
    """Run up to two repair attempts with verifier-controlled success."""

    def __init__(
        self,
        *,
        context: RunContext,
        diagnosis: Diagnosis,
        recommended_action: str,
        repair_agent: RepairAgent,
        verifier: VerifierAgent,
        repair_executor: RepairExecutor,
        verification_probe: VerificationProbe,
        trace: JsonlTraceStore,
        bus: InteractionBus,
        max_attempts: int = 2,
    ) -> None:
        if max_attempts < 1 or max_attempts > 2:
            raise ValueError("max_attempts must be between 1 and 2")
        if max_attempts > context.max_repair_attempts:
            raise ValueError("max_attempts exceeds RunContext max_repair_attempts")
        if not diagnosis.selected_root_cause_ids:
            raise RepairNotAllowedError("diagnosis has no selected repairable root cause")
        self.context = context
        self.diagnosis = diagnosis
        self.recommended_action = recommended_action
        self.repair_agent = repair_agent
        self.verifier = verifier
        self.repair_executor = repair_executor
        self.verification_probe = verification_probe
        self.trace = trace
        self.bus = bus
        self.max_attempts = max_attempts

    def run(self) -> RepairLoopResult:
        repair_agent_id = self.bus.resolve_agent_id("RepairAgent")
        verifier_agent_id = self.bus.resolve_agent_id("VerifierAgent")
        attempts: list[RepairAttemptRecord] = []
        previous_failure_id: str | None = None

        for attempt_no in range(1, self.max_attempts + 1):
            repair_task_id = f"N6.{attempt_no}"
            verify_task_id = f"N7.{attempt_no}"
            self._event(
                task_id=repair_task_id,
                agent_id=repair_agent_id,
                event_type="REPAIR_ATTEMPT_STARTED",
                status="RUNNING",
                details={"attempt_no": attempt_no},
            )
            plan = self.repair_agent.create_plan(
                self.context,
                self.diagnosis,
                recommended_action=self.recommended_action,
                attempt_no=attempt_no,
                previous_failure_id=previous_failure_id,
            )
            self._event(
                task_id=repair_task_id,
                agent_id=repair_agent_id,
                event_type="REPAIR_PLAN_CREATED",
                status="SUCCEEDED",
                details={
                    "attempt_no": attempt_no,
                    "repair_id": plan.repair_id,
                    "previous_failure_id": previous_failure_id,
                },
            )
            repair_result = self.repair_agent.execute_plan(
                self.context,
                plan,
                executor=self.repair_executor,
            )
            self._event(
                task_id=repair_task_id,
                agent_id=repair_agent_id,
                event_type="REPAIR_FINISHED",
                status=repair_result.status.value,
                details={
                    "attempt_no": attempt_no,
                    "repair_id": plan.repair_id,
                    "rollback_performed": repair_result.rollback_performed,
                },
            )

            correlation_id = generate_id("corr")
            review = self.bus.send(
                Message(
                    message_id=generate_id("msg"),
                    incident_id=self.context.incident_id,
                    task_id=repair_task_id,
                    from_agent=repair_agent_id,
                    to_agent=verifier_agent_id,
                    type=MessageType.REVIEW,
                    content=(
                        f"Review repair attempt {attempt_no} "
                        f"with status {repair_result.status.value}"
                    ),
                    correlation_id=correlation_id,
                    timestamp=utc_now(),
                )
            )
            verification_result = self.verifier.verify(
                self.context,
                repair_result,
                probe=self.verification_probe,
            )
            self._event(
                task_id=verify_task_id,
                agent_id=verifier_agent_id,
                event_type="VERIFICATION_FINISHED",
                status="SUCCEEDED" if verification_result.passed else "FAILED",
                details={
                    "attempt_no": attempt_no,
                    "verification_id": verification_result.verification_id,
                },
            )
            outcome_type = (
                MessageType.RESULT if verification_result.passed else MessageType.FEEDBACK
            )
            outcome_content = (
                f"Attempt {attempt_no} verified successfully"
                if verification_result.passed
                else "; ".join(verification_result.failure_reasons)
            )
            outcome_message = self.bus.send(
                Message(
                    message_id=generate_id("msg"),
                    incident_id=self.context.incident_id,
                    task_id=verify_task_id,
                    from_agent=verifier_agent_id,
                    to_agent=repair_agent_id,
                    type=outcome_type,
                    content=outcome_content,
                    correlation_id=correlation_id,
                    reply_to=review.message_id,
                    timestamp=utc_now(),
                )
            )
            attempts.append(
                RepairAttemptRecord(
                    attempt_no=attempt_no,
                    plan=plan,
                    repair_result=repair_result,
                    verification_result=verification_result,
                    review_message_id=review.message_id,
                    outcome_message_id=outcome_message.message_id,
                )
            )
            if verification_result.passed:
                final_status = WorkflowStatus.SUCCESS
                self._event(
                    task_id=verify_task_id,
                    agent_id=verifier_agent_id,
                    event_type="REPAIR_LOOP_SUCCEEDED",
                    status=final_status.value,
                    details={"attempt_no": attempt_no},
                )
                return RepairLoopResult(
                    context=self.context.model_copy(
                        update={
                            "workflow_status": transition_workflow(
                                self.context.workflow_status,
                                final_status,
                            )
                        }
                    ),
                    status=final_status,
                    attempts=tuple(attempts),
                )

            previous_failure_id = verification_result.verification_id
            if attempt_no < self.max_attempts:
                self._event(
                    task_id=verify_task_id,
                    agent_id=verifier_agent_id,
                    event_type="REPAIR_RETRY_SCHEDULED",
                    status="FAILED_RETRYABLE",
                    details={
                        "attempt_no": attempt_no,
                        "previous_failure_id": previous_failure_id,
                    },
                )

        final_status = WorkflowStatus.UNRESOLVED
        self._event(
            task_id=f"N7.{self.max_attempts}",
            agent_id=verifier_agent_id,
            event_type="REPAIR_LOOP_UNRESOLVED",
            status=final_status.value,
            details={"attempts": len(attempts)},
        )
        return RepairLoopResult(
            context=self.context.model_copy(
                update={
                    "workflow_status": transition_workflow(
                        self.context.workflow_status,
                        final_status,
                    )
                }
            ),
            status=final_status,
            attempts=tuple(attempts),
        )

    def _event(
        self,
        *,
        task_id: str,
        agent_id: str,
        event_type: str,
        status: str,
        details: dict[str, object],
    ) -> None:
        self.trace.append(
            TraceEvent(
                trace_id=generate_id("trace"),
                incident_id=self.context.incident_id,
                task_id=task_id,
                agent_id=agent_id,
                event_type=event_type,
                status=status,
                timestamp=utc_now(),
                details=details,
            )
        )
