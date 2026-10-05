@echo off
title WLO Item Collector & Database
cls
echo ==============================================================================
echo             WLO SMART ITEM COLLECTOR AND DATABASE (THU THAP VAT PHAM)
echo ==============================================================================
echo.
echo  [1] Chay Thu Thap Vat Pham (Tu dong luu khi Mo qua hoac Vut do)
echo  [2] Xem danh sach vat pham da thu thap (wlo_items_database.txt)
echo  [3] Mo file co so du lieu JSON (wlo_items_database.json)
echo  [4] Xem file nhat ky log (item_collector_log.txt)
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
echo [*] Dang khoi chay WLO Item Collector...
python "%~dp0wlo_item_collector.py"
goto end

:opt2
if exist "%~dp0wlo_items_database.txt" (
    start notepad "%~dp0wlo_items_database.txt"
) else (
    echo [!] Chua co file wlo_items_database.txt. Hay chay lua chon [1] de thu thap vat pham truoc.
)
goto end

:opt3
if exist "%~dp0wlo_items_database.json" (
    start notepad "%~dp0wlo_items_database.json"
) else (
    echo [!] Chua co file wlo_items_database.json.
)
goto end

:opt4
if exist "%~dp0item_collector_log.txt" (
    start notepad "%~dp0item_collector_log.txt"
) else (
    echo [!] Chua co file log item_collector_log.txt.
)
goto end

:end
echo.
echo ==============================================================================
pause
