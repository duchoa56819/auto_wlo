@echo off
title WLO Session Analyzer - alogin-F032.exe
cls
echo ==============================================================================
echo             WLO SESSION ANALYZER - alogin-F032.exe (PID: 15504)
echo ==============================================================================
echo.
echo [*] Dang khoi chay bo lang nghe phien dang nhap moi...
python "%~dp0wlo_session_analyzer.py" -p "alogin-F032.exe"
pause
