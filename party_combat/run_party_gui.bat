@echo off
chcp 65001 >nul
title WLO Auto Party Manager - Giao Dien Dieu Khien To Doi
color 0B

echo =====================================================================
echo            WLO AUTO PARTY MANAGER - GIAO DIEN TO DOI TU DONG
echo =====================================================================
echo [*] Dang khoi chay giao dien do hoa...
echo.

python -u "%~dp0wlo_party_gui.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Ung dung da dong hoac gap loi.
    pause
)
