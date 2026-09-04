@echo off
setlocal
if "%~1"=="" (
  echo Usage: run_example.bat examples\01_emulator_smoke.robot
  exit /b 2
)
set ROOT=%~dp0..
if not exist "%ROOT%\.venv\Scripts\robot.exe" (
  echo Run scripts\setup_venv.bat first.
  exit /b 1
)
"%ROOT%\.venv\Scripts\robot.exe" --outputdir "%ROOT%\build\examples" "%~1"
