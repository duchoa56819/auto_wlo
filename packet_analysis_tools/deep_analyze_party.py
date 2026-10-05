import sys
import re
import struct

sys.stdout.reconfigure(encoding='utf-8')

log_path = r'G:\WLOI_beta\WLOI\party_instance_capture.log'

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

# Let's inspect early packets to find lobby and instance ID
entries = text.split('\n[')

print(f"Total entries: {len(entries)}")

# 1. Find Dungeon ID
print("\n=== 1. DUNGEON / LOBBY SELECTION ===")
for e in entries:
    if 'Op:0x55' in e or 'DUNGEON_INSTANCE_LOBBY' in e:
        print(e.strip())

# 2. Find Party setup
print("\n=== 2. PARTY PACKETS ===")
for e in entries[:50]:
    if 'Op:0x0D' in e or 'PARTY_SYSTEM' in e or 'TEAM_FORMATION' in e:
        print(e.strip())

# 3. Find Map / Scene loads
print("\n=== 3. MAP LOADS & WARPS ===")
for e in entries:
    if 'Op:0x16' in e or 'MAP_SCENE_QUEST' in e or 'Op:0x35' in e or 'WARP' in e:
        print(e.strip()[:200])

