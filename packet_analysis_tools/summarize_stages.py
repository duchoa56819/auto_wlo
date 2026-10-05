import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

with open('all_combats_breakdown.txt', 'r', encoding='utf-8') as f:
    text = f.read()

sections = text.split('================================================================================\n')
print(f"Total sections: {len(sections)-1}")

stages = []
for s in sections[1:]:
    lines = [l.strip() for l in s.split('\n') if l.strip()]
    if not lines:
        continue
    # Title
    title = lines[0] # ẢI / TRẬN ĐÁNH #XX
    time_line = lines[1]
    
    # Extract end coordinate of leader move
    coords = None
    npc_click = None
    options = []
    
    for l in lines:
        if 'Leader di chuyển' in l:
            # find last coord
            m = re.findall(r'\((\d+),\s*(\d+)\)', l)
            if m:
                coords = m[-1]
        if 'Leader đối thoại/chọn option:' in l:
            options = l.replace('• Leader đối thoại/chọn option:', '').strip()
        if 'Leader clicks:' in l:
            npc_click = l.replace('• Leader clicks:', '').strip()
            
    # Skill used
    skills = [l for l in lines if 'RA ĐÒN' in l]
    
    stages.append({
        'title': title,
        'time': time_line,
        'coords': coords,
        'npc_click': npc_click,
        'options': options,
        'skills_count': len(skills)
    })

print(f"{'ẢI':<10} | {'TỌA ĐỘ (X, Y)':<18} | {'CLICKS / MENU':<45} | {'SỐ RA ĐÒN'}")
print("-" * 90)
for st in stages:
    c_str = f"({st['coords'][0]}, {st['coords'][1]})" if st['coords'] else "Tại chỗ"
    opt_str = (st['options'][:42] + '...') if len(st['options']) > 45 else st['options']
    print(f"{st['title']:<10} | {c_str:<18} | {opt_str:<45} | {st['skills_count']}")

