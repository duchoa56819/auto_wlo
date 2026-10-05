@echo off
chcp 65001 >nul
title WLO Item Namer va Discard Manager - Dat Ten va Vut Do
color 0B

echo =====================================================================
echo       WLO ITEM NAMER VA DISCARD MANAGER - QUAN LY TUI DO VA VAT PHAM
echo =====================================================================
echo [*] Dang khoi chay giao dien do hoa...
echo.

python -u "%~dp0wlo_item_namer_gui.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Ung dung da dong hoac gap loi.
    pause
)
