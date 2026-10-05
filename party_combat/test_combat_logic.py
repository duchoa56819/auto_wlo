#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit test mô phỏng kiểm tra máy trạng thái với đúng pha vòng đời chiến đấu.
"""

import re
import struct
from datetime import datetime

class MockCombatController:
    def __init__(self):
        self.in_battle = False
        self.turn_count = 0
        self.battle_phase = "IDLE"  # IDLE, WAITING_COMMAND, COMMAND_SENT, ANIMATING
        self.entities_hp = {}
        self.entities_sp = {}
        self.events_log = []
        self.last_33_time = 0.0
        self.pending_turn_trigger = False

    def handle_packet(self, t_sec: float, dir_name: str, opcode: int, subcode: int, data: bytes):
        if opcode == 0x08:
            return

        # 1. Bắt đầu trận
        if dir_name == "recv" and opcode == 0x0B and subcode in (0xFA, 0x02):
            self.in_battle = True
            self.turn_count = 1
            self.battle_phase = "WAITING_COMMAND"
            self.entities_hp.clear()
            self.entities_sp.clear()
            self.pending_turn_trigger = False
            self.events_log.append(f"[{t_sec:.2f}s] BATTLE_START: Turn 1 initialized (Op 0x0B Sub 0x{subcode:02X})")

        # 2. Đồng bộ HP/SP
        elif dir_name == "recv" and opcode == 0x33 and subcode == 0x01:
            if len(data) >= 7:
                slot, row, stat_type = data[0], data[1], data[2]
                val = struct.unpack("<I", data[3:7])[0]
                if stat_type == 0x19:
                    self.entities_hp[(slot, row)] = val
                elif stat_type == 0x1A:
                    self.entities_sp[(slot, row)] = val

            # Chỉ kích hoạt chốt lượt khi đang ở giai đoạn ANIMATING (sau khi các đòn đánh đã diễn hoạt)
            if self.in_battle and self.battle_phase in ("ANIMATING",):
                self.pending_turn_trigger = True
                self.last_33_time = t_sec

        # 3. Animation Phase
        elif dir_name == "recv" and opcode == 0x32:
            if self.in_battle:
                self.battle_phase = "ANIMATING"

        # 4. Action Sent từ Client
        elif dir_name == "send" and opcode == 0x32 and subcode == 0x01:
            if self.in_battle:
                if len(data) >= 6:
                    a_slot, a_row = data[0], data[1]
                    skill = data[4:6].hex()
                    self.events_log.append(f"[{t_sec:.2f}s] [C->S] Actor(S{a_slot}R{a_row}) cast skill 0x{skill}")
                self.battle_phase = "COMMAND_SENT"

        # 5. Battle End
        elif dir_name == "recv" and opcode == 0x0B and subcode == 0x00:
            if self.in_battle:
                self.in_battle = False
                self.battle_phase = "IDLE"
                self.pending_turn_trigger = False
                self.events_log.append(f"[{t_sec:.2f}s] BATTLE_END: Battle ended! Total turns: {self.turn_count}")

    def check_debounce(self, current_time: float):
        if self.in_battle and self.pending_turn_trigger:
            if current_time - self.last_33_time >= 0.200:  # 200ms debounce
                self.pending_turn_trigger = False
                self.turn_count += 1
                self.battle_phase = "WAITING_COMMAND"
                self.events_log.append(f"[{current_time:.2f}s] >>> TURN_ADVANCE: Turn {self.turn_count} started (HP/SP resolved) <<<")

def parse_line(line):
    m = re.search(r'\[(\d{2}:\d{2}:\d{2}\.\d{3})\]', line)
    if not m:
        return None
    try:
        t_str = m.group(1)
        dt = datetime.strptime(t_str, "%H:%M:%S.%f")
        t_sec = dt.hour * 3600 + dt.minute * 60 + dt.second + dt.microsecond / 1e6
        dir_name = "recv" if "S->C" in line else ("send" if "C->S" in line else None)
        if not dir_name:
            return None
        op_part = line.split("Op:")[1].split()[0]
        opcode = int(op_part, 16)
        sub_part = line.split("Sub:")[1].split()[0]
        subcode = int(sub_part, 16)
        hex_idx = line.find("Hex: ")
        data = bytes.fromhex(line[hex_idx+5:].split("|")[0].strip()) if hex_idx != -1 else b""
        return t_sec, dir_name, opcode, subcode, data
    except Exception:
        return None

def test_battle(file_path):
    print(f"\n=======================================================")
    print(f"=== Testing: {file_path} ===")
    print(f"=======================================================")
    mock = MockCombatController()
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    last_t = 0.0
    for line in lines:
        parsed = parse_line(line)
        if parsed:
            t_sec, dir_name, opcode, subcode, data = parsed
            last_t = t_sec
            mock.check_debounce(t_sec)
            mock.handle_packet(t_sec, dir_name, opcode, subcode, data)

    mock.check_debounce(last_t + 1.0)

    print("Events Summary:")
    for ev in mock.events_log:
        print(f"  * {ev}")
    print(f"\nFinal Monster HP: Pos 1(1,1)={mock.entities_hp.get((1,1))}, Pos 2(2,2)={mock.entities_hp.get((2,2))}")
    print(f"Final Ally HP: Char(4,2)={mock.entities_hp.get((4,2))}, Niss(3,2)={mock.entities_hp.get((3,2))}")
    return mock

if __name__ == "__main__":
    test_battle("battle_1_detailed.txt")
    test_battle("battle_2_detailed.txt")
    test_battle("battle_3_detailed.txt")
