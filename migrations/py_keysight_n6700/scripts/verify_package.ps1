. "$PSScriptRoot\_common.ps1"
& $Python scripts\generate_ai_contract.py --check
& $Python scripts\verify_project_package.py --source . --expected-release 26.09
exit $LASTEXITCODE
