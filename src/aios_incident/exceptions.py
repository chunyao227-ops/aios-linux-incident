"""Application exception hierarchy used across modules."""


class AIOSIncidentError(Exception):
    """Base class for expected project errors."""


class ConfigurationError(AIOSIncidentError):
    """Raised when application configuration is missing or invalid."""


class InputValidationError(AIOSIncidentError):
    """Raised when an external payload does not satisfy a schema."""


class AdapterInvocationError(AIOSIncidentError):
    """Raised when an AIOS or model adapter call fails."""


class ToolExecutionError(AIOSIncidentError):
    """Raised when a controlled tool cannot complete safely."""
