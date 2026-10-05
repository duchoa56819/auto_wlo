@echo off
chcp 65001 >nul
title Cai dat moi truong WLO
color 0A

echo ==============================================================================
echo        CAI DAT THU VIEN PYTHON CHO WLO AUTO TOOLS (FRIDA, TKINTER...)
echo ==============================================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Khong tim thay Python tren he thong!
    echo [*] Vui long cai dat Python (khuyen nghi 3.10 tro len) tu: https://www.python.org/
    echo [*] LUU Y: Khi cai dat, nho tich vao o: "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)

echo [*] Python da duoc tim thay:
python --version
echo.

echo [*] Dang cap nhat pip va cai dat cac thu vien can thiet (frida, psutil...)...
python -m pip install --upgrade pip
python -m pip install -r "%~dp0requirements.txt"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ==============================================================================
    echo [V] Cai dat hoan tat! Ban co the chay run_party_auto_combat.bat ngay bay gio.
    echo ==============================================================================
) else (
    echo.
    echo [!] Co loi xay ra trong qua trinh cai dat. Vui long kiem tra ket noi mang.
)

echo.
pause
