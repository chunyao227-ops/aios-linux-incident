"""W03 structured model, DAG and serialization tests."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from aios_incident.exceptions import InputValidationError
from aios_incident.models import (
    AgentCard,
    AgentStatus,
    AllowedScope,
    Diagnosis,
    Evidence,
    EvidenceKind,
    IncidentTarget,
    Message,
    MessageType,
    RepairAction,
    RepairActionResult,
    RepairPlan,
    RepairResult,
    RepairStatus,
    RiskLevel,
    RootCauseCandidate,
    RunContext,
    TaskDAG,
    TaskNode,
    TokenUsage,
    TraceEvent,
    VerificationCheck,
    VerificationResult,
    build_fixed_task_dag,
)
from aios_incident.validation import (
    get_json_schema,
    model_from_json,
    model_to_json,
    validate_json_schema,
    validate_json_text,
    validate_model,
)

T0 = "2026-11-19T12:00:00+08:00"
T1 = "2026-11-19T12:01:00+08:00"
INCIDENT_ID = "inc-20261119-001"


def make_run_context() -> RunContext:
    return RunContext(
        run_id="run-001",
        incident_id=INCIDENT_ID,
        objective="诊断并修复 web-app 不可用问题",
        target=IncidentTarget(host="sandbox-01", service="web-app", environment="docker"),
        allowed_scope=AllowedScope(
            read_paths=("/var/log", "/etc/web-app"),
            write_paths=("/etc/web-app",),
            allowed_services=("web-app", "postgresql"),
        ),
        time_budget_seconds=600,
        max_repair_attempts=2,
        success_criteria=("health_endpoint_returns_200", "smoke_test_passes"),
        created_at=T0,
    )


def make_evidence() -> Evidence:
    return Evidence(
        evidence_id="evi-N1-001",
        incident_id=INCIDENT_ID,
        task_id="N1",
        producer_agent="LogAgent",
        kind=EvidenceKind.LOG,
        summary="web-app 连续报告数据库连接被拒绝",
        source_ref="/var/log/web-app/error.log:318",
        observed_at=T0,
        facts={"error_code": "ECONNREFUSED", "target": "127.0.0.1:5432"},
        confidence=0.91,
    )


def make_diagnosis() -> Diagnosis:
    root_cause = RootCauseCandidate(
        root_cause_id="rc-001",
        description="数据库服务未运行",
        supporting_evidence=("evi-N1-001",),
        confidence=0.88,
        repair_risk=RiskLevel.MEDIUM,
        required_scope=("postgresql",),
    )
    return Diagnosis(
        diagnosis_id="diag-001",
        incident_id=INCIDENT_ID,
        root_causes=(root_cause,),
        selected_root_cause_ids=("rc-001",),
        repair_constraints=("only_operate_postgresql",),
        created_at=T0,
    )


def make_repair_plan() -> RepairPlan:
    action = RepairAction(
        action_id="act-001",
        description="启动 PostgreSQL 服务",
        tool_name="controlled_service_start",
        parameters={"service": "postgresql"},
        timeout_seconds=30,
    )
    return RepairPlan(
        repair_id="repair-001",
        incident_id=INCIDENT_ID,
        root_cause_ids=("rc-001",),
        actions=(action,),
        preconditions=("container_is_healthy",),
        expected_effect="PostgreSQL 恢复监听",
        risk_level=RiskLevel.MEDIUM,
        rollback_plan=("重新停止 PostgreSQL 服务",),
        timeout_seconds=60,
        created_at=T0,
    )


def make_repair_result() -> RepairResult:
    action_result = RepairActionResult(
        action_id="act-001",
        success=True,
        return_code=0,
        output_summary="service started",
        duration_ms=1200,
    )
    return RepairResult(
        repair_id="repair-001",
        incident_id=INCIDENT_ID,
        status=RepairStatus.SUCCEEDED,
        action_results=(action_result,),
        started_at=T0,
        ended_at=T1,
    )


def make_verification_result() -> VerificationResult:
    return VerificationResult(
        verification_id="verify-001",
        incident_id=INCIDENT_ID,
        repair_id="repair-001",
        passed=True,
        checks=(
            VerificationCheck(name="health_endpoint", passed=True, details={"status": 200}),
            VerificationCheck(name="smoke_test", passed=True),
        ),
        started_at=T0,
        ended_at=T1,
    )


def test_run_context_uses_structured_nested_objects() -> None:
    context = make_run_context()
    assert context.target.environment == "docker"
    assert context.allowed_scope.write_paths == ("/etc/web-app",)
    assert context.max_repair_attempts == 2


def test_scope_rejects_relative_paths() -> None:
    with pytest.raises(ValidationError, match="absolute Linux paths"):
        AllowedScope(read_paths=("var/log",))


def test_fixed_dag_contains_parallel_collection_and_two_repair_rounds() -> None:
    dag = build_fixed_task_dag(INCIDENT_ID)
    order = dag.topological_order()
    node_ids = {node.task_id for node in dag.nodes}

    assert {"N6.1", "N7.1", "N6.2", "N7.2"} <= node_ids
    assert order[:5] == ("N0", "N1", "N2", "N3", "N4")
    assert order.index("N5") > max(order.index(node_id) for node_id in ("N1", "N2", "N3", "N4"))
    assert order.index("N7.2") == len(order) - 1


def test_dag_rejects_self_reference() -> None:
    with pytest.raises(ValidationError, match="cannot depend on itself"):
        TaskNode(
            task_id="N1",
            task_type="log_analysis",
            agent_type="LogAgent",
            required_capabilities=("log_analysis",),
            depends_on=("N1",),
        )


def test_dag_rejects_missing_dependency() -> None:
    node = TaskNode(
        task_id="N1",
        task_type="log_analysis",
        agent_type="LogAgent",
        required_capabilities=("log_analysis",),
        depends_on=("N0",),
    )
    with pytest.raises(ValidationError, match="unknown dependencies"):
        TaskDAG(incident_id=INCIDENT_ID, nodes=(node,))


def test_dag_rejects_cycles() -> None:
    first = TaskNode(
        task_id="N1",
        task_type="log_analysis",
        agent_type="LogAgent",
        required_capabilities=("log_analysis",),
        depends_on=("N2",),
    )
    second = TaskNode(
        task_id="N2",
        task_type="metrics_analysis",
        agent_type="MetricsAgent",
        required_capabilities=("metrics_analysis",),
        depends_on=("N1",),
    )
    with pytest.raises(ValidationError, match="contains a cycle"):
        TaskDAG(incident_id=INCIDENT_ID, nodes=(first, second))


def test_agent_card_enforces_capacity_and_unique_capabilities() -> None:
    card = AgentCard(
        agent_id="log-agent-01",
        agent_type="LogAgent",
        capabilities=("log_analysis",),
        status=AgentStatus.IDLE,
        max_concurrency=2,
        last_heartbeat=T0,
    )
    assert card.current_task_count == 0

    with pytest.raises(ValidationError, match="cannot exceed max_concurrency"):
        AgentCard(
            agent_id="log-agent-02",
            agent_type="LogAgent",
            capabilities=("log_analysis",),
            current_task_count=2,
            max_concurrency=1,
        )
    with pytest.raises(ValidationError, match="capabilities values must be unique"):
        AgentCard(
            agent_id="log-agent-03",
            agent_type="LogAgent",
            capabilities=("log_analysis", "log_analysis"),
        )


def test_evidence_is_immutable() -> None:
    evidence = make_evidence()
    with pytest.raises(ValidationError, match="frozen"):
        evidence.summary = "changed"


def test_message_requires_distinct_agents_and_reply_reference() -> None:
    question = Message(
        message_id="msg-001",
        incident_id=INCIDENT_ID,
        task_id="N1",
        from_agent="LogAgent",
        to_agent="ConfigAgent",
        type=MessageType.QUESTION,
        content="请核对 web-app 的实际监听端口。",
        evidence_ids=("evi-N1-001",),
        timestamp=T0,
    )
    reply = Message(
        message_id="msg-002",
        incident_id=INCIDENT_ID,
        task_id="N1",
        from_agent="ConfigAgent",
        to_agent="LogAgent",
        type=MessageType.REPLY,
        content="配置监听 5432 端口。",
        reply_to=question.message_id,
        timestamp=T1,
    )
    assert reply.reply_to == question.message_id

    with pytest.raises(ValidationError, match="must be different"):
        Message(
            message_id="msg-003",
            incident_id=INCIDENT_ID,
            task_id="N1",
            from_agent="LogAgent",
            to_agent="LogAgent",
            type=MessageType.QUESTION,
            content="invalid self message",
        )
    with pytest.raises(ValidationError, match="must reference reply_to"):
        Message(
            message_id="msg-004",
            incident_id=INCIDENT_ID,
            task_id="N1",
            from_agent="ConfigAgent",
            to_agent="LogAgent",
            type=MessageType.REPLY,
            content="missing reference",
        )


def test_repair_and_verification_time_order_is_enforced() -> None:
    with pytest.raises(ValidationError, match="ended_at cannot precede"):
        RepairResult(
            repair_id="repair-001",
            incident_id=INCIDENT_ID,
            status=RepairStatus.SUCCEEDED,
            started_at=T1,
            ended_at=T0,
        )
    with pytest.raises(ValidationError, match="must include failure reasons"):
        VerificationResult(
            verification_id="verify-001",
            incident_id=INCIDENT_ID,
            repair_id="repair-001",
            passed=False,
            checks=(VerificationCheck(name="health_endpoint", passed=False),),
            started_at=T0,
            ended_at=T1,
        )


def test_all_contracts_serialize_and_deserialize() -> None:
    contracts = [
        make_run_context(),
        AgentCard(
            agent_id="log-agent-01",
            agent_type="LogAgent",
            capabilities=("log_analysis",),
            last_heartbeat=T0,
        ),
        make_evidence(),
        Message(
            message_id="msg-001",
            incident_id=INCIDENT_ID,
            task_id="N1",
            from_agent="LogAgent",
            to_agent="ConfigAgent",
            type=MessageType.QUESTION,
            content="请核对端口。",
            timestamp=T0,
        ),
        make_diagnosis(),
        make_repair_plan(),
        make_repair_result(),
        make_verification_result(),
        TraceEvent(
            trace_id="trace-001",
            incident_id=INCIDENT_ID,
            task_id="N1",
            agent_id="log-agent-01",
            event_type="TASK_FINISHED",
            status="SUCCEEDED",
            timestamp=T0,
            duration_ms=5230,
            token_usage=TokenUsage(prompt=1800, completion=420),
            tool_calls=6,
            parent_task_id="N0",
        ),
    ]

    for contract in contracts:
        restored = model_from_json(model_to_json(contract), type(contract))
        assert restored == contract


def test_json_schema_rejects_unknown_fields_and_invalid_json() -> None:
    payload = make_evidence().model_dump(mode="json")
    payload["unexpected"] = True

    with pytest.raises(InputValidationError, match="JSON Schema validation failed"):
        validate_json_schema(payload, Evidence)
    with pytest.raises(InputValidationError, match="Additional properties"):
        validate_model(payload, Evidence)
    with pytest.raises(InputValidationError, match="invalid JSON"):
        validate_json_text("{", Evidence)

    schema = get_json_schema(Evidence)
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["EvidenceKind"]["enum"] == [
        "log",
        "metrics",
        "config",
        "dependency",
    ]


@pytest.mark.parametrize(
    "model_type",
    [
        RunContext,
        TaskNode,
        TaskDAG,
        AgentCard,
        Evidence,
        Message,
        Diagnosis,
        RepairPlan,
        RepairResult,
        VerificationResult,
        TraceEvent,
    ],
)
def test_all_contracts_produce_valid_json_schema(model_type: type) -> None:
    schema = get_json_schema(model_type)
    assert schema["additionalProperties"] is False


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        RunContext(
            run_id="run-001",
            incident_id=INCIDENT_ID,
            objective="test",
            target=IncidentTarget(host="sandbox-01", service="web-app", environment="docker"),
            allowed_scope=AllowedScope(),
            time_budget_seconds=600,
            max_repair_attempts=2,
            success_criteria=("health_check",),
            created_at=datetime(2026, 11, 19, 12, 0, 0),
        )
