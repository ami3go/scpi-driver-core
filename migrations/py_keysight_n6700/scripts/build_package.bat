@echo off
setlocal
cd /d "%~dp0.."
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
"%PYTHON%" scripts\generate_ai_contract.py --check || exit /b 1
if exist dist rmdir /s /q dist
"%PYTHON%" -m build || exit /b 1
"%PYTHON%" -m robot.libdoc KeysightN6700Library docs\KeysightN6700Library.html || exit /b 1
"%PYTHON%" -m mkdocs build --strict --clean || exit /b 1
"%PYTHON%" scripts\make_release.py || exit /b 1
endlocal
