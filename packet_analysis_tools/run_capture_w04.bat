@echo off
chcp 65001 >nul
title WLO Capture & Analyze Cursed Palace - alogin-W04
color 0E

echo =====================================================================
echo       WLO CAPTURE & ANALYZE CURSED PALACE ON ALOGIN-W04
echo =====================================================================
echo.

python -u "%~dp0wlo_capture_w04.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Script gap loi hoac da dung.
    pause
)
