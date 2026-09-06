#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
ROBOT="$ROOT/.venv/bin/robot"
[[ -x "$PYTHON" ]] || { echo "Run scripts/setup_venv.sh first." >&2; exit 1; }
cd "$ROOT"
"$PYTHON" -m pytest
"$ROBOT" --outputdir build/robot tests/robot/acceptance.robot
"$PYTHON" -m ruff check .
"$PYTHON" -m build
