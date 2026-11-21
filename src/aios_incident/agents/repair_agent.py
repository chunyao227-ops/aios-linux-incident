"""Minimal RepairAgent plan and controlled simulation executor."""

from __future__ import annotations

from typing import Protocol

from ..models import (
    Diagnosis,
    RepairAction,
    RepairPlan,
    RepairResult,
    RiskLevel,
    RunContext,
)
from ..orchestrator.blackboard import ArtifactKind, Blackboard, BlackboardArtifact
from ..utils import generate_id, utc_now


class RepairExecutor(Protocol):
    def execute(self, context: RunContext, plan: RepairPlan) -> RepairResult:
        """Execute a reviewed or simulated repair plan."""


class RepairAgent:
    """Generate a rollback-aware plan and delegate its execution."""

    def __init__(self, blackboard: Blackboard, *, agent_id: str = "repair-agent-01") -> None:
        self.blackboard = blackboard
        self.agent_id = agent_id

    def repair(
        self,
        context: RunContext,
        diagnosis: Diagnosis,
        *,
        recommended_action: str,
        executor: RepairExecutor,
    ) -> tuple[RepairPlan, RepairResult]:
        plan = self.create_plan(
            context,
            diagnosis,
            recommended_action=recommended_action,
        )
        result = self.execute_plan(context, plan, executor=executor)
        return plan, result

    def create_plan(
        self,
        context: RunContext,
        diagnosis: Diagnosis,
        *,
        recommended_action: str,
    ) -> RepairPlan:
        root_cause_ids = diagnosis.selected_root_cause_ids or tuple(
            root.root_cause_id for root in diagnosis.root_causes
        )
        action = RepairAction(
            action_id=generate_id("action"),
            description=recommended_action,
            tool_name="simulated_repair",
            parameters={"service": context.target.service},
            timeout_seconds=30,
            critical=True,
        )
        plan = RepairPlan(
            repair_id=generate_id("repair"),
            incident_id=context.incident_id,
            root_cause_ids=root_cause_ids,
            actions=(action,),
            preconditions=("diagnosis_contains_supporting_evidence",),
            expected_effect=f"{context.target.service} passes health and smoke checks",
            risk_level=RiskLevel.MEDIUM,
            rollback_plan=("restore the pre-repair simulated service state",),
            timeout_seconds=60,
            created_at=utc_now(),
        )
        self.blackboard.put(
            BlackboardArtifact(
                artifact_id=generate_id("art"),
                incident_id=context.incident_id,
                producer_agent="RepairAgent",
                kind=ArtifactKind.REPAIR_PLAN,
                content_ref=f"{plan.repair_id}:plan",
                created_at=utc_now(),
            )
        )
        return plan

    def execute_plan(
        self,
        context: RunContext,
        plan: RepairPlan,
        *,
        executor: RepairExecutor,
    ) -> RepairResult:
        result = executor.execute(context, plan)
        self.blackboard.put(
            BlackboardArtifact(
                artifact_id=generate_id("art"),
                incident_id=context.incident_id,
                producer_agent="RepairAgent",
                kind=ArtifactKind.REPAIR_EXECUTION,
                content_ref=f"{plan.repair_id}:result",
                created_at=utc_now(),
            )
        )
        return result
