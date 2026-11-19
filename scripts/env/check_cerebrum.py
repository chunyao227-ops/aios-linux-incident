#!/usr/bin/env python3
"""Verify the installed Cerebrum/aios-agent-sdk package version."""

from __future__ import annotations

import importlib.metadata
import json
import sys


EXPECTED = "0.0.3"


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def main() -> int:
    result = {
        "expected": EXPECTED,
        "cerebrum_distribution": package_version("cerebrum"),
        "aios_agent_sdk_distribution": package_version("aios-agent-sdk"),
        "import_check": False,
    }
    try:
        import cerebrum  # noqa: F401

        result["import_check"] = True
    except Exception as exc:
        result["import_error"] = str(exc)

    versions = {
        result["cerebrum_distribution"],
        result["aios_agent_sdk_distribution"],
    }
    result["matches_expected"] = EXPECTED in versions
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["matches_expected"] and result["import_check"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
