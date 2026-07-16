@echo off
chcp 65001 >nul
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
    echo 无法启动 nbs2func 图形界面。
    echo Make sure Python is installed and run:
    echo 请确认已安装 Python，然后运行：
    echo   python -m pip install -r requirements.txt
    echo.
    pause
)
