param(
    [ValidateSet("setup", "test", "lint", "check-config", "verify")]
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

