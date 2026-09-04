@echo off
setlocal
cd /d "%~dp0.."
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
"%PYTHON%" -m robot.libdoc KeysightN6700Library docs\KeysightN6700Library.html || exit /b 1
"%PYTHON%" -m mkdocs build --strict --clean || exit /b 1
endlocal
