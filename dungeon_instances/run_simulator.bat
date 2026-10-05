@echo off
echo ================================================================
echo           WLO DUNGEON AND ACTION SIMULATOR
echo ================================================================
echo.
echo Chon che do chay:
echo   [1] Xem truoc kich ban (Dry-Run: Khong gui mang)
echo   [2] Chay thuc te ket noi den Server (Live: 127.0.0.1:6414)
echo   [3] Chay thuc te tang toc do gap doi (--live --speed 2.0)
echo   [4] Chay tung buoc (Bam Enter xac nhan truoc moi giai doan)
echo   [5] Thoat
echo.

choice /c 12345 /n /m "Nhap lua chon [1-5]: "

if errorlevel 5 goto quit
if errorlevel 4 goto step
if errorlevel 3 goto speed
if errorlevel 2 goto live
if errorlevel 1 goto dry

:dry
python "%~dp0wlo_simulate_dungeon.py" --dry-run
goto end

:live
python "%~dp0wlo_simulate_dungeon.py" --live
goto end

:speed
python "%~dp0wlo_simulate_dungeon.py" --live --speed 2.0
goto end

:step
python "%~dp0wlo_simulate_dungeon.py" --live --step
goto end

:quit
echo Tam biet!
goto end

:end
echo.
pause
