@echo off
chcp 65001 > nul
cls
echo ==============================================================================
echo        WLO LIVE SKILL MONITOR FOR ALOGIN-F04 (HỆ LỬA)
echo ==============================================================================
echo.
echo [*] Dang khoi chay bat goi tin alogin-F04...
python "%~dp0wlo_capture_f04.py"
pause
