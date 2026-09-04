#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=.venv/bin/python
[[ -x "$PYTHON" ]] || PYTHON=python3
CONNECTION_TYPE=${N6700_CONNECTION_TYPE:-usb}
RESOURCE=${N6700_RESOURCE:-}
DEFAULT_USB_RESOURCE='USB0::0x0957::0x0907::MY43014421::INSTR'
[[ "$CONNECTION_TYPE" == "usb" && -z "$RESOURCE" ]] && RESOURCE="$DEFAULT_USB_RESOURCE"
CHANNEL=${N6700_CHANNEL:-1}
PORT=${N6700_PORT:-5025}
EXPECTED_MODULE=${N6700_EXPECTED_MODULE:-N6775A}
ALLOW_RESET=${N6700_ALLOW_RESET:-false}
ALLOW_ACTIVE_OUTPUT=${N6700_ALLOW_ACTIVE_OUTPUT:-false}
if [[ "$CONNECTION_TYPE" != "simulated" && -z "$RESOURCE" ]]; then
  echo "ERROR: Set N6700_RESOURCE before running." >&2
  exit 2
fi
if [[ "$CONNECTION_TYPE" == "simulated" ]]; then
  HIL_ENABLE=false
  [[ "$EXPECTED_MODULE" == "N6775A" ]] && EXPECTED_MODULE=N6751A
  RESOURCE=NOT_SET
else
  HIL_ENABLE=true
fi
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="results/call_protocol_conformance/keysight_n6700/$STAMP"
mkdir -p "$OUT"
set +e
"$PYTHON" -m robot \
  --name "N6775A Full Self Check" \
  --outputdir "$OUT" \
  --variable "HIL_ENABLE:$HIL_ENABLE" \
  --variable "CONNECTION_TYPE:$CONNECTION_TYPE" \
  --variable "N6700_RESOURCE:$RESOURCE" \
  --variable "N6700_PORT:$PORT" \
  --variable "CHANNEL:$CHANNEL" \
  --variable "EXPECTED_MODULE:$EXPECTED_MODULE" \
  --variable "ALLOW_RESET:$ALLOW_RESET" \
  --variable "ALLOW_ACTIVE_OUTPUT:$ALLOW_ACTIVE_OUTPUT" \
  tests/conformance/driver_call_protocol_conformance.robot
RC=$?
set -e
"$PYTHON" scripts/summarize_n6775a_self_check.py "$OUT" || [[ "$RC" -ne 0 ]] || RC=$?
echo "Result directory: $OUT"
exit "$RC"
