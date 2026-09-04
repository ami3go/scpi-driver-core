param(
    [string]$Resource = $env:N6700_RESOURCE,
    [ValidateSet("visa", "usb", "ethernet", "socket", "simulated")]
    [string]$ConnectionType = $(if ($env:N6700_CONNECTION_TYPE) { $env:N6700_CONNECTION_TYPE } else { "usb" }),
    [int]$Channel = $(if ($env:N6700_CHANNEL) { [int]$env:N6700_CHANNEL } else { 1 }),
    [int]$Port = $(if ($env:N6700_PORT) { [int]$env:N6700_PORT } else { 5025 }),
    [string]$ExpectedModule = $(if ($env:N6700_EXPECTED_MODULE) { $env:N6700_EXPECTED_MODULE } else { "N6775A" }),
    [switch]$AllowReset,
    [switch]$AllowActiveOutput,
    [string]$OutputRoot = "results\call_protocol_conformance\keysight_n6700"
)

$ErrorActionPreference = "Stop"
$DefaultUsbResource = "USB0::0x0957::0x0907::MY43014421::INSTR"
if ($ConnectionType -eq "usb" -and [string]::IsNullOrWhiteSpace($Resource)) {
    $Resource = $DefaultUsbResource
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

if ($ConnectionType -ne "simulated" -and [string]::IsNullOrWhiteSpace($Resource)) {
    throw "Resource is required. Example: -Resource 'USB0::0x0957::0x0907::MY43014421::INSTR' -ConnectionType usb"
}
if ($ConnectionType -eq "simulated" -and $ExpectedModule -eq "N6775A") {
    $ExpectedModule = "N6751A"
}

$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$OutputDir = Join-Path $OutputRoot $Timestamp
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$HilEnable = if ($ConnectionType -eq "simulated") { "false" } else { "true" }
$ResetEnable = if ($AllowReset) { "true" } else { "false" }
$OutputEnable = if ($AllowActiveOutput) { "true" } else { "false" }
$ResourceValue = if ([string]::IsNullOrWhiteSpace($Resource)) { "NOT_SET" } else { $Resource }

Write-Host "N6775A self-check output: $OutputDir"
Write-Host "Connection: $ConnectionType  Resource: $ResourceValue  Channel: $Channel"
Write-Host "Reset enabled: $ResetEnable  Active output enabled: $OutputEnable"

& $Python -m robot `
    --name "N6775A Full Self Check" `
    --outputdir $OutputDir `
    --variable "HIL_ENABLE:$HilEnable" `
    --variable "CONNECTION_TYPE:$ConnectionType" `
    --variable "N6700_RESOURCE:$ResourceValue" `
    --variable "N6700_PORT:$Port" `
    --variable "CHANNEL:$Channel" `
    --variable "EXPECTED_MODULE:$ExpectedModule" `
    --variable "ALLOW_RESET:$ResetEnable" `
    --variable "ALLOW_ACTIVE_OUTPUT:$OutputEnable" `
    tests\conformance\driver_calltocol_conformance.robot
$ExitCode = $LASTEXITCODE
& $Python scripts\summarize_n6775a_self_check.py $OutputDir
if ($LASTEXITCODE -ne 0 -and $ExitCode -eq 0) { $ExitCode = $LASTEXITCODE }
Write-Host "Result directory: $OutputDir"
exit $ExitCode
