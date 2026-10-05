@echo off
title WLO Inventory Sync & Gift Verification
cls
echo ==============================================================================
echo       WLO INVENTORY SYNC ^& GIFT OPENING VERIFICATION TOOL
echo ==============================================================================
echo.
echo  [1] Phan tich file bat goi tin mau (wlo_game_only.pcapng)
echo  [2] Theo doi truc tiep tien trinh game dang chay (Live Frida Hook)
echo  [0] Thoat
echo.
echo ==============================================================================
set /p opt="Nhap lua chon [1-2] (Mac dinh 1): "

if "%opt%"=="" set opt=1
if "%opt%"=="1" goto opt1
if "%opt%"=="2" goto opt2
if "%opt%"=="0" exit /b

:opt1
cls
echo [*] Dang phan tich goi tin dang nhap va mo qua tu file PCAP...
python "%~dp0wlo_verify_inventory_sync.py" --pcap "%~dp0captures\wlo_game_only.pcapng"
goto end

:opt2
cls
echo [*] Dang khoi chay Live Hook tren tien trinh game...
python "%~dp0wlo_verify_inventory_sync.py"
goto end

:end
echo.
echo ==============================================================================
pause
