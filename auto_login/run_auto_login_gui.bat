@echo off
chcp 65001 >nul
title WLO Auto Login - GUI
cd /d "%~dp0"

echo ========================================================
echo   KHOI DONG GIAO DIEN WLO AUTO LOGIN
echo ========================================================
python auto_login_gui.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Gap loi khi chay giao dien. Vui long kiem tra Python.
    pause
)
