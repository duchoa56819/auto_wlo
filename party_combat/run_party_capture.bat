@echo off
chcp 65001 >nul
title WLO Party Packet Sniffer - Bat goi to doi
color 0E

echo =====================================================================
echo            WLO PARTY PACKET SNIFFER (aloginF02 va alogin-F04)
echo =====================================================================
echo.

python -u "%~dp0wlo_capture_party.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Ung dung da dong hoac gap loi.
    pause
)
