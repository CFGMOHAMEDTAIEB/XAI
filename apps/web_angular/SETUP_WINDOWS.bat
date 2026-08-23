@echo off
npm ci
if errorlevel 1 exit /b 1
npm run typecheck
if errorlevel 1 exit /b 1
npm run build
