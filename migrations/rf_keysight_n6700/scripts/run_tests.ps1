. "$PSScriptRoot\_common.ps1"
& $Python scripts\generate_ai_contract.py --check
& $Python scripts\verify_project_package.py --source . --expected-release 26.09
& $Python -m pytest -m "not hardware"
& $Python -m robot --outputdir build\robot-results tests\robot
& $Python -m robot --outputdir build\example-results examples\robot
& $Python -m ruff check .
& $Python -m mypy keysight_n6700 KeysightN6700Library
