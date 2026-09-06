#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=.venv/bin/python
[[ -x "$PYTHON" ]] || PYTHON=python3
EXAMPLE="${1:-01_simulator_smoke.robot}"
[[ -f "examples/robot/$EXAMPLE" ]] || { echo "Example not found: examples/robot/$EXAMPLE" >&2; exit 2; }
"$PYTHON" -m robot --outputdir "build/example-results/${EXAMPLE%.robot}" "examples/robot/$EXAMPLE"
