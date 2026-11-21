"""Agent message bus with request-response and bidirectional graph tracking."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Condition, RLock
from typing import Any

from pydantic import Field

from ..exceptions import (
    InteractionParticipantUnavailableError,
    InteractionProtocolError,
    InteractionResponseTimeoutError,
)
from ..models import (
    Message,
    MessageType,
    NonEmptyStr,
    StrictModel,
    TraceEvent,
)
from ..utils import generate_id, utc_now
from .blackboard import ArtifactKind, Blackboard, BlackboardArtifact
from .trace import JsonlTraceStore


class InteractionEdge(StrictModel):
    from_agent: NonEmptyStr
    to_agent: NonEmptyStr
    message_count: int = Field(gt=0)


class InteractionGraph(StrictModel):
    incident_id: NonEmptyStr
    nodes: tuple[NonEmptyStr, ...]
    edges: tuple[InteractionEdge, ...]
    bidirectional_pairs: tuple[NonEmptyStr, ...]
    bidirectional_edge_count: int = Field(ge=0)
    message_count: int = Field(ge=0)


@dataclass(slots=True)
class _PendingQuery:
    question: Message
    response_message_id: str | None = None


@dataclass(frozen=True, slots=True)
class _Participant:
    agent_id: str
    agent_type: str
    online: bool = True


class InteractionBus:
    """Trace every message and enforce request-response correlation."""

    def __init__(
        self,
        incident_id: str,
        trace: JsonlTraceStore,
        blackboard: Blackboard | None = None,
    ) -> None:
        if trace.incident_id != incident_id:
            raise InteractionProtocolError("bus and trace incident IDs differ")
        self.incident_id = incident_id
        self.trace = trace
        self.blackboard = blackboard
        self._participants: dict[str, _Participant] = {}
        self._messages: list[Message] = []
        self._messages_by_id: dict[str, Message] = {}
        self._pending: dict[str, _PendingQuery] = {}
        self._condition = Condition(RLock())

    def register_agent(self, agent_id: str, agent_type: str) -> None:
        with self._condition:
            existing = self._participants.get(agent_id)
            if existing is not None and existing.agent_type != agent_type:
                raise InteractionProtocolError(
                    f"agent ID {agent_id} is already registered as {existing.agent_type}"
                )
            self._participants[agent_id] = _Participant(agent_id, agent_type, True)

    def disconnect_agent(self, agent_id: str) -> None:
        with self._condition:
            participant = self._participants.get(agent_id)
            if participant is None:
                raise InteractionParticipantUnavailableError(f"unknown Agent: {agent_id}")
            self._participants[agent_id] = _Participant(
                participant.agent_id,
                participant.agent_type,
                False,
            )

    def resolve_agent_id(self, agent_type: str) -> str:
        matches = [
            participant.agent_id
            for participant in self._participants.values()
            if participant.agent_type == agent_type and participant.online
        ]
        if len(matches) != 1:
            raise InteractionParticipantUnavailableError(
                f"expected one online {agent_type}, found {len(matches)}"
            )
        return matches[0]

    def send(self, message: Message) -> Message:
        with self._condition:
            sender = self._participants.get(message.from_agent)
            recipient = self._participants.get(message.to_agent)
            unavailable = (
                sender is None or not sender.online or recipient is None or not recipient.online
            )
            if unavailable:
                reason = "sender or recipient is offline or unknown"
                self._trace_message(
                    message,
                    event_type="MESSAGE_SEND_FAILED",
                    status="FAILED",
                    error=reason,
                )
                raise InteractionParticipantUnavailableError(reason)

            if message.incident_id != self.incident_id:
                raise InteractionProtocolError("message incident does not match bus incident")
            if message.message_id in self._messages_by_id:
                raise InteractionProtocolError(f"duplicate message ID: {message.message_id}")

            if message.type in {MessageType.REPLY, MessageType.RESPONSE}:
                self._validate_response(message)
            if (
                message.type in {MessageType.QUESTION, MessageType.QUERY}
                and message.correlation_id in self._pending
            ):
                raise InteractionProtocolError(
                    f"correlation_id already pending: {message.correlation_id}"
                )

            self._messages.append(message)
            self._messages_by_id[message.message_id] = message
            if message.type in {MessageType.QUESTION, MessageType.QUERY}:
                self._pending[message.correlation_id] = _PendingQuery(question=message)
            elif message.type in {MessageType.REPLY, MessageType.RESPONSE}:
                pending = self._pending[message.correlation_id]
                pending.response_message_id = message.message_id
                self._condition.notify_all()

            self._trace_message(
                message,
                event_type="MESSAGE_SENT",
                status="DELIVERED",
            )
            self._trace_message(
                message,
                event_type="MESSAGE_RECEIVED",
                status="DELIVERED",
            )
            if self.blackboard is not None:
                self.blackboard.put(
                    BlackboardArtifact(
                        artifact_id=generate_id("art"),
                        incident_id=message.incident_id,
                        producer_agent=message.from_agent,
                        kind=ArtifactKind.MESSAGE,
                        content_ref=message.message_id,
                        created_at=message.timestamp,
                    )
                )
            return message

    def wait_for_response(
        self,
        correlation_id: str,
        *,
        timeout_seconds: float,
    ) -> Message:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        with self._condition:
            pending = self._pending.get(correlation_id)
            if pending is None:
                raise InteractionProtocolError(f"unknown correlation_id: {correlation_id}")
            completed = self._condition.wait_for(
                lambda: pending.response_message_id is not None,
                timeout=timeout_seconds,
            )
            if not completed:
                self._pending.pop(correlation_id, None)
                self._trace_message(
                    pending.question,
                    event_type="MESSAGE_RESPONSE_TIMEOUT",
                    status="TIMEOUT",
                    error=f"no response within {timeout_seconds:g}s",
                )
                raise InteractionResponseTimeoutError(
                    f"no response for correlation {correlation_id}"
                )
            response_id = pending.response_message_id
            assert response_id is not None
            return self._messages_by_id[response_id]

    def send_question(
        self,
        *,
        incident_id: str,
        task_id: str,
        from_agent: str,
        to_agent: str,
        content: str,
        evidence_ids: tuple[str, ...] = (),
        correlation_id: str | None = None,
        message_type: MessageType = MessageType.QUESTION,
    ) -> Message:
        if message_type not in {MessageType.QUESTION, MessageType.QUERY}:
            raise ValueError("message_type must be QUESTION or QUERY")
        message = Message(
            message_id=generate_id("msg"),
            incident_id=incident_id,
            task_id=task_id,
            from_agent=from_agent,
            to_agent=to_agent,
            type=message_type,
            content=content,
            evidence_ids=evidence_ids,
            correlation_id=correlation_id or generate_id("corr"),
            timestamp=utc_now(),
        )
        return self.send(message)

    def send_reply(
        self,
        question: Message,
        *,
        from_agent: str,
        content: str,
        evidence_ids: tuple[str, ...] = (),
        message_type: MessageType = MessageType.REPLY,
    ) -> Message:
        if message_type not in {MessageType.REPLY, MessageType.RESPONSE}:
            raise ValueError("message_type must be REPLY or RESPONSE")
        message = Message(
            message_id=generate_id("msg"),
            incident_id=question.incident_id,
            task_id=question.task_id,
            from_agent=from_agent,
            to_agent=question.from_agent,
            type=message_type,
            content=content,
            evidence_ids=evidence_ids,
            correlation_id=question.correlation_id,
            reply_to=question.message_id,
            timestamp=utc_now(),
        )
        return self.send(message)

    def messages(self, *, incident_id: str | None = None) -> tuple[Message, ...]:
        with self._condition:
            if incident_id is None:
                return tuple(self._messages)
            return tuple(
                message for message in self._messages if message.incident_id == incident_id
            )

    def graph(self) -> InteractionGraph:
        with self._condition:
            messages = tuple(self._messages)
            participant_types = {
                participant.agent_id: participant.agent_type
                for participant in self._participants.values()
            }

        directed_counts: dict[tuple[str, str], int] = {}
        directed_correlations: dict[tuple[str, str], set[str]] = {}
        for message in messages:
            from_type = participant_types.get(message.from_agent, message.from_agent)
            to_type = participant_types.get(message.to_agent, message.to_agent)
            key = (from_type, to_type)
            directed_counts[key] = directed_counts.get(key, 0) + 1
            directed_correlations.setdefault(key, set()).add(message.correlation_id)

        bidirectional_pairs: list[str] = []
        for left, right in directed_counts:
            if left >= right:
                continue
            reverse = (right, left)
            if reverse not in directed_counts:
                continue
            if directed_correlations[(left, right)] & directed_correlations[reverse]:
                pair = f"{left}<->{right}"
                if pair not in bidirectional_pairs:
                    bidirectional_pairs.append(pair)

        edges = tuple(
            InteractionEdge(from_agent=left, to_agent=right, message_count=count)
            for (left, right), count in sorted(directed_counts.items())
        )
        return InteractionGraph(
            incident_id=self.incident_id,
            nodes=tuple(sorted(set(participant_types.values()))),
            edges=edges,
            bidirectional_pairs=tuple(sorted(bidirectional_pairs)),
            bidirectional_edge_count=len(bidirectional_pairs),
            message_count=len(messages),
        )

    def _validate_response(self, response: Message) -> None:
        assert response.reply_to is not None
        question = self._messages_by_id.get(response.reply_to)
        if question is None:
            raise InteractionProtocolError("response references an unknown message")
        if question.type not in {MessageType.QUESTION, MessageType.QUERY}:
            raise InteractionProtocolError("response must reference a query message")
        if question.correlation_id != response.correlation_id:
            raise InteractionProtocolError("response correlation_id does not match query")
        if question.from_agent != response.to_agent:
            raise InteractionProtocolError("response recipient is not the query sender")
        if question.to_agent != response.from_agent:
            raise InteractionProtocolError("response sender is not the query recipient")
        if response.correlation_id not in self._pending:
            raise InteractionProtocolError("response arrived after query timeout")

    def _trace_message(
        self,
        message: Message,
        *,
        event_type: str,
        status: str,
        error: str | None = None,
    ) -> None:
        details: dict[str, Any] = {
            "message_id": message.message_id,
            "message_type": message.type.value,
            "from_agent": message.from_agent,
            "to_agent": message.to_agent,
            "from_agent_type": self._participants.get(
                message.from_agent,
                _Participant(message.from_agent, message.from_agent, False),
            ).agent_type,
            "to_agent_type": self._participants.get(
                message.to_agent,
                _Participant(message.to_agent, message.to_agent, False),
            ).agent_type,
            "correlation_id": message.correlation_id,
        }
        if error is not None:
            details["error"] = error
        self.trace.append(
            TraceEvent(
                trace_id=generate_id("trace"),
                incident_id=message.incident_id,
                task_id=message.task_id,
                agent_id=message.from_agent,
                event_type=event_type,
                status=status,
                timestamp=utc_now(),
                details=details,
            )
        )
