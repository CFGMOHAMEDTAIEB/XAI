@echo off
where flutter >nul 2>nul || (echo ERROR: Flutter is missing from PATH. & exit /b 1)
flutter config --enable-windows-desktop
flutter create .
flutter pub get
flutter test
if errorlevel 1 exit /b 1
flutter build windows
if errorlevel 1 exit /b 1
echo Desktop application built successfully.
