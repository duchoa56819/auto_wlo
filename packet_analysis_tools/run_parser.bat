@echo off
echo =======================================================
echo          WLO PACKET PARSER AND ANALYZER
echo =======================================================
echo.
python "%~dp0wlo_packet_parser.py" --no-ping -n 50
echo.
echo =======================================================
echo Huong dan su dung lenh:
echo   - Xem tat ca:             python wlo_packet_parser.py -n 0
echo   - Loc ma Chat (0x14):     python wlo_packet_parser.py -o 0x14
echo   - Loc di chuyen (0x32):   python wlo_packet_parser.py -o 0x32
echo   - Luu log ra file txt:    python wlo_packet_parser.py --no-ping --save packet_log.txt
echo =======================================================
pause
