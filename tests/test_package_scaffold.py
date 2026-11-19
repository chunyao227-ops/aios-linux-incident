"""W02 package boundary checks."""

import importlib
from pathlib import Path

import pytest

EXPECTED_MODULES = [
    "aios_incident",
    "aios_incident.agent_base",
    "aios_incident.api",
    "aios_incident.models",
    "aios_incident.state",
    "aios_incident.validation",
    "aios_incident.agents",
    "aios_incident.orchestrator",
    "aios_incident.adapters",
    "aios_incident.tools",
    "aios_incident.benchmark",
    "aios_incident.ui",
]


@pytest.mark.parametrize("module_name", EXPECTED_MODULES)
def test_expected_module_imports(module_name: str) -> None:
    assert importlib.import_module(module_name)


def test_no_parallel_top_level_code_directories(project_root: Path) -> None:
    forbidden = {"agents", "orchestrator", "adapters", "tools", "benchmark", "ui"}
    assert not {name for name in forbidden if (project_root / name).exists()}
