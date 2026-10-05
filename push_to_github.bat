@echo off
chcp 65001 >nul
echo ========================================================
echo  Đang đẩy toàn bộ code auto_wlo lên GitHub...
echo  Repo: https://github.com/duchoa56819/auto_wlo
echo ========================================================
echo.

git push origin main

if %ERRORLEVEL% equ 0 (
    echo.
    echo ========================================================
    echo  [THANH CONG] Da day toan bo source code len GitHub!
    echo ========================================================
) else (
    echo.
    echo ========================================================
    echo  [THAT BAI] Khong the day code. Vui long kiem tra dang nhap hoac Personal Access Token.
    echo ========================================================
)

pause
