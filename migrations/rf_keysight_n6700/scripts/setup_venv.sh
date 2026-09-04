#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -e ".[dev,docs]"
.venv/bin/python -c "from KeysightN6700Library import KeysightN6700Library; print('RF Keysight N6700 environment ready')"
