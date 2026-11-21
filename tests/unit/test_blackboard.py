"""W05 blackboard isolation and artifact readiness tests."""

from datetime import datetime, timezone

import pytest

from aios_incident.exceptions import (
    BlackboardArtifactNotFoundError,
    BlackboardArtifactNotReadyError,
    BlackboardConflictError,
)
from aios_incident.orchestrator.blackboard import (
    ArtifactKind,
    ArtifactState,
    Blackboard,
    BlackboardArtifact,
)

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def artifact(
    *,
    incident_id: str = "inc-001",
    artifact_id: str = "art-001",
    content_ref: str = "evi-N1-001",
    state: ArtifactState = ArtifactState.READY,
) -> BlackboardArtifact:
    return BlackboardArtifact(
        artifact_id=artifact_id,
        incident_id=incident_id,
        producer_agent="LogAgent",
        kind=ArtifactKind.EVIDENCE,
        content_ref=content_ref,
        created_at=NOW,
        state=state,
    )


def test_ready_artifact_can_be_read_and_resolved() -> None:
    board = Blackboard()
    item = artifact()
    board.put(item)

    assert board.get("inc-001", "art-001") == item
    assert board.resolve_ref("inc-001", "evi-N1-001") == item
    assert board.list_ready("inc-001") == (item,)


def test_pending_artifact_is_hidden_from_downstream_readers() -> None:
    board = Blackboard()
    board.put(artifact(state=ArtifactState.PENDING))

    with pytest.raises(BlackboardArtifactNotReadyError, match="not ready"):
        board.get("inc-001", "art-001")
    with pytest.raises(BlackboardArtifactNotFoundError, match="reference not found"):
        board.resolve_ref("inc-001", "evi-N1-001")
    assert board.list_ready("inc-001") == ()


def test_pending_artifact_can_be_completed_once_then_is_immutable() -> None:
    board = Blackboard()
    pending = artifact(state=ArtifactState.PENDING)
    ready = artifact()
    board.put(pending)
    board.put(ready)

    assert board.get("inc-001", "art-001") == ready
    with pytest.raises(BlackboardConflictError, match="immutable"):
        board.put(
            artifact(
                content_ref="evi-N1-002",
            )
        )


def test_incident_boundaries_are_isolated() -> None:
    board = Blackboard()
    board.put(artifact(incident_id="inc-001"))

    with pytest.raises(BlackboardArtifactNotFoundError):
        board.get("inc-002", "art-001")
    with pytest.raises(BlackboardArtifactNotFoundError):
        board.resolve_ref("inc-002", "evi-N1-001")


def test_duplicate_content_reference_is_rejected_within_incident() -> None:
    board = Blackboard()
    board.put(artifact())

    with pytest.raises(BlackboardConflictError, match="content_ref"):
        board.put(artifact(artifact_id="art-002"))


def test_same_content_reference_is_allowed_in_different_incidents() -> None:
    board = Blackboard()
    board.put(artifact(incident_id="inc-001"))
    board.put(artifact(incident_id="inc-002"))

    assert board.resolve_ref("inc-001", "evi-N1-001").incident_id == "inc-001"
    assert board.resolve_ref("inc-002", "evi-N1-001").incident_id == "inc-002"


def test_list_ready_is_filtered_by_kind() -> None:
    board = Blackboard()
    board.put(artifact())
    board.put(
        BlackboardArtifact(
            artifact_id="art-002",
            incident_id="inc-001",
            producer_agent="RepairAgent",
            kind=ArtifactKind.REPAIR_PLAN,
            content_ref="repair-001",
            created_at=NOW,
        )
    )

    assert len(board.list_ready("inc-001")) == 2
    evidence_artifacts = board.list_ready("inc-001", kind=ArtifactKind.EVIDENCE)
    assert [item.artifact_id for item in evidence_artifacts] == ["art-001"]
