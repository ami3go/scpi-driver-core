$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Robot = Join-Path $Root ".venv\Scripts\robot.exe"
if (-not (Test-Path $Python)) { throw "Run scripts/setup_venv.ps1 first." }
Push-Location $Root
try {
    & $Python -m pytest
    & $Robot --outputdir build/robot tests/robot/acceptance.robot
    & $Python -m ruff check .
    & $Python -m build
} finally { Pop-Location }
