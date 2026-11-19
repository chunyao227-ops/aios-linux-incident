"""Strict YAML configuration loading with safe model endpoint switching."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from .exceptions import ConfigurationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "app.example.yaml"
CONFIG_ENV_VAR = "AIOS_INCIDENT_CONFIG"


@dataclass(frozen=True, slots=True)
class AppMetadata:
    name: str
    environment: str
    log_level: str


@dataclass(frozen=True, slots=True)
class AIOSConfig:
    base_url: str
    timeout_seconds: float
    max_retries: int


@dataclass(frozen=True, slots=True)
class ModelConfig:
    deployment: str
    backend: str
    name: str
    base_url: str
    served_model_name: str
    api_key_env: str | None
    timeout_seconds: float
    max_retries: int
    temperature: float
    max_tokens: int

    def resolve_api_key(self) -> str | None:
        """Read a credential from the configured environment variable only."""

        if self.api_key_env is None:
            return None
        return os.getenv(self.api_key_env)


@dataclass(frozen=True, slots=True)
class WorkflowConfig:
    collect_concurrency: int
    task_timeout_seconds: float
    max_repair_rounds: int


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    output_dir: str


@dataclass(frozen=True, slots=True)
class AppConfig:
    version: int
    app: AppMetadata
    aios: AIOSConfig
    model: ModelConfig
    workflow: WorkflowConfig
    runtime: RuntimeConfig

    def to_public_dict(self) -> dict[str, Any]:
        """Return the configuration without credentials for logs or screenshots."""

        return asdict(self)


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load and validate an application configuration file."""

    config_path = _resolve_path(path)
    payload = _read_yaml(config_path)
    root = _as_mapping(payload, "root")
    _check_keys(root, {"version", "app", "aios", "model", "workflow", "runtime"}, "root")

    version = _as_int(root.get("version"), "version")
    if version != 1:
        raise ConfigurationError("version must be 1")

    return AppConfig(
        version=version,
        app=_parse_app(_as_mapping(root.get("app"), "app")),
        aios=_parse_aios(_as_mapping(root.get("aios"), "aios")),
        model=_parse_model(_as_mapping(root.get("model"), "model")),
        workflow=_parse_workflow(_as_mapping(root.get("workflow"), "workflow")),
        runtime=_parse_runtime(_as_mapping(root.get("runtime"), "runtime")),
    )


def _resolve_path(path: str | Path | None) -> Path:
    if path is None:
        configured = os.getenv(CONFIG_ENV_VAR)
        return Path(configured).expanduser() if configured else DEFAULT_CONFIG_PATH
    return Path(path).expanduser()


def _read_yaml(path: Path) -> Any:
    if not path.is_file():
        raise ConfigurationError(f"configuration file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except OSError as exc:
        raise ConfigurationError(f"cannot read configuration file: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"invalid YAML in {path}: {exc}") from exc


def _parse_app(data: Mapping[str, Any]) -> AppMetadata:
    _check_keys(data, {"name", "environment", "log_level"}, "app")
    log_level = _as_str(data.get("log_level"), "app.log_level").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigurationError("app.log_level is invalid")
    return AppMetadata(
        name=_as_str(data.get("name"), "app.name"),
        environment=_as_str(data.get("environment"), "app.environment"),
        log_level=log_level,
    )


def _parse_aios(data: Mapping[str, Any]) -> AIOSConfig:
    _check_keys(data, {"base_url", "timeout_seconds", "max_retries"}, "aios")
    return AIOSConfig(
        base_url=_as_url(data.get("base_url"), "aios.base_url"),
        timeout_seconds=_as_positive_number(data.get("timeout_seconds"), "aios.timeout_seconds"),
        max_retries=_as_non_negative_int(data.get("max_retries"), "aios.max_retries"),
    )


def _parse_model(data: Mapping[str, Any]) -> ModelConfig:
    _check_keys(
        data,
        {
            "deployment",
            "backend",
            "name",
            "base_url",
            "served_model_name",
            "api_key_env",
            "timeout_seconds",
            "max_retries",
            "temperature",
            "max_tokens",
        },
        "model",
    )
    deployment = _as_str(data.get("deployment"), "model.deployment")
    if deployment not in {"local", "remote"}:
        raise ConfigurationError("model.deployment must be local or remote")

    temperature = _as_number(data.get("temperature"), "model.temperature")
    if not 0.0 <= temperature <= 2.0:
        raise ConfigurationError("model.temperature must be between 0 and 2")

    return ModelConfig(
        deployment=deployment,
        backend=_as_str(data.get("backend"), "model.backend"),
        name=_as_str(data.get("name"), "model.name"),
        base_url=_as_url(data.get("base_url"), "model.base_url"),
        served_model_name=_as_str(data.get("served_model_name"), "model.served_model_name"),
        api_key_env=_as_optional_str(data.get("api_key_env"), "model.api_key_env"),
        timeout_seconds=_as_positive_number(data.get("timeout_seconds"), "model.timeout_seconds"),
        max_retries=_as_non_negative_int(data.get("max_retries"), "model.max_retries"),
        temperature=temperature,
        max_tokens=_as_positive_int(data.get("max_tokens"), "model.max_tokens"),
    )


def _parse_workflow(data: Mapping[str, Any]) -> WorkflowConfig:
    _check_keys(
        data,
        {"collect_concurrency", "task_timeout_seconds", "max_repair_rounds"},
        "workflow",
    )
    collect_concurrency = _as_positive_int(
        data.get("collect_concurrency"), "workflow.collect_concurrency"
    )
    if collect_concurrency < 4:
        raise ConfigurationError("workflow.collect_concurrency must be at least 4")
    max_repair_rounds = _as_non_negative_int(
        data.get("max_repair_rounds"), "workflow.max_repair_rounds"
    )
    if max_repair_rounds > 2:
        raise ConfigurationError("workflow.max_repair_rounds cannot exceed 2")
    return WorkflowConfig(
        collect_concurrency=collect_concurrency,
        task_timeout_seconds=_as_positive_number(
            data.get("task_timeout_seconds"), "workflow.task_timeout_seconds"
        ),
        max_repair_rounds=max_repair_rounds,
    )


def _parse_runtime(data: Mapping[str, Any]) -> RuntimeConfig:
    _check_keys(data, {"output_dir"}, "runtime")
    return RuntimeConfig(output_dir=_as_str(data.get("output_dir"), "runtime.output_dir"))


def _as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{label} must be a mapping")
    return value


def _check_keys(data: Mapping[str, Any], expected: set[str], label: str) -> None:
    missing = expected - set(data)
    unknown = set(data) - expected
    if missing:
        raise ConfigurationError(f"{label} is missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ConfigurationError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")


def _as_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{label} must be a non-empty string")
    return value.strip()


def _as_optional_str(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _as_str(value, label)


def _as_url(value: Any, label: str) -> str:
    text = _as_str(value, label).rstrip("/")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError(f"{label} must be an HTTP(S) URL")
    return text


def _as_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{label} must be a number")
    return float(value)


def _as_positive_number(value: Any, label: str) -> float:
    number = _as_number(value, label)
    if number <= 0:
        raise ConfigurationError(f"{label} must be greater than zero")
    return number


def _as_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(f"{label} must be an integer")
    return value


def _as_non_negative_int(value: Any, label: str) -> int:
    number = _as_int(value, label)
    if number < 0:
        raise ConfigurationError(f"{label} cannot be negative")
    return number


def _as_positive_int(value: Any, label: str) -> int:
    number = _as_int(value, label)
    if number <= 0:
        raise ConfigurationError(f"{label} must be greater than zero")
    return number
