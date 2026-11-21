"""Incident FastAPI service backed by in-memory metadata and JSONL traces."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AwareDatetime, Field, ValidationError

from .benchmark.metrics import BenchmarkSummary
from .config import PROJECT_ROOT, AppConfig, load_config
from .exceptions import (
    AIOSIncidentError,
    IncidentNotFoundError,
    IncidentStateError,
)
from .models import (
    AllowedScope,
    IncidentTarget,
    Message,
    NonEmptyStr,
    PositiveFloat,
    RunContext,
    StrictModel,
    TaskDAG,
    TraceEvent,
    build_fixed_task_dag,
)
from .orchestrator.blackboard import Blackboard
from .orchestrator.trace import JsonlTraceStore
from .state import TaskStatus, WorkflowStatus, is_workflow_terminal, transition_workflow
from .utils import generate_id, utc_now

UI_DIR = Path(__file__).with_name("ui")
DEFAULT_BENCHMARK_RAW = (
    PROJECT_ROOT / "docs" / "experiment_reports" / "raw" / "local_ollama_2026-11-22.json"
)


class IncidentCreateRequest(StrictModel):
    objective: NonEmptyStr
    target: IncidentTarget
    allowed_scope: AllowedScope
    time_budget_seconds: PositiveFloat
    max_repair_attempts: int = Field(default=2, ge=1, le=2)
    success_criteria: tuple[NonEmptyStr, ...] = Field(min_length=1)


class IncidentCreateResponse(StrictModel):
    incident_id: NonEmptyStr
    run_id: NonEmptyStr
    state: WorkflowStatus
    created_at: AwareDatetime


class IncidentStatusResponse(StrictModel):
    incident_id: NonEmptyStr
    run_id: NonEmptyStr
    state: WorkflowStatus
    current_tasks: tuple[str, ...] = ()
    completed_tasks: tuple[str, ...] = ()
    repair_attempt: int = Field(ge=0, le=2)
    elapsed_seconds: int = Field(ge=0)
    final_report: dict[str, Any] | None = None


class IncidentResultResponse(StrictModel):
    incident_id: NonEmptyStr
    run_id: NonEmptyStr
    state: WorkflowStatus
    final_report: dict[str, Any] | None = None


class IncidentEventsResponse(StrictModel):
    incident_id: NonEmptyStr
    run_id: NonEmptyStr
    events: tuple[TraceEvent, ...]
    messages: tuple[Message, ...] = ()


class IncidentHistoryItem(StrictModel):
    incident_id: NonEmptyStr
    run_id: NonEmptyStr
    objective: NonEmptyStr
    service: NonEmptyStr
    state: WorkflowStatus
    created_at: AwareDatetime
    elapsed_seconds: int = Field(ge=0)
    repair_attempt: int = Field(ge=0, le=2)


class IncidentHistoryResponse(StrictModel):
    incidents: tuple[IncidentHistoryItem, ...]


class BenchmarkDashboardResponse(StrictModel):
    available: bool
    summary: BenchmarkSummary | None = None
    raw_path: NonEmptyStr | None = None
    error: NonEmptyStr | None = None


@dataclass(slots=True)
class IncidentRecord:
    context: RunContext
    dag: TaskDAG
    trace: JsonlTraceStore
    final_report: dict[str, Any] | None = None
    repair_attempt: int = 0


class IncidentService:
    """Own incident state, isolation boundaries and append-only traces."""

    def __init__(self, config: AppConfig, trace_root: Path) -> None:
        self.config = config
        self.trace_root = trace_root
        self.blackboard = Blackboard()
        self._records: dict[str, IncidentRecord] = {}
        self._lock = RLock()
        self._load_persisted_records()

    def create(self, request: IncidentCreateRequest) -> IncidentCreateResponse:
        with self._lock:
            created_at = utc_now()
            incident_id = self._new_incident_id(created_at)
            run_id = generate_id("run", at=created_at)
            context = RunContext(
                run_id=run_id,
                incident_id=incident_id,
                objective=request.objective,
                target=request.target,
                allowed_scope=request.allowed_scope,
                time_budget_seconds=request.time_budget_seconds,
                max_repair_attempts=request.max_repair_attempts,
                success_criteria=request.success_criteria,
                workflow_status=WorkflowStatus.CREATED,
                created_at=created_at,
            )
            dag = build_fixed_task_dag(
                incident_id,
                max_repair_attempts=request.max_repair_attempts,
            )
            trace = JsonlTraceStore(self.trace_root, incident_id, run_id)
            trace.append(
                TraceEvent(
                    trace_id=generate_id("trace", at=created_at),
                    incident_id=incident_id,
                    task_id="N0",
                    agent_id="incident-api",
                    event_type="INCIDENT_CREATED",
                    status=WorkflowStatus.CREATED.value,
                    timestamp=created_at,
                    details={
                        "run_id": run_id,
                        "target": request.target.model_dump(mode="json"),
                    },
                )
            )
            trace.append(
                TraceEvent(
                    trace_id=generate_id("trace", at=created_at),
                    incident_id=incident_id,
                    task_id="N0",
                    agent_id="CoordinatorAgent",
                    event_type="DAG_INSTANTIATED",
                    status=TaskStatus.CREATED.value,
                    timestamp=created_at,
                    details={"node_count": len(dag.nodes)},
                )
            )
            self._records[incident_id] = IncidentRecord(context=context, dag=dag, trace=trace)
            self._persist_record(self._records[incident_id])
            return IncidentCreateResponse(
                incident_id=incident_id,
                run_id=run_id,
                state=context.workflow_status,
                created_at=created_at,
            )

    def get_status(self, incident_id: str) -> IncidentStatusResponse:
        record = self._get_record(incident_id)
        completed = tuple(
            node.task_id for node in record.dag.nodes if node.status is TaskStatus.SUCCEEDED
        )
        current = tuple(
            node.task_id
            for node in record.dag.nodes
            if node.status
            in {
                TaskStatus.READY,
                TaskStatus.ASSIGNED,
                TaskStatus.RUNNING,
                TaskStatus.VERIFYING,
            }
        )
        elapsed = max(
            0,
            int((utc_now() - record.context.created_at).total_seconds()),
        )
        return IncidentStatusResponse(
            incident_id=record.context.incident_id,
            run_id=record.context.run_id,
            state=record.context.workflow_status,
            current_tasks=current,
            completed_tasks=completed,
            repair_attempt=record.repair_attempt,
            elapsed_seconds=elapsed,
            final_report=record.final_report,
        )

    def get_dag(self, incident_id: str) -> TaskDAG:
        return self._get_record(incident_id).dag

    def get_result(self, incident_id: str) -> IncidentResultResponse:
        record = self._get_record(incident_id)
        return IncidentResultResponse(
            incident_id=record.context.incident_id,
            run_id=record.context.run_id,
            state=record.context.workflow_status,
            final_report=record.final_report,
        )

    def get_events(self, incident_id: str) -> IncidentEventsResponse:
        record = self._get_record(incident_id)
        return IncidentEventsResponse(
            incident_id=record.context.incident_id,
            run_id=record.context.run_id,
            events=record.trace.read_events(),
        )

    def cancel(self, incident_id: str) -> IncidentStatusResponse:
        with self._lock:
            record = self._get_record(incident_id)
            current = record.context.workflow_status
            if current is WorkflowStatus.CANCELLED:
                return self.get_status(incident_id)
            if is_workflow_terminal(current):
                raise IncidentStateError(
                    f"incident cannot be cancelled from terminal state {current.value}"
                )
            target = transition_workflow(current, WorkflowStatus.CANCELLED)
            cancelled_at = utc_now()
            record.trace.append(
                TraceEvent(
                    trace_id=generate_id("trace", at=cancelled_at),
                    incident_id=incident_id,
                    task_id="N0",
                    agent_id="incident-api",
                    event_type="INCIDENT_CANCELLED",
                    status=target.value,
                    timestamp=cancelled_at,
                )
            )
            record.context = record.context.model_copy(update={"workflow_status": target})
            self._persist_record(record)
        return self.get_status(incident_id)

    def history(self) -> IncidentHistoryResponse:
        with self._lock:
            records = sorted(
                self._records.values(),
                key=lambda record: record.context.created_at,
                reverse=True,
            )
            items = tuple(
                IncidentHistoryItem(
                    incident_id=record.context.incident_id,
                    run_id=record.context.run_id,
                    objective=record.context.objective,
                    service=record.context.target.service,
                    state=record.context.workflow_status,
                    created_at=record.context.created_at,
                    elapsed_seconds=max(
                        0,
                        int((utc_now() - record.context.created_at).total_seconds()),
                    ),
                    repair_attempt=record.repair_attempt,
                )
                for record in records
            )
        return IncidentHistoryResponse(incidents=items)

    def _get_record(self, incident_id: str) -> IncidentRecord:
        with self._lock:
            record = self._records.get(incident_id)
        if record is None:
            raise IncidentNotFoundError(f"incident not found: {incident_id}")
        return record

    def _new_incident_id(self, created_at: AwareDatetime) -> str:
        while True:
            incident_id = generate_id("inc", at=created_at)
            if incident_id not in self._records:
                return incident_id

    def _metadata_path(self, record: IncidentRecord) -> Path:
        return self.trace_root / record.context.incident_id / f"{record.context.run_id}.meta.json"

    def _persist_record(self, record: IncidentRecord) -> None:
        path = self._metadata_path(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "context": record.context.model_dump(mode="json"),
            "dag": record.dag.model_dump(mode="json"),
            "final_report": record.final_report,
            "repair_attempt": record.repair_attempt,
        }
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(path)

    def _load_persisted_records(self) -> None:
        if not self.trace_root.exists():
            return
        for path in self.trace_root.glob("*/*.meta.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                context = RunContext.model_validate(payload["context"])
                dag = TaskDAG.model_validate(payload["dag"])
                trace = JsonlTraceStore(
                    self.trace_root,
                    context.incident_id,
                    context.run_id,
                )
                record = IncidentRecord(
                    context=context,
                    dag=dag,
                    trace=trace,
                    final_report=payload.get("final_report"),
                    repair_attempt=int(payload.get("repair_attempt", 0)),
                )
                self._records[context.incident_id] = record
            except (OSError, KeyError, ValueError, ValidationError, AIOSIncidentError):
                continue


def create_app(
    config: AppConfig | None = None,
    *,
    trace_root: Path | None = None,
    benchmark_raw_path: Path | None = None,
) -> FastAPI:
    """Create an isolated API application for production or tests."""

    app_config = config or load_config()
    root = trace_root or (PROJECT_ROOT / app_config.runtime.output_dir)
    benchmark_path = benchmark_raw_path or DEFAULT_BENCHMARK_RAW
    service = IncidentService(app_config, root)

    app = FastAPI(
        title="AIOS Linux Incident API",
        version="0.1.0",
    )
    app.state.incident_service = service
    app.state.blackboard = service.blackboard
    app.state.benchmark_raw_path = benchmark_path

    app.mount("/ui-assets", StaticFiles(directory=UI_DIR), name="ui-assets")

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _request: object,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "INVALID_INCIDENT_REQUEST",
                    "message": "request validation failed",
                    "details": jsonable_encoder(exc.errors()),
                }
            },
        )

    @app.exception_handler(AIOSIncidentError)
    async def domain_error_handler(_request: object, exc: AIOSIncidentError) -> JSONResponse:
        return JSONResponse(
            status_code=getattr(exc, "status_code", 500),
            content={
                "error": {
                    "code": getattr(exc, "code", "INTERNAL_ERROR"),
                    "message": str(exc),
                    "details": [],
                }
            },
        )

    @app.post(
        "/api/v1/incidents",
        response_model=IncidentCreateResponse,
        status_code=201,
    )
    def create_incident(request: IncidentCreateRequest) -> IncidentCreateResponse:
        return service.create(request)

    @app.get("/", include_in_schema=False)
    def dashboard_page() -> FileResponse:
        return FileResponse(UI_DIR / "index.html")

    @app.get("/api/v1/incidents", response_model=IncidentHistoryResponse)
    def list_incidents() -> IncidentHistoryResponse:
        return service.history()

    @app.get(
        "/api/v1/benchmarks/latest",
        response_model=BenchmarkDashboardResponse,
    )
    def get_latest_benchmark() -> BenchmarkDashboardResponse:
        try:
            payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
            summary = BenchmarkSummary.model_validate(payload["summary"])
            return BenchmarkDashboardResponse(
                available=True,
                summary=summary,
                raw_path=str(benchmark_path),
            )
        except (OSError, KeyError, ValueError, ValidationError) as exc:
            return BenchmarkDashboardResponse(
                available=False,
                raw_path=str(benchmark_path),
                error=f"benchmark data unavailable: {exc}",
            )

    @app.get(
        "/api/v1/incidents/{incident_id}",
        response_model=IncidentStatusResponse,
    )
    def get_incident(incident_id: str) -> IncidentStatusResponse:
        return service.get_status(incident_id)

    @app.get(
        "/api/v1/incidents/{incident_id}/dag",
        response_model=TaskDAG,
    )
    def get_incident_dag(incident_id: str) -> TaskDAG:
        return service.get_dag(incident_id)

    @app.get(
        "/api/v1/incidents/{incident_id}/events",
        response_model=IncidentEventsResponse,
    )
    def get_incident_events(incident_id: str) -> IncidentEventsResponse:
        return service.get_events(incident_id)

    @app.get(
        "/api/v1/incidents/{incident_id}/result",
        response_model=IncidentResultResponse,
    )
    def get_incident_result(incident_id: str) -> IncidentResultResponse:
        return service.get_result(incident_id)

    @app.post(
        "/api/v1/incidents/{incident_id}/cancel",
        response_model=IncidentStatusResponse,
    )
    def cancel_incident(incident_id: str) -> IncidentStatusResponse:
        return service.cancel(incident_id)

    return app


app = create_app()
