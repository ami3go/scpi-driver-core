@echo off
setlocal
set ROOT=%~dp0..
if not exist "%ROOT%\.venv\Scripts\python.exe" (
  echo Run scripts\setup_venv.bat first.
  exit /b 1
)
pushd "%ROOT%"
".venv\Scripts\python.exe" -m pytest || goto :error
".venv\Scripts\robot.exe" --outputdir build\robot tests\robot\acceptance.robot || goto :error
".venv\Scripts\python.exe" -m ruff check . || goto :error
".venv\Scripts\python.exe" -m build || goto :error
popd
exit /b 0
:error
popd
exit /b 1
