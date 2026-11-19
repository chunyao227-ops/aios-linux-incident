#!/usr/bin/env python3
"""Check AIOS kernel health without storing credentials."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def fetch_json(url: str, timeout: float) -> tuple[int, object]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    checks = ["/status", "/core/status"]
    failed = False
    output: dict[str, object] = {"base_url": base, "checks": {}}

    for path in checks:
        try:
            status, payload = fetch_json(base + path, args.timeout)
            output["checks"][path] = {"http_status": status, "payload": payload}
            print(f"OK {path}: HTTP {status}")
        except Exception as exc:
            output["checks"][path] = {"error": str(exc)}
            print(f"FAIL {path}: {exc}", file=sys.stderr)
            failed = True

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
