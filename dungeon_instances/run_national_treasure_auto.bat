@echo off
chcp 65001 >nul
title WLO National Treasure - Tu Dong Mo Ruong Quoc Bao
color 0E

echo =====================================================================
echo       WLO NATIONAL TREASURE - TU DONG MO RUONG VA GIAI MA PHONG
echo =====================================================================
echo [*] Quy tac:
echo     - Tu dong gui lenh mo tung ruong (1..30)
echo     - Tu dong chien dau neu gap quai vat
echo     - Tu dong dung mo ruong NGAY LAP TUC khi co Chia khoa Quoc Bao!
echo     - Tu dong xuat chien lai Pet neu Pet bi nga xuong
echo =====================================================================
echo.

python -u "%~dp0wlo_national_treasure_auto.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Chuong trinh da dung hoac gap loi.
    pause
)
