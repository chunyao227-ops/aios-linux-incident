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
