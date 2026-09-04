param([Parameter(Mandatory=$true)][string]$Example)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Robot = Join-Path $Root ".venv\Scripts\robot.exe"
if (-not (Test-Path $Robot)) { throw "Run scripts/setup_venv.ps1 first." }
$ExamplePath = Resolve-Path $Example
& $Robot --outputdir (Join-Path $Root "build\examples") $ExamplePath
