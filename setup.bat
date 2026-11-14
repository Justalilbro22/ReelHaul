@echo off
setlocal
cd /d "%~dp0"
echo.
echo  ReelHaul setup
echo  --------------
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Creating a private Python environment...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3.11 -m venv .venv 2>nul || py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo Could not create the environment. Install Python 3.10+ from python.org
        echo and run this file again.
        pause
        exit /b 1
    )
)

echo Installing the downloader engine...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo Dependency install failed. Check your internet connection and try again.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" make_assets.py >nul 2>nul

echo.
echo Done! Double-click ReelHaul.bat to start.
echo.
pause
