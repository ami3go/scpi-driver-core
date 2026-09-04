#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=.venv/bin/python
[[ -x "$PYTHON" ]] || PYTHON=python3
"$PYTHON" -m robot.libdoc KeysightN6700Library docs/KeysightN6700Library.html
"$PYTHON" -m mkdocs build --strict --clean
