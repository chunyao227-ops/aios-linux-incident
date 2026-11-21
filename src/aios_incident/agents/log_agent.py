"""Minimal LogAgent evidence collection through the controlled tool gateway."""

from __future__ import annotations

from ..models import Evidence, EvidenceKind, RunContext
from ..orchestrator.blackboard import ArtifactKind, Blackboard, BlackboardArtifact
from ..tools.base import ToolName, ToolRequest
from ..tools.gateway import ToolGateway
from ..utils import generate_id, utc_now
from .coordinator_agent import MinimalAnalysisTask


class LogAgent:
    """Collect bounded log evidence for the minimal workflow."""

    def __init__(
        self,
        gateway: ToolGateway,
        blackboard: Blackboard,
        *,
        agent_id: str = "log-agent-01",
    ) -> None:
        self.gateway = gateway
        self.blackboard = blackboard
        self.agent_id = agent_id

    def collect(self, context: RunContext, task: MinimalAnalysisTask) -> Evidence:
        tool_result = self.gateway.execute(
            ToolRequest(
                request_id=generate_id("tool-request"),
                incident_id=context.incident_id,
                task_id=task.task_id,
                agent_id=self.agent_id,
                agent_type="LogAgent",
                tool_name=ToolName.LOG_READ,
                arguments={"path": task.log_path, "max_lines": 100},
                timeout_seconds=5,
                max_output_bytes=16 * 1024,
            )
        )
        lines = tool_result.data.get("lines", [])
        if not isinstance(lines, list):
            lines = []
        last_line = str(lines[-1]) if lines else "no log lines observed"
        evidence = Evidence(
            evidence_id=generate_id("evi"),
            incident_id=context.incident_id,
            task_id=task.task_id,
            producer_agent="LogAgent",
            kind=EvidenceKind.LOG,
            summary=f"Observed {len(lines)} bounded log lines for {task.service}",
            source_ref=task.log_path,
            observed_at=utc_now(),
            facts={
                "line_count": len(lines),
                "last_line": last_line,
                "truncated": tool_result.truncated,
            },
            confidence=0.85,
        )
        self.blackboard.put(
            BlackboardArtifact(
                artifact_id=generate_id("art"),
                incident_id=context.incident_id,
                producer_agent="LogAgent",
                kind=ArtifactKind.EVIDENCE,
                content_ref=evidence.evidence_id,
                created_at=utc_now(),
            )
        )
        return evidence
