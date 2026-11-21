"""One deterministic incident loop from log evidence through verification."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

from ..agents.coordinator_agent import (
    CoordinatorAgent,
    DiagnosisJsonClient,
)
from ..agents.log_agent import LogAgent
from ..agents.repair_agent import RepairAgent, RepairExecutor
from ..agents.verifier_agent import VerificationProbe, VerifierAgent
from ..exceptions import IncidentStateError
from ..models import (
    AllowedScope,
    Diagnosis,
    Evidence,
    FinalReport,
    RepairActionResult,
    RepairPlan,
    RepairResult,
    RepairStatus,
    RunContext,
    TraceEvent,
    VerificationCheck,
    VerificationResult,
)
from ..state import WorkflowStatus, transition_workflow
from ..utils import generate_id, utc_now
from .blackboard import ArtifactKind, Blackboard, BlackboardArtifact
from .trace import JsonlTraceStore


@dataclass(slots=True)
class SimulatedFaultScenario:
    """In-memory fault state used for a controlled W07 repair simulation."""

    service: str
    repair_succeeds: bool = True
    _repaired: bool = False
    _lock: RLock = field(default_factory=RLock, repr=False)

    def apply_repair(self) -> bool:
        with self._lock:
            if self.repair_succeeds:
                self._repaired = True
            return self._repaired

    @property
    def healthy(self) -> bool:
        with self._lock:
            return self._repaired


class SimulatedRepairExecutor:
    """Apply a repair only to the in-memory scenario state."""

    def __init__(self, scenario: SimulatedFaultScenario) -> None:
        self.scenario = scenario

    def execute(self, context: RunContext, plan: RepairPlan) -> RepairResult:
        started_at = utc_now()
        success = self.scenario.apply_repair()
        ended_at = utc_now()
        action_results = tuple(
            RepairActionResult(
                action_id=action.action_id,
                success=success,
                return_code=0 if success else 1,
                output_summary=(
                    f"simulated repair restored {self.scenario.service}"
                    if success
                    else f"simulated repair did not restore {self.scenario.service}"
                ),
                duration_ms=0,
            )
            for action in plan.actions
        )
        return RepairResult(
            repair_id=plan.repair_id,
            incident_id=context.incident_id,
            attempt_no=plan.attempt_no,
            status=RepairStatus.SUCCEEDED if success else RepairStatus.FAILED,
            action_results=action_results,
            rollback_performed=False,
            error=None if success else "simulated repair did not restore the service",
            started_at=started_at,
            ended_at=ended_at,
        )


class SimulatedScenarioVerifier:
    """Return deterministic health, smoke and regression checks."""

    def __init__(self, scenario: SimulatedFaultScenario) -> None:
        self.scenario = scenario

    def run_checks(
        self,
        context: RunContext,
        repair_result: RepairResult,
    ) -> tuple[VerificationCheck, ...]:
        healthy = self.scenario.healthy and repair_result.status is RepairStatus.SUCCEEDED
        reason = "service remains unhealthy" if not healthy else "service recovered"
        return (
            VerificationCheck(
                name="process_and_port_check",
                passed=healthy,
                details={"reason": reason, "service": context.target.service},
            ),
            VerificationCheck(
                name="health_endpoint",
                passed=healthy,
                details={"reason": reason, "status": 200 if healthy else 503},
            ),
            VerificationCheck(
                name="smoke_test",
                passed=healthy,
                details={"reason": reason},
            ),
            VerificationCheck(
                name="regression_test",
                passed=healthy,
                details={"reason": reason},
            ),
        )


@dataclass(frozen=True, slots=True)
class MinimalFlowResult:
    context: RunContext
    evidence: Evidence
    diagnosis: Diagnosis
    repair_plan: RepairPlan
    repair_result: RepairResult
    verification_result: VerificationResult
    final_report: FinalReport


class MinimalFlowRunner:
    """Run one incident through plan, log, LLM, repair and verification."""

    def __init__(
        self,
        *,
        coordinator: CoordinatorAgent,
        log_agent: LogAgent,
        repair_agent: RepairAgent,
        verifier: VerifierAgent,
        llm: DiagnosisJsonClient,
        blackboard: Blackboard,
        trace: JsonlTraceStore,
        repair_executor: RepairExecutor,
        verification_probe: VerificationProbe,
    ) -> None:
        self.coordinator = coordinator
        self.log_agent = log_agent
        self.repair_agent = repair_agent
        self.verifier = verifier
        self.llm = llm
        self.blackboard = blackboard
        self.trace = trace
        self.repair_executor = repair_executor
        self.verification_probe = verification_probe

    def run(self, context: RunContext, *, log_path: str) -> MinimalFlowResult:
        if context.incident_id != self.trace.incident_id:
            raise IncidentStateError("run context and trace store incident IDs differ")
        if context.workflow_status is WorkflowStatus.CREATED:
            running_context = context.model_copy(
                update={
                    "workflow_status": transition_workflow(
                        context.workflow_status,
                        WorkflowStatus.RUNNING,
                    )
                }
            )
        elif context.workflow_status is WorkflowStatus.RUNNING:
            running_context = context
        else:
            raise IncidentStateError(
                f"minimal flow requires CREATED or RUNNING, got {context.workflow_status.value}"
            )

        timing: dict[str, int] = {}
        flow_started = time.perf_counter()
        self._event(
            running_context,
            task_id="N0",
            agent_id=self.coordinator.agent_id,
            event_type="MINIMAL_FLOW_STARTED",
            status=WorkflowStatus.RUNNING.value,
        )
        try:
            stage_started = time.perf_counter()
            task = self.coordinator.plan(running_context, log_path=log_path)
            timing["plan_ms"] = _elapsed_ms(stage_started)
            self._event(
                running_context,
                task_id="N0",
                agent_id=self.coordinator.agent_id,
                event_type="MINIMAL_PLAN_CREATED",
                status="SUCCEEDED",
                duration_ms=timing["plan_ms"],
            )

            stage_started = time.perf_counter()
            evidence = self.log_agent.collect(running_context, task)
            timing["log_collection_ms"] = _elapsed_ms(stage_started)
            self._event(
                running_context,
                task_id="N1",
                agent_id=self.log_agent.agent_id,
                event_type="LOG_EVIDENCE_COLLECTED",
                status="SUCCEEDED",
                duration_ms=timing["log_collection_ms"],
                details={"evidence_id": evidence.evidence_id},
            )

            stage_started = time.perf_counter()
            diagnosis_outcome = self.coordinator.diagnose(
                running_context,
                task,
                evidence,
                self.llm,
            )
            diagnosis = diagnosis_outcome.diagnosis
            timing["diagnosis_ms"] = _elapsed_ms(stage_started)
            self._add_root_cause_artifact(running_context, diagnosis)
            self._event(
                running_context,
                task_id="N5",
                agent_id=self.coordinator.agent_id,
                event_type="DIAGNOSIS_COMPLETED",
                status="SUCCEEDED",
                duration_ms=timing["diagnosis_ms"],
                details={"diagnosis_id": diagnosis.diagnosis_id},
            )

            stage_started = time.perf_counter()
            repair_plan = self.repair_agent.create_plan(
                running_context,
                diagnosis,
                recommended_action=diagnosis_outcome.repair_action,
            )
            timing["repair_plan_ms"] = _elapsed_ms(stage_started)
            self._event(
                running_context,
                task_id="N6.1",
                agent_id=self.repair_agent.agent_id,
                event_type="REPAIR_PLAN_CREATED",
                status="SUCCEEDED",
                duration_ms=timing["repair_plan_ms"],
                details={"repair_id": repair_plan.repair_id},
            )

            stage_started = time.perf_counter()
            repair_result = self.repair_agent.execute_plan(
                running_context,
                repair_plan,
                executor=self.repair_executor,
            )
            timing["repair_execution_ms"] = _elapsed_ms(stage_started)
            self._event(
                running_context,
                task_id="N6.1",
                agent_id=self.repair_agent.agent_id,
                event_type="REPAIR_FINISHED",
                status=repair_result.status.value,
                duration_ms=timing["repair_execution_ms"],
                details={"repair_id": repair_plan.repair_id},
            )

            stage_started = time.perf_counter()
            verification_result = self.verifier.verify(
                running_context,
                repair_result,
                probe=self.verification_probe,
            )
            timing["verification_ms"] = _elapsed_ms(stage_started)
            self._event(
                running_context,
                task_id="N7.1",
                agent_id=self.verifier.agent_id,
                event_type="VERIFICATION_FINISHED",
                status="SUCCEEDED" if verification_result.passed else "FAILED",
                duration_ms=timing["verification_ms"],
                details={"verification_id": verification_result.verification_id},
            )

            final_status = (
                WorkflowStatus.SUCCESS if verification_result.passed else WorkflowStatus.UNRESOLVED
            )
            final_context = running_context.model_copy(
                update={
                    "workflow_status": transition_workflow(
                        running_context.workflow_status,
                        final_status,
                    )
                }
            )
            timing["total_ms"] = _elapsed_ms(flow_started)
            report = FinalReport(
                report_id=generate_id("report"),
                incident_id=final_context.incident_id,
                run_id=final_context.run_id,
                final_status=final_status,
                root_causes=diagnosis.root_causes,
                evidence=(evidence,),
                repair_actions=repair_result.action_results,
                rollback_record=repair_plan.rollback_plan,
                verification=verification_result,
                timing=timing,
                agent_interactions=(
                    "CoordinatorAgent -> LogAgent: analysis task",
                    "CoordinatorAgent -> RepairAgent: diagnosis",
                    "RepairAgent -> VerifierAgent: repair result",
                    "VerifierAgent -> CoordinatorAgent: verification result",
                ),
                trace_ref=str(self.trace.path),
                created_at=utc_now(),
            )
            self.blackboard.put(
                BlackboardArtifact(
                    artifact_id=generate_id("art"),
                    incident_id=final_context.incident_id,
                    producer_agent="CoordinatorAgent",
                    kind=ArtifactKind.FINAL_REPORT,
                    content_ref=report.report_id,
                    created_at=utc_now(),
                )
            )
            self._event(
                final_context,
                task_id="N7.1",
                agent_id=self.coordinator.agent_id,
                event_type="FINAL_REPORT_CREATED",
                status=final_status.value,
                duration_ms=timing["total_ms"],
                details={"report_id": report.report_id},
            )
            self._event(
                final_context,
                task_id="N7.1",
                agent_id=self.coordinator.agent_id,
                event_type="MINIMAL_FLOW_FINISHED",
                status=final_status.value,
                duration_ms=timing["total_ms"],
            )
        except Exception as exc:
            self._event(
                running_context,
                task_id="N0",
                agent_id=self.coordinator.agent_id,
                event_type="MINIMAL_FLOW_FAILED",
                status=WorkflowStatus.ABORTED.value,
                duration_ms=_elapsed_ms(flow_started),
                details={"error_type": type(exc).__name__, "error": str(exc)},
            )
            raise

        return MinimalFlowResult(
            context=final_context,
            evidence=evidence,
            diagnosis=diagnosis,
            repair_plan=repair_plan,
            repair_result=repair_result,
            verification_result=verification_result,
            final_report=report,
        )

    def _add_root_cause_artifact(
        self,
        context: RunContext,
        diagnosis: Diagnosis,
    ) -> None:
        for root_cause in diagnosis.root_causes:
            self.blackboard.put(
                BlackboardArtifact(
                    artifact_id=generate_id("art"),
                    incident_id=context.incident_id,
                    producer_agent="CoordinatorAgent",
                    kind=ArtifactKind.ROOT_CAUSE,
                    content_ref=root_cause.root_cause_id,
                    created_at=utc_now(),
                )
            )

    def _event(
        self,
        context: RunContext,
        *,
        task_id: str,
        agent_id: str,
        event_type: str,
        status: str,
        duration_ms: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.trace.append(
            TraceEvent(
                trace_id=generate_id("trace"),
                incident_id=context.incident_id,
                task_id=task_id,
                agent_id=agent_id,
                event_type=event_type,
                status=status,
                timestamp=utc_now(),
                duration_ms=duration_ms,
                details=details or {},
            )
        )


def seed_demo_target(root_dir: Path, *, service: str = "web-app") -> tuple[str, AllowedScope]:
    """Create a small file-backed target for the W07 demo and tests."""

    log_path = f"/var/log/{service}/error.log"
    config_path = f"/etc/{service}/config.yaml"
    files = {
        log_path: (
            f"{service} started\n"
            f"{service}: database connection refused\n"
            f"{service}: health check returned 503\n"
        ),
        config_path: f"service: {service}\nport: 8080\n",
        "/proc/loadavg": "0.10 0.20 0.30 1/100 123\n",
        "/proc/meminfo": "MemTotal: 16384 kB\nMemFree: 8192 kB\n",
        "/proc/stat": "cpu 1 2 3 4\ncpu0 1 2 3 4\n",
        "/proc/net/dev": (
            "Inter-| Receive | Transmit\n"
            " face |bytes packets errs drop fifo frame compressed multicast|"
            "bytes packets errs drop fifo colls carrier compressed\n"
            " eth0: 100 2 0 0 0 0 0 0 200 3 0 0 0 0 0 0\n"
        ),
    }
    for target_path, content in files.items():
        path = root_dir / target_path.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return log_path, AllowedScope(
        read_paths=(f"/var/log/{service}", f"/etc/{service}"),
        allowed_services=(service,),
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
