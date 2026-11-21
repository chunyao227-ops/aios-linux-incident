"""Serial baseline runner."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from ..models import TokenUsage
from .metrics import COLLECTION_TASKS, RunMeasurement, Workload


class SerialBenchmarkRunner:
    def run(
        self,
        workload: Workload,
        *,
        scenario_id: str,
        sample_no: int,
        warmup: bool = False,
    ) -> RunMeasurement:
        workload.prepare()
        started_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        collections = []
        for task_id in COLLECTION_TASKS:
            collections.append(workload.collect(task_id))
        collection_seconds = time.perf_counter() - started
        finalized = workload.finalize(tuple(collections))
        ended_at = datetime.now(timezone.utc)
        total_seconds = time.perf_counter() - started
        errors = tuple(
            error
            for error in (
                *(item.error for item in collections),
                finalized.error,
            )
            if error
        )
        return RunMeasurement(
            scenario_id=scenario_id,
            mode="serial",
            sample_no=sample_no,
            warmup=warmup,
            valid=(all(item.success for item in collections) and finalized.correct),
            started_at=started_at,
            ended_at=ended_at,
            total_seconds=total_seconds,
            collection_seconds=collection_seconds,
            finalize_seconds=finalized.elapsed_seconds,
            model_seconds=sum(item.model_seconds for item in collections) + finalized.model_seconds,
            tool_seconds=sum(item.tool_seconds for item in collections) + finalized.tool_seconds,
            token_usage=_sum_tokens(
                *(item.token_usage for item in collections),
                finalized.token_usage,
            ),
            tool_calls=sum(item.tool_calls for item in collections) + finalized.tool_calls,
            retry_count=finalized.retries,
            correct=all(item.success for item in collections) and finalized.correct,
            message_count=finalized.message_count,
            unauthorized_operations=finalized.unauthorized_operations,
            errors=errors,
            collections=tuple(collections),
            trace=(*(event for item in collections for event in item.trace), *finalized.trace),
        )


def _sum_tokens(*items: TokenUsage) -> TokenUsage:
    sources = {item.source for item in items}
    source = "reported" if sources == {"reported"} else "estimated"
    return TokenUsage(
        prompt=sum(item.prompt for item in items),
        completion=sum(item.completion for item in items),
        source=source,
    )
