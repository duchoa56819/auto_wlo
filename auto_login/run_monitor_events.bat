@echo off
chcp 65001 >nul
title WLO Window & Pixel Event Monitor
cd /d "%~dp0"

echo ========================================================
echo   GIAM SAT SU KIEN CUA SO & PIXEL DANG NHAP WLO
echo ========================================================
echo.
echo Hay thuc hien cac buoc dang nhap binh thuong.
echo Script se tu dong ghi nhan moi cua so moi va su thay doi giao dien.
echo.
python monitor_events.py
echo.
pause
