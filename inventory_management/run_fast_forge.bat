@echo off
chcp 65001 >nul
title WLO Fast Forge - Enhance Manager - Cường Hóa - Khảm Ngọc Siêu Tốc
color 0D

echo =====================================================================
echo       WLO FAST FORGE - ENHANCE MANAGER - CUONG HOA - KHAM NGOC
echo =====================================================================
echo [*] Dang khoi chay giao dien do hoa cuong hoa sieu toc...
echo.

python -u "%~dp0wlo_fast_forge_gui.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Ung dung da dong hoac gap loi.
    pause
)
