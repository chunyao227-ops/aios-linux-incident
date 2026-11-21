"""Minimal VerifierAgent with structured checks."""

from __future__ import annotations

from typing import Protocol

from ..models import (
    RepairResult,
    RunContext,
    VerificationCheck,
    VerificationResult,
)
from ..orchestrator.blackboard import ArtifactKind, Blackboard, BlackboardArtifact
from ..utils import generate_id, utc_now


class VerificationProbe(Protocol):
    def run_checks(
        self,
        context: RunContext,
        repair_result: RepairResult,
    ) -> tuple[VerificationCheck, ...]:
        """Return structured health, smoke and regression checks."""


class VerifierAgent:
    """Run structured checks after repair and never rely on LLM judgement."""

    def __init__(
        self,
        blackboard: Blackboard,
        *,
        agent_id: str = "verifier-agent-01",
    ) -> None:
        self.blackboard = blackboard
        self.agent_id = agent_id

    def verify(
        self,
        context: RunContext,
        repair_result: RepairResult,
        *,
        probe: VerificationProbe,
    ) -> VerificationResult:
        started_at = utc_now()
        checks = probe.run_checks(context, repair_result)
        ended_at = utc_now()
        passed = bool(checks) and all(check.passed for check in checks)
        failure_reasons = tuple(
            f"{check.name}: {check.details.get('reason', 'check failed')}"
            for check in checks
            if not check.passed
        )
        if not checks:
            failure_reasons = ("no verification checks were executed",)
        result = VerificationResult(
            verification_id=generate_id("verify"),
            incident_id=context.incident_id,
            repair_id=repair_result.repair_id,
            attempt_no=repair_result.attempt_no,
            passed=passed,
            checks=checks,
            failure_reasons=failure_reasons,
            started_at=started_at,
            ended_at=ended_at,
        )
        self.blackboard.put(
            BlackboardArtifact(
                artifact_id=generate_id("art"),
                incident_id=context.incident_id,
                producer_agent="VerifierAgent",
                kind=ArtifactKind.VERIFICATION_RESULT,
                content_ref=result.verification_id,
                created_at=utc_now(),
            )
        )
        return result
