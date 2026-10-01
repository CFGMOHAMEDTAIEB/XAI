@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\status-all.ps1" %*
exit /b %ERRORLEVEL%
