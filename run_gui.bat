@echo off
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

where py >nul 2>nul
if errorlevel 1 (
    python -m nbs2func.gui.app
) else (
    py -3 -m nbs2func.gui.app
)

if errorlevel 1 (
    echo.
    echo Failed to start nbs2func GUI.
    echo Make sure Python is installed and run:
    echo   python -m pip install -r requirements.txt
    echo.
    pause
)
