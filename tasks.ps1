param(
    [ValidateSet(
        "setup",
        "test",
        "lint",
        "check-config",
        "api",
        "integration",
        "scenarios",
        "benchmark",
        "verify"
    )]
    [string]$Task = "test"
)

$ErrorActionPreference = "Stop"
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

Push-Location $PSScriptRoot
try {
    switch ($Task) {
        "setup" {
            & $Python -m pip install -e ".[dev]"
        }
        "test" {
            & $Python -m pytest
        }
        "lint" {
            & $Python -m ruff check .
        }
        "check-config" {
            & $Python -m aios_incident --config "config/app.example.yaml"
        }
        "api" {
            & $Python -m uvicorn aios_incident.api:app --host "127.0.0.1" --port 8080
        }
        "integration" {
            $env:RUN_AIOS_INTEGRATION = "1"
            & $Python -m pytest tests/integration/test_aios_smoke.py -v
        }
        "scenarios" {
            $env:RUN_DOCKER_SCENARIOS = "1"
            & $Python -m pytest tests/scenarios/test_all_scenarios.py -v
        }
        "benchmark" {
            & $Python scripts/benchmark/run_local_benchmark.py
        }
        "verify" {
            & $Python -m ruff check .
            if ($LASTEXITCODE -ne 0) {
                exit $LASTEXITCODE
            }
            & $Python -m ruff format --check src tests
            if ($LASTEXITCODE -ne 0) {
                exit $LASTEXITCODE
            }
            & $Python -m pytest
            if ($LASTEXITCODE -ne 0) {
                exit $LASTEXITCODE
            }
            & $Python -m aios_incident --config "config/app.example.yaml" --show-config
        }
    }
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}

