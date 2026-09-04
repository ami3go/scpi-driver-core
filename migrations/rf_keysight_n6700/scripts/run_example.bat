@echo off
setlocal
cd /d "%~dp0.."
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "EXAMPLE=%~1"
if "%EXAMPLE%"=="" set "EXAMPLE=01_simulator_smoke.robot"
if not exist "examples\robot\%EXAMPLE%" (
    echo Example not found: examples\robot\%EXAMPLE%
    exit /b 2
)
"%PYTHON%" -m robot --outputdir "build\example-results" "examples\robot\%EXAMPLE%"
endlocal
