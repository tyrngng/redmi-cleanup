@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Redmi Cleanup (Wi-Fi)

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 redmi_cleanup.py --wifi %*
    goto end
)

where python >nul 2>&1
if %errorlevel%==0 (
    python redmi_cleanup.py --wifi %*
    goto end
)

echo.
echo ERROR: Python 3 is not installed.
echo.
echo 1. Download it from https://www.python.org/downloads/
echo 2. During installation check "Add python.exe to PATH"
echo 3. Run START.bat again
echo.
start https://www.python.org/downloads/

:end
echo.
pause
