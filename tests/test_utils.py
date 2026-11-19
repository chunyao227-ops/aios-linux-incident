"""Timestamp and identifier utility tests."""

from datetime import datetime, timezone

import pytest

from aios_incident.utils import generate_id, utc_now


def test_utc_now_is_timezone_aware() -> None:
    now = utc_now()
    assert now.tzinfo is timezone.utc


def test_generated_ids_are_prefixed_and_unique() -> None:
    first = generate_id("run", at=datetime(2026, 11, 19, tzinfo=timezone.utc))
    second = generate_id("run", at=datetime(2026, 11, 19, tzinfo=timezone.utc))
    assert first.startswith("run-20261119T000000000000Z-")
    assert second.startswith("run-20261119T000000000000Z-")
    assert first != second


def test_identifier_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        generate_id("run", at=datetime(2026, 11, 19))
