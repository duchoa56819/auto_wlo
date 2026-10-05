#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compile Sky Tower 27 floors data
"""
import sys
import re
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

# Read summary to get battle boundaries
with open("tower_29_stages_summary.txt", "r", encoding="utf-8", errors="ignore") as f:
    s_lines = [l.strip() for l in f if l.strip()]

battles = []
for l in s_lines:
    m = re.search(r"\[W04\]\s+BẮT ĐẦU TRẬN ĐÁNH #(\d+)\s+\(Lúc\s+(\d{2}:\d{2}:\d{2})\)", l)
    if m:
        battles.append({"num": int(m.group(1)), "start": m.group(2), "dur": 0, "rounds": 0})
    m2 = re.search(r"\[W04\]\s+HOÀN THÀNH TRẬN #(\d+)\s+trong\s+([\d\.]+)s\s+\((\d+)\s+hiệp\)", l)
    if m2:
        num = int(m2.group(1))
        for b in battles:
            if b["num"] == num:
                b["dur"] = float(m2.group(2))
                b["rounds"] = int(m2.group(3))

with open("tower_29_extracted_events.txt", "r", encoding="utf-8", errors="ignore") as f:
    e_lines = [l.strip() for l in f if l.strip()]

def parse_t(t_str):
    parts = t_str.split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

for i, b in enumerate(battles):
    t_start = parse_t(b["start"])
    t_end = t_start + b["dur"]
    t_next = parse_t(battles[i+1]["start"]) if i+1 < len(battles) else t_end + 60
    
    b["actions"] = []
    b["rewards"] = []
    b["mobs_killed"] = []
    
    for l in e_lines:
        m_t = re.search(r"\[(\d{2}:\d{2}:\d{2}\.\d{3})\]", l)
        if not m_t:
            continue
        t = parse_t(m_t.group(1))
        if t_start - 2.0 <= t < t_next - 2.0:
            if "Op:0x32 Sub:0x01" in l and "C->S" in l:
                b["actions"].append(l)
            elif "NHẬN THƯỞNG VẬT PHẨM" in l and "[W04" in l:
                m_it = re.search(r"Item ID:\s+(\d+)\s+\(0x([0-9A-Fa-f]+)\),\s+SL:\s+(\d+)", l)
                if m_it:
                    b["rewards"].append({
                        "id": int(m_it.group(1)),
                        "hex": m_it.group(2),
                        "qty": int(m_it.group(3))
                    })
            elif "QUÁI TỬ TRẬN" in l and "[W04" in l:
                b["mobs_killed"].append(l)

print("Done matching", len(battles), "battles!")
for b in battles:
    num = b["num"]
    st = b["start"]
    dur = b["dur"]
    rnd = b["rounds"]
    acts = len(b["actions"])
    r_list = [f"0x{r['hex']} ({r['id']}) x{r['qty']}" for r in b["rewards"]]
    rews = ", ".join(r_list) if r_list else "Không có vật phẩm"
    print(f"Tầng {num:02d} ({st}, {dur:5.1f}s, {rnd:2d} hiệp) | Thao tác: {acts:2d} | Thưởng: {rews}")

with open("tower_29_compiled_stages.json", "w", encoding="utf-8") as f:
    json.dump(battles, f, ensure_ascii=False, indent=2)
