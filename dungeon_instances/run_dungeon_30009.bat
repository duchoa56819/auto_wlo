@echo off
chcp 65001 >nul
title WLO Auto Dungeon 30009 Manager - Giao Dien Phu Ban Tu Dong
color 0B

echo =====================================================================
echo          WLO AUTO DUNGEON 30009 - GIAO DIEN PHU BAN TU DONG
echo =====================================================================
echo [*] Dang khoi chay giao dien do hoa...
echo.

python -u "%~dp0wlo_dungeon_30009_gui.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Ung dung da dong hoac gap loi.
    pause
)
