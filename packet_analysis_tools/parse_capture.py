import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

log_path = r'G:\WLOI_beta\WLOI\party_instance_capture.log'

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")

keywords = [
    'CHỌN PHỤ BẢN', 'BẮT ĐẦU PHỤ BẢN', 'SẴN SÀNG LOBBY',
    'VÀO TRẬN ĐÁNH', 'KẾT THÚC TRẬN ĐÁNH', 'NẠP BẢN ĐỒ CẢNH MỚI',
    'CỔNG DỊCH CHUYỂN', 'CHIẾC LU', 'NHẬN PHẦN THƯỞNG',
    'CHỌN MENU NPC', 'BƯỚC VÀO THOẠI NPC', 'TỔ ĐỘI', 'ĐỒNG BỘ ĐỘI HÌNH',
    'CHUYỂN ĐỘI TRƯỞNG', 'DI CHUYỂN', 'CLICK TƯƠNG TÁC'
]

events = []
i = 0
while i < len(lines):
    line = lines[i]
    # Check if this line or next line has details
    has_kw = False
    kw_found = ""
    for kw in keywords:
        if kw in line:
            has_kw = True
            kw_found = kw
            break
    
    if has_kw:
        events.append((i+1, line.strip()))
    i += 1

print(f"Found {len(events)} event lines.")
# Write events to summary file
with open('capture_events_summary.txt', 'w', encoding='utf-8') as out:
    for line_no, ev in events:
        out.write(f"Line {line_no}: {ev}\n")

print("Saved capture_events_summary.txt")
