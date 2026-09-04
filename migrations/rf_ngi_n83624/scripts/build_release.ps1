$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
Push-Location $Root
try {
    Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
    & $Python -m build
} finally { Pop-Location }
