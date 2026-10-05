@echo off
chcp 65001 >nul
title WLO Capture & Analyzer - alogin-F02 (Instance Monitor)
color 0E

echo =====================================================================
echo       WLO LIVE PACKET CAPTURE & ANALYZER - ALOGIN-F02
echo =====================================================================
echo [*] Dang khoi dong bo giam sat goi tin F02...
echo.

python -u "%~dp0wlo_capture_f02.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Ung dung da dung lai.
    pause
)
