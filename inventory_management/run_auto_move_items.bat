@echo off
chcp 65001 >nul
title WLO Auto Move Items - Relog, Merge Stacks & Push to Bottom
color 0B

echo =====================================================================
echo    WLO AUTO MOVE ITEMS (RELOG, MERGE TRUNG LAP ^& DON XUONG CUOI)
echo =====================================================================
echo.
echo  [1] Chay tren alogin-W03 (Mac dinh)
echo  [2] Chay tren alogin-W04
echo  [3] Chay tren alogin-F02
echo  [4] Chay tren alogin-F04
echo  [5] Tuy chon tien trinh khac
echo.

set /p CHOICE="Nhap lua chon cua ban [1-5, mac dinh 1]: "
if "%CHOICE%"=="" set CHOICE=1

if "%CHOICE%"=="1" (
    python "%~dp0wlo_auto_move_items.py" -p w03
) else if "%CHOICE%"=="2" (
    python "%~dp0wlo_auto_move_items.py" -p w04
) else if "%CHOICE%"=="3" (
    python "%~dp0wlo_auto_move_items.py" -p f02
) else if "%CHOICE%"=="4" (
    python "%~dp0wlo_auto_move_items.py" -p f04
) else if "%CHOICE%"=="5" (
    set /p CUSTOM_PROC="Nhap ten tien trinh (VD: alogin-W03): "
    python "%~dp0wlo_auto_move_items.py" -p "%CUSTOM_PROC%"
) else (
    python "%~dp0wlo_auto_move_items.py" -p w03
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Da hoan tat hoac co loi say ra.
    pause
)
