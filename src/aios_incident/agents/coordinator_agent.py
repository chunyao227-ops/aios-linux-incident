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
    Message,
    MessageType,
    NonEmptyStr,
    RepairResult,
    RiskLevel,
    RootCauseCandidate,
    RunContext,
    StrictModel,
    VerificationResult,
)
from ..orchestrator.interaction_bus import InteractionBus, InteractionGraph
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

    def coordinate_required_interactions(
        self,
        context: RunContext,
        bus: InteractionBus,
        *,
        log_evidence: Evidence,
        config_evidence: Evidence,
        metrics_evidence: Evidence,
        dependency_evidence: Evidence,
        repair_result: RepairResult,
        verification_result: VerificationResult,
    ) -> InteractionGraph:
        """Generate the three fixed bidirectional evidence/verification exchanges."""

        log_agent = bus.resolve_agent_id("LogAgent")
        config_agent = bus.resolve_agent_id("ConfigAgent")
        metrics_agent = bus.resolve_agent_id("MetricsAgent")
        dependency_agent = bus.resolve_agent_id("DependencyAgent")
        repair_agent = bus.resolve_agent_id("RepairAgent")
        verifier_agent = bus.resolve_agent_id("VerifierAgent")

        log_question = bus.send_question(
            incident_id=context.incident_id,
            task_id="N1",
            from_agent=log_agent,
            to_agent=config_agent,
            content=(
                f"Check configuration for {context.target.service} after log evidence: "
                f"{log_evidence.summary}; latest={log_evidence.facts.get('last_line', '')}"
            ),
            evidence_ids=(log_evidence.evidence_id,),
        )
        bus.send_reply(
            log_question,
            from_agent=config_agent,
            content=(
                f"Configuration reference {config_evidence.source_ref} has sha256 "
                f"{config_evidence.facts.get('sha256')}"
            ),
            evidence_ids=(config_evidence.evidence_id,),
        )
        bus.wait_for_response(log_question.correlation_id, timeout_seconds=1)

        config_question = bus.send_question(
            incident_id=context.incident_id,
            task_id="N3",
            from_agent=config_agent,
            to_agent=log_agent,
            content=(
                f"Provide log timeline context for configuration evidence "
                f"{config_evidence.evidence_id}"
            ),
            evidence_ids=(config_evidence.evidence_id,),
        )
        bus.send_reply(
            config_question,
            from_agent=log_agent,
            content=(
                f"Log reference {log_evidence.source_ref}: "
                f"{log_evidence.facts.get('last_line', log_evidence.summary)}"
            ),
            evidence_ids=(log_evidence.evidence_id,),
        )
        bus.wait_for_response(config_question.correlation_id, timeout_seconds=1)

        metrics_question = bus.send_question(
            incident_id=context.incident_id,
            task_id="N2",
            from_agent=metrics_agent,
            to_agent=dependency_agent,
            content=(
                f"Check process and port state for {context.target.service} after metrics: "
                f"{metrics_evidence.summary}"
            ),
            evidence_ids=(metrics_evidence.evidence_id,),
        )
        dependency_reply = bus.send_reply(
            metrics_question,
            from_agent=dependency_agent,
            content=(
                f"Observed {len(dependency_evidence.facts.get('processes', []))} matching "
                f"processes and {len(dependency_evidence.facts.get('ports', []))} ports"
            ),
            evidence_ids=(dependency_evidence.evidence_id,),
        )
        bus.wait_for_response(metrics_question.correlation_id, timeout_seconds=1)

        dependency_question = bus.send_question(
            incident_id=context.incident_id,
            task_id="N4",
            from_agent=dependency_agent,
            to_agent=metrics_agent,
            content=f"Provide metric trend for dependency evidence {dependency_reply.message_id}",
            evidence_ids=(dependency_evidence.evidence_id,),
        )
        bus.send_reply(
            dependency_question,
            from_agent=metrics_agent,
            content=(
                f"Load average={metrics_evidence.facts.get('load_average')}; "
                f"memory={metrics_evidence.facts.get('memory_kib')}"
            ),
            evidence_ids=(metrics_evidence.evidence_id,),
        )
        bus.wait_for_response(dependency_question.correlation_id, timeout_seconds=1)

        handoff = bus.send(
            Message(
                message_id=generate_id("msg"),
                incident_id=context.incident_id,
                task_id="N6.1",
                from_agent=repair_agent,
                to_agent=verifier_agent,
                type=MessageType.HANDOFF,
                content=(
                    f"Repair {repair_result.repair_id} finished with {repair_result.status.value}"
                ),
                evidence_ids=(
                    log_evidence.evidence_id,
                    config_evidence.evidence_id,
                    metrics_evidence.evidence_id,
                    dependency_evidence.evidence_id,
                ),
                correlation_id=generate_id("corr"),
                timestamp=utc_now(),
            )
        )
        if verification_result.passed:
            bus.send(
                Message(
                    message_id=generate_id("msg"),
                    incident_id=context.incident_id,
                    task_id="N7.1",
                    from_agent=verifier_agent,
                    to_agent=repair_agent,
                    type=MessageType.VERIFIED,
                    content=f"Verification passed: {verification_result.verification_id}",
                    correlation_id=handoff.correlation_id,
                    reply_to=handoff.message_id,
                    timestamp=utc_now(),
                )
            )
            bus.send(
                Message(
                    message_id=generate_id("msg"),
                    incident_id=context.incident_id,
                    task_id="N7.1",
                    from_agent=verifier_agent,
                    to_agent=repair_agent,
                    type=MessageType.RESULT,
                    content=f"Final verification result: {verification_result.verification_id}",
                    correlation_id=handoff.correlation_id,
                    reply_to=handoff.message_id,
                    timestamp=utc_now(),
                )
            )
        else:
            bus.send(
                Message(
                    message_id=generate_id("msg"),
                    incident_id=context.incident_id,
                    task_id="N7.1",
                    from_agent=verifier_agent,
                    to_agent=repair_agent,
                    type=MessageType.FEEDBACK,
                    content="; ".join(verification_result.failure_reasons),
                    correlation_id=handoff.correlation_id,
                    reply_to=handoff.message_id,
                    timestamp=utc_now(),
                )
            )
        return bus.graph()
