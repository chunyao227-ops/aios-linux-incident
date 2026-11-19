"""Configuration loading, secret handling and endpoint switching tests."""

from pathlib import Path

import pytest
import yaml

from aios_incident.config import DEFAULT_CONFIG_PATH, load_config
from aios_incident.exceptions import ConfigurationError


def _write_config(source: Path, target: Path, update: dict[str, object]) -> Path:
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    payload["model"].update(update)
    target.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return target


def test_example_config_loads_with_frozen_workflow_limits() -> None:
    config = load_config(DEFAULT_CONFIG_PATH)
    assert config.app.name == "aios-linux-incident"
    assert config.model.deployment == "local"
    assert config.workflow.collect_concurrency >= 4
    assert config.workflow.max_repair_rounds == 2


def test_model_endpoint_switches_through_yaml_only(tmp_path: Path) -> None:
    remote_path = _write_config(
        DEFAULT_CONFIG_PATH,
        tmp_path / "app.yaml",
        {
            "deployment": "remote",
            "name": "qwen2.5-7b-awq",
            "base_url": "https://vllm.example.invalid/v1",
            "served_model_name": "qwen2.5-7b-awq",
            "api_key_env": "TEST_MODEL_API_KEY",
        },
    )
    config = load_config(remote_path)
    assert config.model.deployment == "remote"
    assert config.model.base_url == "https://vllm.example.invalid/v1"
    assert config.model.api_key_env == "TEST_MODEL_API_KEY"


def test_public_config_excludes_resolved_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_MODEL_API_KEY", "must-not-appear")
    config_path = _write_config(
        DEFAULT_CONFIG_PATH,
        tmp_path / "app.yaml",
        {"api_key_env": "TEST_MODEL_API_KEY"},
    )
    config = load_config(config_path)
    assert config.model.resolve_api_key() == "must-not-appear"
    assert "must-not-appear" not in repr(config.to_public_dict())


def test_unknown_configuration_field_is_rejected(tmp_path: Path) -> None:
    payload = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    payload["model"]["api_key"] = "inline-secret-is-forbidden"
    invalid_path = tmp_path / "invalid.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="unknown fields: api_key"):
        load_config(invalid_path)


def test_non_http_model_endpoint_is_rejected(tmp_path: Path) -> None:
    invalid_path = _write_config(
        DEFAULT_CONFIG_PATH,
        tmp_path / "invalid.yaml",
        {"base_url": "file:///tmp/model"},
    )
    with pytest.raises(ConfigurationError, match=r"HTTP\(S\) URL"):
        load_config(invalid_path)
