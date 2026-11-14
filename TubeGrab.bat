@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    call setup.bat
    if not exist ".venv\Scripts\pythonw.exe" exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "app.py"
