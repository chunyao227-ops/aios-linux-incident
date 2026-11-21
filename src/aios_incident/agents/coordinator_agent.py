"""Minimal CoordinatorAgent planning and diagnosis."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import Field

from ..adapters.llm_adapter import ChatMessage, StructuredLLMResponse
from ..models import (
    Diagnosis,
    Evidence,
    NonEmptyStr,
    RiskLevel,
    RootCauseCandidate,
    RunContext,
    StrictModel,
)
from ..utils import generate_id, utc_now

OutputModelT = TypeVar("OutputModelT")


class DiagnosisJsonClient(Protocol):
    def chat_json(
        self,
        messages: Sequence[ChatMessage],
        *,
        output_model: type[OutputModelT],
        agent_name: str = "CoordinatorAgent",
        temperature: float | None = None,
        max_new_tokens: int | None = None,
        user_id: str | None = None,
    ) -> StructuredLLMResponse[OutputModelT]:
        """Return a typed JSON model response."""


class MinimalAnalysisTask(StrictModel):
    task_id: NonEmptyStr = "N1"
    incident_id: NonEmptyStr
    service: NonEmptyStr
    log_path: NonEmptyStr
    objective: NonEmptyStr


class MinimalDiagnosisOutput(StrictModel):
    root_cause: NonEmptyStr
    confidence: float = Field(ge=0, le=1)
    repair_action: NonEmptyStr


@dataclass(frozen=True, slots=True)
class CoordinatorDiagnosis:
    diagnosis: Diagnosis
    repair_action: str


class CoordinatorAgent:
    """Create the single analysis task and fuse its output into a diagnosis."""

    def __init__(self, agent_id: str = "coordinator-01") -> None:
        self.agent_id = agent_id

    def plan(self, context: RunContext, *, log_path: str) -> MinimalAnalysisTask:
        return MinimalAnalysisTask(
            incident_id=context.incident_id,
            service=context.target.service,
            log_path=log_path,
            objective=context.objective,
        )

    def diagnose(
        self,
        context: RunContext,
        task: MinimalAnalysisTask,
        evidence: Evidence,
        llm: DiagnosisJsonClient,
    ) -> CoordinatorDiagnosis:
        last_line = str(evidence.facts.get("last_line", evidence.summary))
        structured = llm.chat_json(
            [
                ChatMessage(
                    role="system",
                    content=(
                        "Analyze one Linux service incident from structured evidence. "
                        "Return the requested JSON only. Do not invent evidence."
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=(
                        f"Service: {task.service}\n"
                        f"Objective: {task.objective}\n"
                        f"Evidence summary: {evidence.summary}\n"
                        f"Latest log line: {last_line}\n"
                        "Return root_cause, confidence from 0 to 1, and one repair_action."
                    ),
                ),
            ],
            output_model=MinimalDiagnosisOutput,
            agent_name="CoordinatorAgent",
            max_new_tokens=256,
        )
        output = structured.data
        root_cause = RootCauseCandidate(
            root_cause_id=generate_id("rc"),
            description=output.root_cause,
            supporting_evidence=(evidence.evidence_id,),
            confidence=output.confidence,
            repair_risk=RiskLevel.MEDIUM,
            required_scope=(task.service,),
        )
        diagnosis = Diagnosis(
            diagnosis_id=generate_id("diag"),
            incident_id=context.incident_id,
            root_causes=(root_cause,),
            selected_root_cause_ids=(root_cause.root_cause_id,),
            repair_constraints=(f"allowed_service:{task.service}",),
            created_at=utc_now(),
        )
        return CoordinatorDiagnosis(
            diagnosis=diagnosis,
            repair_action=output.repair_action,
        )
