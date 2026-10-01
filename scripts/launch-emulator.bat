@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch-emulator.ps1" %*
exit /b %ERRORLEVEL%
