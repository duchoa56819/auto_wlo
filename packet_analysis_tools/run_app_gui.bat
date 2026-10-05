@echo off
title WLO Companion App (GUI)
cls
echo ==============================================================================
echo                 WONDERLAND ONLINE COMPANION APPLICATION (GUI)
echo ==============================================================================
echo.
echo [*] Dang khoi chay giao dien do hoa WLO App...
echo.

start pythonw "%~dp0wlo_app_gui.py"

if errorlevel 1 (
    echo [!] Khong khoi dong duoc bang pythonw, dang thu lai bang python...
    python "%~dp0wlo_app_gui.py"
)

exit /b
