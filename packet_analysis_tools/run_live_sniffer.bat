@echo off
chcp 65001 > nul
cls
echo ==============================================================================
echo             WLO LIVE PACKET SNIFFER & TRANSLATOR (FRIDA)
echo ==============================================================================
echo.
echo  [1] Lang nghe truc tiep aloginF02.exe (An Ping/Heartbeat)
echo  [2] Lang nghe toan bo goi tin (Bao gom ca Ping)
echo  [3] Chi theo doi thao tac Di chuyen (Opcode 0x32)
echo  [4] Chi theo doi tin nhan Chat / He thong (Opcode 0x14)
echo  [5] Chi theo doi hanh dong Chien dau (Opcode 0x06)
echo  [6] Lang nghe va Luu toan bo log vao file live_packet_log.txt
echo  [0] Thoat
echo.
echo ==============================================================================
set /p opt="Nhap lua chon cua ban [1-6] (Mac dinh 1): "

if "%opt%"=="" set opt=1
if "%opt%"=="1" goto opt1
if "%opt%"=="2" goto opt2
if "%opt%"=="3" goto opt3
if "%opt%"=="4" goto opt4
if "%opt%"=="5" goto opt5
if "%opt%"=="6" goto opt6
if "%opt%"=="0" exit /b

:opt1
cls
echo [*] Dang khoi chay lang nghe aloginF02.exe (Khong hien Ping)...
python "%~dp0wlo_live_sniffer.py" -p aloginF02.exe --no-ping
goto end

:opt2
cls
echo [*] Dang khoi chay lang nghe tat ca goi tin...
python "%~dp0wlo_live_sniffer.py" -p aloginF02.exe
goto end

:opt3
cls
echo [*] Dang theo doi thao tac di chuyen (Opcode 0x32)...
python "%~dp0wlo_live_sniffer.py" -p aloginF02.exe -o 0x32
goto end

:opt4
cls
echo [*] Dang theo doi kenh Chat va Thong bao (Opcode 0x14)...
python "%~dp0wlo_live_sniffer.py" -p aloginF02.exe -o 0x14
goto end

:opt5
cls
echo [*] Dang theo doi hanh dong Chien dau (Opcode 0x06)...
python "%~dp0wlo_live_sniffer.py" -p aloginF02.exe -o 0x06
goto end

:opt6
cls
echo [*] Dang ghi log goi tin vao file live_packet_log.txt...
python "%~dp0wlo_live_sniffer.py" -p aloginF02.exe --no-ping --save "%~dp0live_packet_log.txt"
goto end

:end
echo.
echo ==============================================================================
pause
