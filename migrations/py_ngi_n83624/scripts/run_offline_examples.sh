#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROBOT="$ROOT/.venv/bin/robot"
"$ROBOT" --outputdir "$ROOT/build/offline_examples" \
  "$ROOT/examples/01_emulator_smoke.robot" \
  "$ROOT/examples/03_safe_source_mode.robot" \
  "$ROOT/examples/04_charge_mode.robot" \
  "$ROOT/examples/05_measurement_assertions.robot" \
  "$ROOT/examples/06_multi_channel_measurement.robot" \
  "$ROOT/examples/07_soc_profile.robot" \
  "$ROOT/examples/08_sequence_profile.robot" \
  "$ROOT/examples/09_protection_and_capture.robot" \
  "$ROOT/examples/10_heartbeat_health.robot" \
  "$ROOT/examples/13_raw_scpi_diagnostics.robot" \
  "$ROOT/examples/14_audit_log.robot"
