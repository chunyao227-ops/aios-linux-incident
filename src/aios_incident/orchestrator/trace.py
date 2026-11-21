"""Append-only JSONL trace storage."""

from __future__ import annotations

import re
from pathlib import Path
from threading import RLock

from pydantic import ValidationError

from ..exceptions import TraceStoreError
from ..models import TraceEvent

SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class JsonlTraceStore:
    """Store one incident run as an append-only JSONL file."""

    def __init__(self, root_dir: Path, incident_id: str, run_id: str) -> None:
        _validate_component(incident_id, "incident_id")
        _validate_component(run_id, "run_id")
        self.root_dir = root_dir.resolve()
        self.incident_id = incident_id
        self.run_id = run_id
        self.path = self.root_dir / incident_id / f"{run_id}.jsonl"
        if self.root_dir not in self.path.parents:
            raise TraceStoreError("trace path escapes the configured trace root")
        self._lock = RLock()
        self._trace_ids = self._read_existing_trace_ids()

    def append(self, event: TraceEvent) -> None:
        """Append one validated event without overwriting prior events."""

        if event.incident_id != self.incident_id:
            raise TraceStoreError(
                f"trace incident mismatch: expected {self.incident_id}, got {event.incident_id}"
            )
        with self._lock:
            if event.trace_id in self._trace_ids:
                raise TraceStoreError(f"trace event already exists: {event.trace_id}")
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(event.model_dump_json())
                    stream.write("\n")
                    stream.flush()
            except OSError as exc:
                raise TraceStoreError(f"cannot append trace event: {exc}") from exc
            self._trace_ids.add(event.trace_id)

    def read_events(self) -> tuple[TraceEvent, ...]:
        """Read all trace events from the append-only file."""

        with self._lock:
            if not self.path.exists():
                return ()
            events: list[TraceEvent] = []
            try:
                with self.path.open("r", encoding="utf-8") as stream:
                    for line_number, line in enumerate(stream, start=1):
                        if not line.strip():
                            continue
                        try:
                            events.append(TraceEvent.model_validate_json(line))
                        except ValidationError as exc:
                            raise TraceStoreError(
                                f"invalid trace event at line {line_number}: {exc}"
                            ) from exc
            except OSError as exc:
                raise TraceStoreError(f"cannot read trace file: {exc}") from exc
            return tuple(events)

    def _read_existing_trace_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                trace_ids: set[str] = set()
                for _line_number, line in enumerate(stream, start=1):
                    if not line.strip():
                        continue
                    event = TraceEvent.model_validate_json(line)
                    if event.trace_id in trace_ids:
                        raise TraceStoreError(
                            f"duplicate trace event during load: {event.trace_id}"
                        )
                    trace_ids.add(event.trace_id)
                return trace_ids
        except ValidationError as exc:
            raise TraceStoreError(
                f"invalid existing trace file at line {_line_number}: {exc}"
            ) from exc
        except OSError as exc:
            raise TraceStoreError(f"cannot inspect existing trace file: {exc}") from exc


def _validate_component(value: str, label: str) -> None:
    if not SAFE_COMPONENT.fullmatch(value):
        raise TraceStoreError(f"{label} contains unsafe path characters")
