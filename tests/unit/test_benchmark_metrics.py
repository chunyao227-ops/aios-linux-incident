"""W13 benchmark statistics tests."""

from datetime import datetime, timedelta, timezone

import pytest

from aios_incident.benchmark.metrics import (
    RunMeasurement,
    build_summary,
    percentile,
    speedup,
    summarize_measurements,
)
from aios_incident.models import TokenUsage

NOW = datetime(2026, 11, 22, tzinfo=timezone.utc)


def measurement(
    scenario_id: str,
    mode: str,
    sample_no: int,
    total_seconds: float,
    *,
    warmup: bool = False,
    correct: bool = True,
    valid: bool = True,
) -> RunMeasurement:
    return RunMeasurement(
        scenario_id=scenario_id,
        mode=mode,  # type: ignore[arg-type]
        sample_no=sample_no,
        warmup=warmup,
        valid=valid,
        started_at=NOW,
        ended_at=NOW + timedelta(seconds=total_seconds),
        total_seconds=total_seconds,
        collection_seconds=total_seconds * 0.8,
        finalize_seconds=total_seconds * 0.2,
        model_seconds=total_seconds * 0.7,
        tool_seconds=total_seconds * 0.1,
        token_usage=TokenUsage(prompt=10, completion=5, source="estimated"),
        tool_calls=7,
        correct=correct,
        message_count=11,
    )


def test_percentile_and_speedup() -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5
    assert percentile([1.0, 2.0, 3.0], 95) == pytest.approx(2.9)
    assert speedup(10.0, 7.0) == pytest.approx(0.3)


def test_warmups_are_excluded_from_summary() -> None:
    measurements = (
        measurement("f1", "serial", -1, 99.0, warmup=True),
        measurement("f1", "serial", 1, 50.0, correct=False, valid=False),
        measurement("f1", "serial", 1, 10.0),
        measurement("f1", "serial", 2, 12.0),
        measurement("f1", "parallel", -1, 99.0, warmup=True),
        measurement("f1", "parallel", 1, 7.0),
        measurement("f1", "parallel", 2, 9.0),
    )
    summaries = summarize_measurements(measurements)

    assert len(summaries) == 2
    assert all(summary.sample_count == 2 for summary in summaries)
    assert all(summary.median_seconds != 99.0 for summary in summaries)
    serial_summary = next(summary for summary in summaries if summary.mode == "serial")
    assert serial_summary.invalid_sample_count == 1


def test_summary_reports_average_speedup_and_correctness() -> None:
    measurements = tuple(
        [
            measurement("f1", "serial", sample, value)
            for sample, value in enumerate((10.0, 11.0, 12.0, 13.0, 14.0), 1)
        ]
        + [
            measurement("f1", "parallel", sample, value)
            for sample, value in enumerate((6.0, 6.5, 7.0, 7.5, 8.0), 1)
        ]
        + [
            measurement("f2", "serial", sample, value)
            for sample, value in enumerate((20.0, 21.0, 22.0, 23.0, 24.0), 1)
        ]
        + [
            measurement("f2", "parallel", sample, value)
            for sample, value in enumerate((14.0, 15.0, 16.0, 17.0, 18.0), 1)
        ]
    )
    summary = build_summary(
        environment="test",
        model="test-model",
        backend="test",
        samples_per_mode=5,
        measurements=measurements,
    )

    assert summary.average_speedup > 0.2
    assert summary.minimum_speedup > 0.2
    assert summary.correctness_preserved is True
