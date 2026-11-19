"""Cross-module structured data contracts for the incident workflow."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from .state import TaskStatus, WorkflowStatus
from .utils import utc_now

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveFloat = Annotated[float, Field(gt=0)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class StrictModel(BaseModel):
    """Reject unknown fields and whitespace-only identifiers."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class ImmutableModel(StrictModel):
    """Base class for evidence and other append-only records."""

    model_config = ConfigDict(frozen=True)


class AgentStatus(str, Enum):
    IDLE = "IDLE"
    BUSY = "BUSY"
    OFFLINE = "OFFLINE"


class EvidenceKind(str, Enum):
    LOG = "log"
    METRICS = "metrics"
    CONFIG = "config"
    DEPENDENCY = "dependency"


class MessageType(str, Enum):
    ASSIGN = "ASSIGN"
    RESULT = "RESULT"
    QUESTION = "QUESTION"
    REPLY = "REPLY"
    HANDOFF = "HANDOFF"
    FEEDBACK = "FEEDBACK"
    ABORT = "ABORT"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RepairStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"


class IncidentTarget(StrictModel):
    host: NonEmptyStr
    service: NonEmptyStr
    environment: NonEmptyStr


class AllowedScope(StrictModel):
    read_paths: tuple[NonEmptyStr, ...] = ()
    write_paths: tuple[NonEmptyStr, ...] = ()
    allowed_services: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_paths_and_services(self) -> AllowedScope:
        for path in (*self.read_paths, *self.write_paths):
            if not path.startswith("/"):
                raise ValueError("scope paths must be absolute Linux paths")
        for label, values in (
            ("read_paths", self.read_paths),
            ("write_paths", self.write_paths),
            ("allowed_services", self.allowed_services),
        ):
            _ensure_unique(values, label)
        return self


class RunContext(StrictModel):
    run_id: NonEmptyStr
    incident_id: NonEmptyStr
    objective: NonEmptyStr
    target: IncidentTarget
    allowed_scope: AllowedScope
    time_budget_seconds: PositiveFloat
    max_repair_attempts: int = Field(ge=1, le=2)
    success_criteria: tuple[NonEmptyStr, ...] = Field(min_length=1)
    workflow_status: WorkflowStatus = WorkflowStatus.CREATED
    created_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_success_criteria(self) -> RunContext:
        _ensure_unique(self.success_criteria, "success_criteria")
        return self


class TaskConstraints(StrictModel):
    max_tokens: PositiveInt = 2048
    max_tool_calls: NonNegativeInt = 12


class TaskNode(StrictModel):
    task_id: NonEmptyStr
    task_type: NonEmptyStr
    agent_type: NonEmptyStr
    required_capabilities: tuple[NonEmptyStr, ...] = Field(min_length=1)
    depends_on: tuple[NonEmptyStr, ...] = ()
    attempt: PositiveInt = 1
    deadline: AwareDatetime | None = None
    constraints: TaskConstraints = Field(default_factory=TaskConstraints)
    status: TaskStatus = TaskStatus.CREATED

    @model_validator(mode="after")
    def validate_references(self) -> TaskNode:
        if self.task_id in self.depends_on:
            raise ValueError("task cannot depend on itself")
        _ensure_unique(self.required_capabilities, "required_capabilities")
        _ensure_unique(self.depends_on, "depends_on")
        return self


class TaskDAG(StrictModel):
    incident_id: NonEmptyStr
    nodes: tuple[TaskNode, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_graph(self) -> TaskDAG:
        node_ids = [node.task_id for node in self.nodes]
        _ensure_unique(node_ids, "task_id")
        known_ids = set(node_ids)
        for node in self.nodes:
            missing = set(node.depends_on) - known_ids
            if missing:
                raise ValueError(
                    f"task {node.task_id} references unknown dependencies: {sorted(missing)}"
                )
        self.topological_order()
        return self

    def topological_order(self) -> tuple[str, ...]:
        """Return a deterministic topological order or reject cycles."""

        by_id = {node.task_id: node for node in self.nodes}
        in_degree = {node_id: len(node.depends_on) for node_id, node in by_id.items()}
        dependents: dict[str, list[str]] = {node_id: [] for node_id in by_id}
        for node in self.nodes:
            for dependency in node.depends_on:
                dependents[dependency].append(node.task_id)

        ready = sorted(node_id for node_id, degree in in_degree.items() if degree == 0)
        ordered: list[str] = []
        while ready:
            node_id = ready.pop(0)
            ordered.append(node_id)
            for dependent in sorted(dependents[node_id]):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    ready.append(dependent)
            ready.sort()

        if len(ordered) != len(self.nodes):
            cyclic = sorted(node_id for node_id, degree in in_degree.items() if degree > 0)
            raise ValueError(f"task DAG contains a cycle involving: {cyclic}")
        return tuple(ordered)


def build_fixed_task_dag(incident_id: str, *, max_repair_attempts: int = 2) -> TaskDAG:
    """Instantiate the frozen N0-N7 task graph for up to two repair rounds."""

    if max_repair_attempts not in {1, 2}:
        raise ValueError("max_repair_attempts must be 1 or 2")

    nodes = [
        TaskNode(
            task_id="N0",
            task_type="validate_and_plan",
            agent_type="CoordinatorAgent",
            required_capabilities=("planning", "fusion"),
        ),
        TaskNode(
            task_id="N1",
            task_type="log_analysis",
            agent_type="LogAgent",
            required_capabilities=("log_analysis",),
            depends_on=("N0",),
        ),
        TaskNode(
            task_id="N2",
            task_type="metrics_analysis",
            agent_type="MetricsAgent",
            required_capabilities=("metrics_analysis",),
            depends_on=("N0",),
        ),
        TaskNode(
            task_id="N3",
            task_type="config_analysis",
            agent_type="ConfigAgent",
            required_capabilities=("config_analysis",),
            depends_on=("N0",),
        ),
        TaskNode(
            task_id="N4",
            task_type="dependency_analysis",
            agent_type="DependencyAgent",
            required_capabilities=("dependency_analysis",),
            depends_on=("N0",),
        ),
        TaskNode(
            task_id="N5",
            task_type="diagnose",
            agent_type="CoordinatorAgent",
            required_capabilities=("planning", "fusion"),
            depends_on=("N1", "N2", "N3", "N4"),
        ),
    ]
    for attempt in range(1, max_repair_attempts + 1):
        repair_id = f"N6.{attempt}"
        verify_id = f"N7.{attempt}"
        repair_dependencies = ("N5",) if attempt == 1 else ("N5", f"N7.{attempt - 1}")
        nodes.extend(
            [
                TaskNode(
                    task_id=repair_id,
                    task_type="repair",
                    agent_type="RepairAgent",
                    required_capabilities=("repair",),
                    depends_on=repair_dependencies,
                    attempt=attempt,
                ),
                TaskNode(
                    task_id=verify_id,
                    task_type="verification",
                    agent_type="VerifierAgent",
                    required_capabilities=("verification",),
                    depends_on=(repair_id,),
                    attempt=attempt,
                ),
            ]
        )
    return TaskDAG(incident_id=incident_id, nodes=tuple(nodes))


class AgentCard(StrictModel):
    agent_id: NonEmptyStr
    agent_type: NonEmptyStr
    capabilities: tuple[NonEmptyStr, ...] = Field(min_length=1)
    status: AgentStatus = AgentStatus.IDLE
    current_task_count: NonNegativeInt = 0
    max_concurrency: PositiveInt = 1
    last_heartbeat: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_capacity(self) -> AgentCard:
        _ensure_unique(self.capabilities, "capabilities")
        if self.current_task_count > self.max_concurrency:
            raise ValueError("current_task_count cannot exceed max_concurrency")
        return self


class Evidence(ImmutableModel):
    evidence_id: NonEmptyStr
    incident_id: NonEmptyStr
    task_id: NonEmptyStr
    producer_agent: NonEmptyStr
    kind: EvidenceKind
    summary: NonEmptyStr
    source_ref: NonEmptyStr
    observed_at: AwareDatetime
    facts: dict[str, Any]
    confidence: Confidence


class Message(StrictModel):
    message_id: NonEmptyStr
    incident_id: NonEmptyStr
    task_id: NonEmptyStr
    from_agent: NonEmptyStr
    to_agent: NonEmptyStr
    type: MessageType
    content: NonEmptyStr
    evidence_ids: tuple[NonEmptyStr, ...] = ()
    reply_to: NonEmptyStr | None = None
    timestamp: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_protocol(self) -> Message:
        if self.from_agent == self.to_agent:
            raise ValueError("message sender and recipient must be different Agents")
        if self.type is MessageType.REPLY and self.reply_to is None:
            raise ValueError("REPLY message must reference reply_to")
        if self.type is MessageType.QUESTION and self.reply_to is not None:
            raise ValueError("QUESTION message cannot reference reply_to")
        _ensure_unique(self.evidence_ids, "evidence_ids")
        return self


class RootCauseCandidate(ImmutableModel):
    root_cause_id: NonEmptyStr
    description: NonEmptyStr
    supporting_evidence: tuple[NonEmptyStr, ...] = ()
    contradicting_evidence: tuple[NonEmptyStr, ...] = ()
    confidence: Confidence
    repair_risk: RiskLevel
    required_scope: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_evidence_references(self) -> RootCauseCandidate:
        _ensure_unique(self.supporting_evidence, "supporting_evidence")
        _ensure_unique(self.contradicting_evidence, "contradicting_evidence")
        overlap = set(self.supporting_evidence) & set(self.contradicting_evidence)
        if overlap:
            raise ValueError(f"evidence cannot support and contradict: {sorted(overlap)}")
        return self


class Diagnosis(StrictModel):
    diagnosis_id: NonEmptyStr
    incident_id: NonEmptyStr
    root_causes: tuple[RootCauseCandidate, ...] = Field(min_length=1)
    selected_root_cause_ids: tuple[NonEmptyStr, ...] = ()
    excluded_hypotheses: tuple[NonEmptyStr, ...] = ()
    conflicting_evidence: tuple[NonEmptyStr, ...] = ()
    repair_constraints: tuple[NonEmptyStr, ...] = ()
    created_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_selection(self) -> Diagnosis:
        root_ids = [root.root_cause_id for root in self.root_causes]
        _ensure_unique(root_ids, "root_cause_id")
        unknown = set(self.selected_root_cause_ids) - set(root_ids)
        if unknown:
            raise ValueError(f"selected root causes are unknown: {sorted(unknown)}")
        return self


class RepairAction(StrictModel):
    action_id: NonEmptyStr
    description: NonEmptyStr
    tool_name: NonEmptyStr
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: PositiveFloat
    critical: bool = True


class RepairPlan(StrictModel):
    repair_id: NonEmptyStr
    incident_id: NonEmptyStr
    root_cause_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    actions: tuple[RepairAction, ...] = Field(min_length=1)
    preconditions: tuple[NonEmptyStr, ...] = ()
    expected_effect: NonEmptyStr
    risk_level: RiskLevel
    rollback_plan: tuple[NonEmptyStr, ...] = Field(min_length=1)
    timeout_seconds: PositiveFloat
    created_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_actions(self) -> RepairPlan:
        _ensure_unique(self.root_cause_ids, "root_cause_ids")
        _ensure_unique([action.action_id for action in self.actions], "action_id")
        return self


class RepairActionResult(StrictModel):
    action_id: NonEmptyStr
    success: bool
    return_code: int | None = None
    output_summary: NonEmptyStr
    duration_ms: NonNegativeInt
    rolled_back: bool = False


class RepairResult(StrictModel):
    repair_id: NonEmptyStr
    incident_id: NonEmptyStr
    status: RepairStatus
    action_results: tuple[RepairActionResult, ...] = ()
    rollback_performed: bool = False
    error: NonEmptyStr | None = None
    started_at: AwareDatetime
    ended_at: AwareDatetime

    @model_validator(mode="after")
    def validate_result(self) -> RepairResult:
        _validate_time_order(self.started_at, self.ended_at, "repair")
        if self.status is RepairStatus.FAILED and self.error is None:
            raise ValueError("failed repair result must include error")
        if self.status is RepairStatus.ROLLED_BACK and not self.rollback_performed:
            raise ValueError("ROLLED_BACK repair result requires rollback_performed")
        return self


class VerificationCheck(StrictModel):
    name: NonEmptyStr
    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(StrictModel):
    verification_id: NonEmptyStr
    incident_id: NonEmptyStr
    repair_id: NonEmptyStr
    passed: bool
    checks: tuple[VerificationCheck, ...] = Field(min_length=1)
    failure_reasons: tuple[NonEmptyStr, ...] = ()
    started_at: AwareDatetime
    ended_at: AwareDatetime

    @model_validator(mode="after")
    def validate_result(self) -> VerificationResult:
        _validate_time_order(self.started_at, self.ended_at, "verification")
        if self.passed and self.failure_reasons:
            raise ValueError("passed verification cannot include failure reasons")
        if not self.passed and not self.failure_reasons:
            raise ValueError("failed verification must include failure reasons")
        return self


class TokenUsage(StrictModel):
    prompt: NonNegativeInt = 0
    completion: NonNegativeInt = 0


class TraceEvent(StrictModel):
    trace_id: NonEmptyStr
    incident_id: NonEmptyStr
    task_id: NonEmptyStr
    agent_id: NonEmptyStr
    event_type: NonEmptyStr
    status: NonEmptyStr | None = None
    timestamp: AwareDatetime = Field(default_factory=utc_now)
    duration_ms: NonNegativeInt | None = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    tool_calls: NonNegativeInt = 0
    retry_count: NonNegativeInt = 0
    parent_task_id: NonEmptyStr | None = None
    details: dict[str, Any] = Field(default_factory=dict)


def _ensure_unique(values: tuple[str, ...] | list[str], label: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{label} values must be unique")


def _validate_time_order(started_at: datetime, ended_at: datetime, label: str) -> None:
    if ended_at < started_at:
        raise ValueError(f"{label} ended_at cannot precede started_at")
