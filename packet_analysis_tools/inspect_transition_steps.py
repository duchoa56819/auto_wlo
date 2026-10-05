import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('transitions_utf8.txt', 'r', encoding='utf-8') as f:
    text = f.read()

sections = text.split('========================================================\n')
for s in sections[1:]:
    lines = [l for l in s.split('\n') if l.strip()]
    if not lines:
        continue
    title = lines[0]
    print(f"\n========================================================")
    print(f"{title}")
    print(f"========================================================")
    for l in lines[1:]:
        # Print leader C->S dialogue, movement, or any reward
        if any(k in l for k in ['NHẬN PHẦN THƯỞNG', 'Sub:0x01 Len:2', 'Sub:0x02 Len:1', 'Sub:0x06 Len:0', 'Sub:0x03 Len:0', 'Sub:0x08 Len:2', 'NẠP BẢN ĐỒ', 'WARP']):
            print(" ", l[:120])
