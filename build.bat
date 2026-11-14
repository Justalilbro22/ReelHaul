@echo off
setlocal
cd /d "%~dp0"

echo.
echo  TubeGrab release build
echo  ----------------------
echo.

if not exist ".venv\Scripts\python.exe" (
    call setup.bat || exit /b 1
)

".venv\Scripts\python.exe" -m pip install pyinstaller --quiet
if errorlevel 1 exit /b 1

echo Refreshing assets...
".venv\Scripts\python.exe" make_assets.py
".venv\Scripts\python.exe" make_installer_art.py

echo Packaging the app...
".venv\Scripts\pyinstaller.exe" --noconfirm --clean TubeGrab.spec
if errorlevel 1 (
    echo PyInstaller failed.
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "signing\sign.ps1" -Stage app
if errorlevel 1 exit /b 1

set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo.
    echo Inno Setup 6 is needed to build the installer:
    echo     winget install -e --id JRSoftware.InnoSetup
    echo The packaged app is still ready in dist\TubeGrab\.
    exit /b 1
)

echo Building the installer...
"%ISCC%" installer.iss
if errorlevel 1 exit /b 1

powershell -NoProfile -ExecutionPolicy Bypass -File "signing\sign.ps1" -Stage setup
if errorlevel 1 exit /b 1

echo.
echo Done! Installer: release\TubeGrab-Setup-*.exe
echo Standalone app:  dist\TubeGrab\TubeGrab.exe
echo.
pause
