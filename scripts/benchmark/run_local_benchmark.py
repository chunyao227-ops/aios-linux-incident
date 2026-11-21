"""Run the six-scenario local Ollama serial/parallel development benchmark."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from aios_incident.adapters.aios_client import AiosClient
from aios_incident.adapters.llm_adapter import ChatMessage, LlmAdapter
from aios_incident.agents.coordinator_agent import CoordinatorAgent
from aios_incident.benchmark.metrics import (
    CollectionOutcome,
    FinalizeOutcome,
    RawBenchmarkBundle,
    RunMeasurement,
    build_summary,
)
from aios_incident.benchmark.parallel import ParallelBenchmarkRunner
from aios_incident.benchmark.report import write_markdown_report, write_raw_bundle
from aios_incident.benchmark.serial import SerialBenchmarkRunner
from aios_incident.config import PROJECT_ROOT, load_config
from aios_incident.models import (
    AllowedScope,
    Evidence,
    EvidenceKind,
    IncidentTarget,
    RepairResult,
    RepairStatus,
    RunContext,
    TokenUsage,
    VerificationCheck,
    VerificationResult,
)
from aios_incident.orchestrator.blackboard import Blackboard
from aios_incident.orchestrator.interaction_bus import InteractionBus
from aios_incident.orchestrator.planner import build_default_agent_cards
from aios_incident.orchestrator.trace import JsonlTraceStore
from aios_incident.utils import generate_id, utc_now

SCENARIO_IDS = ("f1", "f2", "f3", "f4", "f5", "f6")
COLLECTION_CONFIG = {
    "N1": (
        "LogAgent",
        "log-analysis-v1",
        "Analyze the log failure signal for {scenario}. Return one concise diagnosis sentence.",
        EvidenceKind.LOG,
    ),
    "N2": (
        "MetricsAgent",
        "metrics-analysis-v1",
        "Analyze resource metrics for {scenario}. Return one concise diagnosis sentence.",
        EvidenceKind.METRICS,
    ),
    "N3": (
        "ConfigAgent",
        "config-analysis-v1",
        "Analyze configuration state for {scenario}. Return one concise diagnosis sentence.",
        EvidenceKind.CONFIG,
    ),
    "N4": (
        "DependencyAgent",
        "dependency-analysis-v1",
        "Analyze process and port dependencies for {scenario}. Return one concise sentence.",
        EvidenceKind.DEPENDENCY,
    ),
}


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    remainder = str(resolved)[len(resolved.drive) :].replace("\\", "/")
    return f"/mnt/{drive}{remainder}"


def run_command(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )


class LocalScenarioWorkload:
    def __init__(
        self,
        *,
        scenario_id: str,
        llm: LlmAdapter,
        model_name: str,
        run_serial: int,
    ) -> None:
        self.scenario_id = scenario_id
        self.llm = llm
        self.model_name = model_name
        self.run_serial = run_serial
        self.incident_id = f"bench-{scenario_id}-{run_serial}"
        self.run_id = f"run-{scenario_id}-{run_serial}"
        self.target_root = PROJECT_ROOT / "scenarios"

    def prepare(self) -> None:
        self._action("reset")
        self._action("inject")

    def collect(self, task_id: str) -> CollectionOutcome:
        agent_type, prompt_id, prompt_template, _ = COLLECTION_CONFIG[task_id]
        prompt = prompt_template.format(scenario=self.scenario_id)
        started_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        error = None
        response_message = ""
        token_usage = TokenUsage(source="unavailable")
        try:
            prompt_started = time.perf_counter()
            response = self.llm.chat(
                [ChatMessage(role="user", content=prompt)],
                agent_name=agent_type,
                temperature=0.0,
                max_new_tokens=16,
            )
            model_seconds = time.perf_counter() - prompt_started
            response_message = response.response_message or ""
            token_usage = response.token_usage
            success = response.finished and bool(response_message)
        except Exception as exc:
            model_seconds = time.perf_counter() - started
            error = f"{type(exc).__name__}: {exc}"
            success = False
        ended_at = datetime.now(timezone.utc)
        elapsed = time.perf_counter() - started
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
        return CollectionOutcome(
            task_id=task_id,
            prompt_id=f"{prompt_id}:{prompt_hash}",
            started_at=started_at,
            ended_at=ended_at,
            elapsed_seconds=elapsed,
            model_seconds=model_seconds,
            tool_seconds=0,
            token_usage=token_usage,
            success=success,
            evidence_id=generate_id(f"evi-{task_id.lower()}"),
            error=error,
            tool_calls=1,
            trace=(
                {
                    "event_type": "COLLECTION_MODEL_FINISHED",
                    "task_id": task_id,
                    "agent_type": agent_type,
                    "prompt_id": prompt_id,
                    "prompt_hash": prompt_hash,
                    "elapsed_seconds": elapsed,
                    "model_seconds": model_seconds,
                    "tokens": token_usage.model_dump(mode="json"),
                    "success": success,
                    "error": error,
                    "response_preview": response_message[:160],
                },
            ),
        )

    def finalize(self, collections: tuple[CollectionOutcome, ...]) -> FinalizeOutcome:
        started_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        model_seconds = 0.0
        token_usage = TokenUsage(source="unavailable")
        trace: list[dict[str, object]] = [
            {
                "event_type": "DIAGNOSIS_STARTED",
                "task_id": "N5",
                "collection_evidence": [item.evidence_id for item in collections],
            }
        ]
        diagnosis_prompt = (
            f"Scenario {self.scenario_id} has four evidence groups. "
            "Return one concise root-cause sentence."
        )
        errors: list[str] = []
        try:
            model_started = time.perf_counter()
            diagnosis = self.llm.chat(
                [ChatMessage(role="user", content=diagnosis_prompt)],
                agent_name="CoordinatorAgent",
                temperature=0.0,
                max_new_tokens=16,
            )
            model_seconds += time.perf_counter() - model_started
            token_usage = diagnosis.token_usage
            trace.append(
                {
                    "event_type": "DIAGNOSIS_FINISHED",
                    "task_id": "N5",
                    "elapsed_seconds": model_seconds,
                    "tokens": diagnosis.token_usage.model_dump(mode="json"),
                    "success": diagnosis.finished,
                }
            )
        except Exception as exc:
            errors.append(f"diagnosis: {type(exc).__name__}: {exc}")
            trace.append(
                {
                    "event_type": "DIAGNOSIS_FAILED",
                    "task_id": "N5",
                    "error": errors[-1],
                }
            )

        tool_calls = 0
        tool_seconds = 0.0
        repair_action = self._timed_action("repair")
        tool_calls += 1
        tool_seconds += repair_action[0]
        if repair_action[1].returncode != 0:
            errors.append(f"repair: {repair_action[1].stderr.strip()}")

        verification = self._timed_action("verify")
        tool_calls += 1
        tool_seconds += verification[0]
        verify_passed = verification[1].returncode == 0
        if not verify_passed:
            errors.append(f"verify: {verification[1].stdout.strip()}")

        pressure_passed = False
        if verify_passed:
            pressure = self._timed_action("pressure")
            tool_calls += 1
            tool_seconds += pressure[0]
            pressure_passed = pressure[1].returncode == 0
            if not pressure_passed:
                errors.append(f"pressure: {pressure[1].stdout.strip()}")

        message_count, interaction_trace = self._interaction_trace(collections, verify_passed)
        trace.extend(interaction_trace)
        trace.extend(
            [
                {"event_type": "REPAIR_FINISHED", "success": repair_action[1].returncode == 0},
                {"event_type": "VERIFICATION_FINISHED", "success": verify_passed},
                {"event_type": "PRESSURE_FINISHED", "success": pressure_passed},
            ]
        )
        ended_at = datetime.now(timezone.utc)
        return FinalizeOutcome(
            started_at=started_at,
            ended_at=ended_at,
            elapsed_seconds=time.perf_counter() - started,
            model_seconds=model_seconds,
            tool_seconds=tool_seconds,
            tool_calls=tool_calls,
            token_usage=token_usage,
            correct=all(item.success for item in collections) and verify_passed and pressure_passed,
            message_count=message_count,
            unauthorized_operations=0,
            retries=0,
            error="; ".join(errors) or None,
            trace=tuple(trace),
        )

    def close(self) -> None:
        self._action("destroy")

    def _interaction_trace(
        self,
        collections: tuple[CollectionOutcome, ...],
        verify_passed: bool,
    ) -> tuple[int, tuple[dict[str, object], ...]]:
        with TemporaryDirectory() as temp_dir:
            trace = JsonlTraceStore(Path(temp_dir), self.incident_id, self.run_id)
            bus = InteractionBus(self.incident_id, trace, Blackboard())
            for card in build_default_agent_cards():
                bus.register_agent(card.agent_id, card.agent_type)
            context = RunContext(
                run_id=self.run_id,
                incident_id=self.incident_id,
                objective=f"benchmark {self.scenario_id}",
                target=IncidentTarget(
                    host="sandbox-01",
                    service="web-app",
                    environment="docker",
                ),
                allowed_scope=AllowedScope(
                    read_paths=("/var/log/web-app", "/etc/demo"),
                    write_paths=("/etc/demo",),
                    allowed_services=("web-app",),
                ),
                time_budget_seconds=600,
                max_repair_attempts=2,
                success_criteria=("health_endpoint", "smoke_test"),
            )
            evidence_items = tuple(
                Evidence(
                    evidence_id=item.evidence_id or generate_id("evi"),
                    incident_id=self.incident_id,
                    task_id=item.task_id,
                    producer_agent=COLLECTION_CONFIG[item.task_id][0],
                    kind=COLLECTION_CONFIG[item.task_id][3],
                    summary=f"{self.scenario_id} {item.task_id} benchmark evidence",
                    source_ref=f"benchmark://{self.scenario_id}/{item.task_id}",
                    observed_at=utc_now(),
                    facts={"prompt_id": item.prompt_id},
                    confidence=0.8 if item.success else 0.2,
                )
                for item in collections
            )
            repair_result = RepairResult(
                repair_id=generate_id("repair"),
                incident_id=self.incident_id,
                status=RepairStatus.SUCCEEDED,
                started_at=utc_now(),
                ended_at=utc_now(),
            )
            verification_result = VerificationResult(
                verification_id=generate_id("verify"),
                incident_id=self.incident_id,
                repair_id=repair_result.repair_id,
                passed=verify_passed,
                checks=(
                    VerificationCheck(
                        name="health_endpoint",
                        passed=verify_passed,
                        details={"reason": "benchmark verification"},
                    ),
                ),
                failure_reasons=() if verify_passed else ("benchmark verification failed",),
                started_at=utc_now(),
                ended_at=utc_now(),
            )
            graph = CoordinatorAgent().coordinate_required_interactions(
                context,
                bus,
                log_evidence=evidence_items[0],
                config_evidence=evidence_items[2],
                metrics_evidence=evidence_items[1],
                dependency_evidence=evidence_items[3],
                repair_result=repair_result,
                verification_result=verification_result,
            )
            events = tuple(event.model_dump(mode="json") for event in trace.read_events())
            return graph.message_count, events

    def _timed_action(
        self,
        action: str,
    ) -> tuple[float, subprocess.CompletedProcess[str]]:
        started = time.perf_counter()
        result = self._action(action)
        return time.perf_counter() - started, result

    def _action(self, action: str) -> subprocess.CompletedProcess[str]:
        script = self.target_root / self.scenario_id / f"{action}.sh"
        if os.name == "nt":
            command = ["wsl", "-d", "Ubuntu-22.04", "bash", wsl_path(script)]
        else:
            command = ["bash", str(script)]
        return run_command(command)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--max-sample-attempts", type=int, default=3)
    parser.add_argument("--scenarios", nargs="+", default=list(SCENARIO_IDS))
    parser.add_argument(
        "--raw-path",
        type=Path,
        default=PROJECT_ROOT
        / "docs"
        / "experiment_reports"
        / "raw"
        / "local_ollama_2026-11-22.json",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=PROJECT_ROOT / "docs" / "experiment_reports" / "benchmark_results.md",
    )
    args = parser.parse_args()
    if args.samples < 5:
        parser.error("at least five valid samples per mode are required")
    if args.warmups < 1:
        parser.error("at least one warmup per mode is required")
    if args.max_sample_attempts < 1:
        parser.error("max-sample-attempts must be positive")

    build = run_command(
        [
            "wsl",
            "-d",
            "Ubuntu-22.04",
            "bash",
            wsl_path(PROJECT_ROOT / "scenarios" / "common" / "build.sh"),
        ]
        if os.name == "nt"
        else ["bash", str(PROJECT_ROOT / "scenarios" / "common" / "build.sh")],
        timeout=300,
    )
    if build.returncode != 0:
        raise RuntimeError(f"scenario image build failed: {build.stderr}")

    config = load_config()
    llm = LlmAdapter(AiosClient(config.aios), config.model)
    serial_runner = SerialBenchmarkRunner()
    parallel_runner = ParallelBenchmarkRunner()
    measurements: list[RunMeasurement] = []
    sample_counter = 0

    for scenario_id in args.scenarios:
        for _mode, runner in (("serial", serial_runner), ("parallel", parallel_runner)):
            workload = LocalScenarioWorkload(
                scenario_id=scenario_id,
                llm=llm,
                model_name=config.model.served_model_name,
                run_serial=sample_counter,
            )
            sample_counter += 1
            try:
                for warmup_no in range(args.warmups):
                    warmup_measurement = runner.run(
                        workload,
                        scenario_id=scenario_id,
                        sample_no=-(warmup_no + 1),
                        warmup=True,
                    )
                    measurements.append(warmup_measurement)
                    print(
                        f"{scenario_id} {_mode} warmup={warmup_no + 1} "
                        f"seconds={warmup_measurement.total_seconds:.3f} "
                        f"valid={warmup_measurement.valid}",
                        flush=True,
                    )
                for sample_no in range(1, args.samples + 1):
                    for _attempt_no in range(1, args.max_sample_attempts + 1):
                        measurement = runner.run(
                            workload,
                            scenario_id=scenario_id,
                            sample_no=sample_no,
                        )
                        measurements.append(measurement)
                        print(
                            f"{scenario_id} {_mode} sample={sample_no} "
                            f"attempt={_attempt_no} "
                            f"seconds={measurement.total_seconds:.3f} "
                            f"valid={measurement.valid}",
                            flush=True,
                        )
                        if measurement.valid:
                            break
                    else:
                        raise RuntimeError(
                            f"{scenario_id} {_mode} sample {sample_no} did not produce "
                            f"a valid result after {args.max_sample_attempts} attempts"
                        )
            finally:
                workload.close()

    all_measurements = tuple(measurements)
    summary = build_summary(
        environment="local-wsl2-ollama-development",
        model=config.model.served_model_name,
        backend=config.model.backend,
        samples_per_mode=args.samples,
        measurements=all_measurements,
    )
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": "local-wsl2-ollama-development",
        "model": config.model.served_model_name,
        "backend": config.model.backend,
        "prompt_versions": {
            task_id: config[1] for task_id, config in COLLECTION_CONFIG.items()
        },
        "scenario_ids": args.scenarios,
        "warmups_per_mode": args.warmups,
        "samples_per_mode": args.samples,
        "max_sample_attempts": args.max_sample_attempts,
        "raw_path": str(args.raw_path),
        "official_result": False,
    }
    bundle = RawBenchmarkBundle(
        summary=summary,
        measurements=all_measurements,
        metadata=metadata,
    )
    write_raw_bundle(bundle, args.raw_path)
    write_markdown_report(bundle, args.report_path)
    print(
        f"average_speedup={summary.average_speedup:.4f} "
        f"minimum_speedup={summary.minimum_speedup:.4f} "
        f"correctness_preserved={summary.correctness_preserved}"
    )
    return 0 if summary.average_speedup >= 0.20 and summary.correctness_preserved else 3


if __name__ == "__main__":
    raise SystemExit(main())
