"""Evidence fusion, conflict detection and structured root-cause diagnosis."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import AwareDatetime, Field

from ..exceptions import DiagnosticEvidenceError
from ..models import (
    Diagnosis,
    Evidence,
    EvidenceKind,
    Message,
    NonEmptyStr,
    RiskLevel,
    RootCauseCandidate,
    RunContext,
    StrictModel,
)
from ..utils import generate_id, utc_now

REQUIRED_EVIDENCE_KINDS = frozenset(
    {
        EvidenceKind.LOG,
        EvidenceKind.METRICS,
        EvidenceKind.CONFIG,
        EvidenceKind.DEPENDENCY,
    }
)


class EvidenceChainEntry(StrictModel):
    evidence_id: NonEmptyStr
    kind: EvidenceKind
    producer_agent: NonEmptyStr
    service: NonEmptyStr
    source_ref: NonEmptyStr
    observed_at: AwareDatetime
    linked_message_ids: tuple[NonEmptyStr, ...] = ()


class MergedFact(StrictModel):
    fact_key: NonEmptyStr
    value: Any
    evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    source_kinds: tuple[EvidenceKind, ...] = Field(min_length=1)


class EvidenceConflict(StrictModel):
    fact_key: NonEmptyStr
    evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=2)
    values: tuple[Any, ...] = Field(min_length=2)


class FollowUpRequest(StrictModel):
    follow_up_id: NonEmptyStr
    target_agent: NonEmptyStr
    fact_key: NonEmptyStr
    question: NonEmptyStr
    related_evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=2)
    correlation_id: NonEmptyStr


class DiagnosisFusionResult(StrictModel):
    status: Literal["READY", "BLOCKED"]
    service: NonEmptyStr
    evidence_chain: tuple[EvidenceChainEntry, ...]
    merged_facts: tuple[MergedFact, ...]
    conflicts: tuple[EvidenceConflict, ...]
    follow_up_requests: tuple[FollowUpRequest, ...]
    diagnosis: Diagnosis
    interaction_message_ids: tuple[NonEmptyStr, ...]


class DiagnosisFusionEngine:
    """Fuse four evidence classes without inventing unsupported references."""

    def fuse(
        self,
        context: RunContext,
        evidence: Sequence[Evidence],
        interaction_messages: Sequence[Message] = (),
    ) -> DiagnosisFusionResult:
        self._validate_inputs(context, evidence, interaction_messages)
        ordered_evidence = tuple(sorted(evidence, key=lambda item: item.observed_at))
        merged_facts, conflicts = _merge_facts(ordered_evidence)
        conflict_evidence_ids = {
            evidence_id for conflict in conflicts for evidence_id in conflict.evidence_ids
        }
        root_causes, excluded = _build_root_causes(
            context,
            ordered_evidence,
            conflict_evidence_ids,
        )
        follow_ups = _build_follow_ups(conflicts)
        status = "BLOCKED" if conflicts else "READY"
        selected = (
            () if conflicts else tuple(root_cause.root_cause_id for root_cause in root_causes[:1])
        )
        diagnosis = Diagnosis(
            diagnosis_id=generate_id("diag"),
            incident_id=context.incident_id,
            root_causes=root_causes,
            selected_root_cause_ids=selected,
            excluded_hypotheses=excluded,
            conflicting_evidence=tuple(sorted(conflict_evidence_ids)),
            repair_constraints=_repair_constraints(context, root_causes, conflicts),
            created_at=utc_now(),
        )
        chain = _build_evidence_chain(context, ordered_evidence, interaction_messages)
        return DiagnosisFusionResult(
            status=status,
            service=context.target.service,
            evidence_chain=chain,
            merged_facts=merged_facts,
            conflicts=conflicts,
            follow_up_requests=follow_ups,
            diagnosis=diagnosis,
            interaction_message_ids=tuple(message.message_id for message in interaction_messages),
        )

    @staticmethod
    def _validate_inputs(
        context: RunContext,
        evidence: Sequence[Evidence],
        interaction_messages: Sequence[Message],
    ) -> None:
        if not evidence:
            raise DiagnosticEvidenceError("at least four evidence records are required")
        evidence_ids = [item.evidence_id for item in evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise DiagnosticEvidenceError("evidence IDs must be unique")
        kinds = {item.kind for item in evidence}
        missing = REQUIRED_EVIDENCE_KINDS - kinds
        if missing:
            raise DiagnosticEvidenceError(
                f"missing evidence kinds: {sorted(kind.value for kind in missing)}"
            )
        for item in evidence:
            if item.incident_id != context.incident_id:
                raise DiagnosticEvidenceError("evidence incident does not match context")
        for message in interaction_messages:
            if message.incident_id != context.incident_id:
                raise DiagnosticEvidenceError("interaction message incident does not match")
            unknown_refs = set(message.evidence_ids) - set(evidence_ids)
            if unknown_refs:
                raise DiagnosticEvidenceError(
                    f"message references unknown evidence: {sorted(unknown_refs)}"
                )


def _merge_facts(
    evidence: Sequence[Evidence],
) -> tuple[tuple[MergedFact, ...], tuple[EvidenceConflict, ...]]:
    grouped: dict[str, list[tuple[Any, str, EvidenceKind]]] = {}
    for item in evidence:
        for key, value in item.facts.items():
            grouped.setdefault(key, []).append((value, item.evidence_id, item.kind))

    merged: list[MergedFact] = []
    conflicts: list[EvidenceConflict] = []
    for key in sorted(grouped):
        value_groups: dict[str, list[tuple[Any, str, EvidenceKind]]] = {}
        for value, evidence_id, kind in grouped[key]:
            signature = json.dumps(value, sort_keys=True, default=str)
            value_groups.setdefault(signature, []).append((value, evidence_id, kind))
        if len(value_groups) > 1:
            values = tuple(next(iter(group))[0] for group in value_groups.values())
            evidence_ids = tuple(
                sorted(
                    {evidence_id for group in value_groups.values() for _, evidence_id, _ in group}
                )
            )
            conflicts.append(
                EvidenceConflict(
                    fact_key=key,
                    evidence_ids=evidence_ids,
                    values=values,
                )
            )
        for group in value_groups.values():
            first_value = group[0][0]
            merged.append(
                MergedFact(
                    fact_key=key,
                    value=first_value,
                    evidence_ids=tuple(sorted({item[1] for item in group})),
                    source_kinds=tuple(
                        sorted({item[2] for item in group}, key=lambda item: item.value)
                    ),
                )
            )
    return tuple(merged), tuple(conflicts)


def _build_root_causes(
    context: RunContext,
    evidence: Sequence[Evidence],
    conflict_evidence_ids: set[str],
) -> tuple[tuple[RootCauseCandidate, ...], tuple[str, ...]]:
    by_kind = {item.kind: item for item in evidence}
    log = by_kind[EvidenceKind.LOG]
    metrics = by_kind[EvidenceKind.METRICS]
    config = by_kind[EvidenceKind.CONFIG]
    dependency = by_kind[EvidenceKind.DEPENDENCY]
    log_text = f"{log.summary} {log.facts.get('last_line', '')}".lower()
    config_text = str(config.facts.get("content", "")).lower()
    processes = dependency.facts.get("processes", [])
    ports = dependency.facts.get("ports", [])
    memory = metrics.facts.get("memory_kib", {})
    load = metrics.facts.get("load_average", {})

    candidates: list[RootCauseCandidate] = []
    excluded: list[str] = []

    dependency_signal = (
        "connection refused" in log_text or "econnrefused" in log_text or not processes or not ports
    )
    if dependency_signal:
        support = (log.evidence_id, dependency.evidence_id)
        supporting, contradicting = _split_support_and_conflicts(
            support,
            conflict_evidence_ids,
        )
        candidates.append(
            RootCauseCandidate(
                root_cause_id=generate_id("rc"),
                description="required service dependency or listener is unavailable",
                supporting_evidence=supporting,
                contradicting_evidence=contradicting,
                confidence=0.86,
                repair_risk=RiskLevel.MEDIUM,
                required_scope=(context.target.service,),
            )
        )
    else:
        excluded.append("dependency outage excluded: process and port evidence were present")

    memory_available = (
        _positive_number(memory.get("MemAvailable")) if isinstance(memory, dict) else 0
    )
    one_minute_load = _positive_number(load.get("one_minute")) if isinstance(load, dict) else 0
    if memory_available and memory_available < 256 * 1024:
        supporting, contradicting = _split_support_and_conflicts(
            (metrics.evidence_id,),
            conflict_evidence_ids,
        )
        candidates.append(
            RootCauseCandidate(
                root_cause_id=generate_id("rc"),
                description="available memory is critically low",
                supporting_evidence=supporting,
                contradicting_evidence=contradicting,
                confidence=0.82,
                repair_risk=RiskLevel.HIGH,
                required_scope=(context.target.service,),
            )
        )
    elif not (one_minute_load > 4 and "timeout" in log_text):
        excluded.append("resource exhaustion excluded: no critical memory or load signal")

    if config.facts.get("truncated") is True or (
        "invalid" in config_text and "configuration" in config_text
    ):
        supporting, contradicting = _split_support_and_conflicts(
            (config.evidence_id,),
            conflict_evidence_ids,
        )
        candidates.append(
            RootCauseCandidate(
                root_cause_id=generate_id("rc"),
                description="configuration evidence is invalid or incomplete",
                supporting_evidence=supporting,
                contradicting_evidence=contradicting,
                confidence=0.75,
                repair_risk=RiskLevel.MEDIUM,
                required_scope=(context.target.service,),
            )
        )
    else:
        excluded.append("configuration corruption excluded: bounded config evidence was readable")

    if not candidates:
        all_evidence_ids = tuple(item.evidence_id for item in evidence)
        supporting, contradicting = _split_support_and_conflicts(
            all_evidence_ids,
            conflict_evidence_ids,
        )
        candidates.append(
            RootCauseCandidate(
                root_cause_id=generate_id("rc"),
                description="service failure requires further isolation",
                supporting_evidence=supporting,
                contradicting_evidence=contradicting,
                confidence=0.45,
                repair_risk=RiskLevel.MEDIUM,
                required_scope=(context.target.service,),
            )
        )
    return tuple(candidates), tuple(excluded)


def _split_support_and_conflicts(
    support: tuple[str, ...],
    conflict_evidence_ids: set[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    contradicting = tuple(
        evidence_id for evidence_id in support if evidence_id in conflict_evidence_ids
    )
    clean_support = tuple(
        evidence_id for evidence_id in support if evidence_id not in conflict_evidence_ids
    )
    if not clean_support:
        clean_support = (support[0],)
        contradicting = tuple(
            evidence_id for evidence_id in contradicting if evidence_id != support[0]
        )
    return clean_support, contradicting


def _build_follow_ups(
    conflicts: Sequence[EvidenceConflict],
) -> tuple[FollowUpRequest, ...]:
    requests: list[FollowUpRequest] = []
    for conflict in conflicts:
        target = _follow_up_target(conflict.fact_key)
        requests.append(
            FollowUpRequest(
                follow_up_id=generate_id("followup"),
                target_agent=target,
                fact_key=conflict.fact_key,
                question=(
                    f"Please resolve conflicting values for {conflict.fact_key}; "
                    "return the observed value and source reference."
                ),
                related_evidence_ids=conflict.evidence_ids,
                correlation_id=generate_id("corr"),
            )
        )
    return tuple(requests)


def _follow_up_target(fact_key: str) -> str:
    if "config" in fact_key:
        return "ConfigAgent"
    if "metric" in fact_key or "memory" in fact_key or "load" in fact_key:
        return "MetricsAgent"
    if "process" in fact_key or "port" in fact_key or "dependency" in fact_key:
        return "DependencyAgent"
    return "LogAgent"


def _repair_constraints(
    context: RunContext,
    root_causes: Sequence[RootCauseCandidate],
    conflicts: Sequence[EvidenceConflict],
) -> tuple[str, ...]:
    if conflicts:
        return (
            "repair_blocked_until_conflicts_resolved",
            f"allowed_service:{context.target.service}",
        )
    scopes = {scope for root_cause in root_causes for scope in root_cause.required_scope}
    return tuple(f"allowed_service:{scope}" for scope in sorted(scopes))


def _build_evidence_chain(
    context: RunContext,
    evidence: Sequence[Evidence],
    messages: Sequence[Message],
) -> tuple[EvidenceChainEntry, ...]:
    entries: list[EvidenceChainEntry] = []
    for item in evidence:
        linked_messages = [
            message.message_id for message in messages if item.evidence_id in message.evidence_ids
        ]
        entries.append(
            EvidenceChainEntry(
                evidence_id=item.evidence_id,
                kind=item.kind,
                producer_agent=item.producer_agent,
                service=context.target.service,
                source_ref=item.source_ref,
                observed_at=item.observed_at,
                linked_message_ids=tuple(linked_messages),
            )
        )
    return tuple(entries)


def _positive_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0.0, float(value))
