@echo off
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    python -m pip install -r requirements.txt
) else (
    py -3 -m pip install -r requirements.txt
)

echo.
if errorlevel 1 (
    echo Failed to install requirements.
    echo 无法安装依赖项。
) else (
    echo Requirements installed successfully.
    echo 依赖项安装成功。
)
pause
