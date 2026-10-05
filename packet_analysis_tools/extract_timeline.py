import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

log_path = r'G:\WLOI_beta\WLOI\party_instance_capture.log'

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Split by packet entries
entries = content.split('\n[')

print(f"Total packet entries: {len(entries)}")

timeline = []
for entry in entries:
    header_line = entry.split('\n')[0]
    # Check for important tags
    tags = []
    if 'CHỌN PHỤ BẢN' in entry:
        tags.append('CHỌN PHỤ BẢN')
    if 'BẮT ĐẦU PHỤ BẢN' in entry:
        tags.append('BẮT ĐẦU PHỤ BẢN')
    if 'SẴN SÀNG LOBBY' in entry:
        tags.append('SẴN SÀNG LOBBY')
    if 'VÀO TRẬN ĐÁNH' in entry:
        tags.append('VÀO TRẬN ĐÁNH')
    if 'KẾT THÚC TRẬN ĐÁNH' in entry:
        tags.append('KẾT THÚC TRẬN ĐÁNH')
    if 'NẠP BẢN ĐỒ CẢNH MỚI' in entry:
        tags.append('NẠP MAP')
    if 'CỔNG DỊCH CHUYỂN' in entry:
        tags.append('WARP')
    if 'CHIẾC LU' in entry:
        tags.append('CHIẾC LU')
    if 'NHẬN PHẦN THƯỞNG' in entry:
        tags.append('NHẬN THƯỞNG')
    if 'CHỌN MENU NPC' in entry:
        tags.append('MENU NPC')
    if 'BƯỚC VÀO THOẠI NPC' in entry:
        tags.append('THOẠI NPC')
    if 'ĐỒNG BỘ ĐỘI HÌNH' in entry:
        tags.append('ĐỒNG BỘ ĐỘI HÌNH')
    if 'CHUYỂN ĐỘI TRƯỞNG' in entry:
        tags.append('CHUYỂN ĐỘI TRƯỞNG')
    if 'CLICK TƯƠNG TÁC' in entry:
        tags.append('CLICK TƯƠNG TÁC')
    if 'DI CHUYỂN' in entry and ('W01' in header_line or 'F02' in header_line or 'F04' in header_line):
        # We can selectively log movement
        pass

    if tags:
        timeline.append((tags, entry.strip()))

print(f"Timeline events count: {len(timeline)}")

with open('high_level_timeline.txt', 'w', encoding='utf-8') as f:
    for tags, entry in timeline:
        f.write(f"=== [{', '.join(tags)}] ===\n")
        f.write(entry + "\n\n")

print("Saved high_level_timeline.txt")
