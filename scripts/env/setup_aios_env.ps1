param(
    [string]$EnvPath = ".venv",
    [string]$CondaExe = ""
)

$ErrorActionPreference = "Stop"

$venvPython = Join-Path $EnvPath "Scripts\python.exe"
$condaPython = Join-Path $EnvPath "python.exe"
$pythonExe = if (Test-Path -LiteralPath $venvPython) {
    $venvPython
} elseif (Test-Path -LiteralPath $condaPython) {
    $condaPython
} else {
    $null
}

if (-not $pythonExe) {
    $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pythonLauncher) {
        & $pythonLauncher.Source -3.10 -m venv $EnvPath
    } else {
        if (-not $CondaExe) {
            $conda = Get-Command conda -ErrorAction SilentlyContinue
            if ($conda) {
                $CondaExe = $conda.Source
            } elseif (Test-Path "D:\anaconda3\Scripts\conda.exe") {
                $CondaExe = "D:\anaconda3\Scripts\conda.exe"
            }
        }
        if (-not $CondaExe) {
            throw "Python 3.10 launcher and Conda were not found."
        }
        & $CondaExe create -y -p $EnvPath python=3.10 pip
    }
}

$pythonExe = if (Test-Path -LiteralPath $venvPython) {
    $venvPython
} elseif (Test-Path -LiteralPath $condaPython) {
    $condaPython
} else {
    $null
}

if (-not $pythonExe) {
    throw "Python executable not found after environment creation: $pythonExe"
}

& $pythonExe -m pip --version
& $pythonExe -m pip install --upgrade pip

Write-Output "Python 3.10 environment ready: $EnvPath"
if (Test-Path -LiteralPath $venvPython) {
    Write-Output "Activate with: `"$(Join-Path (Resolve-Path $EnvPath).Path 'Scripts\Activate.ps1')`""
} else {
    Write-Output "Activate with: conda activate `"$((Resolve-Path $EnvPath).Path)`""
}
Write-Output "Next: install AIOS/Cerebrum using the locked project baseline."

