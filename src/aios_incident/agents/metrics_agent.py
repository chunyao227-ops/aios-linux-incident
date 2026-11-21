"""MetricsAgent evidence collection through the controlled tool gateway."""

from __future__ import annotations

from ..models import Evidence, EvidenceKind, RunContext
from ..orchestrator.blackboard import ArtifactKind, Blackboard, BlackboardArtifact
from ..tools.base import ToolName, ToolRequest
from ..tools.gateway import ToolGateway
from ..utils import generate_id, utc_now


class MetricsAgent:
    """Collect structured resource metrics without executing arbitrary commands."""

    def __init__(
        self,
        gateway: ToolGateway,
        blackboard: Blackboard,
        *,
        agent_id: str = "metrics-agent-01",
    ) -> None:
        self.gateway = gateway
        self.blackboard = blackboard
        self.agent_id = agent_id

    def collect(self, context: RunContext, *, task_id: str = "N2") -> Evidence:
        result = self.gateway.execute(
            ToolRequest(
                request_id=generate_id("tool-request"),
                incident_id=context.incident_id,
                task_id=task_id,
                agent_id=self.agent_id,
                agent_type="MetricsAgent",
                tool_name=ToolName.METRICS_COLLECT,
                arguments={
                    "service": context.target.service,
                    "window_seconds": 60,
                },
                timeout_seconds=5,
                max_output_bytes=16 * 1024,
            )
        )
        evidence = Evidence(
            evidence_id=generate_id("evi"),
            incident_id=context.incident_id,
            task_id=task_id,
            producer_agent="MetricsAgent",
            kind=EvidenceKind.METRICS,
            summary=f"Collected bounded resource metrics for {context.target.service}",
            source_ref="sandbox:/proc",
            observed_at=utc_now(),
            facts={key: value for key, value in result.data.items() if key != "max_output_bytes"},
            confidence=0.8,
        )
        self.blackboard.put(
            BlackboardArtifact(
                artifact_id=generate_id("art"),
                incident_id=context.incident_id,
                producer_agent="MetricsAgent",
                kind=ArtifactKind.EVIDENCE,
                content_ref=evidence.evidence_id,
                created_at=utc_now(),
            )
        )
        return evidence
