#!/usr/bin/env sh
set -eu
if [ "$#" -eq 0 ]; then
  echo "Usage: scripts/run_example.sh examples/01_identity.robot [Robot options]" >&2
  exit 2
fi
python -m robot --outputdir results "$@"

