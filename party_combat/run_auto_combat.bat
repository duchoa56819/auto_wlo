@echo off
chcp 65001 >nul
title WLO Auto Combat & Skill Assistant - Tu Dong Ra Chieu Chien Dau
color 0B

echo =====================================================================
echo       WLO AUTO COMBAT & SKILL ASSISTANT - TU DONG RA CHIEU
echo =====================================================================
echo [*] Dang khoi chay giao dien tu dong ra chieu chien dau...
echo.

python -u "%~dp0wlo_auto_combat_gui.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Ung dung da dong hoac gap loi.
    pause
)
