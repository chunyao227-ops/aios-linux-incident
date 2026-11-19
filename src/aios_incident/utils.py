"""Small deterministic utilities shared by application modules."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def generate_id(prefix: str, *, at: datetime | None = None) -> str:
    """Generate a sortable, prefixed identifier with a random suffix."""

    normalized = re.sub(r"[^a-z0-9]+", "-", prefix.lower()).strip("-")
    if not normalized:
        raise ValueError("prefix must contain at least one letter or digit")
    timestamp = at or utc_now()
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    utc_timestamp = timestamp.astimezone(timezone.utc)
    return f"{normalized}-{utc_timestamp:%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex[:12]}"
