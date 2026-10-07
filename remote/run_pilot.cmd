@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r remote\requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m remote.launcher
pause
exit /b
:failed
echo Install Python 3.11 or newer, then run this launcher again.
pause
exit /b 1
