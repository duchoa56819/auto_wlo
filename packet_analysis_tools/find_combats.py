import sys
import re
import struct

sys.stdout.reconfigure(encoding='utf-8')

log_path = r'G:\WLOI_beta\WLOI\party_instance_capture.log'

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

entries = text.split('\n[')

print(f"=== ALL COMBAT ENCOUNTERS ===")
combats = []
current_combat = None

for i, e in enumerate(entries):
    lines = e.strip().split('\n')
    hdr = lines[0]
    
    # Check combat start
    if 'Op:0x0B' in hdr and ('Sub:0xFA' in hdr or 'Sub:0x02' in hdr):
        # find client and timestamp
        m = re.search(r'\[?([\d:\.]+)[\]\s]+\[\+\s*([\d\.]+)s\]\s*\[#(\d+)\s*\]\s*\[(\w+)\]', hdr)
        if m:
            t_str, elapsed, pkt_no, client = m.groups()
            if not current_combat:
                current_combat = {
                    'start_time': t_str,
                    'start_elapsed': float(elapsed),
                    'start_pkt': pkt_no,
                    'client': client,
                    'rounds': 0,
                    'actions': [],
                    'end_time': None,
                    'end_elapsed': None,
                    'entry_index': i
                }
                combats.append(current_combat)
    
    # Check combat round
    if current_combat and 'Op:0x0B' in hdr and 'Sub:0x01' in hdr:
        current_combat['rounds'] += 1

    # Check combat action (skills)
    if current_combat and 'Op:0x32' in hdr and 'Sub:0x01' in hdr and 'C->S' in hdr:
        for l in lines:
            if 'RA ĐÒN' in l:
                current_combat['actions'].append(l.strip())

    # Check combat end
    if current_combat and 'Op:0x0B' in hdr and 'Sub:0x00' in hdr:
        m = re.search(r'\[?([\d:\.]+)[\]\s]+\[\+\s*([\d\.]+)s\]', hdr)
        if m and current_combat['end_time'] is None:
            current_combat['end_time'] = m.group(1)
            current_combat['end_elapsed'] = float(m.group(2))
            
    # If we have end_time and elapsed time moved ahead by > 2s, close current_combat
    if current_combat and current_combat['end_elapsed'] is not None:
        m = re.search(r'\[\+\s*([\d\.]+)s\]', hdr)
        if m:
            now_e = float(m.group(1))
            if now_e - current_combat['end_elapsed'] > 2.0:
                current_combat = None

print(f"Total combat encounters detected: {len(combats)}")
for idx, c in enumerate(combats):
    dur = (c['end_elapsed'] - c['start_elapsed']) if c['end_elapsed'] else 0
    print(f"\n--- TRẬN ĐÁNH #{idx+1} ---")
    print(f"Bắt đầu: {c['start_time']} (+{c['start_elapsed']:.1f}s) | Kết thúc: {c['end_time']} (+{c['end_elapsed']:.1f}s) | Thời gian: {dur:.1f}s")
    print(f"Số gói hiệp/round: {c['rounds']} | Số lượt ra đòn ghi nhận: {len(c['actions'])}")
    # Deduplicate actions
    uniq_actions = list(dict.fromkeys(c['actions']))
    for act in uniq_actions[:15]:
        print(f"   {act}")
    if len(uniq_actions) > 15:
        print(f"   ... ({len(uniq_actions)-15} actions more)")
