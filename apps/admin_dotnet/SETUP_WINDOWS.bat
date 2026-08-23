@echo off
where dotnet >nul 2>nul
if errorlevel 1 (
  echo ERROR: .NET 8 SDK is not installed or not in PATH.
  exit /b 1
)
dotnet restore
if errorlevel 1 exit /b 1
dotnet build
if errorlevel 1 exit /b 1
echo Admin Console setup complete. Run: dotnet run
