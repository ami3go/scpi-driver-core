$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Robot = Join-Path $Root ".venv\Scripts\robot.exe"
$Examples = @(
  "01_emulator_smoke.robot", "03_safe_source_mode.robot", "04_charge_mode.robot",
  "05_measurement_assertions.robot", "06_multi_channel_measurement.robot",
  "07_soc_profile.robot", "08_sequence_profile.robot", "09_protection_and_capture.robot",
  "10_heartbeat_health.robot", "13_raw_scpi_diagnostics.robot", "14_audit_log.robot"
)
$Paths = $Examples | ForEach-Object { Join-Path $Root "examples\$_" }
& $Robot --outputdir (Join-Path $Root "build\offline_examples") $Paths
