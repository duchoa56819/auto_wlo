@echo off
title WLO Discard Cursed Palace Trash Rewards
chcp 65001 >nul
cd /d "%~dp0"
python wlo_cursed_palace_auto_discard.py %*
pause
