"""W08 DAG validation, parallel dispatch and retry integration tests."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from threading import Barrier

import pytest

from aios_incident.agents.config_agent import ConfigAgent
from aios_incident.agents.coordinator_agent import MinimalAnalysisTask
from aios_incident.agents.dependency_agent import DependencyAgent
from aios_incident.agents.log_agent import LogAgent
from aios_incident.agents.metrics_agent import MetricsAgent
from aios_incident.exceptions import DAGValidationError
from aios_incident.models import (
    AgentCard,
    IncidentTarget,
    RunContext,
    TaskDAG,
    TaskNode,
    build_fixed_task_dag,
)
from aios_incident.orchestrator.blackboard import Blackboard
from aios_incident.orchestrator.minimal_flow import seed_demo_target
from aios_incident.orchestrator.planner import TaskPlanner
from aios_incident.orchestrator.scheduler import (
    NodeExecutor,
    Scheduler,
    TaskOutcome,
)
from aios_incident.orchestrator.trace import JsonlTraceStore
from aios_incident.state import TaskStatus, WorkflowStatus
from aios_incident.tools.gateway import SandboxReadOnlyBackend, ToolGateway


def make_context(tmp_path: Path) -> tuple[RunContext, str, ToolGateway, JsonlTraceStore]:
    root = tmp_path / "sandbox"
    log_path, scope = seed_demo_target(root)
    context = RunContext(
        run_id="run-w08",
        incident_id="inc-w08",
        objective="诊断并修复 web-app 不可用问题",
        target=IncidentTarget(
            host="sandbox-01",
            service="web-app",
            environment="docker",
        ),
        allowed_scope=scope,
        time_budget_seconds=600,
        max_repair_attempts=2,
        success_criteria=("health_endpoint", "smoke_test", "regression_test"),
        workflow_status=WorkflowStatus.RUNNING,
    )
    trace = JsonlTraceStore(tmp_path / "traces", context.incident_id, context.run_id)
    gateway = ToolGateway(
        SandboxReadOnlyBackend(root),
        scope_resolver=lambda _: scope,
        trace_resolver=lambda _: trace,
    )
    return context, log_path, gateway, trace


def success_executor(
    context: RunContext,
    node: TaskNode,
    agent: AgentCard,
) -> TaskOutcome:
    return TaskOutcome(
        success=True,
        result_ref=f"{node.task_id}-{agent.agent_id}",
    )


def test_dag_capability_validation_and_selection() -> None:
    dag = build_fixed_task_dag("inc-w08")
    planner = TaskPlanner()
    planner.validate(dag)

    log_node = next(node for node in dag.nodes if node.task_id == "N1")
    card = planner.matcher.reserve(log_node)
    try:
        assert card.agent_type == "LogAgent"
        assert card.agent_id == "log-agent-01"
        assert card.current_task_count == 1
    finally:
        planner.matcher.release(card)
    assert card.current_task_count == 0

    invalid_node = TaskNode(
        task_id="N-invalid",
        task_type="invalid",
        agent_type="LogAgent",
        required_capabilities=("repair",),
    )
    with pytest.raises(DAGValidationError, match="no registered Agent"):
        planner.validate(TaskDAG(incident_id="inc-w08", nodes=(invalid_node,)))


def test_four_collection_agents_start_in_same_dispatch_batch(tmp_path: Path) -> None:
    context, log_path, gateway, trace = make_context(tmp_path)
    blackboard = Blackboard()
    log_agent = LogAgent(gateway, blackboard)
    metrics_agent = MetricsAgent(gateway, blackboard)
    config_agent = ConfigAgent(gateway, blackboard)
    dependency_agent = DependencyAgent(gateway, blackboard)
    barrier = Barrier(4)

    def log_executor(
        context: RunContext,
        node: TaskNode,
        agent: AgentCard,
    ) -> TaskOutcome:
        barrier.wait(timeout=2)
        evidence = log_agent.collect(
            context,
            MinimalAnalysisTask(
                incident_id=context.incident_id,
                service=context.target.service,
                log_path=log_path,
                objective=context.objective,
            ),
        )
        return TaskOutcome(success=True, result_ref=evidence.evidence_id)

    def metrics_executor(
        context: RunContext,
        node: TaskNode,
        agent: AgentCard,
    ) -> TaskOutcome:
        barrier.wait(timeout=2)
        evidence = metrics_agent.collect(context)
        return TaskOutcome(success=True, result_ref=evidence.evidence_id)

    def config_executor(
        context: RunContext,
        node: TaskNode,
        agent: AgentCard,
    ) -> TaskOutcome:
        barrier.wait(timeout=2)
        evidence = config_agent.collect(
            context,
            config_path="/etc/web-app/config.yaml",
        )
        return TaskOutcome(success=True, result_ref=evidence.evidence_id)

    def dependency_executor(
        context: RunContext,
        node: TaskNode,
        agent: AgentCard,
    ) -> TaskOutcome:
        barrier.wait(timeout=2)
        evidence = dependency_agent.collect(context)
        return TaskOutcome(success=True, result_ref=evidence.evidence_id)

    executors: dict[str, NodeExecutor] = {
        "N0": success_executor,
        "N1": log_executor,
        "N2": metrics_executor,
        "N3": config_executor,
        "N4": dependency_executor,
    }
    dag = build_fixed_task_dag(context.incident_id)
    report = Scheduler(
        dag=dag,
        context=context,
        trace=trace,
        executors=executors,
        max_concurrency=4,
        max_retries=1,
    ).run()

    assert report.gate_ready is True
    assert report.ready_tasks == ("N5",)
    assert report.failed_tasks == ()
    assert all(
        next(node for node in dag.nodes if node.task_id == task_id).status is TaskStatus.SUCCEEDED
        for task_id in ("N1", "N2", "N3", "N4")
    )

    events = trace.read_events()
    collection_starts = [
        event
        for event in events
        if event.event_type == "TASK_STARTED" and event.task_id in {"N1", "N2", "N3", "N4"}
    ]
    assert len(collection_starts) == 4
    assert len({event.details["dispatch_batch_id"] for event in collection_starts}) == 1
    assert max(event.timestamp for event in collection_starts) - min(
        event.timestamp for event in collection_starts
    ) < timedelta(seconds=1)

    collection_finishes = [
        event
        for event in events
        if event.event_type == "TASK_FINISHED" and event.task_id in {"N1", "N2", "N3", "N4"}
    ]
    diagnose_ready = next(
        event for event in events if event.event_type == "TASK_READY" and event.task_id == "N5"
    )
    assert diagnose_ready.timestamp > max(event.timestamp for event in collection_finishes)


def test_retryable_collection_failure_recovers_before_diagnose(
    tmp_path: Path,
) -> None:
    context, _, _, trace = make_context(tmp_path)
    calls = {"N1": 0}

    def flaky_log_executor(
        context: RunContext,
        node: TaskNode,
        agent: AgentCard,
    ) -> TaskOutcome:
        calls["N1"] += 1
        if calls["N1"] == 1:
            return TaskOutcome(success=False, error="temporary read failure", retryable=True)
        return TaskOutcome(success=True, result_ref="evidence-log")

    dag = build_fixed_task_dag(context.incident_id)
    report = Scheduler(
        dag=dag,
        context=context,
        trace=trace,
        executors={
            "N0": success_executor,
            "N1": flaky_log_executor,
            "N2": success_executor,
            "N3": success_executor,
            "N4": success_executor,
        },
        max_concurrency=4,
        max_retries=1,
    ).run()

    assert report.gate_ready is True
    assert calls["N1"] == 2
    assert report.retry_counts == {"N1": 1}
    assert next(node for node in dag.nodes if node.task_id == "N1").attempt == 2


def test_diagnose_starts_after_all_collection_tasks_finish(tmp_path: Path) -> None:
    context, _, _, trace = make_context(tmp_path)
    diagnose_calls: list[str] = []

    def diagnose_executor(
        context: RunContext,
        node: TaskNode,
        agent: AgentCard,
    ) -> TaskOutcome:
        diagnose_calls.append(node.task_id)
        return TaskOutcome(success=True, result_ref="diagnosis-ready")

    dag = build_fixed_task_dag(context.incident_id)
    Scheduler(
        dag=dag,
        context=context,
        trace=trace,
        executors={
            "N0": success_executor,
            "N1": success_executor,
            "N2": success_executor,
            "N3": success_executor,
            "N4": success_executor,
            "N5": diagnose_executor,
        },
        max_concurrency=4,
        max_retries=1,
    ).run()

    events = trace.read_events()
    collection_finishes = [
        event
        for event in events
        if event.event_type == "TASK_FINISHED" and event.task_id in {"N1", "N2", "N3", "N4"}
    ]
    diagnose_start = next(
        event for event in events if event.event_type == "TASK_STARTED" and event.task_id == "N5"
    )
    assert diagnose_calls == ["N5"]
    assert diagnose_start.timestamp > max(event.timestamp for event in collection_finishes)


def test_exhausted_collection_failure_blocks_diagnose(tmp_path: Path) -> None:
    context, _, _, trace = make_context(tmp_path)
    calls = {"N1": 0}

    def failing_log_executor(
        context: RunContext,
        node: TaskNode,
        agent: AgentCard,
    ) -> TaskOutcome:
        calls["N1"] += 1
        return TaskOutcome(success=False, error="persistent read failure", retryable=True)

    dag = build_fixed_task_dag(context.incident_id)
    report = Scheduler(
        dag=dag,
        context=context,
        trace=trace,
        executors={
            "N0": success_executor,
            "N1": failing_log_executor,
            "N2": success_executor,
            "N3": success_executor,
            "N4": success_executor,
        },
        max_concurrency=4,
        max_retries=1,
    ).run()

    assert report.gate_ready is False
    assert report.failed_tasks == ("N1",)
    assert calls["N1"] == 2
    nodes = {node.task_id: node for node in dag.nodes}
    assert nodes["N1"].status is TaskStatus.FAILED_FINAL
    assert nodes["N5"].status is not TaskStatus.READY
