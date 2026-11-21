"""Application exception hierarchy used across modules."""


class AIOSIncidentError(Exception):
    """Base class for expected project errors."""


class ConfigurationError(AIOSIncidentError):
    """Raised when application configuration is missing or invalid."""


class InputValidationError(AIOSIncidentError):
    """Raised when an external payload does not satisfy a schema."""


class DAGValidationError(InputValidationError):
    """Raised when task graph structure or dependencies are invalid."""


class MessageValidationError(InputValidationError):
    """Raised when an Agent message violates protocol constraints."""


class InvalidStateTransitionError(AIOSIncidentError):
    """Raised when a task or workflow state transition is forbidden."""


class AdapterInvocationError(AIOSIncidentError):
    """Base class for normalized AIOS and model adapter failures."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class AdapterTimeoutError(AdapterInvocationError):
    """Raised when an AIOS request exceeds its configured timeout."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class AdapterTransportError(AdapterInvocationError):
    """Raised when AIOS cannot be reached."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class AdapterHTTPError(AdapterInvocationError):
    """Raised for a non-success AIOS HTTP response."""


class AdapterProtocolError(AdapterInvocationError):
    """Raised when AIOS returns a malformed response envelope."""


class ModelResponseError(AdapterInvocationError):
    """Raised when AIOS reports a failed or empty model response."""


class ToolExecutionError(AIOSIncidentError):
    """Raised when a controlled tool cannot complete safely."""


class ToolNotAllowedError(ToolExecutionError):
    """Raised when a tool is absent from the frozen allowlist."""


class ToolPermissionError(ToolExecutionError):
    """Raised when an Agent is not authorized for the requested tool."""


class ToolArgumentError(ToolExecutionError):
    """Raised when tool arguments violate its fixed schema."""


class ToolPathError(ToolExecutionError):
    """Raised when a path leaves the incident or sandbox boundary."""


class ToolTimeoutError(ToolExecutionError):
    """Raised when a tool exceeds its effective timeout."""


class ToolOutputLimitError(ToolExecutionError):
    """Raised when a tool result exceeds its effective output limit."""


class RepairDisabledError(ToolExecutionError):
    """Raised when a repair write is attempted before a safe implementation exists."""


class IncidentNotFoundError(AIOSIncidentError):
    """Raised when an incident ID is not present in the active registry."""

    code = "INCIDENT_NOT_FOUND"
    status_code = 404


class IncidentStateError(AIOSIncidentError):
    """Raised when an operation is invalid for the incident workflow state."""

    code = "INCIDENT_STATE_CONFLICT"
    status_code = 409


class BlackboardArtifactNotFoundError(AIOSIncidentError):
    """Raised when an artifact is absent from its incident blackboard."""

    code = "BLACKBOARD_ARTIFACT_NOT_FOUND"
    status_code = 404


class BlackboardArtifactNotReadyError(AIOSIncidentError):
    """Raised when a downstream reader requests an incomplete artifact."""

    code = "BLACKBOARD_ARTIFACT_NOT_READY"
    status_code = 409


class BlackboardConflictError(AIOSIncidentError):
    """Raised when an immutable artifact or content reference would be replaced."""

    code = "BLACKBOARD_CONFLICT"
    status_code = 409


class TraceStoreError(AIOSIncidentError):
    """Raised when a JSONL trace cannot be safely appended or read."""

    code = "TRACE_STORE_ERROR"
    status_code = 500


class InteractionParticipantUnavailableError(AIOSIncidentError):
    """Raised when one side of an Agent interaction is offline or unknown."""


class InteractionProtocolError(AIOSIncidentError):
    """Raised when messages do not form a valid request-response relationship."""


class InteractionResponseTimeoutError(AIOSIncidentError):
    """Raised when a query receives no response before its explicit timeout."""
