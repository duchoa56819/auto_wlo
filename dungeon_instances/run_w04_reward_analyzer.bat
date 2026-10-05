@echo off
chcp 65001 >nul
title WLO W04 - Giam Sat Va Phan Tich Mo Hop Qua Thuong
color 0A

echo =====================================================================
echo       WLO W04 - THEO DOI VA PHAN TICH MO HOP QUA THUONG THOI GIAN THUC
echo =====================================================================
echo [*] Dang khoi chay giam sat alogin-W04...
echo.

python -u "%~dp0wlo_w04_reward_analyzer.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Chuong trinh da dong hoac gap loi.
    pause
)
