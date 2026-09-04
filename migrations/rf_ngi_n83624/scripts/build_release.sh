#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rm -rf "$ROOT/dist"
cd "$ROOT"
"$ROOT/.venv/bin/python" -m build
