#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 examples/01_emulator_smoke.robot" >&2
  exit 2
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROBOT="$ROOT/.venv/bin/robot"
[[ -x "$ROBOT" ]] || { echo "Run scripts/setup_venv.sh first." >&2; exit 1; }
"$ROBOT" --outputdir "$ROOT/build/examples" "$1"
