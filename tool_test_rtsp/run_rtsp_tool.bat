@echo off
chcp 65001 >nul
title Mắt Phố - RTSP Virtual Camera Studio

echo ======================================================================
echo           MẮT PHỐ - RTSP VIRTUAL CAMERA FLEET STUDIO
echo ======================================================================
echo.

cd /d "%~dp0.."

set "PYTHON_EXE="
if exist "D:\Project\Team_Project\NOD89\MatPho-Draft\backend\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=D:\Project\Team_Project\NOD89\MatPho-Draft\backend\.venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [INFO] Dang su dung Python: %PYTHON_EXE%
echo [INFO] Khoi chay giao dien RTSP Studio GUI...
echo.

set PYTHONPATH=.
"%PYTHON_EXE%" -m tool_test_rtsp.src.gui_app

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Co loi xay ra khi chay tool RTSP! Ma loi: %ERRORLEVEL%
    pause
)
