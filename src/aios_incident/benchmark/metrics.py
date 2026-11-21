"""Benchmark contracts and deterministic statistics."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from ..models import StrictModel, TokenUsage

COLLECTION_TASKS = ("N1", "N2", "N3", "N4")


class CollectionOutcome(StrictModel):
    task_id: str
    prompt_id: str
    started_at: datetime
    ended_at: datetime
    elapsed_seconds: float
    model_seconds: float
    tool_seconds: float
    tool_calls: int = 0
    token_usage: TokenUsage
    success: bool
    evidence_id: str | None = None
    error: str | None = None
    trace: tuple[dict[str, Any], ...] = ()


class FinalizeOutcome(StrictModel):
    started_at: datetime
    ended_at: datetime
    elapsed_seconds: float
    model_seconds: float
    tool_seconds: float
    tool_calls: int = 0
    token_usage: TokenUsage
    correct: bool
    message_count: int = 0
    unauthorized_operations: int = 0
    retries: int = 0
    error: str | None = None
    trace: tuple[dict[str, Any], ...] = ()


class Workload(Protocol):
    def prepare(self) -> None:
        """Reset and fault the same scenario before timing starts."""

    def collect(self, task_id: str) -> CollectionOutcome:
        """Execute one fixed collection prompt and return evidence metadata."""

    def finalize(self, collections: tuple[CollectionOutcome, ...]) -> FinalizeOutcome:
        """Run diagnosis, repair, verification and report generation."""


class RunMeasurement(StrictModel):
    scenario_id: str
    mode: Literal["serial", "parallel"]
    sample_no: int
    warmup: bool
    valid: bool = True
    started_at: datetime
    ended_at: datetime
    total_seconds: float
    collection_seconds: float
    finalize_seconds: float
    model_seconds: float
    tool_seconds: float
    token_usage: TokenUsage
    tool_calls: int = 0
    retry_count: int = 0
    correct: bool
    message_count: int = 0
    unauthorized_operations: int = 0
    errors: tuple[str, ...] = ()
    collections: tuple[CollectionOutcome, ...] = ()
    trace: tuple[dict[str, Any], ...] = ()


class ScenarioModeSummary(StrictModel):
    scenario_id: str
    mode: Literal["serial", "parallel"]
    sample_count: int
    invalid_sample_count: int
    mean_seconds: float
    median_seconds: float
    p95_seconds: float
    correctness_rate: float
    mean_model_seconds: float
    mean_tool_seconds: float
    total_tokens: int
    total_tool_calls: int
    total_retries: int
    unauthorized_operations: int


class ScenarioComparison(StrictModel):
    scenario_id: str
    serial: ScenarioModeSummary
    parallel: ScenarioModeSummary
    median_speedup: float
    correctness_preserved: bool


class BenchmarkSummary(StrictModel):
    environment: str
    model: str
    backend: str
    samples_per_mode: int
    comparisons: tuple[ScenarioComparison, ...]
    average_speedup: float
    minimum_speedup: float
    correctness_preserved: bool
    unauthorized_operations: int
    invalid_sample_count: int


@dataclass(frozen=True, slots=True)
class RawBenchmarkBundle:
    summary: BenchmarkSummary
    measurements: tuple[RunMeasurement, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


def summarize_measurements(
    measurements: tuple[RunMeasurement, ...],
) -> tuple[ScenarioModeSummary, ...]:
    grouped: dict[tuple[str, str], list[RunMeasurement]] = {}
    for item in measurements:
        if item.warmup:
            continue
        grouped.setdefault((item.scenario_id, item.mode), []).append(item)

    summaries: list[ScenarioModeSummary] = []
    for (scenario_id, mode), attempts in sorted(grouped.items()):
        items = [item for item in attempts if item.valid]
        elapsed = sorted(item.total_seconds for item in items)
        summaries.append(
            ScenarioModeSummary(
                scenario_id=scenario_id,
                mode=mode,
                sample_count=len(items),
                invalid_sample_count=sum(not item.valid for item in attempts),
                mean_seconds=statistics.fmean(elapsed),
                median_seconds=statistics.median(elapsed),
                p95_seconds=percentile(elapsed, 95),
                correctness_rate=sum(item.correct for item in items) / len(items),
                mean_model_seconds=statistics.fmean(item.model_seconds for item in items),
                mean_tool_seconds=statistics.fmean(item.tool_seconds for item in items),
                total_tokens=sum(
                    item.token_usage.prompt + item.token_usage.completion for item in items
                ),
                total_tool_calls=sum(item.tool_calls for item in items),
                total_retries=sum(item.retry_count for item in items),
                unauthorized_operations=sum(item.unauthorized_operations for item in items),
            )
        )
    return tuple(summaries)


def count_invalid_samples(measurements: tuple[RunMeasurement, ...]) -> int:
    return sum(not item.warmup and not item.valid for item in measurements)


def compare_scenarios(
    summaries: tuple[ScenarioModeSummary, ...],
) -> tuple[ScenarioComparison, ...]:
    by_key = {(summary.scenario_id, summary.mode): summary for summary in summaries}
    scenario_ids = sorted({summary.scenario_id for summary in summaries})
    comparisons: list[ScenarioComparison] = []
    for scenario_id in scenario_ids:
        serial = by_key[(scenario_id, "serial")]
        parallel = by_key[(scenario_id, "parallel")]
        comparisons.append(
            ScenarioComparison(
                scenario_id=scenario_id,
                serial=serial,
                parallel=parallel,
                median_speedup=speedup(serial.median_seconds, parallel.median_seconds),
                correctness_preserved=parallel.correctness_rate >= serial.correctness_rate,
            )
        )
    return tuple(comparisons)


def build_summary(
    *,
    environment: str,
    model: str,
    backend: str,
    samples_per_mode: int,
    measurements: tuple[RunMeasurement, ...],
) -> BenchmarkSummary:
    comparisons = compare_scenarios(summarize_measurements(measurements))
    speedups = [comparison.median_speedup for comparison in comparisons]
    return BenchmarkSummary(
        environment=environment,
        model=model,
        backend=backend,
        samples_per_mode=samples_per_mode,
        comparisons=comparisons,
        average_speedup=statistics.fmean(speedups),
        minimum_speedup=min(speedups),
        correctness_preserved=all(comparison.correctness_preserved for comparison in comparisons),
        unauthorized_operations=sum(
            comparison.parallel.unauthorized_operations for comparison in comparisons
        ),
        invalid_sample_count=count_invalid_samples(measurements),
    )


def speedup(serial_seconds: float, parallel_seconds: float) -> float:
    if serial_seconds <= 0:
        raise ValueError("serial_seconds must be greater than zero")
    return (serial_seconds - parallel_seconds) / serial_seconds


def percentile(values: list[float], percent: float) -> float:
    """Return an interpolated percentile for a non-empty sorted numeric sample."""

    if not values:
        raise ValueError("values cannot be empty")
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * percent / 100
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return values[lower]
    fraction = rank - lower
    return values[lower] + (values[upper] - values[lower]) * fraction
