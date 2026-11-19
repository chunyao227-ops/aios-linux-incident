"""Command-line entry point for configuration validation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .config import load_config
from .exceptions import ConfigurationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate an AIOS incident configuration.")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to app YAML. Defaults to AIOS_INCIDENT_CONFIG or config/app.example.yaml.",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print the validated configuration with secrets omitted.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigurationError as exc:
        print(f"configuration error: {exc}")
        return 2

    if args.show_config:
        print(json.dumps(config.to_public_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"configuration valid: {config.app.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
