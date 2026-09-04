@echo off
setlocal
cd /d "%~dp0.."
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
"%PYTHON%" scripts\generate_ai_contract.py --check || exit /b 1
"%PYTHON%" scripts\verify_project_package.py --source . --expected-release 26.09 || exit /b 1
"%PYTHON%" -m pytest -m "not hardware" || exit /b 1
"%PYTHON%" -m robot --outputdir build\robot-results tests\robot || exit /b 1
"%PYTHON%" -m robot --outputdir build\example-results examples\robot || exit /b 1
"%PYTHON%" -m ruff check . || exit /b 1
"%PYTHON%" -m mypy keysight_n6700 KeysightN6700Library || exit /b 1
endlocal
