import sys
import re
import json

sys.stdout.reconfigure(encoding='utf-8')

log_path = r'G:\WLOI_beta\WLOI\party_instance_capture.log'

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

entries = text.split('\n[')

# Load all combats
import analyze_all_stages

# Ải 1-5: Dungeon 30039
# Ải 6-9: Dungeon 30025
# Ải 10-18: Dungeon 30021
# Ải 19-27: Dungeon 30013

combats = analyze_all_stages.combats

dungeon_definitions = {
    "30039": {
        "name": "Phụ bản 30039 (5 Ải)",
        "dungeon_id": 30039,
        "dungeon_hex": "5775",
        "stages": combats[0:5]
    },
    "30025": {
        "name": "Phụ bản 30025 (4 Ải)",
        "dungeon_id": 30025,
        "dungeon_hex": "4975",
        "stages": combats[5:9]
    },
    "30021": {
        "name": "Phụ bản 30021 (9 Ải)",
        "dungeon_id": 30021,
        "dungeon_hex": "4575",
        "stages": combats[9:18]
    },
    "30013": {
        "name": "Phụ bản 30013 (9 Ải - Boss Cuối)",
        "dungeon_id": 30013,
        "dungeon_hex": "3d75",
        "stages": combats[18:27]
    }
}

clean_definitions = {}

for did, ddata in dungeon_definitions.items():
    stage_list = []
    for s_idx, st in enumerate(ddata['stages']):
        stage_list.append({
            "stage_num": s_idx + 1,
            "moves": st['pre_moves'],
            "target_coord": st['pre_moves'][-1] if st['pre_moves'] else None,
            "clicks": st['pre_clicks'],
            "dialogues": st['pre_dialogues']
        })
    clean_definitions[did] = {
        "dungeon_id": ddata['dungeon_id'],
        "dungeon_hex": ddata['dungeon_hex'],
        "name": ddata['name'],
        "stages": stage_list
    }

with open('exact_dungeon_scripts.json', 'w', encoding='utf-8') as f:
    json.dump(clean_definitions, f, indent=2, ensure_ascii=False)

print("Saved exact_dungeon_scripts.json successfully!")
