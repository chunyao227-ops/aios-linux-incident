"""ConfigAgent evidence collection through the controlled tool gateway."""

from __future__ import annotations

from ..models import Evidence, EvidenceKind, RunContext
from ..orchestrator.blackboard import ArtifactKind, Blackboard, BlackboardArtifact
from ..tools.base import ToolName, ToolRequest
from ..tools.gateway import ToolGateway
from ..utils import generate_id, utc_now


class ConfigAgent:
    """Read one known configuration file inside the incident read scope."""

    def __init__(
        self,
        gateway: ToolGateway,
        blackboard: Blackboard,
        *,
        agent_id: str = "config-agent-01",
    ) -> None:
        self.gateway = gateway
        self.blackboard = blackboard
        self.agent_id = agent_id

    def collect(
        self,
        context: RunContext,
        *,
        config_path: str,
        task_id: str = "N3",
    ) -> Evidence:
        result = self.gateway.execute(
            ToolRequest(
                request_id=generate_id("tool-request"),
                incident_id=context.incident_id,
                task_id=task_id,
                agent_id=self.agent_id,
                agent_type="ConfigAgent",
                tool_name=ToolName.CONFIG_READ,
                arguments={"path": config_path},
                timeout_seconds=5,
                max_output_bytes=16 * 1024,
            )
        )
        evidence = Evidence(
            evidence_id=generate_id("evi"),
            incident_id=context.incident_id,
            task_id=task_id,
            producer_agent="ConfigAgent",
            kind=EvidenceKind.CONFIG,
            summary=f"Read bounded configuration evidence from {config_path}",
            source_ref=config_path,
            observed_at=utc_now(),
            facts={
                "sha256": result.data.get("sha256"),
                "size_bytes": result.data.get("size_bytes"),
                "truncated": result.truncated,
                "content": result.data.get("content"),
            },
            confidence=0.85,
        )
        self.blackboard.put(
            BlackboardArtifact(
                artifact_id=generate_id("art"),
                incident_id=context.incident_id,
                producer_agent="ConfigAgent",
                kind=ArtifactKind.EVIDENCE,
                content_ref=evidence.evidence_id,
                created_at=utc_now(),
            )
        )
        return evidence
