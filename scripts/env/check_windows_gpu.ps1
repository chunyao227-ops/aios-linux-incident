$ErrorActionPreference = "Continue"
$env:WSL_UTF8 = "1"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

Write-Output "=== Windows / GPU environment ==="
Get-CimInstance Win32_ComputerSystem |
    Select-Object Manufacturer, Model, TotalPhysicalMemory |
    Format-List

if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    nvidia-smi
    nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used --format=csv
} else {
    Write-Output "nvidia-smi: NOT FOUND"
}

Write-Output "=== WSL ==="
if (Get-Command wsl -ErrorAction SilentlyContinue) {
    wsl --status
    wsl -l -v
} else {
    Write-Output "wsl: NOT FOUND"
}

Write-Output "=== Docker ==="
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker --version
    docker info
} else {
    Write-Output "docker: NOT FOUND"
}

Write-Output "=== Python ==="
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    python --version
    python -c "import sys; print(sys.executable)"
} else {
    Write-Output "python: NOT FOUND"
}
py -0p 2>$null

Write-Output "=== Git ==="
git --version

Write-Output "=== Disk ==="
Get-PSDrive -PSProvider FileSystem |
    Select-Object Name, Used, Free

