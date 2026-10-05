#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO Dungeon & Dynamic Auto-Battle Simulator
===========================================
Chế độ chiến đấu tự động động (Dynamic Auto-Battle) kết hợp bộ lắng nghe phản hồi Server:
1. Đăng nhập & Vào phó bản (Login & Enter Dungeon).
2. Tự động di chuyển lần lượt tới 5 NPC.
3. Cơ chế Dynamic Auto-Battle cho từng NPC:
   - Nhân vật chính: Đánh thường (Action 0x00) vào mục tiêu đầu tiên ở tất cả các hiệp.
   - Pet: Dùng kỹ năng (Action 0x06 hoặc tùy chọn) vào mục tiêu đầu tiên ở tất cả các hiệp.
   - Bộ lắng nghe (Listener): Kiểm tra phản hồi S->C từ server sau mỗi hiệp (Op:0x14 Sub:0x01, Quest 0x16, Map 0x35)
     để biết chính xác khi nào trận đấu kết thúc, tự động đóng thoại và tiếp tục.
4. Di chuyển tới điểm nhận thưởng và hoàn tất phó bản.

Cách sử dụng:
  - Chạy thử nghiệm xem trước kịch bản (Dry-run, không gửi mạng):
      python wlo_simulate_dungeon.py --dry-run
  - Chạy thực tế kết nối tới server cục bộ (127.0.0.1:6414):
      python wlo_simulate_dungeon.py --live
  - Chạy thực tế với tốc độ tăng gấp đôi:
      python wlo_simulate_dungeon.py --live --speed 2.0
  - Chạy từng giai đoạn bấm Enter để xác nhận:
      python wlo_simulate_dungeon.py --live --step
  - Tùy chỉnh mã kỹ năng của Pet (mặc định: 0x06):
      python wlo_simulate_dungeon.py --live --pet-skill 0x01
"""

import sys
import time
import socket
import struct
import threading
import argparse

# Thiết lập UTF-8 tránh lỗi hiển thị trên console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

# ==============================================================================
# ĐỊNH NGHĨA DỮ LIỆU ĐĂNG NHẬP, VÀO PHÓ BẢN VÀ 5 NPC
# ==============================================================================

STAGE_LOGIN = {
    "title": "Giai đoạn 1: Đăng nhập & Chọn nhân vật",
    "description": "Bắt tay kết nối, xác thực tài khoản BGDF02, chọn nhân vật Slot 1 và vào thế giới",
    "steps": [
        {"desc": "Bắt tay khởi tạo kết nối (Handshake)", "body": "00", "delay": 1.0},
        {"desc": "Xác thực tài khoản BGDF02 / Mật khẩu 111111", "body": "3f04b004064247444630320631313131313107784b4d4f484d4e4f", "delay": 1.5},
        {"desc": "Chọn nhân vật slot 1", "body": "3f0201", "delay": 1.4},
        {"desc": "Đồng bộ thuộc tính ban đầu", "body": "174d", "delay": 0.2},
        {"desc": "Gửi tín hiệu vào thế giới game (Enter World)", "body": "050700", "delay": 0.2},
        {"desc": "Khởi tạo thông số giao diện & tính năng phụ", "body": "59004d000000", "delay": 0.1},
        {"desc": "Đồng bộ client", "body": "5c01", "delay": 0.1},
        {"desc": "Yêu cầu bảng thuộc tính (Attributes Request)", "body": "1736", "delay": 0.2},
        {"desc": "Xác thực mở rộng (Special Extension)", "body": "b71100", "delay": 1.0},
        {"desc": "Đồng bộ danh sách bạn bè / trạng thái", "body": "5501", "delay": 1.0},
        {"desc": "Đồng bộ trạng thái bang hội / kênh", "body": "5503397500", "delay": 0.3},
        {"desc": "Hoàn tất vào game", "body": "5501", "delay": 2.0},
    ]
}

STAGE_ENTER_DUNGEON = {
    "title": "Giai đoạn 2: Vào phó bản (Enter Dungeon)",
    "description": "Gửi lệnh 'go', đối thoại NPC cổng và chuyển cảnh vào phó bản",
    "steps": [
        {"desc": "Gửi lệnh kích hoạt phó bản ('go')", "body": "0202676f", "delay": 0.5},
        {"desc": "Đồng bộ tính năng phó bản", "body": "550201", "delay": 2.5},
        {"desc": "Kiểm tra danh sách đồng đội phó bản", "body": "0c01", "delay": 0.2},
        {"desc": "Đồng bộ kênh chat phụ bản", "body": "1406", "delay": 0.1},
        {"desc": "Xác nhận đối thoại NPC cổng phó bản (Vào trong)", "body": "20020c", "delay": 0.2},
        {"desc": "Làm mới chỉ số khi vào phụ bản", "body": "1736", "delay": 2.5},
    ]
}

# Danh sách 5 NPC cần tiêu diệt trong phó bản
NPC_LIST = [
    {
        "id": 1,
        "name": "NPC 1 (Tiền đồn)",
        "move_steps": [],  # Đã đứng sẵn tại vị trí đầu phó bản
        "target_player": "0205bb03a2f4",
        "target_pet": "c6046b03a2f1",
        "win_trigger": "14010200",
        "close_dialog": "200209",
        "expected_rounds": 1,
    },
    {
        "id": 2,
        "name": "NPC 2",
        "move_steps": [
            {"desc": "Bắt đầu lộ trình di chuyển đến NPC 2", "body": "174e0100724b4c00724b4c000300030000000132", "delay": 0.2},
            {"desc": "Di chuyển bước 1", "body": "3201040201021227332800", "delay": 0.2},
            {"desc": "Di chuyển bước 2", "body": "3201030201021227c40900", "delay": 2.0},
            {"desc": "Di chuyển bước 3", "body": "320104020201c53a270500", "delay": 1.2},
            {"desc": "Di chuyển bước 4 tới sát NPC 2", "body": "3201030202031f3b292500", "delay": 2.5},
            {"desc": "Cập nhật vị trí nhân vật", "body": "174e0100724b4c00724b4c000300030000000132", "delay": 0.2},
            {"desc": "Di chuyển bước căn chỉnh vị trí", "body": "320104020201c53adb0800", "delay": 0.2},
            {"desc": "Dừng di chuyển trước mặt NPC 2", "body": "3201030202011f3bf7de00", "delay": 2.5},
        ],
        "target_player": "8e059303a2c8",
        "target_pet": "42067f03a2e3",
        "win_trigger": "14010100",
        "close_dialog": "20020f",
        "expected_rounds": 1,
    },
    {
        "id": 3,
        "name": "NPC 3",
        "move_steps": [
            {"desc": "Di chuyển bước 1 đến NPC 3", "body": "320104020102c53a81d200", "delay": 0.2},
            {"desc": "Di chuyển bước 2 tới sát NPC 3", "body": "3201030201021f3b1dd500", "delay": 2.5},
        ],
        "target_player": "1e07cf03a2f7",
        "target_pet": "e6070b04a2d2",
        "win_trigger": "14010400",
        "close_dialog": "20020f",
        "expected_rounds": 3,
    },
    {
        "id": 4,
        "name": "NPC 4",
        "move_steps": [
            {"desc": "Di chuyển bước 1 theo lộ trình NPC 4", "body": "320104020102c53a8e1600", "delay": 0.2},
            {"desc": "Di chuyển bước 2", "body": "3201030201021f3b3a6800", "delay": 2.0},
            {"desc": "Di chuyển bước 3 tới trước mặt NPC 4", "body": "320104020203c53a3aca00", "delay": 0.2},
            {"desc": "Dừng di chuyển tại vị trí NPC 4", "body": "3201030202031f3be57400", "delay": 2.5},
        ],
        "target_player": "fa07e303a2ce",
        "target_pet": "46072f03a2eb",
        "win_trigger": "14010600",
        "close_dialog": "20020f",
        "expected_rounds": 4,
    },
    {
        "id": 5,
        "name": "NPC 5 (Trùm phụ bản)",
        "move_steps": [
            {"desc": "Di chuyển chặng 1 hướng về boss NPC 5", "body": "320104020101c53aba7300", "delay": 0.2},
            {"desc": "Di chuyển chặng 2", "body": "3201030201011f3b142800", "delay": 2.5},
            {"desc": "Di chuyển chặng 3", "body": "320104020101c53a1ff100", "delay": 0.2},
            {"desc": "Di chuyển chặng 4", "body": "3201030201011f3b3eb900", "delay": 2.5},
            {"desc": "Di chuyển chặng 5", "body": "320104020101c53a1b2f00", "delay": 0.2},
            {"desc": "Di chuyển chặng 6", "body": "3201030201011f3b630300", "delay": 2.5},
            {"desc": "Di chuyển bước áp sát boss NPC 5", "body": "320104020103c53a26b700", "delay": 0.2},
            {"desc": "Dừng trước mặt boss NPC 5", "body": "3201030201031f3b8df400", "delay": 2.0},
        ],
        "target_player": "7e06ef01a2dc",
        "target_pet": "7e06ef01a2dc",
        "win_trigger": "14010500",
        "close_dialog": "20020d",
        "expected_rounds": 1,
    }
]

STAGE_CLAIM_REWARD = {
    "title": "Giai đoạn cuối: Di chuyển & Nhận thưởng (Claim Reward)",
    "description": "Di chuyển đến rương / NPC trao thưởng, đối thoại nhận quà và hoàn tất",
    "move_steps": [
        {"desc": "Di chuyển chặng 1 đến vị trí nhận thưởng", "body": "320104020102c53a43b300", "delay": 0.2},
        {"desc": "Di chuyển chặng 2", "body": "3201030201021f3b859e00", "delay": 2.5},
        {"desc": "Di chuyển chặng 3", "body": "320104020104c53aa0df00", "delay": 0.2},
        {"desc": "Di chuyển chặng 4", "body": "3201030201041f3b158100", "delay": 2.5},
        {"desc": "Di chuyển chặng 5 tới vị trí NPC/Rương thưởng", "body": "320104020104c53a53f400", "delay": 0.2},
        {"desc": "Dừng di chuyển tại điểm nhận thưởng", "body": "3201030201041f3b162900", "delay": 2.0},
    ],
    "claim_steps": [
        {"desc": "Tương tác đối thoại nhận thưởng", "body": "2003", "delay": 0.2},
        {"desc": "Gửi hành động xác nhận mở rương / nhận quà", "body": "060107aa07c701a2ec", "delay": 1.5},
        {"desc": "Thông báo nhận thưởng thành công", "body": "14011300", "delay": 0.8},
        {"desc": "Xác nhận kết thúc đối thoại nhận thưởng", "body": "20020f", "delay": 0.2},
        {"desc": "Đồng bộ thuộc tính / EXP / Vật phẩm nhận được", "body": "1736", "delay": 0.2},
        {"desc": "Hoàn tất phó bản!", "body": "1736", "delay": 1.0},
    ]
}

# ==============================================================================
# HÀM MÃ HÓA & ĐÓNG GÓI GIAO THỨC WLO
# ==============================================================================

def pack_wlo_packet(body_bytes):
    """Đóng gói Magic 0xF4 0x44, Length (uint16 LE) và XOR 0xAD."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain_packet = header + body_bytes
    return bytes(b ^ 0xAD for b in plain_packet)

def decrypt_wlo_packet(encrypted_bytes):
    """Giải mã gói tin từ server bằng XOR 0xAD."""
    return bytes(b ^ 0xAD for b in encrypted_bytes)

# ==============================================================================
# BỘ MÔ PHỎNG CHIẾN ĐẤU ĐỘNG & BỘ LẮNG NGHE PHẢN HỒI SERVER
# ==============================================================================

class WLOSimulator:
    def __init__(self, host="127.0.0.1", port=6414, speed=1.0, pet_skill=0x06, is_dry_run=False, interactive=False):
        self.host = host
        self.port = port
        self.speed = speed if speed > 0 else 1.0
        self.pet_skill = pet_skill
        self.is_dry_run = is_dry_run
        self.interactive = interactive
        self.sock = None
        self.running = False
        self.recv_thread = None

        # Trạng thái chiến đấu và cờ đồng bộ lắng nghe
        self.in_combat = False
        self.battle_finished = False
        self.battle_event = threading.Event()
        self.lock = threading.Lock()

    def connect(self):
        print(f"[*] Đang kết nối tới server game: {self.host}:{self.port} ...")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10.0)
        self.sock.connect((self.host, self.port))
        self.sock.settimeout(None)
        self.running = True
        print(f"[+] Kết nối thành công tới {self.host}:{self.port}!\n")

        # Khởi chạy luồng nhận phản hồi từ server
        self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.recv_thread.start()

    def _recv_loop(self):
        """Luồng đọc ngầm liên tục và bóc tách các gói tin server gửi về."""
        buffer = bytearray()
        try:
            while self.running:
                data = self.sock.recv(4096)
                if not data:
                    print("\n[!] Kết nối từ server đã đóng.")
                    break
                decrypted = decrypt_wlo_packet(data)
                buffer.extend(decrypted)

                # Bóc tách các gói tin server
                while len(buffer) >= 4:
                    if buffer[0] != 0xF4 or buffer[1] != 0x44:
                        idx = buffer.find(b'\xF4\x44')
                        if idx == -1:
                            buffer.clear()
                            break
                        buffer = buffer[idx:]
                        if len(buffer) < 4:
                            break

                    payload_len = struct.unpack("<H", buffer[2:4])[0]
                    total_len = 4 + payload_len
                    if len(buffer) < total_len:
                        break

                    body = buffer[4:total_len]
                    buffer = buffer[total_len:]

                    op = body[0] if len(body) > 0 else None
                    sub = body[1] if len(body) > 1 else None
                    payload_data = body[2:] if len(body) > 2 else b''

                    self._handle_server_packet(op, sub, payload_data)
        except Exception:
            pass

    def _handle_server_packet(self, op, sub, data):
        """Bộ lắng nghe: Phân tích gói tin Server để bắt tín hiệu kết thúc chiến đấu và phần thưởng."""
        if op == 0x08:
            return  # Bỏ qua nhịp tim định kỳ

        # 1. Tín hiệu chiến thắng / kết quả trận đấu (Opcode 0x14 Subcode 0x01)
        if op == 0x14 and sub == 0x01:
            print(f"   <- [Server Listener] PHÁT HIỆN TÍN HIỆU CHIẾN THẮNG TRẬN ĐẤU (Op:0x14 Sub:0x01)!")
            with self.lock:
                self.battle_finished = True
                self.battle_event.set()
            return

        # 2. Tín hiệu cập nhật tiến trình nhiệm vụ (Opcode 0x16 Subcode 0x08 hoặc 0x09)
        if op == 0x16 and sub in (0x08, 0x09):
            print(f"   <- [Server Listener] CẬP NHẬT TIẾN TRÌNH TIÊU DIỆT NPC (Op:0x16 Sub:0x{sub:02X})!")
            with self.lock:
                self.battle_finished = True
                self.battle_event.set()
            return

        # 3. Tín hiệu chuyển cảnh / Trở về map phó bản sau trận (Opcode 0x35 Subcode 0x05)
        if op == 0x35 and sub == 0x05 and self.in_combat:
            print(f"   <- [Server Listener] ĐÃ RỜI BÀN CỜ CHIẾN ĐẤU, TRỞ VỀ BẢN ĐỒ (Op:0x35 Sub:0x05)!")
            with self.lock:
                self.battle_finished = True
                self.battle_event.set()
            return

        # 4. Tín hiệu nhận vật phẩm / trang bị thưởng (Opcode 0x0B)
        if op == 0x0B and sub in (0x04, 0xFA, 0x0A):
            print(f"   <- [Server Listener] NHẬN VẬT PHẨM VÀO TÚI ĐỒ (Op:0x0B Sub:0x{sub:02X})")
            return

        # 5. Tín hiệu cập nhật EXP / Chỉ số nhân vật (Opcode 0x17)
        if op == 0x17 and sub == 0x36:
            print(f"   <- [Server Listener] CẬP NHẬT THUỘC TÍNH & ĐIỂM EXP (Op:0x17 Sub:0x36)")
            return

    def send_packet(self, body_bytes):
        """Gửi gói tin WLO qua socket (có mã hóa XOR 0xAD)."""
        packet = pack_wlo_packet(body_bytes)
        if self.sock:
            self.sock.sendall(packet)

    def send_step(self, step):
        body_bytes = bytes.fromhex(step["body"])
        op = body_bytes[0] if len(body_bytes) > 0 else 0
        sub = body_bytes[1] if len(body_bytes) > 1 else 0

        print(f"   -> Gửi Op:0x{op:02X} Sub:0x{sub:02X} | {step['desc']}")
        self.send_packet(body_bytes)

        sleep_time = step["delay"] / self.speed
        if sleep_time > 0:
            time.sleep(sleep_time)

    def execute_steps(self, steps):
        for idx, step in enumerate(steps, 1):
            print(f" [{idx:02d}/{len(steps):02d}]", end=" ")
            self.send_step(step)

    def run_dynamic_battle(self, npc):
        """
        CƠ CHẾ DYNAMIC AUTO-BATTLE:
        - Nhân vật chính: Luôn đánh thường (Action 0x00) vào mục tiêu đầu tiên.
        - Pet: Luôn dùng kỹ năng (Action 0x{self.pet_skill:02X}) vào mục tiêu đầu tiên.
        - Với NPC Quest WLO, client phải tự báo cáo Win Trigger (Opcode 0x14 Subcode 0x01) 
          để server tính là hoàn thành nhiệm vụ!
        """
        npc_name = npc["name"]
        print("\n" + "=" * 75)
        print(f"[*] TIẾP CẬN VÀ KÍCH HOẠT DYNAMIC AUTO-BATTLE: {npc_name}")
        print(f"    - Nhân vật chính: ĐÁNH THƯỜNG (Action 0x00) vào mục tiêu 1")
        print(f"    - Pet đồng hành : DÙNG KỸ NĂNG (Action 0x{self.pet_skill:02X}) vào mục tiêu 1")
        print("=" * 75)

        with self.lock:
            self.in_combat = True
            self.battle_finished = False
            self.battle_event.clear()

        # Bước 1: Tiếp cận đối thoại khiêu chiến NPC (Op:0x20 Sub:0x03)
        print(f" [01] Tiếp cận và gửi đối thoại khiêu chiến {npc_name} (Op:0x20 Sub:0x03)")
        self.send_packet(bytes.fromhex("2003"))
        time.sleep(1.0 / self.speed)

        round_num = 1
        max_rounds = 25  # Giới hạn an toàn

        while round_num <= max_rounds:
            with self.lock:
                if self.battle_finished:
                    break

            print(f"\n >>> [HIỆP {round_num}] Gửi lệnh hiệp đấu cho Nhân vật & Pet:")

            # 1. Nhân vật chính đánh thường vào mục tiêu đầu tiên (Action 0x00)
            player_cmd = bytes([0x06, 0x01, 0x00]) + bytes.fromhex(npc["target_player"])
            print(f"   -> [Nhân vật] Đánh thường (Op:0x06 Action:0x00) -> Mục tiêu 1 [Hex: {player_cmd.hex()}]")
            self.send_packet(player_cmd)
            time.sleep(0.6 / self.speed)

            with self.lock:
                if self.battle_finished:
                    break

            # 2. Pet dùng kỹ năng vào mục tiêu đầu tiên (Action pet_skill)
            pet_cmd = bytes([0x06, 0x01, self.pet_skill]) + bytes.fromhex(npc["target_pet"])
            print(f"   -> [Pet] Dùng kỹ năng (Op:0x06 Action:0x{self.pet_skill:02X}) -> Mục tiêu 1 [Hex: {pet_cmd.hex()}]")
            self.send_packet(pet_cmd)

            # 3. Kịch bản chiến đấu với Boss Quest trong WLO:
            # Client tự tính toán kết quả và gửi Win Trigger khi đạt đủ số hiệp yêu cầu
            if round_num >= npc["expected_rounds"]:
                time.sleep(1.0 / self.speed)
                print(f"   [!] Đạt đủ số hiệp dự kiến ({npc['expected_rounds']}), trận đấu kết thúc.")
                break
            else:
                time.sleep(1.5 / self.speed)

            round_num += 1

        with self.lock:
            self.in_combat = False

        print(f"\n[+] {npc_name} ĐÃ BỊ TIÊU DIỆT HOÀN TOÀN SAU {round_num} HIỆP!")

        # Bước 3: Gửi Win Trigger (Báo cáo kết quả thắng lên Server) để hoàn thành quest step
        win_trigger = npc.get("win_trigger")
        if win_trigger:
            print(f" [V] Gửi tín hiệu Báo cáo Chiến thắng (Op:0x14 Sub:0x01) -> Hex: {win_trigger}")
            self.send_packet(bytes.fromhex(win_trigger))
            time.sleep(1.0 / self.speed)

        # Bước 4: Đóng hộp thoại kết thúc trận đấu
        close_dialog = npc.get("close_dialog", "20020f")
        print(f" [Xong] Gửi lệnh đóng hộp thoại kết thúc trận ({close_dialog})")
        self.send_packet(bytes.fromhex(close_dialog))
        time.sleep(1.5 / self.speed)

    def run_all(self):
        start_time = time.time()

        # ==========================================
        # GIAI ĐOẠN 1: ĐĂNG NHẬP & CHỌN NHÂN VẬT
        # ==========================================
        print("\n" + "=" * 75)
        print(f"[*] {STAGE_LOGIN['title']}")
        print(f"    Mô tả: {STAGE_LOGIN['description']}")
        print("=" * 75)
        if self.interactive:
            input(">>> Nhấn [ENTER] để bắt đầu Đăng nhập... ")
        self.execute_steps(STAGE_LOGIN["steps"])
        print("[+] Đăng nhập & vào game thành công!\n")

        # ==========================================
        # GIAI ĐOẠN 2: VÀO PHÓ BẢN
        # ==========================================
        print("=" * 75)
        print(f"[*] {STAGE_ENTER_DUNGEON['title']}")
        print(f"    Mô tả: {STAGE_ENTER_DUNGEON['description']}")
        print("=" * 75)
        if self.interactive:
            input(">>> Nhấn [ENTER] để vào Phó bản... ")
        self.execute_steps(STAGE_ENTER_DUNGEON["steps"])
        print("[+] Đã vào trong phó bản thành công!\n")

        # ==========================================
        # GIAI ĐOẠN 3 -> 7: DI CHUYỂN & ĐÁNH 5 NPC
        # ==========================================
        for idx, npc in enumerate(NPC_LIST, 1):
            stage_title = f"Giai đoạn {idx + 2}: Di chuyển & Tiêu diệt {npc['name']}"
            print("=" * 75)
            print(f"[*] {stage_title}")
            print("=" * 75)
            if self.interactive:
                input(f">>> Nhấn [ENTER] để bắt đầu xử lý {npc['name']}... ")

            # 1. Di chuyển tới vị trí của NPC (nếu có lộ trình)
            if npc["move_steps"]:
                print(f"[*] Đang di chuyển theo tọa độ tới {npc['name']}...")
                self.execute_steps(npc["move_steps"])

            # 2. Thực hiện Dynamic Auto-Battle có kiểm tra kết thúc
            self.run_dynamic_battle(npc)
            print(f"[+] Hoàn tất xử lý {npc['name']}!\n")

        # ==========================================
        # GIAI ĐOẠN 8: DI CHUYỂN NHẬN THƯỞNG
        # ==========================================
        print("=" * 75)
        print(f"[*] {STAGE_CLAIM_REWARD['title']}")
        print(f"    Mô tả: {STAGE_CLAIM_REWARD['description']}")
        print("=" * 75)
        if self.interactive:
            input(">>> Nhấn [ENTER] để di chuyển nhận thưởng... ")

        print("[*] Đang di chuyển đến vị trí rương / NPC nhận thưởng...")
        self.execute_steps(STAGE_CLAIM_REWARD["move_steps"])

        print("[*] Đối thoại và nhận phần thưởng hoàn tất phó bản...")
        self.execute_steps(STAGE_CLAIM_REWARD["claim_steps"])
        print("[+] ĐÃ NHẬN THƯỞNG THÀNH CÔNG!\n")

        total_time = time.time() - start_time
        print("=" * 75)
        print(f"[+] HOÀN TẤT TOÀN BỘ PHÓ BẢN VÀ TIÊU DIỆT ĐỦ 5 NPC!")
        print(f"    Tổng thời gian hoàn thành: {total_time:.2f} giây")
        print("=" * 75)

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

# ==============================================================================
# HÀM CHÍNH
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="WLO Dynamic Auto-Battle & Dungeon Simulator: Nhân vật đánh thường, Pet dùng kỹ năng, tự động check xong trận."
    )
    parser.add_argument("--dry-run", action="store_true", help="Chế độ xem trước kịch bản mà không gửi gói tin qua mạng")
    parser.add_argument("--live", action="store_true", help="Chế độ kết nối thực tế tới server và gửi gói tin")
    parser.add_argument("--host", default="127.0.0.1", help="Địa chỉ server (mặc định: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=6414, help="Cổng server game (mặc định: 6414)")
    parser.add_argument("--speed", type=float, default=1.0, help="Hệ số tăng tốc (VD: 2.0 là nhanh gấp đôi, mặc định: 1.0)")
    parser.add_argument("--pet-skill", type=lambda x: int(x, 0), default=0x06, help="Mã kỹ năng của Pet (Hex hoặc Dec, mặc định: 0x06)")
    parser.add_argument("--step", action="store_true", help="Chế độ từng bước: Dừng lại chờ bấm Enter trước mỗi giai đoạn")

    args = parser.parse_args()

    # Mặc định là dry-run nếu không chỉ định live
    if not args.live and not args.dry_run:
        print("[!] Chưa chỉ định chế độ. Mặc định kích hoạt chế độ xem trước (--dry-run).")
        print("    Để kết nối và gửi trực tiếp tới server, hãy thêm cờ: --live\n")
        args.dry_run = True

    sim = WLOSimulator(
        host=args.host,
        port=args.port,
        speed=args.speed,
        pet_skill=args.pet_skill,
        is_dry_run=args.dry_run,
        interactive=args.step
    )

    if args.live:
        try:
            sim.connect()
        except ConnectionRefusedError:
            print(f"[!] Không thể kết nối tới {args.host}:{args.port}!")
            print("    Vui lòng đảm bảo game server / proxy (aProxy.exe) đang chạy trước khi chạy --live.")
            return
        except Exception as e:
            print(f"[!] Lỗi kết nối: {e}")
            return

    try:
        sim.run_all()
    except KeyboardInterrupt:
        print("\n[!] Đã dừng script bởi người dùng.")
    finally:
        sim.close()

if __name__ == "__main__":
    main()
