@echo off
setlocal
if "%~1"=="" (
  echo Usage: scripts\run_example.bat examples\01_identity.robot [Robot options]
  exit /b 2
)
python -m robot --outputdir results %*

