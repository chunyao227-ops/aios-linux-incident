#!/usr/bin/env python3
"""Measure real one-shot, serial-four, and parallel-four latency."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def normalize_openai_base(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base
    return base + "/v1"


def call_model(
    base_url: str, model: str, api_key: str | None, prompt: str, max_tokens: int, timeout: float
):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        normalize_openai_base(base_url) + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
        },
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return {"elapsed_sec": time.perf_counter() - started, "raw": json.loads(body)}


async def measure_parallel(args, prompt: str):
    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(
            None,
            call_model,
            args.base_url,
            args.model,
            args.api_key,
            prompt,
            args.max_tokens,
            args.timeout,
        )
        for _ in range(4)
    ]
    started = time.perf_counter()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return time.perf_counter() - started, results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("MODEL_BASE_URL", ""))
    parser.add_argument("--model", default=os.getenv("MODEL_NAME", "Qwen2.5-7B-Instruct-AWQ"))
    parser.add_argument("--backend", default=os.getenv("MODEL_BACKEND", "openai-compatible"))
    parser.add_argument("--api-key", default=os.getenv("MODEL_API_KEY"))
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output", default="docs/environment/concurrency_probe_results.json")
    args = parser.parse_args()

    if not args.base_url:
        raise SystemExit("MODEL_BASE_URL or --base-url is required")

    prompt = "List three Linux service checks in concise plain text."
    record = {
        "model": args.model,
        "backend": args.backend,
        "base_url": args.base_url,
        "one_request": None,
        "serial_4_total_sec": None,
        "parallel_4_total_sec": None,
        "parallel_speedup": None,
        "errors": [],
    }

    try:
        one = call_model(
            args.base_url, args.model, args.api_key, prompt, args.max_tokens, args.timeout
        )
        record["one_request"] = {"elapsed_sec": one["elapsed_sec"]}
    except Exception as exc:
        record["errors"].append(f"single: {exc}")

    try:
        started = time.perf_counter()
        for _ in range(4):
            call_model(
                args.base_url, args.model, args.api_key, prompt, args.max_tokens, args.timeout
            )
        record["serial_4_total_sec"] = time.perf_counter() - started
    except Exception as exc:
        record["errors"].append(f"serial: {exc}")

    try:
        parallel_total, results = asyncio.run(measure_parallel(args, prompt))
        record["parallel_4_total_sec"] = parallel_total
        for item in results:
            if isinstance(item, Exception):
                record["errors"].append(f"parallel: {item}")
    except Exception as exc:
        record["errors"].append(f"parallel-run: {exc}")

    if record["serial_4_total_sec"] and record["parallel_4_total_sec"]:
        record["parallel_speedup"] = (
            record["serial_4_total_sec"] - record["parallel_4_total_sec"]
        ) / record["serial_4_total_sec"]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0 if not record["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
