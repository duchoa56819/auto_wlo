import sys
import re
import json

sys.stdout.reconfigure(encoding='utf-8')

log_path = r'G:\WLOI_beta\WLOI\party_instance_capture.log'

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

entries = text.split('\n[')

# Let's find boundaries for each of the 4 instances:
# Instance 1: Start (16:54:39) -> Reward (16:59:40) -> Exit (17:00:05)
# Instance 2: Lobby (17:00:10) -> Combats (17:01:15 - 17:03:54) -> Reward (17:04:27) -> Exit (17:04:40)
# Instance 3: Lobby (17:06:02) -> Combats (17:06:58 - 17:10:26) -> Reward (17:10:31) -> Exit (17:11:00)
# Instance 4: Lobby (17:13:18) -> Combats (17:13:57 - 17:17:10) -> Reward (17:17:11) -> Exit (17:17:30)

instance_ranges = [
    ("Instance 30039", 0, 4000),
    ("Instance 30025", 4000, 7260),
    ("Instance 30021", 7260, 11550),
    ("Instance 30013", 11550, len(entries))
]

for name, start_i, end_i in instance_ranges:
    print(f"\n================================================================================")
    print(f"=== {name} ===")
    print(f"================================================================================")
    inst_entries = entries[start_i:end_i]
    
    # 1. Lobby creation & join
    lobby_pkts = []
    # 2. Team formation
    team_pkts = []
    # 3. Movements & NPC talks
    actions = []
    # 4. Combats
    combats = []
    current_combat = None
    # 5. Rewards
    rewards = []
    
    for e in inst_entries:
        hdr = e.strip().split('\n')[0]
        if 'DUNGEON_INSTANCE_LOBBY' in hdr and 'C->S' in hdr:
            lobby_pkts.append(hdr)
        if 'PARTY_SYSTEM' in hdr and 'C->S' in hdr:
            team_pkts.append(hdr)
        if 'NHẬN PHẦN THƯỞNG' in e:
            for l in e.split('\n'):
                if 'NHẬN PHẦN THƯỞNG' in l:
                    rewards.append(l.strip())
                    
        # Track leader movements and NPC choices
        if '[F02] C->S' in hdr:
            if 'Op:0x06' in hdr and 'Sub:0x01' in hdr:
                m = re.findall(r'Tọa độ \(X=(\d+), Y=(\d+)\)', e)
                if m:
                    actions.append(('MOVE', m[0]))
            elif 'Op:0x14' in hdr and 'Sub:0x01' in hdr:
                m = re.findall(r'Hex:\s*([0-9a-fA-F]+)', hdr)
                if m:
                    actions.append(('NPC_CLICK', m[0]))
            elif 'Op:0x20' in hdr and 'Sub:0x02' in hdr:
                m = re.findall(r'Lựa chọn số:\s*(\d+)', e)
                if m:
                    actions.append(('NPC_OPT', int(m[0])))
            elif 'Op:0x14' in hdr and 'Sub:0x06' in hdr:
                actions.append(('CHAT_NEXT', ''))
                
        # Combats
        if 'Op:0x0B' in hdr and ('Sub:0xFA' in hdr or 'Sub:0x02' in hdr) and 'S->C' in hdr:
            if not current_combat:
                current_combat = {'start': hdr, 'end': None}
                combats.append(current_combat)
        if current_combat and 'Op:0x0B' in hdr and 'Sub:0x00' in hdr and 'S->C' in hdr:
            if current_combat['end'] is None:
                current_combat['end'] = hdr
                current_combat = None
                
    print(f"Lobby Packets (C->S): {len(lobby_pkts)}")
    for lp in lobby_pkts[:8]:
        print("  ", lp)
    print(f"Team Packets (C->S): {len(team_pkts)}")
    for tp in team_pkts[:8]:
        print("  ", tp)
    print(f"Combats: {len(combats)}")
    print(f"Rewards: {len(rewards)}")
    for r in rewards[:6]:
        print("  ", r)

