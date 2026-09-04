@echo off
setlocal
set ROOT=%~dp0..
py -m venv "%ROOT%\.venv" || exit /b 1
"%ROOT%\.venv\Scripts\python.exe" -m pip install --upgrade pip || exit /b 1
"%ROOT%\.venv\Scripts\python.exe" -m pip install -e "%ROOT%[dev,docs]" || exit /b 1
echo Environment ready: %ROOT%\.venv
