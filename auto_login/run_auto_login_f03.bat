@echo off
chcp 65001 >nul
title WLO Auto Login F03
cd /d "%~dp0"

echo ========================================================
echo   TU DONG DANG NHAP WLO - TAI KHOAN F03
echo ========================================================
python auto_login.py --account bgdF03 --password 111111 --email backspace.noob@gmail.com
echo.
pause
