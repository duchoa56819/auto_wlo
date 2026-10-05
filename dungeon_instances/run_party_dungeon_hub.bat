@echo off
chcp 65001 >nul
title WLO Auto Party Dungeon Hub - Quan Ly 4 Phu Ban To Doi
color 0B

echo =====================================================================
echo        WLO AUTO PARTY DUNGEON HUB - QUAN LY 4 PHU BAN TO DOI
echo            (30039, 30025, 30021, 30013 - 1 Leader + 3 Members)
echo =====================================================================
echo [*] Dang khoi chay giao dien do hoa...
echo.

python -u "%~dp0wlo_party_dungeon_hub_gui.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Ung dung da dong hoac gap loi.
    pause
)
