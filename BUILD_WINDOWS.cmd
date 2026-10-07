@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\desktop\build-windows.ps1"
if errorlevel 1 (pause & exit /b 1)
pause
