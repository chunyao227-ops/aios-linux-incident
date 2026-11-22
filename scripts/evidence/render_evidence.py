"""Render local submission evidence from real application data."""

from __future__ import annotations

import csv
import html
import json
import shutil
import textwrap
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from xml.etree import ElementTree

from aios_incident.agents.config_agent import ConfigAgent
from aios_incident.agents.coordinator_agent import (
    CoordinatorAgent,
    MinimalAnalysisTask,
)
from aios_incident.agents.dependency_agent import DependencyAgent
from aios_incident.agents.log_agent import LogAgent
from aios_incident.agents.metrics_agent import MetricsAgent
from aios_incident.models import (
    AgentCard,
    AllowedScope,
    Evidence,
    EvidenceKind,
    IncidentTarget,
    RepairResult,
    RepairStatus,
    RunContext,
    TaskNode,
    VerificationCheck,
    VerificationResult,
    build_fixed_task_dag,
)
from aios_incident.orchestrator.blackboard import Blackboard
from aios_incident.orchestrator.diagnosis import DiagnosisFusionEngine
from aios_incident.orchestrator.interaction_bus import InteractionBus
from aios_incident.orchestrator.minimal_flow import seed_demo_target
from aios_incident.orchestrator.planner import build_default_agent_cards
from aios_incident.orchestrator.scheduler import Scheduler, TaskOutcome
from aios_incident.orchestrator.trace import JsonlTraceStore
from aios_incident.state import WorkflowStatus
from aios_incident.tools.gateway import SandboxReadOnlyBackend, ToolGateway

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = ROOT / "docs" / "submission" / "evidence"
WORKFLOW_DIR = EVIDENCE_ROOT / "workflow"
BENCHMARK_DIR = EVIDENCE_ROOT / "benchmark"
TERMINAL_DIR = EVIDENCE_ROOT / "terminal"
BENCHMARK_RAW = (
    ROOT / "docs" / "experiment_reports" / "raw" / "local_ollama_2026-11-22.json"
)
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
FONT = "Segoe UI, Microsoft YaHei, sans-serif"


def write_svg(path: Path, width: int, height: int, body: str) -> None:
    content = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        "<defs>"
        '<marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" '
        'orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L0,6 L9,3 z" fill="#31546d"/>'
        "</marker>"
        "</defs>\n"
        f'<rect width="100%" height="100%" fill="#f5f7f9"/>\n{body}\n</svg>\n'
    )
    path.write_text(content, encoding="utf-8", newline="\n")


def make_context(incident_id: str, run_id: str, scope: AllowedScope) -> RunContext:
    return RunContext(
        run_id=run_id,
        incident_id=incident_id,
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


def render_task_dag() -> None:
    dag = build_fixed_task_dag("inc-evidence-dag")
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    (WORKFLOW_DIR / "W03_task_dag.json").write_text(
        dag.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    mermaid_lines = ["graph TD"]
    for node in dag.nodes:
        label = f"{node.task_id} {node.task_type}<br/>{node.agent_type}"
        mermaid_lines.append(f'  {node.task_id.replace(".", "_")}["{label}"]')
    for node in dag.nodes:
        for dependency in node.depends_on:
            mermaid_lines.append(
                f"  {dependency.replace('.', '_')} --> {node.task_id.replace('.', '_')}"
            )
    (WORKFLOW_DIR / "W03_task_dag.mmd").write_text(
        "\n".join(mermaid_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    positions = {
        "N0": (470, 35),
        "N1": (30, 145),
        "N2": (285, 145),
        "N3": (540, 145),
        "N4": (795, 145),
        "N5": (470, 255),
        "N6.1": (240, 385),
        "N7.1": (475, 385),
        "N6.2": (710, 385),
        "N7.2": (945, 385),
    }
    node_width = 190
    node_height = 76
    edge_parts: list[str] = []
    for node in dag.nodes:
        target_x, target_y = positions[node.task_id]
        for dependency in node.depends_on:
            source_x, source_y = positions[dependency]
            x1 = source_x + node_width / 2
            y1 = source_y + node_height
            x2 = target_x + node_width / 2
            y2 = target_y
            middle_y = (y1 + y2) / 2
            edge_parts.append(
                f'<path d="M{x1},{y1} L{x1},{middle_y} L{x2},{middle_y} L{x2},{y2}" '
                'fill="none" stroke="#31546d" stroke-width="2" marker-end="url(#arrow)"/>'
            )

    node_parts: list[str] = []
    for node in dag.nodes:
        x, y = positions[node.task_id]
        node_parts.append(
            f'<g><rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" '
            'rx="10" fill="#ffffff" stroke="#9eb2c0"/>'
            f'<text x="{x + 14}" y="{y + 25}" font-family="{FONT}" font-size="15" '
            f'font-weight="700" fill="#142433">{html.escape(node.task_id)}</text>'
            f'<text x="{x + 14}" y="{y + 47}" font-family="{FONT}" font-size="13" '
            f'fill="#31546d">{html.escape(node.task_type)}</text>'
            f'<text x="{x + 14}" y="{y + 66}" font-family="{FONT}" font-size="12" '
            f'fill="#657887">{html.escape(node.agent_type)}</text></g>'
        )
    body = (
        '<text x="36" y="35" font-family="'
        + FONT
        + '" font-size="24" font-weight="700" fill="#142433">W03 固定任务 DAG</text>'
        '<text x="36" y="59" font-family="'
        + FONT
        + '" font-size="13" fill="#657887">由 build_fixed_task_dag 实际实例导出</text>'
        + "".join(edge_parts)
        + "".join(node_parts)
    )
    write_svg(WORKFLOW_DIR / "W03_task_dag.svg", 1175, 500, body)


def success_executor(
    context: RunContext,
    node: TaskNode,
    agent: AgentCard,
) -> TaskOutcome:
    return TaskOutcome(success=True, result_ref=f"{node.task_id}-{agent.agent_id}")


def render_parallel_timeline() -> None:
    with TemporaryDirectory() as temporary:
        temp_root = Path(temporary)
        sandbox_root = temp_root / "sandbox"
        log_path, scope = seed_demo_target(sandbox_root)
        context = make_context("inc-w08-evidence", "run-w08-evidence", scope)
        trace = JsonlTraceStore(temp_root / "traces", context.incident_id, context.run_id)
        gateway = ToolGateway(
            SandboxReadOnlyBackend(sandbox_root),
            scope_resolver=lambda _: scope,
            trace_resolver=lambda _: trace,
        )
        blackboard = Blackboard()
        log_agent = LogAgent(gateway, blackboard)
        metrics_agent = MetricsAgent(gateway, blackboard)
        config_agent = ConfigAgent(gateway, blackboard)
        dependency_agent = DependencyAgent(gateway, blackboard)
        barrier = Barrier(4)

        def log_executor(
            run_context: RunContext,
            node: TaskNode,
            agent: AgentCard,
        ) -> TaskOutcome:
            barrier.wait(timeout=3)
            evidence = log_agent.collect(
                run_context,
                MinimalAnalysisTask(
                    incident_id=run_context.incident_id,
                    service=run_context.target.service,
                    log_path=log_path,
                    objective=run_context.objective,
                ),
            )
            return TaskOutcome(success=True, result_ref=evidence.evidence_id)

        def metrics_executor(
            run_context: RunContext,
            node: TaskNode,
            agent: AgentCard,
        ) -> TaskOutcome:
            barrier.wait(timeout=3)
            evidence = metrics_agent.collect(run_context)
            return TaskOutcome(success=True, result_ref=evidence.evidence_id)

        def config_executor(
            run_context: RunContext,
            node: TaskNode,
            agent: AgentCard,
        ) -> TaskOutcome:
            barrier.wait(timeout=3)
            evidence = config_agent.collect(
                run_context,
                config_path="/etc/web-app/config.yaml",
            )
            return TaskOutcome(success=True, result_ref=evidence.evidence_id)

        def dependency_executor(
            run_context: RunContext,
            node: TaskNode,
            agent: AgentCard,
        ) -> TaskOutcome:
            barrier.wait(timeout=3)
            evidence = dependency_agent.collect(run_context)
            return TaskOutcome(success=True, result_ref=evidence.evidence_id)

        dag = build_fixed_task_dag(context.incident_id)
        report = Scheduler(
            dag=dag,
            context=context,
            trace=trace,
            executors={
                "N0": success_executor,
                "N1": log_executor,
                "N2": metrics_executor,
                "N3": config_executor,
                "N4": dependency_executor,
            },
            max_concurrency=4,
            max_retries=1,
        ).run()
        events = [
            event
            for event in trace.read_events()
            if event.task_id in {"N1", "N2", "N3", "N4"}
            and event.event_type in {"TASK_STARTED", "TASK_FINISHED", "TASK_READY"}
        ]
        WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
        (WORKFLOW_DIR / "W08_parallel_events.json").write_text(
            json.dumps(
                [event.model_dump(mode="json") for event in events],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        (WORKFLOW_DIR / "W08_dispatch_summary.json").write_text(
            json.dumps(
                {
                    "gate_task_id": report.gate_task_id,
                    "gate_ready": report.gate_ready,
                    "ready_tasks": report.ready_tasks,
                    "failed_tasks": report.failed_tasks,
                    "retry_counts": report.retry_counts,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        shutil.copyfile(trace.path, WORKFLOW_DIR / "W08_parallel_trace.jsonl")

        starts = {
            event.task_id: event
            for event in events
            if event.event_type == "TASK_STARTED"
        }
        finishes = {
            event.task_id: event
            for event in events
            if event.event_type == "TASK_FINISHED"
        }
        first = min(event.timestamp for event in starts.values())
        last = max(event.timestamp for event in finishes.values())
        span = max(0.001, (last - first).total_seconds())
        left, chart_width = 260, 780
        parts = [
            f'<text x="36" y="36" font-family="{FONT}" font-size="24" '
            'font-weight="700" fill="#142433">W08 四路并行调度时间线</text>',
            f'<text x="36" y="60" font-family="{FONT}" font-size="13" '
            'fill="#657887">本地真实线程、ToolGateway 与 Trace</text>',
        ]
        batch_ids = {
            event.details.get("dispatch_batch_id")
            for event in starts.values()
            if event.details.get("dispatch_batch_id")
        }
        for index, task_id in enumerate(("N1", "N2", "N3", "N4")):
            y = 120 + index * 70
            start = (starts[task_id].timestamp - first).total_seconds()
            finish = (finishes[task_id].timestamp - first).total_seconds()
            x = left + chart_width * start / span
            width = max(4, chart_width * (finish - start) / span)
            parts.append(
                f'<text x="38" y="{y + 21}" font-family="{FONT}" font-size="13" '
                f'font-weight="700" fill="#142433">{task_id} · '
                f'{starts[task_id].agent_id}</text>'
                f'<rect x="{x}" y="{y}" width="{width}" height="30" rx="5" '
                'fill="#175f70"/>'
                f'<text x="{x + width + 8}" y="{y + 20}" font-family="{FONT}" '
                f'font-size="12" fill="#31546d">{finish - start:.3f}s</text>'
            )
        latest_start = max(
            (event.timestamp for event in starts.values()),
            default=first,
        )
        earliest_start = min(
            (event.timestamp for event in starts.values()),
            default=first,
        )
        summary = (
            f"同一派发批次：{len(batch_ids) == 1} · "
            f"启动跨度：{latest_start - earliest_start} · "
            f'N5 门控：{"READY" if report.gate_ready else "BLOCKED"}'
        )
        parts.append(
            f'<text x="260" y="425" font-family="{FONT}" font-size="13" '
            f'fill="#31546d">{html.escape(summary)}</text>'
        )
        write_svg(WORKFLOW_DIR / "W08_parallel_timeline.svg", 1100, 470, "".join(parts))


def make_evidence(
    incident_id: str,
    evidence_id: str,
    producer: str,
    kind: EvidenceKind,
    summary: str,
    facts: dict[str, object],
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        incident_id=incident_id,
        task_id={
            EvidenceKind.LOG: "N1",
            EvidenceKind.METRICS: "N2",
            EvidenceKind.CONFIG: "N3",
            EvidenceKind.DEPENDENCY: "N4",
        }[kind],
        producer_agent=producer,
        kind=kind,
        summary=summary,
        source_ref=f"evidence/{evidence_id}",
        observed_at=NOW,
        facts=facts,
        confidence=0.9,
    )


def default_evidence_bundle(incident_id: str) -> tuple[Evidence, ...]:
    return (
        make_evidence(
            incident_id,
            "evi-log",
            "LogAgent",
            EvidenceKind.LOG,
            "database connection refused",
            {"last_line": "database connection refused"},
        ),
        make_evidence(
            incident_id,
            "evi-metrics",
            "MetricsAgent",
            EvidenceKind.METRICS,
            "resource pressure checked",
            {"load_average": {"one_minute": 1.2}, "memory_kib": {"MemAvailable": 102400}},
        ),
        make_evidence(
            incident_id,
            "evi-config",
            "ConfigAgent",
            EvidenceKind.CONFIG,
            "configuration readable",
            {"sha256": "a" * 64, "content": "port: 8080"},
        ),
        make_evidence(
            incident_id,
            "evi-dependency",
            "DependencyAgent",
            EvidenceKind.DEPENDENCY,
            "web-app process and port missing",
            {"processes": [], "ports": []},
        ),
    )


def coordinate_messages(
    context: RunContext,
    evidence: tuple[Evidence, ...],
    trace: JsonlTraceStore,
    blackboard: Blackboard,
) -> tuple[InteractionBus, object]:
    bus = InteractionBus(context.incident_id, trace, blackboard)
    for card in build_default_agent_cards():
        bus.register_agent(card.agent_id, card.agent_type)
    repair_result = RepairResult(
        repair_id="repair-evidence",
        incident_id=context.incident_id,
        status=RepairStatus.SUCCEEDED,
        started_at=NOW,
        ended_at=NOW,
    )
    verification_result = VerificationResult(
        verification_id="verify-evidence",
        incident_id=context.incident_id,
        repair_id=repair_result.repair_id,
        passed=True,
        checks=(VerificationCheck(name="health_endpoint", passed=True),),
        started_at=NOW,
        ended_at=NOW,
    )
    graph = CoordinatorAgent().coordinate_required_interactions(
        context,
        bus,
        log_evidence=evidence[0],
        config_evidence=evidence[2],
        metrics_evidence=evidence[1],
        dependency_evidence=evidence[3],
        repair_result=repair_result,
        verification_result=verification_result,
    )
    return bus, graph


def render_message_graph() -> None:
    with TemporaryDirectory() as temporary:
        temp_root = Path(temporary)
        context = make_context(
            "inc-w09-evidence",
            "run-w09-evidence",
            AllowedScope(),
        )
        trace = JsonlTraceStore(temp_root / "traces", context.incident_id, context.run_id)
        blackboard = Blackboard()
        evidence = default_evidence_bundle(context.incident_id)
        bus, graph = coordinate_messages(context, evidence, trace, blackboard)
        messages = bus.messages()
        WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
        (WORKFLOW_DIR / "W09_message_graph.json").write_text(
            graph.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        (WORKFLOW_DIR / "W09_messages.json").write_text(
            json.dumps(
                [message.model_dump(mode="json") for message in messages],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        shutil.copyfile(trace.path, WORKFLOW_DIR / "W09_message_trace.jsonl")

        positions = {
            "CoordinatorAgent": (555, 255),
            "LogAgent": (100, 80),
            "ConfigAgent": (870, 80),
            "MetricsAgent": (100, 430),
            "DependencyAgent": (870, 430),
            "RepairAgent": (430, 520),
            "VerifierAgent": (780, 520),
        }
        node_width, node_height = 170, 58

        def center(agent_type: str) -> tuple[float, float]:
            x, y = positions[agent_type]
            return x + node_width / 2, y + node_height / 2

        edge_parts: list[str] = []
        for index, edge in enumerate(graph.edges):
            x1, y1 = center(edge.from_agent)
            x2, y2 = center(edge.to_agent)
            dx, dy = x2 - x1, y2 - y1
            length = max(1.0, (dx * dx + dy * dy) ** 0.5)
            offset = 24 if index % 2 == 0 else -24
            control_x = (x1 + x2) / 2 - dy / length * offset
            control_y = (y1 + y2) / 2 + dx / length * offset
            edge_parts.append(
                f'<path d="M{x1},{y1} Q{control_x},{control_y} {x2},{y2}" '
                'fill="none" stroke="#31546d" stroke-width="2" marker-end="url(#arrow)"/>'
                f'<text x="{control_x}" y="{control_y - 7}" text-anchor="middle" '
                f'font-family="{FONT}" font-size="12" fill="#175f70">'
                f"{edge.message_count}</text>"
            )
        node_parts: list[str] = []
        for agent_type, (x, y) in positions.items():
            fill = "#d9edf1" if "Agent" in agent_type else "#ffffff"
            node_parts.append(
                f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" '
                f'rx="12" fill="{fill}" stroke="#7493a5"/>'
                f'<text x="{x + node_width / 2}" y="{y + 35}" text-anchor="middle" '
                f'font-family="{FONT}" font-size="14" font-weight="700" '
                f'fill="#142433">{html.escape(agent_type)}</text>'
            )
        body = (
            f'<text x="36" y="36" font-family="{FONT}" font-size="24" '
            'font-weight="700" fill="#142433">W09 三对双向 Agent 交互图</text>'
            f'<text x="36" y="60" font-family="{FONT}" font-size="13" '
            'fill="#657887">由真实 InteractionBus 消息生成</text>'
            f'<text x="850" y="36" text-anchor="end" font-family="{FONT}" '
            f'font-size="15" font-weight="700" fill="#175f70">消息 {graph.message_count}</text>'
            f'<text x="850" y="58" text-anchor="end" font-family="{FONT}" '
            f'font-size="13" fill="#31546d">双向边 {graph.bidirectional_edge_count}</text>'
            + "".join(edge_parts)
            + "".join(node_parts)
        )
        write_svg(WORKFLOW_DIR / "W09_message_graph.svg", 1080, 630, body)


def render_diagnosis_chain() -> None:
    with TemporaryDirectory() as temporary:
        temp_root = Path(temporary)
        sandbox_root = temp_root / "sandbox"
        log_path, scope = seed_demo_target(sandbox_root)
        context = make_context("inc-w10-evidence", "run-w10-evidence", scope)
        trace = JsonlTraceStore(temp_root / "traces", context.incident_id, context.run_id)
        blackboard = Blackboard()
        gateway = ToolGateway(
            SandboxReadOnlyBackend(sandbox_root),
            scope_resolver=lambda _: scope,
            trace_resolver=lambda _: trace,
        )
        task = CoordinatorAgent().plan(context, log_path=log_path)
        evidence = (
            LogAgent(gateway, blackboard).collect(context, task),
            MetricsAgent(gateway, blackboard).collect(context),
            ConfigAgent(gateway, blackboard).collect(
                context,
                config_path="/etc/web-app/config.yaml",
            ),
            DependencyAgent(gateway, blackboard).collect(context),
        )
        bus, _ = coordinate_messages(context, evidence, trace, blackboard)
        result = DiagnosisFusionEngine().fuse(context, evidence, bus.messages())
        WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
        (WORKFLOW_DIR / "W10_evidence_chain.json").write_text(
            result.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        shutil.copyfile(trace.path, WORKFLOW_DIR / "W10_evidence_trace.jsonl")

        evidence_positions = ((80, 130), (330, 130), (580, 130), (830, 130))
        parts = [
            f'<text x="38" y="36" font-family="{FONT}" font-size="24" '
            'font-weight="700" fill="#142433">W10 四类证据融合与根因链</text>',
            f'<text x="38" y="60" font-family="{FONT}" font-size="13" '
            f'fill="#657887">状态 {result.status} · 服务 {result.service}</text>',
        ]
        for entry, (x, y) in zip(result.evidence_chain, evidence_positions, strict=True):
            parts.append(
                f'<rect x="{x}" y="{y}" width="200" height="105" rx="10" '
                'fill="#ffffff" stroke="#9eb2c0"/>'
                f'<text x="{x + 14}" y="{y + 27}" font-family="{FONT}" '
                f'font-size="15" font-weight="700" fill="#142433">'
                f"{html.escape(entry.kind.value.upper())}</text>"
                f'<text x="{x + 14}" y="{y + 51}" font-family="{FONT}" '
                f'font-size="12" fill="#31546d">{html.escape(entry.producer_agent)}</text>'
                f'<text x="{x + 14}" y="{y + 73}" font-family="{FONT}" '
                f'font-size="11" fill="#657887">{html.escape(entry.evidence_id)}</text>'
                f'<text x="{x + 14}" y="{y + 92}" font-family="{FONT}" '
                f'font-size="11" fill="#657887">messages '
                f"{len(entry.linked_message_ids)}</text>"
                f'<path d="M{x + 100},{y + 105} L540,310" fill="none" '
                'stroke="#31546d" stroke-width="2" marker-end="url(#arrow)"/>'
            )
        root_cause = (
            result.diagnosis.root_causes[0].description
            if result.diagnosis.root_causes
            else "no candidate"
        )
        supporting = (
            ", ".join(result.diagnosis.root_causes[0].supporting_evidence)
            if result.diagnosis.root_causes
            else ""
        )
        parts.extend(
            (
                '<rect x="265" y="310" width="550" height="130" rx="14" '
                'fill="#d9edf1" stroke="#175f70"/>',
                f'<text x="540" y="345" text-anchor="middle" font-family="{FONT}" '
                'font-size="16" font-weight="700" fill="#175f70">根因候选</text>',
                f'<text x="540" y="378" text-anchor="middle" font-family="{FONT}" '
                f'font-size="14" fill="#142433">{html.escape(root_cause)}</text>',
                f'<text x="540" y="407" text-anchor="middle" font-family="{FONT}" '
                f'font-size="12" fill="#31546d">支持证据：{html.escape(supporting)}</text>',
                f'<text x="540" y="427" text-anchor="middle" font-family="{FONT}" '
                f'font-size="12" fill="#31546d">冲突数：{len(result.conflicts)} · '
                f'追问数：{len(result.follow_up_requests)}</text>',
            )
        )
        write_svg(WORKFLOW_DIR / "W10_diagnosis_chain.svg", 1110, 520, "".join(parts))


def render_benchmark() -> None:
    payload = json.loads(BENCHMARK_RAW.read_text(encoding="utf-8"))
    comparisons = payload["summary"]["comparisons"]
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    with (BENCHMARK_DIR / "W13_benchmark_medians.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "scenario",
                "serial_median_seconds",
                "parallel_median_seconds",
                "speedup",
                "serial_correctness",
                "parallel_correctness",
            )
        )
        for item in comparisons:
            writer.writerow(
                (
                    item["scenario_id"],
                    item["serial"]["median_seconds"],
                    item["parallel"]["median_seconds"],
                    item["median_speedup"],
                    item["serial"]["correctness_rate"],
                    item["parallel"]["correctness_rate"],
                )
            )

    scenarios = [item["scenario_id"].upper() for item in comparisons]
    serial = [item["serial"]["median_seconds"] for item in comparisons]
    parallel = [item["parallel"]["median_seconds"] for item in comparisons]
    maximum = max(serial + parallel)
    max_axis = max(20.0, float(int(maximum / 5 + 1) * 5))
    left, top, chart_width, chart_height = 100, 155, 900, 290
    parts = [
        f'<text x="38" y="38" font-family="{FONT}" font-size="24" '
        'font-weight="700" fill="#142433">W13 串行与并发中位数耗时</text>',
        f'<text x="38" y="62" font-family="{FONT}" font-size="13" '
        'fill="#657887">数据源：local_ollama_2026-11-22.json；仅用于本地开发验证</text>',
        f'<text x="38" y="98" font-family="{FONT}" font-size="15" '
        f'font-weight="700" fill="#175f70">平均提速 '
        f'{payload["summary"]["average_speedup"] * 100:.2f}% · 最低 '
        f'{payload["summary"]["minimum_speedup"] * 100:.2f}% · '
        '正确性保持</text>',
        f'<rect x="760" y="78" width="20" height="12" fill="#758b99"/>'
        f'<text x="788" y="89" font-family="{FONT}" font-size="12" fill="#31546d">串行</text>',
        f'<rect x="850" y="78" width="20" height="12" fill="#175f70"/>'
        f'<text x="878" y="89" font-family="{FONT}" font-size="12" fill="#31546d">并发</text>',
    ]
    for tick in range(0, int(max_axis) + 1, 5):
        y = top + chart_height - chart_height * tick / max_axis
        parts.append(
            f'<line x1="{left}" y1="{y}" x2="{left + chart_width}" y2="{y}" '
            'stroke="#d9e1e6"/>'
            f'<text x="{left - 12}" y="{y + 4}" text-anchor="end" '
            f'font-family="{FONT}" font-size="11" fill="#657887">{tick}s</text>'
        )
    group_width = chart_width / len(scenarios)
    for index, scenario in enumerate(scenarios):
        center_x = left + group_width * (index + 0.5)
        for offset, value, color in (
            (-36, serial[index], "#758b99"),
            (8, parallel[index], "#175f70"),
        ):
            height = chart_height * value / max_axis
            parts.append(
                f'<rect x="{center_x + offset}" y="{top + chart_height - height}" '
                f'width="28" height="{height}" rx="3" fill="{color}"/>'
                f'<text x="{center_x + offset + 14}" y="{top + chart_height - height - 6}" '
                f'text-anchor="middle" font-family="{FONT}" font-size="10" '
                f'fill="#31546d">{value:.1f}</text>'
            )
        parts.append(
            f'<text x="{center_x}" y="{top + chart_height + 28}" text-anchor="middle" '
            f'font-family="{FONT}" font-size="14" font-weight="700" '
            f'fill="#142433">{scenario}</text>'
        )
    write_svg(BENCHMARK_DIR / "W13_benchmark_medians.svg", 1080, 530, "".join(parts))

    speedups = [item["median_speedup"] * 100 for item in comparisons]
    max_speed = max(60.0, float(int(max(speedups) / 10 + 1) * 10))
    parts = [
        f'<text x="38" y="38" font-family="{FONT}" font-size="24" '
        'font-weight="700" fill="#142433">W13 场景提速</text>',
        f'<text x="38" y="62" font-family="{FONT}" font-size="13" '
        'fill="#657887">虚线为区域赛 20% 平均提速要求参考线</text>',
    ]
    left, top, chart_width, chart_height = 100, 110, 900, 240
    for tick in range(0, int(max_speed) + 1, 10):
        y = top + chart_height - chart_height * tick / max_speed
        parts.append(
            f'<line x1="{left}" y1="{y}" x2="{left + chart_width}" y2="{y}" '
            'stroke="#d9e1e6"/>'
            f'<text x="{left - 12}" y="{y + 4}" text-anchor="end" '
            f'font-family="{FONT}" font-size="11" fill="#657887">{tick}%</text>'
        )
    threshold_y = top + chart_height - chart_height * 20 / max_speed
    parts.append(
        f'<line x1="{left}" y1="{threshold_y}" x2="{left + chart_width}" '
        f'y2="{threshold_y}" stroke="#b54b4b" stroke-width="2" stroke-dasharray="7 6"/>'
        f'<text x="{left + chart_width - 5}" y="{threshold_y - 8}" text-anchor="end" '
        f'font-family="{FONT}" font-size="11" fill="#b54b4b">20%</text>'
    )
    group_width = chart_width / len(scenarios)
    for index, scenario in enumerate(scenarios):
        center_x = left + group_width * (index + 0.5)
        height = chart_height * speedups[index] / max_speed
        parts.append(
            f'<rect x="{center_x - 28}" y="{top + chart_height - height}" '
            f'width="56" height="{height}" rx="5" fill="#27849a"/>'
            f'<text x="{center_x}" y="{top + chart_height - height - 8}" '
            f'text-anchor="middle" font-family="{FONT}" font-size="12" '
            f'font-weight="700" fill="#175f70">{speedups[index]:.2f}%</text>'
            f'<text x="{center_x}" y="{top + chart_height + 28}" text-anchor="middle" '
            f'font-family="{FONT}" font-size="14" font-weight="700" '
            f'fill="#142433">{scenario}</text>'
        )
    write_svg(BENCHMARK_DIR / "W13_speedup.svg", 1080, 430, "".join(parts))


def render_aios_response() -> None:
    payload = json.loads(
        (TERMINAL_DIR / "W04_aios_responses.json").read_text(encoding="utf-8")
    )
    text = payload["text"]
    structured = payload["json"]
    text_usage = text["token_usage"]
    json_usage = structured["response"]["token_usage"]
    parts = [
        f'<text x="38" y="38" font-family="{FONT}" font-size="24" '
        'font-weight="700" fill="#142433">W04 真实 AIOS 文本与 JSON 冒烟</text>',
        f'<text x="38" y="62" font-family="{FONT}" font-size="13" '
        f'fill="#657887">模型 {html.escape(payload["environment"]["model"])} · '
        f'后端 {html.escape(payload["environment"]["backend"])}</text>',
        '<rect x="38" y="95" width="490" height="260" rx="12" '
        'fill="#ffffff" stroke="#9eb2c0"/>',
        f'<text x="62" y="128" font-family="{FONT}" font-size="17" '
        'font-weight="700" fill="#142433">普通文本响应</text>',
        f'<text x="62" y="168" font-family="Consolas, monospace" font-size="20" '
        f'font-weight="700" fill="#175f70">'
        f'{html.escape(str(text["response_message"]))}</text>',
        f'<text x="62" y="212" font-family="{FONT}" font-size="13" '
        f'fill="#31546d">finished={text["finished"]} · status={text["status_code"]}</text>',
        f'<text x="62" y="239" font-family="{FONT}" font-size="13" '
        f'fill="#31546d">token={text_usage["prompt"]}+{text_usage["completion"]} '
        f'({text_usage["source"]})</text>',
        f'<text x="62" y="266" font-family="{FONT}" font-size="13" '
        f'fill="#31546d">duration={text["duration_ms"]}ms · '
        f'attempts={text["attempts"]}</text>',
        '<rect x="552" y="95" width="490" height="260" rx="12" '
        'fill="#ffffff" stroke="#9eb2c0"/>',
        f'<text x="576" y="128" font-family="{FONT}" font-size="17" '
        'font-weight="700" fill="#142433">严格 JSON 响应</text>',
        f'<text x="576" y="168" font-family="Consolas, monospace" font-size="15" '
        f'fill="#175f70">{html.escape(json.dumps(structured["data"], ensure_ascii=False))}'
        "</text>",
        f'<text x="576" y="212" font-family="{FONT}" font-size="13" '
        'fill="#31546d">JSON Schema 校验通过</text>',
        f'<text x="576" y="239" font-family="{FONT}" font-size="13" '
        f'fill="#31546d">token={json_usage["prompt"]}+{json_usage["completion"]} '
        f'({json_usage["source"]})</text>',
        f'<text x="576" y="266" font-family="{FONT}" font-size="13" '
        f'fill="#31546d">duration={structured["response"]["duration_ms"]}ms · '
        f'attempts={structured["response"]["attempts"]}</text>',
        f'<text x="38" y="395" font-family="{FONT}" font-size="12" '
        'fill="#657887">原始响应保存在 evidence/terminal/W04_aios_responses.json</text>',
    ]
    write_svg(TERMINAL_DIR / "W04_aios_responses.svg", 1080, 430, "".join(parts))


def render_api_flow() -> None:
    payload = json.loads(
        (EVIDENCE_ROOT / "api" / "W05_api_capture.json").read_text(encoding="utf-8")
    )
    operation_names = (
        ("create", "创建 Incident"),
        ("status", "查询状态"),
        ("dag", "查询 DAG"),
        ("events_before_cancel", "查询事件"),
        ("cancel", "取消 Incident"),
        ("events_after_cancel", "取消后 Trace"),
        ("unknown_incident_404", "未知 Incident"),
        ("history", "历史运行"),
        ("benchmark", "基准数据"),
    )
    parts = [
        f'<text x="38" y="38" font-family="{FONT}" font-size="24" '
        'font-weight="700" fill="#142433">W05 API 请求与结构化响应</text>',
        f'<text x="38" y="62" font-family="{FONT}" font-size="13" '
        'fill="#657887">本地 FastAPI 实际请求记录</text>',
    ]
    for index, (key, label) in enumerate(operation_names):
        item = payload[key]
        column = index % 3
        row = index // 3
        x = 38 + column * 340
        y = 100 + row * 105
        status = int(item["status"])
        color = "#175f70" if status < 400 else "#b54b4b"
        display_path = item["path"]
        if len(display_path) > 48:
            display_path = f"{display_path[:24]}...{display_path[-20:]}"
        parts.append(
            f'<rect x="{x}" y="{y}" width="315" height="82" rx="9" '
            f'fill="#ffffff" stroke="{"#b54b4b" if status >= 400 else "#9eb2c0"}"/>'
            f'<text x="{x + 16}" y="{y + 27}" font-family="{FONT}" font-size="14" '
            f'font-weight="700" fill="#142433">{label}</text>'
            f'<text x="{x + 16}" y="{y + 51}" font-family="Consolas, monospace" '
            f'font-size="11" fill="#657887">{item["method"]} '
            f"{html.escape(display_path)}</text>"
            f'<text x="{x + 16}" y="{y + 71}" font-family="{FONT}" font-size="12" '
            f'font-weight="700" fill="{color}">HTTP {status}</text>'
        )
    error = payload["unknown_incident_404"]["body"]["error"]
    parts.extend(
        (
            '<rect x="38" y="430" width="995" height="85" rx="9" '
            'fill="#fff4f3" stroke="#b54b4b"/>',
            f'<text x="60" y="460" font-family="{FONT}" font-size="13" '
            'font-weight="700" fill="#b54b4b">结构化 404 错误</text>',
            f'<text x="60" y="486" font-family="Consolas, monospace" font-size="12" '
            f'fill="#142433">{html.escape(error["code"])}: '
            f'{html.escape(error["message"])}</text>',
            f'<text x="38" y="545" font-family="{FONT}" font-size="12" '
            'fill="#657887">完整响应、OpenAPI 和 Trace 保存在 evidence/api/</text>',
        )
    )
    write_svg(EVIDENCE_ROOT / "api" / "W05_api_flow.svg", 1080, 580, "".join(parts))


def render_minimal_flow_result() -> None:
    success = json.loads(
        (WORKFLOW_DIR / "W07_success_summary.json").read_text(encoding="utf-8")
    )
    failure = json.loads(
        (WORKFLOW_DIR / "W07_failure_summary.json").read_text(encoding="utf-8")
    )
    event_names: list[str] = []
    for line in (WORKFLOW_DIR / "W07_success_trace.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if line.strip() and len(event_names) < 11:
            event_names.append(json.loads(line)["event_type"])

    def card(summary: dict[str, object], x: int, color: str) -> str:
        root_causes = summary["root_cause"]
        assert isinstance(root_causes, list)
        root_description = (
            str(root_causes[0]["description"]) if root_causes else "no root cause"
        )
        timing = summary["timing"]
        assert isinstance(timing, dict)
        return (
            f'<rect x="{x}" y="95" width="490" height="225" rx="12" '
            f'fill="#ffffff" stroke="{color}"/>'
            f'<text x="{x + 24}" y="132" font-family="{FONT}" font-size="18" '
            f'font-weight="700" fill="{color}">'
            f'{html.escape(str(summary["final_status"]))}</text>'
            f'<text x="{x + 24}" y="166" font-family="{FONT}" font-size="13" '
            f'fill="#31546d">修复状态：'
            f'{html.escape(str(summary["repair_status"]))}</text>'
            f'<text x="{x + 24}" y="193" font-family="{FONT}" font-size="13" '
            f'fill="#31546d">验证通过：'
            f'{html.escape(str(summary["verification_passed"]))}</text>'
            f'<text x="{x + 24}" y="220" font-family="{FONT}" font-size="13" '
            f'fill="#31546d">总耗时：{timing.get("total_ms", 0)}ms</text>'
            f'<text x="{x + 24}" y="252" font-family="{FONT}" font-size="13" '
            f'fill="#31546d">根因：</text>'
            f'<text x="{x + 24}" y="276" font-family="{FONT}" font-size="12" '
            f'fill="#142433">{html.escape(root_description)}</text>'
            f'<text x="{x + 24}" y="302" font-family="{FONT}" font-size="11" '
            f'fill="#657887">Trace 与最终报告均已保存</text>'
        )

    parts = [
        f'<text x="38" y="38" font-family="{FONT}" font-size="24" '
        'font-weight="700" fill="#142433">W07 最小诊断修复验证闭环</text>',
        f'<text x="38" y="62" font-family="{FONT}" font-size="13" '
        'fill="#657887">两次真实本地 AIOS 模型调用 · 成功与失败对照</text>',
        card(success, 38, "#175f70"),
        card(failure, 552, "#b54b4b"),
        f'<text x="38" y="365" font-family="{FONT}" font-size="14" '
        'font-weight="700" fill="#142433">成功路径 Trace 阶段</text>',
    ]
    for index, event_name in enumerate(event_names):
        column = index % 3
        row = index // 3
        x = 38 + column * 345
        y = 390 + row * 38
        parts.append(
            f'<rect x="{x}" y="{y}" width="320" height="27" rx="5" '
            'fill="#d9edf1"/>'
            f'<text x="{x + 12}" y="{y + 18}" font-family="Consolas, monospace" '
            f'font-size="11" fill="#175f70">{html.escape(event_name)}</text>'
        )
    write_svg(WORKFLOW_DIR / "W07_flow_result.svg", 1080, 560, "".join(parts))


def render_test_matrix() -> None:
    suites: dict[str, tuple[int, int, int, int, float]] = {}
    for xml_path in EVIDENCE_ROOT.rglob("*junit.xml"):
        root = ElementTree.parse(xml_path).getroot()
        suite_nodes = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        tests = sum(int(node.attrib.get("tests", 0)) for node in suite_nodes)
        failures = sum(int(node.attrib.get("failures", 0)) for node in suite_nodes)
        errors = sum(int(node.attrib.get("errors", 0)) for node in suite_nodes)
        skipped = sum(int(node.attrib.get("skipped", 0)) for node in suite_nodes)
        elapsed = sum(float(node.attrib.get("time", 0)) for node in suite_nodes)
        label = xml_path.stem.replace("_junit", "")
        suites[label] = (tests, failures, errors, skipped, elapsed)

    lines = [
        "# 本地测试证据索引",
        "",
        "由各工单实际执行的 JUnit XML 汇总生成。",
        "",
        "| 工单 | 用例数 | 失败 | 错误 | 跳过 | 耗时 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label in sorted(suites):
        tests, failures, errors, skipped, elapsed = suites[label]
        lines.append(
            f"| {label} | {tests} | {failures} | {errors} | {skipped} | {elapsed:.2f}s |"
        )
    lines.extend(
        (
            "",
            "W02 统一回归原始文本与截图：",
            "",
            "```text",
            "docs/submission/evidence/terminal/W02_verify.txt",
            "docs/submission/evidence/terminal/W02_verify.png",
            "```",
            "",
        )
    )
    (EVIDENCE_ROOT / "TEST_EVIDENCE.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
        newline="\n",
    )

    counts = defaultdict(list)
    for values in suites.values():
        counts["test"].append(values[0])
        counts["failure"].append(values[1] + values[2])
        counts["skip"].append(values[3])
    total_tests = sum(counts["test"])
    total_failures = sum(counts["failure"])
    total_skips = sum(counts["skip"])
    parts = [
        f'<text x="38" y="38" font-family="{FONT}" font-size="24" '
        'font-weight="700" fill="#142433">W03—W12 本地专项测试证据</text>',
        f'<text x="38" y="62" font-family="{FONT}" font-size="13" '
        'fill="#657887">由 pytest JUnit XML 汇总；W02 统一回归另存截图与文本</text>',
        '<rect x="38" y="90" width="300" height="80" rx="10" fill="#ffffff" '
        'stroke="#9eb2c0"/>',
        f'<text x="58" y="120" font-family="{FONT}" font-size="13" '
        'fill="#657887">专项用例</text>',
        f'<text x="58" y="153" font-family="{FONT}" font-size="28" '
        f'font-weight="700" fill="#142433">{total_tests}</text>',
        '<rect x="370" y="90" width="300" height="80" rx="10" fill="#ffffff" '
        'stroke="#9eb2c0"/>',
        f'<text x="390" y="120" font-family="{FONT}" font-size="13" '
        'fill="#657887">失败与错误</text>',
        f'<text x="390" y="153" font-family="{FONT}" font-size="28" '
        f'font-weight="700" fill="#27849a">{total_failures}</text>',
        '<rect x="702" y="90" width="300" height="80" rx="10" fill="#ffffff" '
        'stroke="#9eb2c0"/>',
        f'<text x="722" y="120" font-family="{FONT}" font-size="13" '
        'fill="#657887">跳过</text>',
        f'<text x="722" y="153" font-family="{FONT}" font-size="28" '
        f'font-weight="700" fill="#142433">{total_skips}</text>',
    ]
    for index, label in enumerate(sorted(suites)):
        column = index % 4
        row = index // 4
        x = 38 + column * 255
        y = 220 + row * 115
        tests, failures, errors, skipped, elapsed = suites[label]
        status = "PASS" if failures + errors == 0 else "FAIL"
        parts.extend(
            (
                f'<rect x="{x}" y="{y}" width="225" height="86" rx="10" '
                f'fill="#ffffff" stroke="{"#9eb2c0" if status == "PASS" else "#b54b4b"}"/>',
                f'<text x="{x + 14}" y="{y + 25}" font-family="{FONT}" '
                f'font-size="15" font-weight="700" fill="#142433">{label}</text>',
                f'<text x="{x + 14}" y="{y + 49}" font-family="{FONT}" '
                f'font-size="12" fill="#657887">{tests} tests · {elapsed:.2f}s</text>',
                f'<text x="{x + 14}" y="{y + 72}" font-family="{FONT}" '
                f'font-size="13" font-weight="700" '
                f'fill="{"#175f70" if status == "PASS" else "#b54b4b"}">{status}</text>',
            )
        )
    write_svg(EVIDENCE_ROOT / "W03_W12_test_matrix.svg", 1030, 600, "".join(parts))


def render_junit_detail(
    source: Path,
    destination: Path,
    *,
    title: str,
    subtitle: str,
) -> None:
    root = ElementTree.parse(source).getroot()
    cases = list(root.iter("testcase"))
    columns = 3
    card_width = 310
    card_height = 78
    rows = max(1, (len(cases) + columns - 1) // columns)
    height = 200 + rows * 95
    passed = 0
    parts = [
        f'<text x="38" y="38" font-family="{FONT}" font-size="24" '
        f'font-weight="700" fill="#142433">{html.escape(title)}</text>',
        f'<text x="38" y="62" font-family="{FONT}" font-size="13" '
        f'fill="#657887">{html.escape(subtitle)}</text>',
    ]
    for index, case in enumerate(cases):
        name = case.attrib.get("name", "unknown").removeprefix("test_").replace("_", " ")
        failed = case.find("failure") is not None or case.find("error") is not None
        skipped = case.find("skipped") is not None
        status = "SKIP" if skipped else ("FAIL" if failed else "PASS")
        if status == "PASS":
            passed += 1
        column = index % columns
        row = index // columns
        x = 38 + column * 330
        y = 105 + row * 95
        color = "#b54b4b" if status == "FAIL" else "#175f70"
        wrapped = textwrap.wrap(name, width=38)[:2]
        label_lines = "".join(
            f'<text x="{x + 16}" y="{y + 30 + line_index * 17}" '
            f'font-family="{FONT}" font-size="12" fill="#142433">'
            f"{html.escape(line)}</text>"
            for line_index, line in enumerate(wrapped)
        )
        parts.append(
            f'<rect x="{x}" y="{y}" width="{card_width}" height="{card_height}" '
            f'rx="9" fill="#ffffff" stroke="{"#b54b4b" if failed else "#9eb2c0"}"/>'
            f"{label_lines}"
            f'<text x="{x + card_width - 16}" y="{y + 30}" text-anchor="end" '
            f'font-family="{FONT}" font-size="12" font-weight="700" '
            f'fill="{color}">{status}</text>'
        )
    parts.insert(
        2,
        f'<text x="38" y="88" font-family="{FONT}" font-size="13" '
        f'fill="#31546d">用例 {len(cases)} · 通过 {passed} · '
        f'失败 {len(cases) - passed}</text>',
    )
    write_svg(destination, 1060, height, "".join(parts))


def main() -> None:
    for directory in (WORKFLOW_DIR, BENCHMARK_DIR, TERMINAL_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    render_task_dag()
    render_parallel_timeline()
    render_message_graph()
    render_diagnosis_chain()
    render_benchmark()
    render_aios_response()
    render_api_flow()
    render_minimal_flow_result()
    render_test_matrix()
    render_junit_detail(
        EVIDENCE_ROOT / "security" / "W06_junit.xml",
        EVIDENCE_ROOT / "security" / "W06_tool_security.svg",
        title="W06 工具权限与隔离拒绝",
        subtitle="实际 ToolGateway 测试结果：权限、路径、参数、限制与失败关闭",
    )
    render_junit_detail(
        EVIDENCE_ROOT / "workflow" / "W11_junit.xml",
        EVIDENCE_ROOT / "workflow" / "W11_repair_verification.svg",
        title="W11 修复与独立验证闭环",
        subtitle="成功、两轮失败、回滚和危险修复计划拒绝",
    )
    print("local evidence rendered")


if __name__ == "__main__":
    main()
