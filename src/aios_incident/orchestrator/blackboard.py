"""Incident-isolated, append-oriented shared blackboard."""

from __future__ import annotations

from enum import Enum
from threading import RLock
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from ..exceptions import (
    BlackboardArtifactNotFoundError,
    BlackboardArtifactNotReadyError,
    BlackboardConflictError,
)
from ..models import ImmutableModel, NonEmptyStr
from ..utils import utc_now


class ArtifactKind(str, Enum):
    TASK_INPUT = "task_input"
    EVIDENCE = "evidence"
    ROOT_CAUSE = "root_cause"
    REPAIR_PLAN = "repair_plan"
    REPAIR_EXECUTION = "repair_execution"
    VERIFICATION_RESULT = "verification_result"
    MESSAGE = "message"
    FINAL_REPORT = "final_report"


class ArtifactState(str, Enum):
    PENDING = "PENDING"
    READY = "READY"


class BlackboardArtifact(ImmutableModel):
    """Immutable reference to one blackboard artifact."""

    artifact_id: NonEmptyStr
    incident_id: NonEmptyStr
    producer_agent: NonEmptyStr
    kind: ArtifactKind
    content_ref: NonEmptyStr
    created_at: AwareDatetime = Field(default_factory=utc_now)
    immutable: Literal[True] = True
    state: ArtifactState = ArtifactState.READY

    @model_validator(mode="after")
    def validate_state(self) -> BlackboardArtifact:
        if not self.immutable:
            raise ValueError("blackboard artifacts must be immutable")
        return self


class Blackboard:
    """Thread-safe in-memory blackboard isolated by incident ID."""

    def __init__(self) -> None:
        self._artifacts: dict[tuple[str, str], BlackboardArtifact] = {}
        self._lock = RLock()

    def put(self, artifact: BlackboardArtifact) -> None:
        """Insert an artifact or complete one pending artifact exactly once."""

        key = (artifact.incident_id, artifact.artifact_id)
        with self._lock:
            existing = self._artifacts.get(key)
            if existing == artifact:
                return
            if existing is not None:
                if (
                    existing.state is not ArtifactState.PENDING
                    or artifact.state is not ArtifactState.READY
                ):
                    raise BlackboardConflictError(
                        f"artifact is immutable: {artifact.incident_id}/{artifact.artifact_id}"
                    )

            if artifact.state is ArtifactState.READY:
                for other in self._artifacts.values():
                    if (
                        other.incident_id == artifact.incident_id
                        and other.content_ref == artifact.content_ref
                        and other.artifact_id != artifact.artifact_id
                    ):
                        raise BlackboardConflictError(
                            "content_ref is already assigned to another artifact in this incident"
                        )
            self._artifacts[key] = artifact

    def get(self, incident_id: str, artifact_id: str) -> BlackboardArtifact:
        """Read a completed artifact without crossing incident boundaries."""

        key = (incident_id, artifact_id)
        with self._lock:
            artifact = self._artifacts.get(key)
        if artifact is None:
            raise BlackboardArtifactNotFoundError(
                f"artifact not found: {incident_id}/{artifact_id}"
            )
        if artifact.state is not ArtifactState.READY:
            raise BlackboardArtifactNotReadyError(
                f"artifact is not ready: {incident_id}/{artifact_id}"
            )
        return artifact

    def resolve_ref(self, incident_id: str, content_ref: str) -> BlackboardArtifact:
        """Resolve a content reference to one completed artifact."""

        with self._lock:
            for artifact in self._artifacts.values():
                if (
                    artifact.incident_id == incident_id
                    and artifact.content_ref == content_ref
                    and artifact.state is ArtifactState.READY
                ):
                    return artifact
        raise BlackboardArtifactNotFoundError(
            f"ready artifact reference not found: {incident_id}/{content_ref}"
        )

    def list_ready(
        self,
        incident_id: str,
        *,
        kind: ArtifactKind | None = None,
    ) -> tuple[BlackboardArtifact, ...]:
        """List completed artifacts for one incident in creation order."""

        with self._lock:
            artifacts = [
                artifact
                for artifact in self._artifacts.values()
                if artifact.incident_id == incident_id
                and artifact.state is ArtifactState.READY
                and (kind is None or artifact.kind is kind)
            ]
        return tuple(sorted(artifacts, key=lambda artifact: artifact.created_at))
