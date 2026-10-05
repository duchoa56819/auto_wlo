@echo off
chcp 65001 >nul
title WLO Capture & Analyze Cursed Palace - alogin-W03
color 0E

echo =====================================================================
echo       WLO CAPTURE & ANALYZE CURSED PALACE ON ALOGIN-W03
echo =====================================================================
echo.

python -u "%~dp0wlo_capture_w03.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Script gap loi hoac da dung.
    pause
)
