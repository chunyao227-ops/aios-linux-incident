#!/usr/bin/env python3
"""Check a remote OpenAI-compatible vLLM endpoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def normalize_openai_base(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base
    return base + "/v1"


def request_json(method: str, url: str, api_key: str | None, payload: dict | None, timeout: float):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body), time.perf_counter() - start
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("MODEL_BASE_URL", ""))
    parser.add_argument("--model", default=os.getenv("MODEL_NAME", "Qwen2.5-7B-Instruct-AWQ"))
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    if not args.base_url:
        print("MODEL_BASE_URL or --base-url is required", file=sys.stderr)
        return 2

    base = normalize_openai_base(args.base_url)
    api_key = os.getenv("MODEL_API_KEY")
    result: dict[str, object] = {"base_url": base, "model": args.model}

    try:
        status, models, elapsed = request_json("GET", base + "/models", api_key, None, args.timeout)
        result["models_check"] = {"status": status, "elapsed_sec": elapsed, "payload": models}
        print(f"OK /v1/models: HTTP {status}, {elapsed:.3f}s")
    except Exception as exc:
        result["models_check"] = {"error": str(exc)}
        print(f"FAIL /v1/models: {exc}", file=sys.stderr)
        return 1

    chat_payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": 'Return {"ok":true,"role":"model"}'},
        ],
        "temperature": 0,
        "max_tokens": 64,
    }
    try:
        status, response, elapsed = request_json(
            "POST", base + "/chat/completions", api_key, chat_payload, args.timeout
        )
        result["chat_check"] = {"status": status, "elapsed_sec": elapsed, "payload": response}
        print(f"OK chat completion: HTTP {status}, {elapsed:.3f}s")
    except Exception as exc:
        result["chat_check"] = {"error": str(exc)}
        print(f"FAIL chat completion: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
