@echo off
chcp 65001 >nul
title WLO All-in-One: Auto Party va Auto Combat Assistant
color 0B

echo ==============================================================================
echo       WLO ALL-IN-ONE: AUTO PARTY MANAGER + AUTO COMBAT ASSISTANT
echo ==============================================================================
echo [*] Che do toi uu tai nguyen: Giao dien hop nhat 2-trong-1 (1 Process Python)
echo     - Tab 1: Quan Ly To Doi (Party Manager)
echo     - Tab 2: Tu Dong Chien Dau (Auto Combat)
echo ==============================================================================
echo.

set "BASE_DIR=%~dp0"

:: Kiem tra file wlo_party_combat_gui.py
set "UNIFIED_PY="
if exist "%BASE_DIR%wlo_party_combat_gui.py" (
    set "UNIFIED_PY=%BASE_DIR%wlo_party_combat_gui.py"
    set "UNIFIED_DIR=%BASE_DIR%"
) else if exist "%BASE_DIR%..\WLOI\wlo_party_combat_gui.py" (
    set "UNIFIED_PY=%BASE_DIR%..\WLOI\wlo_party_combat_gui.py"
    set "UNIFIED_DIR=%BASE_DIR%..\WLOI\"
) else if exist "%BASE_DIR%..\WLOI - Eng\wlo_party_combat_gui.py" (
    set "UNIFIED_PY=%BASE_DIR%..\WLOI - Eng\wlo_party_combat_gui.py"
    set "UNIFIED_DIR=%BASE_DIR%..\WLOI - Eng\"
)

if not defined UNIFIED_PY (
    echo [!] Loi: Khong tim thay file wlo_party_combat_gui.py!
    pause
    exit /b 1
)

:: Khoi dong giao dien hop nhat 2-trong-1
echo [*] Dang khoi dong giao dien WLO All-in-One...
start "WLO All-in-One Assistant" /d "%UNIFIED_DIR%" python -u "%UNIFIED_PY%"

echo.
echo ==============================================================================
echo [V] Da khoi chay thanh cong giao dien hop nhat!
echo ==============================================================================
timeout /t 2 /nobreak >nul 2>&1
exit /b 0
