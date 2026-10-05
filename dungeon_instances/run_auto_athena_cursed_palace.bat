@echo off
chcp 65001 >nul
title WLO Auto Athena to Cursed Palace
color 0B

echo =====================================================================
echo            WLO AUTO ATHENA TO CURSED PALACE (MINIDRAGONFLY)
echo =====================================================================
echo.

python -u "%~dp0wlo_auto_athena_cursed_palace.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Script da dung hoac gap loi.
    pause
)
