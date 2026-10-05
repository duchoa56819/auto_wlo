import sys
import json
import re

sys.stdout.reconfigure(encoding='utf-8')

log_path = r'G:\WLOI_beta\WLOI\party_instance_capture.log'

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

entries = text.split('\n[')

# Load stages
import analyze_all_stages
combats = analyze_all_stages.combats

def get_stage_packets(start_entry, end_entry):
    pkts = []
    for e in entries[start_entry:end_entry]:
        lines = e.strip().split('\n')
        hdr = lines[0]
        if '[F02] C->S' in hdr:
            m = re.search(r'Op:0x([0-9A-Fa-f]{2}).*?Sub:(0x[0-9A-Fa-f]{2}|--).*?Hex:\s*([0-9a-fA-F]*)', hdr)
            if m:
                op, sub, hex_data = m.groups()
                pkts.append({
                    'client': 'F02',
                    'op': op,
                    'sub': sub if sub != '--' else '',
                    'hex': hex_data
                })
    return pkts

dungeons = [
    ("30039", 0, 5, 0, 4000),
    ("30025", 5, 9, 4000, 7260),
    ("30021", 9, 18, 7260, 11550),
    ("30013", 18, 27, 11550, len(entries))
]

full_dungeons = {}

for did, c_start, c_end, e_start, e_end in dungeons:
    stages_data = []
    for s_idx in range(c_start, c_end):
        c = combats[s_idx]
        prev_c_end = combats[s_idx-1]['end_entry'] if s_idx > c_start else e_start
        s_pkts = get_stage_packets(prev_c_end, c['start_entry'])
        stages_data.append({
            'stage': s_idx - c_start + 1,
            'combat_idx': s_idx + 1,
            'start_time': c['start_time'],
            'end_time': c['end_time'],
            'packets': s_pkts
        })
    full_dungeons[did] = stages_data

# Save to full_stage_packets.json
with open('full_stage_packets.json', 'w', encoding='utf-8') as f:
    json.dump(full_dungeons, f, indent=2)

print("Saved full_stage_packets.json successfully!")
for did in full_dungeons:
    print(f"Dungeon {did}: {len(full_dungeons[did])} stages")
    for st in full_dungeons[did]:
        print(f"  Stage {st['stage']}: {len(st['packets'])} leader packets")
