"""DependencyAgent evidence collection through the controlled tool gateway."""

from __future__ import annotations

from ..models import Evidence, EvidenceKind, RunContext
from ..orchestrator.blackboard import ArtifactKind, Blackboard, BlackboardArtifact
from ..tools.base import ToolName, ToolRequest
from ..tools.gateway import ToolGateway
from ..utils import generate_id, utc_now


class DependencyAgent:
    """Inspect bounded process and port evidence for one service."""

    def __init__(
        self,
        gateway: ToolGateway,
        blackboard: Blackboard,
        *,
        agent_id: str = "dependency-agent-01",
    ) -> None:
        self.gateway = gateway
        self.blackboard = blackboard
        self.agent_id = agent_id

    def collect(self, context: RunContext, *, task_id: str = "N4") -> Evidence:
        result = self.gateway.execute(
            ToolRequest(
                request_id=generate_id("tool-request"),
                incident_id=context.incident_id,
                task_id=task_id,
                agent_id=self.agent_id,
                agent_type="DependencyAgent",
                tool_name=ToolName.DEPENDENCY_INSPECT,
                arguments={"service": context.target.service},
                timeout_seconds=5,
                max_output_bytes=24 * 1024,
            )
        )
        evidence = Evidence(
            evidence_id=generate_id("evi"),
            incident_id=context.incident_id,
            task_id=task_id,
            producer_agent="DependencyAgent",
            kind=EvidenceKind.DEPENDENCY,
            summary=f"Inspected process and port dependencies for {context.target.service}",
            source_ref="sandbox:/proc dependency view",
            observed_at=utc_now(),
            facts=result.data,
            confidence=0.82,
        )
        self.blackboard.put(
            BlackboardArtifact(
                artifact_id=generate_id("art"),
                incident_id=context.incident_id,
                producer_agent="DependencyAgent",
                kind=ArtifactKind.EVIDENCE,
                content_ref=evidence.evidence_id,
                created_at=utc_now(),
            )
        )
        return evidence
