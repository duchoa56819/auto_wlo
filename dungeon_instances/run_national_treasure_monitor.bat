@echo off
chcp 65001 >nul
title WLO NATIONAL TREASURE (QUOC BAO) LIVE MONITOR
color 0B

echo =======================================================================
echo          WLO NATIONAL TREASURE (QUOC BAO) LIVE MONITOR ^& ANALYZER
echo =======================================================================
echo.
echo  [*] Dang khoi chay bo theo doi va ghi nhan thoi gian thuc...
echo.

python "%~dp0wlo_national_treasure_monitor.py"

pause
