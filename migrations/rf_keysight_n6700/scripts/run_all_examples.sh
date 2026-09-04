#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=.venv/bin/python
[[ -x "$PYTHON" ]] || PYTHON=python3
"$PYTHON" -m robot --outputdir build/example-results examples/robot
