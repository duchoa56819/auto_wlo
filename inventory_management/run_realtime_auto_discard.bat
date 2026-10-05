@echo off
title WLO Real-Time Auto Discard Service (Thap 29 Tang & Cursed Palace)
chcp 65001 >nul
cd /d "%~dp0"
python wlo_realtime_auto_discard.py
pause
