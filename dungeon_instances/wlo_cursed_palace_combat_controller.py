#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO Cursed Palace Combat Controller
===================================
Bộ điều khiển logic chiến đấu tự động cho chuỗi Ải Cursed Palace (Ải 2 đến Ải 13).
Tuân thủ tuyệt đối quy tắc:
1. Từ Ải 2 đến 13: Wi01 và Pet luôn phòng thủ (75ea).
2. Từ Ải 2 đến 10: W03 và Pet, W04 và Pet luôn phòng thủ (75ea).
3. Ải 11, 12, 13: Quét kẻ địch chưa bị tiêu diệt, dùng chiêu d861 (Char W04/W03) & a33a (Pet W04/W03).
4. Từ Ải 2 đến 13 (F04 & Pet):
   - Lượt 1:
     * Char F04: Chiêu Hỏa 1f3b lên Hàng 2 (ưu tiên Pos 2, rồi Pos 6).
     * Pet F04: Chiêu 043b lên Hàng 3 (ưu tiên Pos 3, rồi Pos 7).
   - Những lượt sau:
     * Quét kẻ địch chưa bị tiêu diệt, ưu tiên Hàng 2 (Pos 2, 6) và Hàng 3 (Pos 3, 7).
"""

import sys
import struct
from typing import Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

# Bảng ánh xạ 8 vị trí kẻ địch sang (Slot, Row)
# Slot 1: Hàng trước (Front), Slot 2: Hàng sau (Back)
ENEMY_GRID = {
    1: {"slot": 1, "row": 1, "name": "Hàng 1 Trước (Pos 1)"},
    2: {"slot": 1, "row": 2, "name": "Hàng 2 Trước (Pos 2)"},
    3: {"slot": 1, "row": 3, "name": "Hàng 3 Trước (Pos 3)"},
    4: {"slot": 1, "row": 4, "name": "Hàng 4 Trước (Pos 4)"},
    5: {"slot": 2, "row": 1, "name": "Hàng 1 Sau (Pos 5)"},
    6: {"slot": 2, "row": 2, "name": "Hàng 2 Sau (Pos 6)"},
    7: {"slot": 2, "row": 3, "name": "Hàng 3 Sau (Pos 7)"},
    8: {"slot": 2, "row": 4, "name": "Hàng 4 Sau (Pos 8)"},
}

# Vị trí hàng của các tài khoản phe ta
CHAR_POSITIONS = {
    "Wi01": {"row": 1, "char_slot": 3, "pet_slot": 4},
    "F04":  {"row": 2, "char_slot": 3, "pet_slot": 4},
    "W03":  {"row": 3, "char_slot": 3, "pet_slot": 4},
    "W04":  {"row": 4, "char_slot": 3, "pet_slot": 4},
}

# Mã chiêu thức theo quy định
SKILLS = {
    "DEFEND": bytes.fromhex("75ea0000"),       # Mã phòng thủ (Target chính mình)
    "F04_CHAR": bytes.fromhex("1f3b0000"),     # Chiêu Hỏa của Char F04
    "F04_PET":  bytes.fromhex("043b0000"),     # Chiêu sát thương của Pet F04
    "WATER_CHAR": bytes.fromhex("d8610000"),   # Chiêu sát thương của Char W04 & W03
    "WATER_PET":  bytes.fromhex("a33a0000"),   # Chiêu sát thương của Pet W04 & W03
}

class CursedPalaceCombatController:
    """Bộ điều khiển chiến đấu tự động theo quy tắc Cursed Palace"""

    def __init__(self):
        pass

    def get_action(
        self,
        nick: str,
        actor_type: str,  # "Char" hoặc "Pet"
        stage: int,
        turn: int,
        alive_enemy_positions: List[int]
    ) -> Tuple[int, int, bytes, str]:
        """
        Xác định mục tiêu và chiêu thức cho một đối tượng hành động.
        Trả về: (target_slot, target_row, skill_bytes, description)
        """
        my_info = CHAR_POSITIONS.get(nick)
        if not my_info:
            raise ValueError(f"Không tìm thấy thông tin cho tài khoản {nick}")

        my_row = my_info["row"]
        my_slot = my_info["char_slot"] if actor_type == "Char" else my_info["pet_slot"]

        # -------------------------------------------------------------
        # 1. QUY TẮC CHO Wi01 (HÀNG 1) & PET
        # Từ Ải 2 đến 13: Luôn phòng thủ (75ea) mọi lượt
        # -------------------------------------------------------------
        if nick == "Wi01" and stage >= 2:
            return (my_slot, my_row, SKILLS["DEFEND"], "Phòng thủ (Wi01 Full Thủ)")

        # -------------------------------------------------------------
        # 2. QUY TẮC CHO W03 & W04 (Ải 2 đến 10)
        # Luôn phòng thủ (75ea) mọi lượt
        # -------------------------------------------------------------
        if nick in ["W03", "W04"] and 2 <= stage <= 10:
            return (my_slot, my_row, SKILLS["DEFEND"], f"Phòng thủ ({nick} Full Thủ Ải 2-10)")

        # -------------------------------------------------------------
        # 3. QUY TẮC CHO W03 & W04 (Ải 11, 12, 13)
        # Tấn công kẻ địch chưa bị tiêu diệt
        # Char dùng d861, Pet dùng a33a
        # -------------------------------------------------------------
        if nick in ["W03", "W04"] and stage in [11, 12, 13]:
            target_pos = self._select_alive_target(alive_enemy_positions)
            if target_pos is not None:
                tgt_info = ENEMY_GRID[target_pos]
                skill = SKILLS["WATER_CHAR"] if actor_type == "Char" else SKILLS["WATER_PET"]
                skill_name = "d861 (Char)" if actor_type == "Char" else "a33a (Pet)"
                desc = f"Tấn công quái sống {tgt_info['name']} [Pos {target_pos}] bằng {skill_name}"
                return (tgt_info["slot"], tgt_info["row"], skill, desc)
            else:
                # Nếu hết quái còn sống -> Phòng thủ
                return (my_slot, my_row, SKILLS["DEFEND"], "Hết quái -> Phòng thủ")

        # -------------------------------------------------------------
        # 4. QUY TẮC CHO F04 (HÀNG 2) & PET (Ải 2 đến 13)
        # -------------------------------------------------------------
        if nick == "F04" and stage >= 2:
            if turn == 1:
                # LƯỢT 1:
                # - Char F04: Chiêu Hỏa 1f3b lên Hàng 2 (Pos 2 hoặc 6)
                if actor_type == "Char":
                    target_pos = self._pick_row2_target(alive_enemy_positions)
                    tgt_info = ENEMY_GRID[target_pos]
                    desc = f"Lượt 1: Chiêu Hỏa 1f3b -> Hàng 2 ({tgt_info['name']} [Pos {target_pos}])"
                    return (tgt_info["slot"], tgt_info["row"], SKILLS["F04_CHAR"], desc)
                # - Pet F04: Chiêu 043b lên Hàng 3 (Pos 3 hoặc 7)
                else:
                    target_pos = self._pick_row3_target(alive_enemy_positions)
                    tgt_info = ENEMY_GRID[target_pos]
                    desc = f"Lượt 1: Chiêu Pet 043b -> Hàng 3 ({tgt_info['name']} [Pos {target_pos}])"
                    return (tgt_info["slot"], tgt_info["row"], SKILLS["F04_PET"], desc)
            else:
                # NHỮNG LƯỢT SAU (Lượt 2 trở đi):
                # Quét quái sống, ưu tiên Hàng 2 (Pos 2, 6) và Hàng 3 (Pos 3, 7)
                target_pos = self._select_alive_target(alive_enemy_positions)
                if target_pos is not None:
                    tgt_info = ENEMY_GRID[target_pos]
                    skill = SKILLS["F04_CHAR"] if actor_type == "Char" else SKILLS["F04_PET"]
                    skill_name = "1f3b (Char)" if actor_type == "Char" else "043b (Pet)"
                    desc = f"Lượt {turn}: Ưu tiên quái sống {tgt_info['name']} [Pos {target_pos}] bằng {skill_name}"
                    return (tgt_info["slot"], tgt_info["row"], skill, desc)
                else:
                    return (my_slot, my_row, SKILLS["DEFEND"], "Hết quái -> Phòng thủ")

        # Mặc định phòng thủ
        return (my_slot, my_row, SKILLS["DEFEND"], "Mặc định phòng thủ")

    def _pick_row2_target(self, alive_positions: List[int]) -> int:
        """Chọn mục tiêu ở Hàng 2: ưu tiên Pos 2, sau đó Pos 6"""
        if 2 in alive_positions:
            return 2
        if 6 in alive_positions:
            return 6
        # Fallback nếu hàng 2 đã sạch quái -> chọn quái sống khác
        return self._select_alive_target(alive_positions) or 2

    def _pick_row3_target(self, alive_positions: List[int]) -> int:
        """Chọn mục tiêu ở Hàng 3: ưu tiên Pos 3, sau đó Pos 7"""
        if 3 in alive_positions:
            return 3
        if 7 in alive_positions:
            return 7
        # Fallback nếu hàng 3 đã sạch quái -> chọn quái sống khác
        return self._select_alive_target(alive_positions) or 3

    def _select_alive_target(self, alive_positions: List[int]) -> Optional[int]:
        """
        Thứ tự ưu tiên quét quái sống:
        1. Hàng 2: Pos 2, Pos 6
        2. Hàng 3: Pos 3, Pos 7
        3. Hàng 1: Pos 1, Pos 5
        4. Hàng 4: Pos 4, Pos 8
        """
        priority_order = [2, 6, 3, 7, 1, 5, 4, 8]
        for pos in priority_order:
            if pos in alive_positions:
                return pos
        return alive_positions[0] if alive_positions else None

    def build_combat_packet(
        self,
        nick: str,
        actor_type: str,
        stage: int,
        turn: int,
        alive_enemy_positions: List[int]
    ) -> Tuple[bytes, str]:
        """
        Xây dựng gói tin Op: 0x32 Sub: 0x01 hoàn chỉnh gửi lên Server.
        Định dạng 9 bytes: [ActorSlot, ActorRow, TargetSlot, TargetRow, Skill4B, 0x00]
        """
        my_info = CHAR_POSITIONS[nick]
        actor_row = my_info["row"]
        actor_slot = my_info["char_slot"] if actor_type == "Char" else my_info["pet_slot"]

        target_slot, target_row, skill_bytes, desc = self.get_action(
            nick, actor_type, stage, turn, alive_enemy_positions
        )

        packet_data = struct.pack(
            "<BBBB4sB",
            actor_slot,
            actor_row,
            target_slot,
            target_row,
            skill_bytes,
            0x00
        )

        log_str = f"[{nick:<4}] {actor_type:<4} -> Mục tiêu: Slot {target_slot} Row {target_row} | {desc} | Hex: {packet_data.hex()}"
        return packet_data, log_str


# =========================================================================
# TEST / MINH HỌA HOẠT ĐỘNG
# =========================================================================
if __name__ == "__main__":
    controller = CursedPalaceCombatController()
    print("=" * 80)
    print("KIỂM THỬ BỘ ĐIỀU KHIỂN CHIẾN ĐẤU CURSED PALACE")
    print("=" * 80)

    # Ví dụ 1: Ải 05 - Lượt 1 (Quái xuất hiện ở các vị trí: 1, 2, 3, 6, 7)
    stage = 5
    turn = 1
    alive = [1, 2, 3, 6, 7]
    print(f"\n--- [ẢI {stage:02d} - LƯỢT {turn}] Kẻ địch còn sống: Pos {alive} ---")
    for nick in ["Wi01", "W03", "W04", "F04"]:
        for actor in ["Char", "Pet"]:
            _, msg = controller.build_combat_packet(nick, actor, stage, turn, alive)
            print(" ", msg)

    # Ví dụ 2: Ải 05 - Lượt 2 (Pos 2 và Pos 3 đã bị F04 tiêu diệt, còn lại Pos 1, 6, 7)
    turn = 2
    alive = [1, 6, 7]
    print(f"\n--- [ẢI {stage:02d} - LƯỢT {turn}] Kẻ địch còn sống: Pos {alive} (Pos 2 và 3 đã chết) ---")
    for nick in ["Wi01", "W03", "W04", "F04"]:
        for actor in ["Char", "Pet"]:
            _, msg = controller.build_combat_packet(nick, actor, stage, turn, alive)
            print(" ", msg)

    # Ví dụ 3: Ải 12 - Lượt 1 (Ải khó: Cả team phối hợp tấn công quái sống)
    stage = 12
    turn = 1
    alive = [1, 2, 3, 5, 6, 7]
    print(f"\n--- [ẢI {stage:02d} - LƯỢT {turn}] Kẻ địch còn sống: Pos {alive} (Ải 12: W03 & W04 cùng đánh) ---")
    for nick in ["Wi01", "W03", "W04", "F04"]:
        for actor in ["Char", "Pet"]:
            _, msg = controller.build_combat_packet(nick, actor, stage, turn, alive)
            print(" ", msg)
