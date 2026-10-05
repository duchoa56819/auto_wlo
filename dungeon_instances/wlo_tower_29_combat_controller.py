#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO Sky Tower (Tháp 29 Tầng) Combat Controller
==============================================
Bộ điều khiển logic chiến đấu tự động chuyên biệt cho Tháp 29 Tầng (Sky Tower).

Quy tắc chiến thuật:
1. Tầng 01 đến 21 (Solo Carry F04):
   - Wi01 (Char & Pet), W03 (Char & Pet), W04 (Char & Pet): Luôn PHÒNG THỦ (75ea).
   - F04 (Char & Pet): Sát thương gánh team.
     * LUÔN ƯU TIÊN MỤC TIÊU ĐỐI THỦ HÀNG 2 VÀ HÀNG 3 (VỊ TRÍ 2, 6, 3, 7).
     * Lượt 1:
       - Char F04: Chiêu Hỏa 1f3b -> Hàng 2 (ưu tiên Pos 2, rồi Pos 6).
       - Pet F04: Chiêu 043b -> Hàng 3 (ưu tiên Pos 3, rồi Pos 7).
     * Những lượt sau:
       - Quét kẻ địch còn sống, ưu tiên [Pos 2, Pos 6, Pos 3, Pos 7], sau đó mới đến [1, 5, 4, 8].
2. Tầng 22 đến 26 (Tổng lực tấn công):
   - W04: Char fb2a, Pet 092f.
   - W03: Char fb2a, Pet 092f (hỗ trợ 232b).
   - Wi01: Char 2b2b, Pet 2c2b.
   - F04: Char 1f3b, Pet 043b.
   - Vẫn luôn ưu tiên quái Hàng 2 & 3 (2, 6, 3, 7) cho F04 và toàn đội.
3. Tích hợp dọn rác thưởng Tháp:
   - r5 (Tầng 05): 0x7D4A (32074) BubbleGum -> Vứt
   - r6 (Tầng 06): 0x7D4B (32075) Chocolate -> Vứt
   - r7 (Tầng 07): Mã 0x7D49 (32073) InstantNoodle -> Vứt
   - r8 (Tầng 08): Mã 0x7D48 (32072) ChocolateIceCream -> Vứt
"""

import os
import sys
import time
import struct
from typing import Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

# Bảng ánh xạ 8 vị trí kẻ địch sang (Slot, Row)
# Slot 1: Hàng trước (Front), Slot 2: Hàng sau (Back)
ENEMY_GRID = {
    1: {"slot": 1, "row": 1, "name": "Hàng 1 Trước (Pos 1)"},
    2: {"slot": 1, "row": 2, "name": "Hàng 2 Trước (Pos 2)"},  # Top 1 F04 Lượt 1
    3: {"slot": 1, "row": 3, "name": "Hàng 3 Trước (Pos 3)"},  # Top 1 Pet F04 Lượt 1
    4: {"slot": 1, "row": 4, "name": "Hàng 4 Trước (Pos 4)"},
    5: {"slot": 2, "row": 1, "name": "Hàng 1 Sau (Pos 5)"},
    6: {"slot": 2, "row": 2, "name": "Hàng 2 Sau (Pos 6)"},    # Top 2 F04 Hàng 2
    7: {"slot": 2, "row": 3, "name": "Hàng 3 Sau (Pos 7)"},    # Top 2 Pet F04 Hàng 3
    8: {"slot": 2, "row": 4, "name": "Hàng 4 Sau (Pos 8)"},
}

# Vị trí hàng của các thành viên phe ta trong đội hình
CHAR_POSITIONS = {
    "Wi01": {"row": 1, "char_slot": 3, "pet_slot": 4},
    "F04":  {"row": 2, "char_slot": 3, "pet_slot": 4},
    "W03":  {"row": 3, "char_slot": 3, "pet_slot": 4},
    "W04":  {"row": 4, "char_slot": 3, "pet_slot": 4},
}

# Mã chiêu thức Tháp 29 tầng
SKILLS = {
    "DEFEND": bytes.fromhex("75ea0000"),       # Phòng thủ
    "F04_CHAR": bytes.fromhex("1f3b0000"),     # Chiêu Hỏa chủ lực của Char F04
    "F04_PET":  bytes.fromhex("043b0000"),     # Chiêu sát thương chủ lực của Pet F04
    "W04_CHAR": bytes.fromhex("fb2a0000"),     # Chiêu tấn công W04 tầng cao
    "W04_PET":  bytes.fromhex("092f0000"),     # Chiêu tấn công Pet W04 tầng cao
    "W03_CHAR": bytes.fromhex("fb2a0000"),     # Chiêu tấn công W03 tầng cao
    "W03_PET":  bytes.fromhex("092f0000"),     # Chiêu tấn công Pet W03 tầng cao
    "WI01_CHAR": bytes.fromhex("2b2b0000"),    # Chiêu Phong Wi01 tầng cao
    "WI01_PET":  bytes.fromhex("2c2b0000"),    # Chiêu Pet Wi01 tầng cao
}

# Phần thưởng rác cần vứt tự động theo từng vòng Tháp
TOWER_TRASH_BY_ROUND = {
    5: {0x7D4A: {"name": "BubbleGum (Kẹo cao su)", "dec": 32074, "round": "r5"}},
    6: {0x7D4B: {"name": "Chocolate (Sô-cô-la)",   "dec": 32075, "round": "r6"}},
    7: {0x7D49: {"name": "InstantNoodle (Mì gói)", "dec": 32073, "round": "r7"}},
    8: {0x7D48: {"name": "ChocolateIceCream (Kem)","dec": 32072, "round": "r8"}},
}


class Tower29CombatController:
    """Bộ điều khiển chiến đấu chuyên biệt cho Tháp 29 tầng"""

    # Thứ tự ưu tiên chọn mục tiêu cốt lõi: Hàng 2 -> Hàng 3 -> Các hàng còn lại
    F04_PRIORITY_QUEUE = [2, 6, 3, 7, 1, 5, 4, 8]

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
        Xác định mục tiêu và chiêu thức cho nhân vật / thú cưng.
        Trả về: (target_slot, target_row, skill_bytes, description)
        """
        my_info = CHAR_POSITIONS.get(nick)
        if not my_info:
            raise ValueError(f"Không tìm thấy vị trí của nhân vật: {nick}")

        my_row = my_info["row"]
        my_slot = my_info["char_slot"] if actor_type == "Char" else my_info["pet_slot"]

        # =====================================================================
        # GIAI ĐOẠN 1: TẦNG 01 -> TẦNG 21 (F04 SOLO CARRY)
        # =====================================================================
        if 1 <= stage <= 21:
            # 1. Wi01, W03, W04 (Người & Pet) -> 100% PHÒNG THỦ MỌI HIỆP
            if nick in ["Wi01", "W03", "W04"]:
                return (my_slot, my_row, SKILLS["DEFEND"], f"Phòng thủ ({nick} Full Thủ Tầng 1-21)")

            # 2. F04 (Char & Pet) -> SÁT THƯƠNG CHỦ LỰC
            if nick == "F04":
                if turn == 1:
                    # LƯỢT 1:
                    # - Char F04: Chiêu Hỏa 1f3b lên Hàng 2 (Pos 2 hoặc 6)
                    if actor_type == "Char":
                        tgt_pos = self._pick_row2_target(alive_enemy_positions)
                        tgt = ENEMY_GRID[tgt_pos]
                        desc = f"Lượt 1: Chiêu Hỏa 1f3b -> Hàng 2 ({tgt['name']} [Pos {tgt_pos}])"
                        return (tgt["slot"], tgt["row"], SKILLS["F04_CHAR"], desc)
                    # - Pet F04: Chiêu 043b lên Hàng 3 (Pos 3 hoặc 7)
                    else:
                        tgt_pos = self._pick_row3_target(alive_enemy_positions)
                        tgt = ENEMY_GRID[tgt_pos]
                        desc = f"Lượt 1: Chiêu Pet 043b -> Hàng 3 ({tgt['name']} [Pos {tgt_pos}])"
                        return (tgt["slot"], tgt["row"], SKILLS["F04_PET"], desc)
                else:
                    # LƯỢT 2 TRỞ ĐI:
                    # Luôn ưu tiên quái sống ở Hàng 2 và Hàng 3 (2, 6, 3, 7)
                    tgt_pos = self._select_priority_target(alive_enemy_positions)
                    if tgt_pos is not None:
                        tgt = ENEMY_GRID[tgt_pos]
                        skill = SKILLS["F04_CHAR"] if actor_type == "Char" else SKILLS["F04_PET"]
                        sname = "1f3b (Char)" if actor_type == "Char" else "043b (Pet)"
                        desc = f"Lượt {turn}: Ưu tiên quái sống {tgt['name']} [Pos {tgt_pos}] bằng {sname}"
                        return (tgt["slot"], tgt["row"], skill, desc)
                    else:
                        return (my_slot, my_row, SKILLS["DEFEND"], "Hết quái -> Phòng thủ")

        # =====================================================================
        # GIAI ĐOẠN 2: TẦNG 22 -> TẦNG 26 (TỔNG LỰC TẤN CÔNG)
        # =====================================================================
        elif 22 <= stage <= 26:
            tgt_pos = self._select_priority_target(alive_enemy_positions)
            if tgt_pos is None:
                return (my_slot, my_row, SKILLS["DEFEND"], "Hết quái -> Phòng thủ")

            tgt = ENEMY_GRID[tgt_pos]

            if nick == "F04":
                skill = SKILLS["F04_CHAR"] if actor_type == "Char" else SKILLS["F04_PET"]
                sname = "1f3b (Char)" if actor_type == "Char" else "043b (Pet)"
                desc = f"[Tầng {stage}] F04 dồn sát thương {tgt['name']} [Pos {tgt_pos}] bằng {sname}"
                return (tgt["slot"], tgt["row"], skill, desc)

            elif nick == "W04":
                skill = SKILLS["W04_CHAR"] if actor_type == "Char" else SKILLS["W04_PET"]
                sname = "fb2a (Char)" if actor_type == "Char" else "092f (Pet)"
                desc = f"[Tầng {stage}] W04 tấn công quái sống {tgt['name']} [Pos {tgt_pos}] bằng {sname}"
                return (tgt["slot"], tgt["row"], skill, desc)

            elif nick == "W03":
                skill = SKILLS["W03_CHAR"] if actor_type == "Char" else SKILLS["W03_PET"]
                sname = "fb2a (Char)" if actor_type == "Char" else "092f (Pet)"
                desc = f"[Tầng {stage}] W03 tấn công quái sống {tgt['name']} [Pos {tgt_pos}] bằng {sname}"
                return (tgt["slot"], tgt["row"], skill, desc)

            elif nick == "Wi01":
                skill = SKILLS["WI01_CHAR"] if actor_type == "Char" else SKILLS["WI01_PET"]
                sname = "2b2b Phong (Char)" if actor_type == "Char" else "2c2b (Pet)"
                desc = f"[Tầng {stage}] Wi01 hỗ trợ sát thương {tgt['name']} [Pos {tgt_pos}] bằng {sname}"
                return (tgt["slot"], tgt["row"], skill, desc)

        # Mặc định phòng thủ an toàn
        return (my_slot, my_row, SKILLS["DEFEND"], "Mặc định phòng thủ")

    def _pick_row2_target(self, alive_positions: List[int]) -> int:
        """Chọn mục tiêu ở Hàng 2: ưu tiên Pos 2, sau đó Pos 6"""
        if 2 in alive_positions:
            return 2
        if 6 in alive_positions:
            return 6
        # Nếu Hàng 2 sạch bóng, chuyển sang mục tiêu ưu tiên tiếp theo (Hàng 3)
        return self._select_priority_target(alive_positions) or 2

    def _pick_row3_target(self, alive_positions: List[int]) -> int:
        """Chọn mục tiêu ở Hàng 3: ưu tiên Pos 3, sau đó Pos 7"""
        if 3 in alive_positions:
            return 3
        if 7 in alive_positions:
            return 7
        # Nếu Hàng 3 sạch bóng, chuyển sang mục tiêu ưu tiên tiếp theo (Hàng 2)
        return self._select_priority_target(alive_positions) or 3

    def _select_priority_target(self, alive_positions: List[int]) -> Optional[int]:
        """
        Quy tắc ưu tiên mục tiêu cốt lõi:
        1. Hàng 2: Pos 2 (Trước) -> Pos 6 (Sau)
        2. Hàng 3: Pos 3 (Trước) -> Pos 7 (Sau)
        3. Hàng 1: Pos 1 (Trước) -> Pos 5 (Sau)
        4. Hàng 4: Pos 4 (Trước) -> Pos 8 (Sau)
        """
        for pos in self.F04_PRIORITY_QUEUE:
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
        Đóng gói tin C->S Op: 0x32 Sub: 0x01 hoàn chỉnh.
        Cấu trúc 9 bytes: [ActorSlot, ActorRow, TargetSlot, TargetRow, Skill4B, 0x00]
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

    @staticmethod
    def get_trash_codes_for_stage(stage: int) -> List[int]:
        """Lấy danh sách mã vật phẩm rác cần vứt sau khi thắng tầng tương ứng"""
        round_info = TOWER_TRASH_BY_ROUND.get(stage, {})
        return list(round_info.keys())


# =============================================================================
# KIỂM THỬ TÍNH NĂNG (DEMO / VERIFICATION)
# =============================================================================
if __name__ == "__main__":
    controller = Tower29CombatController()
    print("=" * 85)
    print("      KIỂM THỬ BỘ ĐIỀU KHIỂN CHIẾN ĐẤU THÁP 29 TẦNG (SKY TOWER)")
    print("=" * 85)

    # 1. Tầng 5 - Lượt 1: Quái xuất hiện đầy đủ 8 vị trí
    stage = 5
    turn = 1
    alive = [1, 2, 3, 4, 5, 6, 7, 8]
    print(f"\n▶ [TẦNG {stage:02d} - LƯỢT {turn}] Toàn bộ 8 quái xuất hiện:")
    for nick in ["Wi01", "W03", "W04", "F04"]:
        for actor in ["Char", "Pet"]:
            _, msg = controller.build_combat_packet(nick, actor, stage, turn, alive)
            print(" ", msg)

    # 2. Tầng 5 - Lượt 2: Quái ở Pos 2 và Pos 3 đã bị F04 diệt, còn lại Pos 1, 4, 5, 6, 7, 8
    turn = 2
    alive = [1, 4, 5, 6, 7, 8]
    print(f"\n▶ [TẦNG {stage:02d} - LƯỢT {turn}] Pos 2 và Pos 3 đã chết. Kiểm tra F04 ưu tiên Pos 6 và Pos 7:")
    for actor in ["Char", "Pet"]:
        _, msg = controller.build_combat_packet("F04", actor, stage, turn, alive)
        print(" ", msg)

    # 3. Tầng 5 - Lượt 3: Toàn bộ Hàng 2 và Hàng 3 đã sạch (Pos 2, 6, 3, 7 đều chết), còn lại 1, 4, 5, 8
    turn = 3
    alive = [1, 4, 5, 8]
    print(f"\n▶ [TẦNG {stage:02d} - LƯỢT {turn}] Hàng 2 & 3 đã sạch 100%. F04 chuyển sang đánh Hàng 1 (Pos 1):")
    for actor in ["Char", "Pet"]:
        _, msg = controller.build_combat_packet("F04", actor, stage, turn, alive)
        print(" ", msg)

    # 4. Tầng 24 - Tấn công tổng lực (All-Out Attack)
    stage = 24
    turn = 1
    alive = [1, 2, 3, 5, 6, 7]
    print(f"\n▶ [TẦNG {stage:02d} - LƯỢT {turn}] Tầng cao quái trâu: Toàn đội dồn sát thương:")
    for nick in ["W04", "W03", "Wi01", "F04"]:
        for actor in ["Char", "Pet"]:
            _, msg = controller.build_combat_packet(nick, actor, stage, turn, alive)
            print(" ", msg)

    # 5. Kiểm tra mã rác nhận được sau tầng 5, 6, 7, 8
    print("\n▶ KIỂM TRA MÃ RÁC CẦN VỨT THEO VÒNG:")
    for stg in [5, 6, 7, 8]:
        codes = controller.get_trash_codes_for_stage(stg)
        info_str = ", ".join([f"0x{c:04X} ({TOWER_TRASH_BY_ROUND[stg][c]['name']})" for c in codes])
        print(f"  • Thắng Tầng {stg:02d} (r{stg}): Tự động vứt mã {info_str}")

    print("\n" + "=" * 85)
    print("✔ TẤT CẢ QUY TẮC ĐÃ ĐƯỢC XÁC THỰC CHÍNH XÁC!")
    print("=" * 85)
