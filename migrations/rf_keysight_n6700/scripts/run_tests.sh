#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=.venv/bin/python
[[ -x "$PYTHON" ]] || PYTHON=python3
"$PYTHON" scripts/generate_ai_contract.py --check
"$PYTHON" scripts/verify_project_package.py --source . --expected-release 26.09
"$PYTHON" -m pytest -m "not hardware"
"$PYTHON" -m robot --outputdir build/robot-results tests/robot
"$PYTHON" -m robot --outputdir build/example-results examples/robot
"$PYTHON" -m ruff check .
"$PYTHON" -m mypy keysight_n6700 KeysightN6700Library
