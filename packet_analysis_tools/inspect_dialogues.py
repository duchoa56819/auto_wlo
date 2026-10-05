import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

with open('party_instance_capture.log', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

entries = text.split('\n[')

print("=== NPC TALK & DIALOGUE OPTIONS ===")
for e in entries:
    if any(k in e for k in ['NPC_DIALOG_CHOICE', 'CHAT_DIALOG_TEXT', 'DUNGEON_INSTANCE_LOBBY', 'MAP_SCENE_QUEST', 'WARP']):
        lines = e.strip().split('\n')
        hdr = lines[0]
        # filter out repetitive ping/map updates
        if 'Sub:0x0A' in hdr and 'Len:5' in hdr: # lobby user list
            continue
        if 'Sub:0x03' in hdr and 'Op:0x35' in hdr:
            continue
        if 'Sub:0x05' in hdr and 'Op:0x35' in hdr:
            continue
        if 'Sub:0x06' in hdr and 'Op:0x35' in hdr:
            continue
        print(hdr)
        for l in lines[1:]:
            print('   ', l)

