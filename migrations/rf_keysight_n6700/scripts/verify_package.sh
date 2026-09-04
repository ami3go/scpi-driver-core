#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=.venv/bin/python
[[ -x "$PYTHON" ]] || PYTHON=python3
"$PYTHON" scripts/generate_ai_contract.py --check
"$PYTHON" scripts/verify_project_package.py --source . --expected-release 26.09
