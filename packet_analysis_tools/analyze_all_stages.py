import sys
import re
import struct

sys.stdout.reconfigure(encoding='utf-8')

log_path = r'G:\WLOI_beta\WLOI\party_instance_capture.log'

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

entries = text.split('\n[')

# Parse entries into structured objects
parsed_entries = []
for idx, e in enumerate(entries):
    lines = e.strip().split('\n')
    hdr = lines[0]
    # Header format: [time] [+ elapsed] [#pkt] [client] dir Op:...
    m = re.search(r'\[?([\d:\.]+)[\]\s]+\[\+\s*([\d\.]+)s\]\s*\[#(\d+)\s*\]\s*\[(\w+)\]\s*(C->S|S->C)\s*Op:0x([0-9A-Fa-f]{2})\s*\((.*?)\)\s*Sub:(0x[0-9A-Fa-f]{2}|--)\s*Len:(\d+)\s*\|\s*Hex:\s*([0-9A-Fa-f]*)', hdr)
    if m:
        t_str, elapsed, pkt_no, client, direction, op_hex, op_name, sub_hex, length, hex_data = m.groups()
        details = "\n".join(lines[1:])
        parsed_entries.append({
            'index': idx,
            'time': t_str,
            'elapsed': float(elapsed),
            'pkt_no': int(pkt_no),
            'client': client,
            'dir': direction,
            'op': int(op_hex, 16),
            'op_name': op_name.strip(),
            'sub': int(sub_hex, 16) if sub_hex != '--' else None,
            'sub_hex': sub_hex,
            'len': int(length),
            'hex': hex_data,
            'details': details,
            'raw': e.strip()
        })

print(f"Total parsed packets: {len(parsed_entries)}")

# Group by Combats
combats = []
current = None

for p in parsed_entries:
    # Combat start
    if p['op'] == 0x0B and p['sub'] in (0xFA, 0x02) and p['dir'] == 'S->C':
        if not current:
            current = {
                'start_time': p['time'],
                'start_elapsed': p['elapsed'],
                'start_pkt': p['pkt_no'],
                'start_entry': p['index'],
                'end_time': None,
                'end_elapsed': None,
                'end_pkt': None,
                'end_entry': None,
                'client': p['client'],
                'actions': [],
                'pre_events': []
            }
            combats.append(current)
            
    # Combat action
    if current and p['op'] == 0x32 and p['sub'] == 0x01 and p['dir'] == 'C->S':
        current['actions'].append(p)
        
    # Combat end
    if current and p['op'] == 0x0B and p['sub'] == 0x00 and p['dir'] == 'S->C':
        if current['end_time'] is None:
            current['end_time'] = p['time']
            current['end_elapsed'] = p['elapsed']
            current['end_pkt'] = p['pkt_no']
            current['end_entry'] = p['index']
            
    if current and current['end_elapsed'] is not None:
        if p['elapsed'] - current['end_elapsed'] > 2.0:
            current = None

print(f"Total combats: {len(combats)}")

# Now for each combat, analyze what happened immediately prior to it:
# (Movements, NPC clicks, NPC dialogue options)
for i, c in enumerate(combats):
    start_idx = c['start_entry']
    # Look back up to 200 packets before start_entry (or after previous combat end)
    prev_end_idx = combats[i-1]['end_entry'] if i > 0 else 0
    lookback_start = max(prev_end_idx if prev_end_idx else 0, start_idx - 150)
    
    pre_moves = []
    pre_dialogues = []
    pre_clicks = []
    pre_warps = []
    
    for p in parsed_entries[lookback_start:start_idx]:
        if p['client'] == 'F02': # Leader
            if p['op'] == 0x06 and p['sub'] == 0x01 and p['dir'] == 'C->S':
                # Move
                if len(p['hex']) >= 10:
                    x = int.from_bytes(bytes.fromhex(p['hex'][2:6]), 'little')
                    y = int.from_bytes(bytes.fromhex(p['hex'][6:10]), 'little')
                    pre_moves.append((x, y))
            elif p['op'] == 0x20 and p['dir'] == 'C->S':
                pre_dialogues.append(f"Sub: {p['sub_hex']}, Hex: {p['hex']}")
            elif p['op'] == 0x14 and p['dir'] == 'C->S':
                pre_dialogues.append(f"Chat/Dialog C->S: Sub: {p['sub_hex']}, Hex: {p['hex']}")
            elif p['op'] == 0x06 and p['sub'] == 0x02 and p['dir'] == 'C->S':
                pre_clicks.append(f"Click entity Hex: {p['hex']}")
        if p['op'] == 0x35 or (p['op'] == 0x16 and p['sub'] == 0x04):
            pre_warps.append(f"Warp/Map: Op:0x{p['op']:02X} Sub:{p['sub_hex']} Hex:{p['hex'][:16]}")
            
    c['pre_moves'] = pre_moves
    c['pre_dialogues'] = pre_dialogues
    c['pre_clicks'] = pre_clicks
    c['pre_warps'] = pre_warps

# Print structured breakdown
with open('all_combats_breakdown.txt', 'w', encoding='utf-8') as f:
    for idx, c in enumerate(combats):
        dur = (c['end_elapsed'] - c['start_elapsed']) if c['end_elapsed'] else 0
        f.write(f"================================================================================\n")
        f.write(f"ẢI / TRẬN ĐÁNH #{idx+1:02d}\n")
        f.write(f"Thời gian: {c['start_time']} -> {c['end_time']} (Kéo dài: {dur:.1f}s)\n")
        f.write(f"Trước trận đánh:\n")
        if c['pre_warps']:
            f.write(f"  • Warps/Maps: {c['pre_warps']}\n")
        if c['pre_moves']:
            f.write(f"  • Leader di chuyển ({len(c['pre_moves'])} bước): {c['pre_moves'][-5:]}\n")
        if c['pre_clicks']:
            f.write(f"  • Leader clicks: {c['pre_clicks']}\n")
        if c['pre_dialogues']:
            f.write(f"  • Leader đối thoại/chọn option: {c['pre_dialogues']}\n")
            
        # Group actions by round
        f.write(f"Chiến đấu ({len(c['actions'])} lượt ra chiêu):\n")
        uniq_act = []
        for a in c['actions']:
            act_str = f"[{a['client']}] Hex: {a['hex']}"
            if a['details']:
                # extract ra don line
                for line in a['details'].split('\n'):
                    if 'RA ĐÒN' in line:
                        act_str = line.strip()
            uniq_act.append(act_str)
        # Deduplicate sequential identical actions
        for act in uniq_act:
            f.write(f"  {act}\n")
        f.write("\n")

print("Saved all_combats_breakdown.txt")
