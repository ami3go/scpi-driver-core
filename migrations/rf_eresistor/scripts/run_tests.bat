@echo off
setlocal
python -m pytest
if errorlevel 1 exit /b %errorlevel%
python -m robot --outputdir results tests\robot

