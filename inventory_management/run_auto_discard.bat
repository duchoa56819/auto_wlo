@echo off
title WLO Smart Auto-Discard
cls
echo ==============================================================================
echo             WLO SMART AUTO-DISCARD AND CLEANER (TU DONG VUT RAC)
echo ==============================================================================
echo.
echo  [1] Chay Tu Dong Vut Rac (Ghi log day du vao auto_discard_log.txt)
echo  [2] Chay Che Do Thu Nghiem (Dry-Run: Chi thong bao, KHONG vut that)
echo  [3] Mo file cau hinh Blacklist (wlo_auto_discard_config.json)
echo  [4] Xem file nhat ky log (auto_discard_log.txt)
echo  [0] Thoat
echo.
echo ==============================================================================
set /p opt="Nhap lua chon [1-4] (Mac dinh 1): "

if "%opt%"=="" set opt=1
if "%opt%"=="1" goto opt1
if "%opt%"=="2" goto opt2
if "%opt%"=="3" goto opt3
if "%opt%"=="4" goto opt4
if "%opt%"=="0" exit /b

:opt1
cls
echo [*] Dang khoi chay Tu dong vut rac WLO...
python "%~dp0wlo_auto_discard.py"
goto end

:opt2
cls
echo [*] Dang khoi chay che do Dry-Run (thu nghiem an toan)...
python "%~dp0wlo_auto_discard.py" --dry-run
goto end

:opt3
start notepad "%~dp0wlo_auto_discard_config.json"
goto end

:opt4
start notepad "%~dp0auto_discard_log.txt"
goto end

:end
echo.
echo ==============================================================================
pause
