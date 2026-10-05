@echo off
chcp 65001 >nul
title WLO Capture Party Instance - Giam Sat Packet To Doi
color 0E

echo =====================================================================
echo         WLO CAPTURE PARTY INSTANCE - GIAM SAT GOI TIN TO DOI
echo                   (alogin-W01, alogin-F02, alogin-F04)
echo =====================================================================
echo [*] Dang khoi chay he thong giam sat...
echo.

python -u "%~dp0wlo_capture_party_instance.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Chuong trinh bi dung hoac gap loi.
    pause
)
