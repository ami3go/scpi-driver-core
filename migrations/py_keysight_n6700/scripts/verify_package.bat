@echo off
setlocal
cd /d "%~dp0\.."
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
"%PYTHON%" scripts\generate_ai_contract.py --check || exit /b 1
"%PYTHON%" scripts\verify_project_package.py --source . --expected-release 26.09
exit /b %ERRORLEVEL%
