@echo off
where flutter >nul 2>nul
if errorlevel 1 (
  echo ERROR: Flutter is not installed or not in PATH.
  exit /b 1
)
flutter create .
flutter pub get
flutter test
if errorlevel 1 exit /b 1
echo Mobile Authenticator setup complete.
