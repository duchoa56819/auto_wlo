import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

log_path = r'G:\WLOI_beta\WLOI\party_instance_capture.log'

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

entries = text.split('\n[')

def inspect_window(name, t_start, t_end):
    print(f"\n========================================================")
    print(f"=== {name} ({t_start} -> {t_end}) ===")
    print(f"========================================================")
    for e in entries:
        hdr = e.strip().split('\n')[0]
        # check timestamp
        for t in t_range:
            if t in hdr:
                lines = e.strip().split('\n')
                # filter out non-essential S->C pings
                if 'Op:0x08' in hdr:
                    continue
                if 'S->C' in hdr and ('TRADE_STALL' in hdr or 'FRIEND_MAIL' in hdr or 'LOGIN_AUTH' in hdr):
                    continue
                print(lines[0])
                for l in lines[1:]:
                    print('   ', l)
                break

# Transition 1: After Combat 5 (16:59:23) to Combat 6 (17:01:15)
t_range = [f"16:59:{s:02d}" for s in range(23, 60)] + [f"17:00:{s:02d}" for s in range(60)] + [f"17:01:{s:02d}" for s in range(16)]
inspect_window("TRANSITION 1 (AFTER COMBAT 5 -> COMBAT 6)", "16:59:23", "17:01:15")

# Transition 2: After Combat 9 (17:03:54) to Combat 10 (17:06:58)
t_range = [f"17:03:{s:02d}" for s in range(54, 60)] + [f"17:04:{s:02d}" for s in range(60)] + [f"17:05:{s:02d}" for s in range(60)] + [f"17:06:{s:02d}" for s in range(59)]
inspect_window("TRANSITION 2 (AFTER COMBAT 9 -> COMBAT 10)", "17:03:54", "17:06:58")

# Transition 3: After Combat 18 (17:10:26) to Combat 19 (17:13:57)
t_range = [f"17:10:{s:02d}" for s in range(26, 60)] + [f"17:11:{s:02d}" for s in range(60)] + [f"17:12:{s:02d}" for s in range(60)] + [f"17:13:{s:02d}" for s in range(58)]
inspect_window("TRANSITION 3 (AFTER COMBAT 18 -> COMBAT 19)", "17:10:26", "17:13:57")

# Transition 4: After Combat 27 (17:17:10) to End
t_range = [f"17:17:{s:02d}" for s in range(10, 30)]
inspect_window("TRANSITION 4 (AFTER COMBAT 27 -> END)", "17:17:10", "17:17:30")

