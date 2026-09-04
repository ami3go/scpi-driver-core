$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

$Launcher = Get-Command py -ErrorAction SilentlyContinue
if ($Launcher) {
    & py -3 -m venv .venv
} else {
    & python -m venv .venv
}

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
& $Python -m pip install --upgrade pip setuptools wheel
& $Python -m pip install -e ".[dev,docs]"
& $Python -c "from KeysightN6700Library import KeysightN6700Library; print('RF Keysight N6700 environment ready')"
