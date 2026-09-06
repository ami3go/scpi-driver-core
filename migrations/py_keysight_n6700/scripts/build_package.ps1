. "$PSScriptRoot\_common.ps1"
& $Python scripts\generate_ai_contract.py --check
if (Test-Path dist) { Remove-Item -Recurse -Force dist }
& $Python -m build
& $Python -m robot.libdoc KeysightN6700Library docs\KeysightN6700Library.html
& $Python -m mkdocs build --strict --clean
& $Python scripts\make_release.py
