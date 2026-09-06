#!/usr/bin/env sh
set -eu
python -m pytest
python -m robot --outputdir results tests/robot

