@echo off
setlocal
cd /d "%~dp0.."
if "%N6700_CONNECTION_TYPE%"=="" set "N6700_CONNECTION_TYPE=usb"
if "%N6700_CHANNEL%"=="" set "N6700_CHANNEL=1"
if "%N6700_PORT%"=="" set "N6700_PORT=5025"
if "%N6700_EXPECTED_MODULE%"=="" set "N6700_EXPECTED_MODULE=N6775A"
if /I "%N6700_CONNECTION_TYPE%"=="usb" if "%N6700_RESOURCE%"=="" set "N6700_RESOURCE=USB0::0x0957::0x0907::MY43014421::INSTR"
if "%N6700_ALLOW_RESET%"=="" set "N6700_ALLOW_RESET=false"
if "%N6700_ALLOW_ACTIVE_OUTPUT%"=="" set "N6700_ALLOW_ACTIVE_OUTPUT=false"
if /I "%N6700_CONNECTION_TYPE%"=="simulated" (
  set "HIL_ENABLE=false"
  set "N6700_RESOURCE=NOT_SET"
  if /I "%N6700_EXPECTED_MODULE%"=="N6775A" set "N6700_EXPECTED_MODULE=N6751A"
) else (
  set "HIL_ENABLE=true"
  if "%N6700_RESOURCE%"=="" (
    echo ERROR: Set N6700_RESOURCE before running.
    echo Example: set N6700_RESOURCE=USB0::0x0957::0x0907::MY43014421::INSTR
    exit /b 2
  )
)
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
for /f %%I in ('powershell -NoProfile -Command "Get-Date -AsUTC -Format yyyyMMddTHHmmssZ"') do set "STAMP=%%I"
set "OUT=results\call_protocol_conformance\keysight_n6700\%STAMP%"
if not exist "%OUT%" mkdir "%OUT%"
"%PYTHON%" -m robot --name "N6775A Full Self Check" --outputdir "%OUT%" ^
  --variable "HIL_ENABLE:%HIL_ENABLE%" ^
  --variable "CONNECTION_TYPE:%N6700_CONNECTION_TYPE%" ^
  --variable "N6700_RESOURCE:%N6700_RESOURCE%" ^
  --variable "N6700_PORT:%N6700_PORT%" ^
  --variable "CHANNEL:%N6700_CHANNEL%" ^
  --variable "EXPECTED_MODULE:%N6700_EXPECTED_MODULE%" ^
  --variable "ALLOW_RESET:%N6700_ALLOW_RESET%" ^
  --variable "ALLOW_ACTIVE_OUTPUT:%N6700_ALLOW_ACTIVE_OUTPUT%" ^
  tests\conformance\driver_call_protocol_conformance.robot
set "RC=%ERRORLEVEL%"
"%PYTHON%" scripts\summarize_n6775a_self_check.py "%OUT%"
if not "%ERRORLEVEL%"=="0" if "%RC%"=="0" set "RC=%ERRORLEVEL%"
echo Result directory: %OUT%
exit /b %RC%
