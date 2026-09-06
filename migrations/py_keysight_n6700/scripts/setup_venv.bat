@echo off
setlocal
cd /d "%~dp0.."
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 exit /b %errorlevel%
.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
if errorlevel 1 exit /b %errorlevel%
.venv\Scripts\python.exe -m pip install -e ".[dev,docs]"
if errorlevel 1 exit /b %errorlevel%
.venv\Scripts\python.exe -c "from KeysightN6700Library import KeysightN6700Library; print('RF Keysight N6700 environment ready')"
endlocal
