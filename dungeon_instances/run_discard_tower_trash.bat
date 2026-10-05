@echo off
title WLO Discard Sky Tower Trash Rewards
chcp 65001 >nul
cd /d "%~dp0"
python wlo_tower_29_auto_discard.py %*
pause
