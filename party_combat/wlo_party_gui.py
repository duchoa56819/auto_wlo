#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO AUTO PARTY MANAGER - GIAO DIỆN ĐỒ HỌA ĐIỀU KHIỂN TỔ ĐỘI TỰ ĐỘNG
===================================================================
Ứng dụng đồ họa đa tiến trình Wonderland Online (WLO):
1. Bảng quét & chọn từ 2 đến 4 cửa sổ game (alogin*.exe).
2. Tự động nhận diện tài khoản tương ứng:
   - alogin-f02 / aloginF02 -> BGDF02 (Mật khẩu: 111111)
   - alogin-f04             -> BGDF04 (Mật khẩu: 111111)
   - alogin-w03             -> BGDW03 (Mật khẩu: 111111)
   - alogin-w04             -> BGDW04 (Mật khẩu: 111111)
   - alogin-f03 / aloginF03 -> BGDF03 (Mật khẩu: 111111)
   - alogin-f032            -> BGDF032 (Mật khẩu: 111111)
3. Tính năng tự động Đăng xuất & Đăng nhập lại (Auto-Relog & Sync All) để lấy Char ID.
4. Chọn Đội Trưởng (Party Leader).
5. Bảng điều khiển trực quan:
   - Nút [⚡ TỰ ĐỘNG THIẾT LẬP TỔ ĐỘI (AUTO ALL)].
   - Nút [🔄 TỰ ĐỘNG RELOG TẤT CẢ ĐỂ LẤY CHAR ID].
   - Tự động chấp thuận (Auto-Accept 100%) khi nhận yêu cầu hoặc lời mời.
   - Thao tác riêng từng thành viên (Xin vào nhóm, Trao quyền đội trưởng, Rời nhóm, Relog riêng).
   - Khung nhật ký gói tin thời gian thực (Real-time Packet Console).
"""

import os
import sys
import time
import json
import queue
import struct
import threading
from datetime import datetime

# GUI Tkinter
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from tkinter.scrolledtext import ScrolledText

# Thiết lập encoding UTF-8 console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    frida = None

CODE_MINIDRAGONFLY = 0x861C  # 34332 - MiniDragonfly (Cố định Ô 1)
CODE_REGISVOUCHER = 0x75AC   # 30124 - RegisVoucher  (Cố định Ô 2)

NON_STACKABLE_KEYWORDS = [
    "spear", "sword", "bow", "blade", "wand", "staff", "mace", "axe", "gun",
    "armor", "suit", "dress", "robe", "coat", "vest", "cloth", "boots", "shoes",
    "cap", "hat", "helm", "crown", "ring", "necklace", "earring", "wrist", "bracer",
    "glove", "shield", "spar", "vehicle", "car", "plane", "boat", "tent",
    "20t", "30t", "40t", "weight", "lottery", "tạ", "kiếm", "cung", "đao", "trượng"
]

GLOBAL_ITEM_DB = {}
_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wlo_items_database.json")
if os.path.exists(_db_path):
    try:
        with open(_db_path, "r", encoding="utf-8") as _f:
            GLOBAL_ITEM_DB = json.load(_f)
    except Exception:
        pass

def is_stackable_item_global(code, observed_max_qty=1):
    if observed_max_qty > 1:
        return True
    code_hex = f"0x{code:04X}"
    item_info = GLOBAL_ITEM_DB.get(code_hex, {})
    name = (item_info.get("name") or "").lower()
    for kw in NON_STACKABLE_KEYWORDS:
        if kw in name:
            return False
    return False

def generate_compaction_plan_to_top(inventory):
    inv = {s: dict(v) for s, v in inventory.items()}
    moves = []
    while True:
        first_empty = None
        for s in range(1, 51):
            if s not in inv:
                first_empty = s
                break
        if first_empty is None:
            break
        next_occupied = None
        for s in range(first_empty + 1, 51):
            if s in inv:
                next_occupied = s
                break
        if next_occupied is None:
            break
        it = inv[next_occupied]
        moves.append((next_occupied, it["qty"], first_empty, it["code"]))
        inv[first_empty] = it
        del inv[next_occupied]
    return moves

def generate_compaction_plan_to_bottom(inventory, protect_slots=None):
    if protect_slots is None:
        protect_slots = set()
    inv = {s: dict(v) for s, v in inventory.items()}
    moves = []
    while True:
        last_empty = None
        for s in range(50, 0, -1):
            if s not in protect_slots and s not in inv:
                last_empty = s
                break
        if last_empty is None:
            break
        first_occupied = None
        for s in range(1, last_empty):
            if s not in protect_slots and s in inv:
                first_occupied = s
                break
        if first_occupied is None:
            break
        it = inv[first_occupied]
        moves.append((first_occupied, it["qty"], last_empty, it["code"]))
        inv[last_empty] = it
        del inv[first_occupied]
    return moves


# Kỹ năng chiến đấu mặc định cho Auto Quốc Bảo
SKILL_DEFEND = bytes.fromhex("75ea0000")
SKILL_FIRE_1F3B = bytes.fromhex("1f3b0000")
SKILL_PET_043B = bytes.fromhex("043b0000")
SKILL_PET_2D2B = bytes.fromhex("2d2b0000")

# Danh sách 5 Chìa khóa / Dấu ấn Quốc Bảo (National Treasure Keys)
NATIONAL_TREASURE_KEYS = {
    0x75AE: "Chìa khóa Quốc Bảo 1 (Mã 30126)",
    0x75AF: "Chìa khóa Quốc Bảo 2 (Mã 30127)",
    0x75B0: "Chìa khóa Quốc Bảo 3 (Mã 30128)",
    0x75B1: "Chìa khóa Quốc Bảo 4 (Mã 30129)",
    0x75B2: "Chìa khóa Quốc Bảo 5 (Mã 30130)",
}

# Danh sách đầy đủ 9 mã phần thưởng rác Tháp 29 Tầng & Cursed Palace cần vứt tức thì khi nhận
ALL_TRASH_REWARDS = {
    # Tháp 29 Tầng (Sky Tower)
    0x7D4A: {"name": "BubbleGum (Kẹo cao su)", "round": "Tháp r5 (Tầng 5)", "dec": 32074},
    0x7D4B: {"name": "Chocolate (Sô-cô-la)",   "round": "Tháp r6 (Tầng 6)", "dec": 32075},
    0x7D49: {"name": "InstantNoodle (Mì gói)", "round": "Tháp r7 (Tầng 7)", "dec": 32073},
    0x7D48: {"name": "ChocolateIceCream (Kem)","round": "Tháp r8 (Tầng 8)", "dec": 32072},
    # Cursed Palace (Cung Điện Bị Nguyền Rủa)
    0x7DB0: {"name": "FuguHotPot",          "round": "Cursed Palace Ải 4, 5", "dec": 32176},
    0x7E1D: {"name": "Turkey",              "round": "Cursed Palace Ải 6, 7", "dec": 32285},
    0x7DB1: {"name": "SoyPorkboneNoodle",   "round": "Cursed Palace Ải 8, 9", "dec": 32177},
    0x7E34: {"name": "CurryRice",           "round": "Cursed Palace Ải 10",    "dec": 32308},
    0x8514: {"name": "LovePicnicLunch",     "round": "Cursed Palace Ải 11",    "dec": 34068},
}

# ==============================================================================
# BẢNG MÀU DARK THEME (CATPPUCCIN MOCHA / NAVY)
# ==============================================================================
THEME = {
    "bg_dark": "#11111b",       # Nền sâu nhất (Header, Statusbar, Log)
    "bg_main": "#181825",       # Nền chính cửa sổ
    "bg_card": "#1e1e2e",       # Nền các khung Card, Container
    "bg_input": "#313244",      # Nền ô nhập liệu / Treeview
    "bg_hover": "#45475a",      # Khi hover
    "bg_selected": "#585b70",   # Khi chọn dòng
    "text_main": "#cdd6f4",     # Chữ sáng chính
    "text_muted": "#a6adc8",    # Chữ mờ, phụ đề
    "primary": "#89b4fa",       # Xanh dương điểm nhấn
    "primary_hover": "#b4befe",
    "green": "#a6e3a1",         # Đã kết nối / Thành công / Đã vào đội
    "yellow": "#f9e2af",        # Cảnh báo / Chưa vào đội
    "gold": "#fab387",          # Đội trưởng huy hiệu / Relog
    "orange": "#fab387",        # Màu cam điểm nhấn (Dồn đồ đáy túi)
    "red": "#f38ba8",           # Ngắt kết nối / Lỗi / Rời nhóm
    "cyan": "#89dceb",          # Socket / Hex ID
    "magenta": "#f5c2e7",       # Sự kiện đặc biệt
    "purple": "#cba6f7",        # Tự động lộ trình Cursed Palace
    "border": "#45475a",        # Màu viền
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "wlo_party_chars.json")

# Danh sách thư mục đồng bộ
SYNC_DIRS = [
    os.path.join(os.path.dirname(SCRIPT_DIR), "WLO"),
    os.path.join(os.path.dirname(SCRIPT_DIR), "WLOI - Eng"),
]

# Database Char ID mặc định đã biết
DEFAULT_KNOWN_CHARS = {
    "aloginf02": 0x00002EC8,
    "alogin-f02": 0x00002EC8,
    "alogin-f04": 0x00002ECB,
    "alogin-w03": 0x00002EE3,
    "alogin-w04": 0x00002EE4,
    "bgdf02": 0x00002EC8,
    "bgdf04": 0x00002ECB,
    "bgdw03": 0x00002EE3,
    "bgdw04": 0x00002EE4,
}

# Cấu hình Slot Pet mặc định cho từng nhân vật (Wi01: slot 2, W04: slot 4, W03: slot 4, F04: slot 2)
DEFAULT_COMBAT_PET_SLOTS = {
    "aloginf04": 2,
    "alogin-f04": 2,
    "f04": 2,
    "aloginw03": 4,
    "alogin-w03": 4,
    "w03": 4,
    "aloginw04": 4,
    "alogin-w04": 4,
    "w04": 4,
    "aloginwi01": 2,
    "alogin-wi01": 2,
    "wi01": 2,
}

# Cấu hình Pet chiến đấu mặc định cho từng nhân vật (Op: 0x13 Sub: 0x01)
DEFAULT_COMBAT_PETS = {
    "aloginf04": 14081,   # Pet slot 2 (0x3701)
    "alogin-f04": 14081,
    "f04": 14081,
    "aloginw03": 14242,   # Pet slot 4 (0x37A2)
    "alogin-w03": 14242,
    "w03": 14242,
    "aloginw04": 14242,   # Pet slot 4 (0x37A2)
    "alogin-w04": 14242,
    "w04": 14242,
    "aloginwi01": 14609,  # Pet slot 2 trong UI / pIdx 2 (0x3911)
    "alogin-wi01": 14609,
    "wi01": 14609,
}

def load_known_chars():
    chars = dict(DEFAULT_KNOWN_CHARS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    if isinstance(v, str) and v.startswith("0x"):
                        try:
                            chars[k.lower()] = int(v, 16)
                        except ValueError:
                            pass
                    elif isinstance(v, int):
                        chars[k.lower()] = v
        except Exception:
            pass
    return chars

def save_known_chars(chars):
    try:
        out = {k: f"0x{v:08X}" for k, v in chars.items() if v}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=4, ensure_ascii=False)
    except Exception:
        pass

def get_default_account_from_proc_name(proc_name):
    """Tự động chuyển tên tiến trình sang tên tài khoản (VD: alogin-F04 -> BGDF04)."""
    base = proc_name.lower().replace(".exe", "")
    for prefix in ["alogin-", "alogin_", "alogin"]:
        if base.startswith(prefix):
            suffix = base[len(prefix):].upper()
            return f"BGD{suffix}"
    return f"BGD{base.upper()}"

def pack_wlo_packet(body_bytes):
    """Đóng gói Magic Header 0xF4 0x44, Length LE và XOR 0xAD toàn bộ."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain = header + body_bytes
    return bytes(b ^ 0xAD for b in plain)

def build_login_packet(username, password):
    """Xây dựng gói tin Op: 0x3F Sub: 0x04 đăng nhập tài khoản."""
    u_bytes = username.encode("ascii")
    p_bytes = password.encode("ascii")
    token = bytes.fromhex("eedddbd9dedbd8d9")
    body = (
        bytes([0x3F, 0x04, 0xB0, 0x04])
        + bytes([len(u_bytes)]) + u_bytes
        + bytes([len(p_bytes)]) + p_bytes
        + bytes([0x07]) + token
    )
    return body

# ==============================================================================
# DANH SÁCH 20 CẶP Ô DI CHUYỂN TÚI ĐỒ (MOVE ITEM SLOTS)
# Giữ nguyên Ô 5 (MiniDragonfly) và Ô 9 (RegisVoucher)
# Chuyển dời toàn bộ các ô còn lại trong dải 1..22 về 26..45
# Lặp 50 lần mỗi cặp ô, số lượng = 1 món, delay 200ms
# ==============================================================================
MOVE_SLOT_PAIRS = [
    (1,  41, "Ô 01 -> Ô 41"),
    (2,  42, "Ô 02 -> Ô 42"),
    (3,  43, "Ô 03 -> Ô 43"),
    (4,  44, "Ô 04 -> Ô 44"),
    (6,  36, "Ô 06 -> Ô 36"),
    (7,  37, "Ô 07 -> Ô 37"),
    (8,  38, "Ô 08 -> Ô 38"),
    (10, 45, "Ô 10 -> Ô 45"),
    (11, 39, "Ô 11 -> Ô 39"),
    (12, 40, "Ô 12 -> Ô 40"),
    (13, 31, "Ô 13 -> Ô 31"),
    (14, 32, "Ô 14 -> Ô 32"),
    (15, 33, "Ô 15 -> Ô 33"),
    (16, 34, "Ô 16 -> Ô 34"),
    (17, 35, "Ô 17 -> Ô 35"),
    (18, 26, "Ô 18 -> Ô 26"),
    (19, 27, "Ô 19 -> Ô 27"),
    (20, 28, "Ô 20 -> Ô 28"),
    (21, 29, "Ô 21 -> Ô 29"),
    (22, 30, "Ô 22 -> Ô 30"),
]

# ==============================================================================
# DANH SÁCH BƯỚC THAO TÁC LỘ TRÌNH: MINIDRAGONFLY -> ATHENA -> CURSED PALACE
# ==============================================================================
ROUTE_STEPS = [
    # GIAI ĐOẠN 1: DÙNG MINIDRAGONFLY TẠI SLOT 1 & BAY SANG ATHENA
    {
        "phase": "PHASE 1: DÙNG MINIDRAGONFLY BAY SANG ATHENA",
        "desc": "Kích hoạt MiniDragonfly tại Ô Slot 1 (Menu GPS)",
        "packet": bytes.fromhex("17591f0102"),
        "delay": 1.10
    },
    {
        "desc": "Chọn điểm đến Thành phố Athena (0x0A)",
        "packet": bytes.fromhex("20020a"),
        "delay": 1.26
    },
    {
        "desc": "Đóng hộp thoại bay / Xác nhận nạp cảnh Athena",
        "packet": bytes.fromhex("2003"),
        "delay": 2.50
    },

    # GIAI ĐOẠN 2: ĐI BỘ QUA 14 TỌA ĐỘ TRONG THÀNH PHỐ ATHENA
    {
        "phase": "PHASE 2: DI CHUYỂN QUA THÀNH PHỐ ATHENA (14 TỌA ĐỘ)",
        "desc": "Bước 1: Đi tới tọa độ (1082, 2355)",
        "packet": bytes.fromhex("0601003a043309affb"),
        "delay": 1.32
    },
    {
        "desc": "Bước 2: Đi tới tọa độ (1002, 2135)",
        "packet": bytes.fromhex("060100ea035708afe1"),
        "delay": 2.34
    },
    {
        "desc": "Bước 3: Đi tới tọa độ (642, 2035)",
        "packet": bytes.fromhex("0601018202f307afd6"),
        "delay": 1.35
    },
    {
        "desc": "Bước 4: Đi tới tọa độ (522, 1975)",
        "packet": bytes.fromhex("0601010a02b707aff1"),
        "delay": 1.20
    },
    {
        "desc": "Bước 5: Đi tới tọa độ (442, 1775)",
        "packet": bytes.fromhex("060107ba01ef06aff1"),
        "delay": 1.14
    },
    {
        "desc": "Bước 6: Đi tới tọa độ (482, 1695)",
        "packet": bytes.fromhex("060107e2019f06afcc"),
        "delay": 1.35
    },
    {
        "desc": "Bước 7: Đi tới tọa độ (662, 1575)",
        "packet": bytes.fromhex("06010796022706afd8"),
        "delay": 1.20
    },
    {
        "desc": "Bước 8: Đi tới tọa độ (562, 1415)",
        "packet": bytes.fromhex("06010032028705affa"),
        "delay": 1.11
    },
    {
        "desc": "Bước 9: Đi tới tọa độ (402, 1275)",
        "packet": bytes.fromhex("0601019201fb04afd3"),
        "delay": 0.81
    },
    {
        "desc": "Bước 10: Đi tới tọa độ (482, 1155)",
        "packet": bytes.fromhex("060100e2018304afd7"),
        "delay": 1.47
    },
    {
        "desc": "Bước 11: Đi tới tọa độ (422, 915)",
        "packet": bytes.fromhex("060100a6019303afff"),
        "delay": 1.20
    },
    {
        "desc": "Bước 12: Đi tới tọa độ (322, 735)",
        "packet": bytes.fromhex("0601004201df02afd4"),
        "delay": 1.23
    },
    {
        "desc": "Bước 13: Đi tới tọa độ (322, 575)",
        "packet": bytes.fromhex("06010042013f02afd0"),
        "delay": 2.31
    },
    {
        "desc": "Bước 14: Đi tới sát cổng ra Athena (282, 455)",
        "packet": bytes.fromhex("0601001a01c701aff0"),
        "delay": 0.72
    },

    # GIAI ĐOẠN 3: BƯỚC QUA CỔNG DỊCH CHUYỂN RA HÀNH LANG
    {
        "phase": "PHASE 3: BƯỚC QUA CỔNG DỊCH CHUYỂN RA HÀNH LANG",
        "desc": "Đồng bộ trạng thái trước cổng",
        "packet": bytes.fromhex("14080e00"),
        "delay": 0.24
    },
    {
        "desc": "Bước vào cổng dịch chuyển tại (282, 463)",
        "packet": bytes.fromhex("0602091a01cf01afcb"),
        "delay": 0.12
    },
    {
        "desc": "Xác nhận đối thoại chuyển map (0x09)",
        "packet": bytes.fromhex("200209"),
        "delay": 2.00
    },

    # GIAI ĐOẠN 4: VƯỢT QUA NPC CHẮN ĐƯỜNG HÀNH LANG (ĐÁNH & BỎ CHẠY)
    {
        "phase": "PHASE 4: VƯỢT QUA NPC CHẮN ĐƯỜNG HÀNH LANG (ĐÁNH & BỎ CHẠY)",
        "desc": "Khiêu chiến NPC lính gác chắn đường hành lang (0x0B Sub: 0x02)",
        "packet": bytes.fromhex("0b0203ff3b00000100"),
        "delay": 1.50
    },
    {
        "desc": "Lệnh Bỏ Chạy cho Pet trong trận đấu (Slot 4 Row 2)",
        "packet": bytes.fromhex("32010402040289ea44c000"),
        "delay": 0.80
    },
    {
        "desc": "Lệnh Bỏ Chạy cho Nhân vật trong trận đấu (Slot 3 Row 2)",
        "packet": bytes.fromhex("32010302030289ea689600"),
        "delay": 1.30
    },

    # GIAI ĐOẠN 5: DI CHUYỂN TỚI TRƯỚC CỔNG CURSED PALACE & ĐỐI THOẠI LÍNH CANH
    {
        "phase": "PHASE 5: DI CHUYỂN TỚI TRƯỚC CỔNG CURSED PALACE & ĐỐI THOẠI LÍNH CANH",
        "desc": "Đi bộ trong hành lang thẳng tới trước cổng Cursed Palace (302, 455)",
        "packet": bytes.fromhex("0601022e01c701aff8"),
        "delay": 2.50
    },
    {
        "desc": "Kích hoạt đối thoại Lính canh tại cổng (Lượt 1)",
        "packet": bytes.fromhex("14020100"),
        "delay": 0.40
    },
    {
        "desc": "Xác nhận xem nội dung đối thoại Lính canh",
        "packet": bytes.fromhex("1406"),
        "delay": 0.20
    },
    {
        "desc": "Chuyển sang trang thoại kế tiếp (0x0C)",
        "packet": bytes.fromhex("20020c"),
        "delay": 1.25
    },
    {
        "desc": "Đồng bộ dữ liệu thoại",
        "packet": bytes.fromhex("14091e"),
        "delay": 0.12
    },
    {
        "desc": "Tiếp tục xem thoại",
        "packet": bytes.fromhex("1406"),
        "delay": 0.20
    },
    {
        "desc": "Chọn Dòng 1 trong Menu: Đồng ý vào Cursed Palace (0x0D)",
        "packet": bytes.fromhex("20020d"),
        "delay": 0.70
    },
    {
        "desc": "Đồng bộ dữ liệu thoại",
        "packet": bytes.fromhex("14091e"),
        "delay": 0.12
    },
    {
        "desc": "Tiếp tục xem thoại",
        "packet": bytes.fromhex("1406"),
        "delay": 0.20
    },
    {
        "desc": "Xác nhận đồng ý điều kiện 2 vé RegisVoucher (0x0D)",
        "packet": bytes.fromhex("20020d"),
        "delay": 0.90
    },
    {
        "desc": "Tiếp tục xem thoại xác nhận",
        "packet": bytes.fromhex("1406"),
        "delay": 0.20
    },
    {
        "desc": "Xác nhận thanh toán trừ 2 vé RegisVoucher (0x0D)",
        "packet": bytes.fromhex("20020d"),
        "delay": 0.85
    },
    {
        "desc": "Đóng xác nhận thanh toán vé",
        "packet": bytes.fromhex("1406"),
        "delay": 0.35
    },

    # GIAI ĐOẠN 6: BƯỚC VÀO TRONG ĐIỆN CURSED PALACE (DỊCH CHUYỂN TOÀN ĐỘI)
    {
        "phase": "PHASE 6: BƯỚC VÀO TRONG ĐIỆN CURSED PALACE (DỊCH CHUYỂN TOÀN ĐỘI)",
        "desc": "Kích hoạt dịch chuyển vào Cursed Palace (Toàn đội theo Leader)",
        "packet": bytes.fromhex("14080e00"),
        "delay": 1.50
    },
    {
        "desc": "Hoàn tất nạp cảnh mới",
        "packet": bytes.fromhex("200200"),
        "delay": 0.20
    },
    {
        "desc": "Đóng giao diện đối thoại",
        "packet": bytes.fromhex("20020a"),
        "delay": 0.20
    },
    {
        "desc": "Cập nhật lại chỉ số & UI nhân vật trong điện - HOÀN TẤT!",
        "packet": bytes.fromhex("1736"),
        "delay": 0.50
    }
]

# ==============================================================================
# FRIDA JAVASCRIPT INSTRUMENTATION CODE
# ==============================================================================
FRIDA_PARTY_JS = """
var activeSocket = -1;
var isInjected = false;

var ws2 = Process.getModuleByName('ws2_32.dll');
var sendPtr = ws2 ? ws2.getExportByName('send') : null;
var getpeernamePtr = ws2 ? ws2.getExportByName('getpeername') : null;

var sendFunc = sendPtr ? new NativeFunction(sendPtr, 'int', ['int', 'pointer', 'int', 'int']) : null;
var getpeernameFunc = getpeernamePtr ? new NativeFunction(getpeernamePtr, 'int', ['pointer', 'pointer', 'pointer']) : null;

// Quét tìm socket TCP kết nối tới port 6414 ngay lập tức
function scanActiveSocket() {
    if (activeSocket > 0) return activeSocket;
    if (!getpeernameFunc) return -1;
    var sockaddr = Memory.alloc(32);
    var lenPtr = Memory.alloc(4);
    for (var h = 4; h < 65536; h += 4) {
        lenPtr.writeU32(32);
        var ret = getpeernameFunc(ptr(h), sockaddr, lenPtr);
        if (ret === 0) {
            var port = (sockaddr.add(2).readU8() << 8) | sockaddr.add(3).readU8();
            if (port === 6414 || port > 1024) {
                activeSocket = h;
                return h;
            }
        }
    }
    return activeSocket;
}

// Hook recv trên cả wsock32.dll và ws2_32.dll
function hookRecv(modName) {
    try {
        var mod = Process.getModuleByName(modName);
        if (!mod) return;
        var rPtr = mod.getExportByName('recv');
        if (!rPtr) return;
        Interceptor.attach(rPtr, {
            onEnter: function(args) {
                var sock = args[0].toInt32();
                if (sock > 0) activeSocket = sock;
                this.sock = sock;
                this.buf = args[1];
            },
            onLeave: function(retval) {
                var len = retval.toInt32();
                if (len > 0) {
                    try {
                        var buf = this.buf.readByteArray(len);
                        send({dir: 'recv', len: len, sock: this.sock}, buf);
                    } catch(e) {}
                }
            }
        });
    } catch(e) {}
}

function hookSend(modName) {
    try {
        var mod = Process.getModuleByName(modName);
        if (!mod) return;
        var sPtr = mod.getExportByName('send');
        if (!sPtr) return;
        Interceptor.attach(sPtr, {
            onEnter: function(args) {
                var sock = args[0].toInt32();
                if (sock > 0) activeSocket = sock;
                if (isInjected) return;
                var len = args[2].toInt32();
                if (len > 0) {
                    try {
                        var buf = args[1].readByteArray(len);
                        send({dir: 'send', len: len, sock: sock}, buf);
                    } catch(e) {}
                }
            }
        });
    } catch(e) {}
}

hookRecv('wsock32.dll');
hookRecv('ws2_32.dll');
hookSend('ws2_32.dll');

scanActiveSocket();

function doSendRaw(hexBytes) {
    if (activeSocket <= 0) {
        scanActiveSocket();
    }
    if (activeSocket <= 0) {
        return {success: false, error: "Chưa tìm thấy socket active"};
    }
    if (!sendFunc) {
        return {success: false, error: "Không tìm thấy hàm send trong ws2_32.dll"};
    }
    var raw = [];
    for (var i = 0; i < hexBytes.length; i += 2) {
        raw.push(parseInt(hexBytes.substr(i, 2), 16));
    }
    var buf = Memory.alloc(raw.length);
    buf.writeByteArray(raw);
    isInjected = true;
    try {
        var ret = sendFunc(activeSocket, buf, raw.length, 0);
        isInjected = false;
        return {success: true, ret: ret, sock: activeSocket};
    } catch(e) {
        isInjected = false;
        return {success: false, error: e.toString()};
    }
}

var cachedBagBase = null;

function readBagMemory(forceRescan) {
    // 1. Kiểm tra địa chỉ đã lưu trong bộ nhớ đệm nếu còn hợp lệ và không yêu cầu quét lại
    if (!forceRescan && cachedBagBase) {
        try {
            var items = {};
            for (var s = 1; s <= 50; s++) {
                var entry = cachedBagBase.add((s - 1) * 4);
                var slot = entry.readU8();
                var code = entry.add(1).readU16();
                var qty = entry.add(3).readU8();
                if (slot === s && code > 0 && qty > 0) {
                    items[s] = {code: code, qty: qty};
                }
            }
            if (Object.keys(items).length >= 1) {
                return {success: true, cached: true, items: items};
            }
        } catch(e) {
            cachedBagBase = null;
        }
    }

    // 2. Bộ quét RAM phổ quát thông minh (Smart Universal Bag Scanner):
    // Quét mảng 50 ô đồ thật, loại bỏ 100% Tủ Đồ Lều và Snapshot cũ
    var ranges = Process.enumerateRanges('rw-');
    var sigs = ['32 00 00 00 00 01', '32 00 00 00 00 00 00 00 00'];
    var candidates = [];

    for (var si = 0; si < sigs.length; si++) {
        var sPattern = sigs[si];
        for (var i = 0; i < ranges.length; i++) {
            var r = ranges[i];
            if (r.size > 2 * 1024 * 1024) continue;
            try {
                var m = Memory.scanSync(r.base, r.size, sPattern);
                for (var j = 0; j < m.length; j++) {
                    var base = m[j].address.add(5);
                    var items = {};
                    var count50 = 0;
                    for (var s = 1; s <= 50; s++) {
                        var entry = base.add((s - 1) * 4);
                        var slot = entry.readU8();
                        var code = entry.add(1).readU16();
                        var qty = entry.add(3).readU8();
                        if (slot === s && code > 0 && qty > 0) {
                            items[s] = {code: code, qty: qty};
                            if (qty === 50) count50++;
                        }
                    }
                    var cnt = Object.keys(items).length;
                    if (cnt >= 2) {
                        // Loại bỏ Tủ Đồ Lều (Cabinet Storage): Tủ đồ hầu như 100% đều là stack 50 món
                        var ratio50 = count50 / cnt;
                        if (ratio50 < 0.70) {
                            candidates.push({
                                base: base,
                                count: cnt,
                                items: items
                            });
                        }
                    }
                }
            } catch(e) {}
        }
        if (candidates.length > 0) break;
    }

    if (candidates.length === 0) return {success: false, items: {}};

    // Sắp xếp các candidates hợp lệ:
    // 1. Ưu tiên buffer có số lượng món nhiều nhất (Active Buffer chứa toàn bộ item mới nhận)
    // 2. Nếu bằng nhau, ưu tiên buffer có số vé RegisVoucher (Slot 2) nhỏ hơn (đã bị trừ vé khi vào điện)
    candidates.sort(function(a, b) {
        if (b.count !== a.count) {
            return b.count - a.count;
        }
        var vA = (a.items[2] && a.items[2].code === 0x75AC) ? a.items[2].qty : 999;
        var vB = (b.items[2] && b.items[2].code === 0x75AC) ? b.items[2].qty : 999;
        if (vA !== vB) {
            return vA - vB;
        }
        return b.base.compare(a.base);
    });

    var best = candidates[0];
    cachedBagBase = best.base;
    return {success: true, cached: false, items: best.items};
}

function readPetInfo() {
    try {
        var playerPtr = ptr('0x8b76dc').readPointer().readPointer();
        if (playerPtr.isNull()) return {success: false};
        var activeSlot = playerPtr.add(0x2230).readU8();
        var pets = [];
        for (var i = 1; i <= 4; i++) {
            var pSlot = playerPtr.add(0x21e8 + i * 4).readPointer();
            if (!pSlot.isNull()) {
                var pId = pSlot.add(4).readU32();
                var pIdx = pSlot.add(0x21bc).readU8();
                var exists = pSlot.add(0xb0).readU8();
                var curHp = pSlot.add(0x158).readU32();
                var maxHp = pSlot.add(0x84).readU32();
                if (pId > 0 && exists > 0) {
                    pets.push({
                        slot: i,
                        id: pId,
                        idx: pIdx,
                        curHp: curHp,
                        maxHp: maxHp,
                        is_active: (activeSlot === i)
                    });
                }
            }
        }
        return {
            success: true,
            activeSlot: activeSlot,
            pets: pets
        };
    } catch(e) {
        return {success: false, error: e.toString()};
    }
}


rpc.exports = {
    getsocket: function() { 
        if (activeSocket <= 0) scanActiveSocket();
        return activeSocket; 
    },
    sendraw: function(hexBytes) { 
        return doSendRaw(hexBytes); 
    },
    readbag: function(forceRescan) {
        return readBagMemory(forceRescan);
    },
    readpetinfo: function() {
        return readPetInfo();
    }
};
"""

# ==============================================================================
# QUẢN LÝ TIẾN TRÌNH CLIENT (NODE)
# ==============================================================================
class PartyClientNode:
    def __init__(self, name, pid, manager, char_id=None, account=None, password="111111", slot=1):
        self.name = name
        self.pid = pid
        self.manager = manager
        self.char_id = char_id
        self.account = account or get_default_account_from_proc_name(name)
        self.password = password
        self.slot = slot
        self.is_leader = False
        self.session = None
        self.script = None
        self.active_socket = -1
        self.in_party = False
        self.in_combat = False
        self.relog_in_progress = False
        self.c2s_buf = bytearray()
        self.s2c_buf = bytearray()

        # Trạng thái theo dõi NPC & phản hồi Server
        self.npc_dialog_received = False
        self.voucher_deducted_received = False
        self.cursed_palace_map_received = False

        # Bộ nhớ đệm danh sách vật phẩm trong túi đồ (Slot 1..50)
        self.inventory = {}
        self.inventory_received = False

        # Trạng thái theo dõi Pet xuất chiến
        base_nick = self.name.lower().replace("alogin-", "").replace(".exe", "")
        self.designated_pet_id = DEFAULT_COMBAT_PETS.get(base_nick)
        self.pet_needs_resummon = False

    def feed_dissector(self, raw_bytes, buffer):
        dec = bytearray(b ^ 0xAD for b in raw_bytes)
        buffer.extend(dec)
        packets = []
        while len(buffer) >= 4:
            if buffer[0] != 0xF4 or buffer[1] != 0x44:
                idx = buffer.find(bytes([0xF4, 0x44]))
                if idx == -1:
                    buffer.clear()
                    break
                del buffer[:idx]
                if len(buffer) < 4:
                    break
            payload_len = struct.unpack("<H", buffer[2:4])[0]
            total_len = 4 + payload_len
            if len(buffer) < total_len:
                break
            pkt_raw = bytes(buffer[:total_len])
            body = pkt_raw[4:]
            del buffer[:total_len]
            opcode = body[0] if len(body) > 0 else None
            subcode = body[1] if len(body) > 1 else None
            data = body[2:] if len(body) > 2 else b''
            packets.append((opcode, subcode, data, pkt_raw))
        return packets

    def send_packet(self, body_bytes):
        enc = pack_wlo_packet(body_bytes)
        try:
            res = self.script.exports_sync.sendraw(enc.hex())
            return res
        except Exception as e:
            return {"success": False, "error": str(e)}

    def accept_party(self, partner_id):
        """Gửi C->S Op: 0x0D Sub: 0x03 [0x01, Partner_ID (4B LE)]"""
        body = bytes([0x0D, 0x03, 0x01]) + struct.pack("<I", partner_id)
        res = self.send_packet(body)
        self.manager.log_event("SUCCESS", self.name, f"Đã chấp thuận vào tổ đội của ID 0x{partner_id:08X} (Kết quả: {res})")

    def request_join_or_invite(self, target_id):
        """Gửi C->S Op: 0x0D Sub: 0x01 [Target_ID (4B LE)] (Xin vào nhóm hoặc Mời)"""
        body = bytes([0x0D, 0x01]) + struct.pack("<I", target_id)
        res = self.send_packet(body)
        self.manager.log_event("C2S", self.name, f"Đã gửi yêu cầu tổ đội tới ID 0x{target_id:08X} (Kết quả: {res})")
        return res

    def transfer_leader(self, new_leader_id):
        """Gửi C->S Op: 0x0D Sub: 0x0A [0x01, NewLeaderID]"""
        body = bytes([0x0D, 0x0A, 0x01]) + struct.pack("<I", new_leader_id)
        res = self.send_packet(body)
        self.manager.log_event("C2S", self.name, f"Đã gửi yêu cầu chuyển Đội trưởng cho ID 0x{new_leader_id:08X} (Kết quả: {res})")
        return res

    def leave_party(self):
        """Rời khỏi nhóm hoặc giải tán nhóm nếu là Đội trưởng."""
        if self.is_leader and self.char_id:
            body = bytes([0x0D, 0x04]) + struct.pack("<I", self.char_id)
            desc = "giải tán tổ đội"
        else:
            body = bytes([0x0D, 0x02])
            desc = "rời tổ đội"
        res = self.send_packet(body)
        self.manager.log_event("C2S", self.name, f"Đã gửi lệnh {desc} (Kết quả: {res})")
        self.in_party = False
        self.manager.notify_state_changed()
        return res

    def read_bag_memory(self):
        """Đọc trực tiếp mảng 50 ô túi đồ từ bộ nhớ RAM của game client (Native Bag Memory)."""
        if not self.script:
            return False
        try:
            res = self.script.exports_sync.readbag()
            if res and res.get("success") and len(res.get("items", {})) > 0:
                self.inventory = {}
                for s_str, it in res["items"].items():
                    self.inventory[int(s_str)] = {"code": it["code"], "qty": it["qty"]}
                self.inventory_received = True
                return True
        except Exception as e:
            self.manager.log_event("WARNING", self.name, f"Lỗi quét túi đồ RAM: {e}")
        return False

    def move_item(self, src_slot, qty, dest_slot):
        """Gửi C->S Op: 0x17 Sub: 0x0A [src_slot, qty, dest_slot] di chuyển vật phẩm trong túi đồ."""
        body = bytes([0x17, 0x0A, src_slot, qty, dest_slot])
        return self.send_packet(body)

    def do_relog(self, account=None, password=None, slot=None):
        """Quy trình tự động Logout & Login lại để nhận diện Char ID."""
        if self.relog_in_progress:
            self.manager.log_event("WARNING", self.name, "Quá trình Relog đang thực hiện, vui lòng chờ...")
            return

        def _relog_thread():
            self.relog_in_progress = True
            acc = account or self.account
            pwd = password or self.password
            s = slot or self.slot
            self.manager.log_event("PARTY", self.name, f"🔄 BẮT ĐẦU RELOG: Tài khoản {acc} (Slot {s})...")

            # 1. Gửi Op: 0x00 (Logout / Chọn lại nhân vật)
            self.manager.log_event("C2S", self.name, "[1/4] Gửi Op: 0x00 (Đăng xuất / Chọn lại nhân vật)...")
            self.send_packet(bytes([0x00]))
            time.sleep(1.2)

            # 2. Gửi Op: 0x3F Sub: 0x04 (Đăng nhập tài khoản)
            self.manager.log_event("C2S", self.name, f"[2/4] Gửi Op: 0x3F Sub: 0x04 (Đăng nhập tài khoản {acc})...")
            login_body = build_login_packet(acc, pwd)
            self.send_packet(login_body)
            time.sleep(1.2)

            # 3. Gửi Op: 0x3F Sub: 0x02 (Chọn nhân vật Slot s)
            self.manager.log_event("C2S", self.name, f"[3/4] Gửi Op: 0x3F Sub: 0x02 (Chọn nhân vật Slot {s})...")
            self.send_packet(bytes([0x3F, 0x02, s]))
            time.sleep(0.5)

            # 4. Gửi chuỗi bắt tay vào thế giới game
            self.manager.log_event("C2S", self.name, "[4/4] Gửi chuỗi bắt tay vào thế giới (Enter World Handshake)...")
            self.send_packet(bytes([0x17, 0x4D]))
            time.sleep(0.1)
            self.send_packet(bytes([0x05, 0x07, 0x00]))
            time.sleep(0.1)
            self.send_packet(bytes([0x59, 0x00, 0x4D, 0x00, 0x00, 0x00]))
            time.sleep(0.1)
            self.send_packet(bytes([0x5C, 0x01]))
            time.sleep(0.1)
            self.send_packet(bytes([0x17, 0x36]))
            time.sleep(0.1)
            self.send_packet(bytes([0xB7, 0x11, 0x00]))

            time.sleep(1.5)
            self.relog_in_progress = False
            if self.char_id:
                self.manager.log_event("SUCCESS", self.name, f"★ RELOG HOÀN TẤT! Char ID = 0x{self.char_id:08X} (Dec: {self.char_id})")
            else:
                self.manager.log_event("INFO", self.name, "Đã hoàn tất gửi chuỗi lệnh Relog. Đang chờ gói tin xác nhận...")
            self.manager.notify_state_changed()

        threading.Thread(target=_relog_thread, daemon=True).start()

    def relog_sync(self, account=None, password=None, slot=None, timeout=8.0):
        """Thực hiện Relog và chờ máy chủ nạp gói khởi tạo túi đồ S->C Op: 0x17 Sub: 0x05."""
        self.inventory_received = False
        self.inventory = {}
        self.relog_in_progress = True
        acc = account or self.account
        pwd = password or self.password
        s = slot or self.slot

        self.manager.log_event("PARTY", self.name, f"🔄 BẮT ĐẦU RELOG: Tài khoản {acc} (Slot {s})...")
        
        # 1. Gửi Op: 0x00 (Logout)
        self.manager.log_event("C2S", self.name, "[1/4] Gửi Op: 0x00 (Đăng xuất / Chọn lại nhân vật)...")
        self.send_packet(bytes([0x00]))
        time.sleep(1.2)

        # 2. Gửi Op: 0x3F Sub: 0x04 (Đăng nhập tài khoản)
        self.manager.log_event("C2S", self.name, f"[2/4] Gửi Op: 0x3F Sub: 0x04 (Đăng nhập tài khoản {acc})...")
        login_body = build_login_packet(acc, pwd)
        self.send_packet(login_body)
        time.sleep(1.2)

        # 3. Gửi Op: 0x3F Sub: 0x02 (Chọn nhân vật Slot s)
        self.manager.log_event("C2S", self.name, f"[3/4] Gửi Op: 0x3F Sub: 0x02 (Chọn nhân vật Slot {s})...")
        self.send_packet(bytes([0x3F, 0x02, s]))
        time.sleep(0.5)

        # 4. Gửi chuỗi bắt tay vào thế giới game
        self.manager.log_event("C2S", self.name, "[4/4] Gửi chuỗi bắt tay vào thế giới (Enter World Handshake)...")
        self.send_packet(bytes([0x17, 0x4D]))
        time.sleep(0.1)
        self.send_packet(bytes([0x05, 0x07, 0x00]))
        time.sleep(0.1)
        self.send_packet(bytes([0x59, 0x00, 0x4D, 0x00, 0x00, 0x00]))
        time.sleep(0.1)
        self.send_packet(bytes([0x5C, 0x01]))
        time.sleep(0.1)
        self.send_packet(bytes([0x17, 0x36]))
        time.sleep(0.1)
        self.send_packet(bytes([0xB7, 0x11, 0x00]))

        # Chờ nhận gói tin túi đồ Op: 0x17 Sub: 0x05
        self.manager.log_event("INFO", self.name, "⏳ Đang chờ máy chủ nạp danh sách 50 ô túi đồ (Op: 0x17 Sub: 0x05)...")
        wait_start = time.time()
        while time.time() - wait_start < timeout:
            if self.inventory_received and len(self.inventory) > 0:
                break
            time.sleep(0.1)

        self.relog_in_progress = False
        self.manager.notify_state_changed()
        return self.inventory_received

    def on_message(self, message, raw_data):
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "recv")
        sock = payload.get("sock", -1)
        if sock > 0:
            if self.active_socket != sock:
                self.active_socket = sock
                self.manager.notify_state_changed()

        is_send = (dir_name == "send")
        buffer = self.c2s_buf if is_send else self.s2c_buf
        packets = self.feed_dissector(raw_data, buffer)

        for opcode, subcode, data, raw_pkt in packets:
            direction = "C->S" if is_send else "S->C"

            # 1. Bắt gói tin nhận diện Char ID khi Login:
            # S->C Op: 0x05 Sub: 0x08 [CharID (4B LE), 0x00]
            if direction == "S->C" and opcode == 0x05 and subcode == 0x08 and len(data) >= 4:
                cid = struct.unpack("<I", data[:4])[0]
                if cid > 1000:
                    self.char_id = cid
                    self.manager.register_char_id(self.name, cid)
                    self.manager.log_event("SUCCESS", self.name, f"★ ĐÃ NHẬN DIỆN CHAR ID: 0x{cid:08X} (Dec: {cid})")

            elif direction == "S->C" and opcode == 0x05 and subcode == 0x1E and len(data) >= 10:
                cid = struct.unpack("<I", data[6:10])[0]
                if cid > 1000:
                    self.char_id = cid
                    self.manager.register_char_id(self.name, cid)
                    self.manager.log_event("SUCCESS", self.name, f"★ ĐÃ NHẬN DIỆN CHAR ID: 0x{cid:08X} (Dec: {cid})")

            # S->C Op: 0x17 Sub: 0x4D (Attributes sync)
            elif direction == "S->C" and opcode == 0x17 and subcode == 0x4D and len(data) >= 4:
                cid = struct.unpack("<I", data[:4])[0]
                if cid > 1000 and not self.char_id:
                    self.char_id = cid
                    self.manager.register_char_id(self.name, cid)

            # Bắt gói tin khởi tạo túi đồ từ Server khi Đăng nhập / Đổi map:
            # S->C Op: 0x17 Sub: 0x05 (Inventory Snapshot: 31 bytes / entry)
            elif direction == "S->C" and opcode == 0x17 and subcode == 0x05:
                entry_len = 31
                num_entries = len(data) // entry_len
                self.inventory = {}
                for i in range(num_entries):
                    entry = data[i * entry_len : (i + 1) * entry_len]
                    slot = entry[0]
                    code = struct.unpack("<H", entry[1:3])[0]
                    qty = entry[3]
                    self.inventory[slot] = {"code": code, "qty": qty}
                self.inventory_received = True
                self.manager.log_event("SUCCESS", self.name, f"🎒 [SERVER] Đã đồng bộ túi đồ ({len(self.inventory)} món đồ) từ máy chủ!")

            # Cập nhật di chuyển vật phẩm: S->C Op: 0x17 Sub: 0x0A [src_slot, qty, dest_slot]
            elif direction == "S->C" and opcode == 0x17 and subcode == 0x0A and len(data) >= 3:
                src_slot, move_qty, dest_slot = data[0], data[1], data[2]
                if src_slot in self.inventory:
                    src_code = self.inventory[src_slot]["code"]
                    src_cur_qty = self.inventory[src_slot]["qty"]
                    if dest_slot in self.inventory and self.inventory[dest_slot]["code"] == src_code:
                        self.inventory[dest_slot]["qty"] += move_qty
                    else:
                        self.inventory[dest_slot] = {"code": src_code, "qty": move_qty}
                    if src_cur_qty <= move_qty:
                        self.inventory.pop(src_slot, None)
                    else:
                        self.inventory[src_slot]["qty"] -= move_qty

            # 2. Xử lý gói tin Op: 0x0D (Party System)
            elif opcode == 0x0D:
                hex_data = data.hex()
                self.manager.log_packet(direction, self.name, opcode, subcode, hex_data)

                # Khi nhận yêu cầu tổ đội: S->C Op: 0x0D Sub: 0x01 [Sender_ID]
                if direction == "S->C" and subcode == 0x01 and len(data) >= 4:
                    sender_id = struct.unpack("<I", data[:4])[0]
                    self.manager.log_event("PARTY", self.name, f"Nhận yêu cầu vào nhóm từ ID: 0x{sender_id:08X}")
                    
                    # Cập nhật Char ID cho node gửi nếu chưa biết
                    self.manager.learn_char_id(sender_id, exclude_name=self.name)

                    # Tự động chấp thuận nếu bật Auto-Accept
                    if self.manager.auto_accept_var.get():
                        def do_accept():
                            time.sleep(0.04)
                            self.accept_party(sender_id)
                        threading.Thread(target=do_accept, daemon=True).start()

                # Khi Server xác nhận chấp thuận: S->C Op: 0x0D Sub: 0x03 [0x01, Member_ID]
                elif direction == "S->C" and subcode == 0x03 and len(data) >= 5:
                    status = data[0]
                    mem_id = struct.unpack("<I", data[1:5])[0]
                    self.in_party = True
                    self.manager.log_event("SUCCESS", self.name, f"★ Thành viên 0x{mem_id:08X} đã vào tổ đội (Status: {status})")
                    self.manager.notify_state_changed()

                # Khi Server đồng bộ cặp thành viên: S->C Op: 0x0D Sub: 0x05 [Member_ID, Leader_ID]
                elif direction == "S->C" and subcode == 0x05 and len(data) >= 8:
                    mem_id = struct.unpack("<I", data[:4])[0]
                    lead_id = struct.unpack("<I", data[4:8])[0]
                    self.in_party = True
                    self.manager.log_event("PARTY", self.name, f"Đồng bộ đội hình: TV 0x{mem_id:08X} | Đội trưởng 0x{lead_id:08X}")
                    self.manager.notify_state_changed()

                # Khi Server đồng bộ giao diện: S->C Op: 0x0D Sub: 0x06 [Member_ID, 0x01, Leader_ID]
                elif direction == "S->C" and subcode == 0x06 and len(data) >= 9:
                    mem_id = struct.unpack("<I", data[:4])[0]
                    lead_id = struct.unpack("<I", data[5:9])[0]
                    self.in_party = True
                    self.manager.log_event("PARTY", self.name, f"Giao diện tổ đội cập nhật: TV 0x{mem_id:08X} trong đội 0x{lead_id:08X}")
                    self.manager.notify_state_changed()

                # Khi chuyển đội trưởng: S->C Op: 0x0D Sub: 0x0F
                elif direction == "S->C" and subcode == 0x0F:
                    if len(data) >= 5 and data[0] == 0x01:
                        old_lead = struct.unpack("<I", data[1:5])[0]
                        self.manager.log_event("PARTY", self.name, f"Nhận đề nghị nhường Đội trưởng từ 0x{old_lead:08X}. Đang tự động nhận...")
                        def do_accept_lead():
                            time.sleep(0.05)
                            self.send_packet(bytes([0x0D, 0x0A, 0x03]))
                        threading.Thread(target=do_accept_lead, daemon=True).start()
                    elif len(data) >= 9 and data[0] == 0x03:
                        new_lead = struct.unpack("<I", data[1:5])[0]
                        old_lead = struct.unpack("<I", data[5:9])[0]
                        self.manager.log_event("SUCCESS", self.name, f"★ ĐÃ CHUYỂN ĐỘI TRƯỞNG: Mới 0x{new_lead:08X} (Cũ: 0x{old_lead:08X})")
                        self.manager.update_leader_by_id(new_lead)

                # Khi giải tán nhóm: S->C Op: 0x0D Sub: 0x04
                elif direction == "S->C" and subcode == 0x04:
                    self.in_party = False
                    self.manager.log_event("PARTY", self.name, "Tổ đội đã giải tán.")
                    self.manager.notify_state_changed()

                # Khi rời nhóm: S->C Op: 0x0D Sub: 0x02
                elif direction == "S->C" and subcode == 0x02:
                    self.in_party = False
                    self.manager.log_event("PARTY", self.name, "Đã rời khỏi tổ đội.")
                    self.manager.notify_state_changed()

            # Bắt gói tin đối thoại NPC từ Server:
            # Op: 0x14 Sub: 0x01 (NPC Dialog Text)
            # Op: 0x18 Sub: 0x05 (NPC Menu/Choice Popup)
            # Op: 0x16 Sub: 0x01 (NPC Quest/Trigger)
            elif opcode == 0x14 and subcode == 0x01:
                self.npc_dialog_received = True
                self.manager.log_event("SUCCESS", self.name, "💬 [SERVER] Nhận gói thoại NPC (Op: 0x14 Sub: 0x01) -> Xác nhận đang đối thoại với NPC thành công!")

            elif opcode == 0x18 and subcode == 0x05:
                self.npc_dialog_received = True
                self.manager.log_event("SUCCESS", self.name, "💬 [SERVER] Nhận menu lựa chọn NPC (Op: 0x18 Sub: 0x05)")

            elif opcode == 0x16 and subcode == 0x01:
                self.npc_dialog_received = True
                if getattr(self.manager, "auto_treasure_running", False):
                    self.manager.auto_treasure_chests_unlocked = True
                    self.manager.log_event("SUCCESS", self.name, "🔓 [MỞ KHÓA RƯƠNG] Server đã mở khóa tất cả rương còn lại trong phòng!")

            # Bắt gói cập nhật số lượng / trừ 2 vé RegisVoucher: Op: 0x17 Sub: 0x09 [slot, remain]
            elif opcode == 0x17 and subcode == 0x09 and len(data) >= 2:
                slot_deducted = data[0]
                remain_n = data[1]
                if slot_deducted in self.inventory:
                    if remain_n == 0:
                        del self.inventory[slot_deducted]
                    else:
                        self.inventory[slot_deducted]["qty"] = remain_n

                if remain_n == 0x02:
                    self.voucher_deducted_received = True
                    self.manager.log_event("SUCCESS", self.name, f"★ [SERVER] ĐÃ XÁC NHẬN TRỪ 2 VÉ REGISVOUCHER TẠI Ô SLOT {slot_deducted} THÀNH CÔNG! ★")

            # Bắt nạp cảnh Cursed Palace: Op: 0x16 Sub: 0x04
            elif opcode == 0x16 and subcode == 0x04:
                self.cursed_palace_map_received = True
                self.manager.log_event("SUCCESS", self.name, "★ [SERVER] ĐÃ NẠP XONG BẢN ĐỒ CẢNH MỚI (CURSED PALACE)! ★")

            # Bắt gói trao phần thưởng từ Server: Op: 0x17 Sub: 0x06
            elif opcode == 0x17 and subcode == 0x06 and len(data) >= 2:
                item_id = struct.unpack("<H", data[:2])[0]
                qty = data[2] if len(data) >= 3 else 1
                if item_id in ALL_TRASH_REWARDS:
                    info = ALL_TRASH_REWARDS[item_id]
                    self.manager.log_event("WARNING", self.name, f"🎁 [NHẬN THƯỞNG RÁC] {info['name']} (Mã: 0x{item_id:04X}) x{qty} [{info['round']}] -> Tiến hành quét RAM vứt ngay!")
                    threading.Thread(target=self._auto_discard_trash_item, args=(item_id, info), daemon=True).start()
                elif item_id in NATIONAL_TREASURE_KEYS:
                    key_name = NATIONAL_TREASURE_KEYS[item_id]
                    self.manager.auto_treasure_key_found = True
                    self.manager.log_event("SUCCESS", self.name, f"👑 [CHÌA KHÓA QUỐC BẢO!] Nhận được {key_name} x{qty}!")
                    self.manager.log_event("SUCCESS", self.name, f"✨ [HOÀN TẤT PHÒNG] ĐÃ CÓ CHÌA KHÓA! DỪNG MỞ RƯƠNG TRONG PHÒNG NÀY NGAY LẬP TỨC!")

            # Bắt sự kiện Pet bị rút về / nghỉ ngơi do hết máu: Op: 0x0E Sub: 0x09 hoặc Op: 0x05 Sub: 0x08
            elif (opcode == 0x0E and subcode == 0x09) or (opcode == 0x05 and subcode == 0x08):
                if len(data) >= 5:
                    pet_id, status = struct.unpack("<IB", data[:5])
                    if status == 0x03:
                        self.pet_needs_resummon = True
                        self.manager.log_event("WARNING", self.name, f"🐾 [PET HẾT MÁU / RÚT VỀ] Pet (ID: 0x{pet_id:04X}) đã bị hạ gục -> Sẽ tự động gọi lại ngay khi hết trận!")
                    elif status == 0x00:
                        self.pet_needs_resummon = False

            # Bắt vào trận đánh: Op: 0x0B Sub: 0xFA hoặc 0x02
            elif opcode == 0x0B and subcode in (0xFA, 0x02):
                self.in_combat = True
                if not getattr(self.manager, "in_battle", False):
                    self.manager.in_battle = True
                    self.manager.combat_turn = 0
                    self.manager.log_event("WARNING", self.name, "⚔️ [QUÁI XUẤT HIỆN] Quái vật xuất hiện từ rương! Bắt đầu trận đánh...")
                    if getattr(self.manager, "auto_treasure_running", False):
                        threading.Thread(target=self.manager._auto_treasure_combat_loop, daemon=True).start()

            # Bắt kết thúc trận đánh / Thoát trận thành công: Op: 0x0B Sub: 0x00
            elif opcode == 0x0B and subcode == 0x00:
                self.in_combat = False
                self.manager.in_battle = False
                self.manager.log_event("SUCCESS", self.name, "⚔️ [SERVER] Đã kết thúc / thoát khỏi trận đánh thành công.")
                threading.Thread(target=self._safety_trash_sweep, daemon=True).start()
                threading.Thread(target=self._check_and_resummon_pet, daemon=True).start()

    def _auto_discard_trash_item(self, target_code, info):
        """Quét RAM và vứt ngay lập tức một món rác khi vừa nhận thưởng"""
        time.sleep(0.3)
        try:
            bag_res = self.script.exports_sync.readbag(True)
            if not bag_res or not bag_res.get("success"):
                time.sleep(0.2)
                bag_res = self.script.exports_sync.readbag(True)
            if bag_res and bag_res.get("success"):
                items = bag_res.get("items", {})
                for slot_str, it in items.items():
                    if it.get("code") == target_code:
                        slot_n = int(slot_str)
                        qty = it.get("qty", 1)
                        pkt_req = pack_wlo_packet(bytes([0x17, 0x03, slot_n, qty, 0x01]))
                        self.script.exports_sync.sendraw(pkt_req.hex())
                        time.sleep(0.12)
                        pkt_cfm = pack_wlo_packet(bytes([0x17, 0x7C, slot_n, qty, 0x02]))
                        self.script.exports_sync.sendraw(pkt_cfm.hex())
                        self.manager.log_event("SUCCESS", self.name, f"🗑️ [VỨT RÁC TỨC THÌ] Đã quét RAM (Ô {slot_n:02d}) và vứt sạch: {info['name']} (x{qty})!")
        except Exception as e:
            self.manager.log_event("ERROR", self.name, f"Lỗi vứt rác tức thì 0x{target_code:04X}: {e}")

    def sweep_trash(self):
        """Quét RAM và dọn sạch toàn bộ vật phẩm rác trong túi đồ của client này"""
        try:
            if not self.script:
                self.manager.log_event("WARNING", self.name, "Chưa kết nối Frida, không thể quét túi đồ.")
                return 0

            bag_res = self.script.exports_sync.readbag(True)
            if not bag_res or not bag_res.get("success"):
                time.sleep(0.3)
                bag_res = self.script.exports_sync.readbag(True)

            if not bag_res or not bag_res.get("success"):
                self.manager.log_event("WARNING", self.name, "Không đọc được mảng túi đồ trong RAM.")
                return 0

            items = bag_res.get("items", {})
            trash_found = []
            for slot_str, it in items.items():
                code = it.get("code")
                if code in ALL_TRASH_REWARDS:
                    trash_found.append((int(slot_str), code, it.get("qty", 1)))

            if not trash_found:
                self.manager.log_event("INFO", self.name, "✨ Túi đồ sạch, không phát hiện vật phẩm rác nào.")
                return 0

            discarded = 0
            for slot_n, code, qty in trash_found:
                info = ALL_TRASH_REWARDS[code]
                pkt_req = pack_wlo_packet(bytes([0x17, 0x03, slot_n, qty, 0x01]))
                self.script.exports_sync.sendraw(pkt_req.hex())
                time.sleep(0.12)
                pkt_cfm = pack_wlo_packet(bytes([0x17, 0x7C, slot_n, qty, 0x02]))
                self.script.exports_sync.sendraw(pkt_cfm.hex())
                discarded += 1
                self.manager.log_event("SUCCESS", self.name, f"🗑️ [ĐÃ VỨT] {info['name']} tại Ô {slot_n:02d} (x{qty})")
                time.sleep(0.15)

            # Đọc lại RAM sau khi vứt để xác nhận
            time.sleep(0.3)
            bag_after = self.script.exports_sync.readbag(True)
            if bag_after and bag_after.get("success"):
                items_after = bag_after.get("items", {})
                still_has = [s for s, it in items_after.items() if it.get("code") in ALL_TRASH_REWARDS]
                if not still_has:
                    self.manager.log_event("SUCCESS", self.name, f"✨ [HOÀN TẤT DỌN TÚI] Đã xóa sạch {discarded} món rác khỏi túi đồ 100%!")
                else:
                    self.manager.log_event("WARNING", self.name, f"Vẫn còn sót rác tại các ô: {still_has}. Hãy thử dọn lại.")
            return discarded
        except Exception as e:
            self.manager.log_event("ERROR", self.name, f"Lỗi dọn rác túi đồ: {e}")
            return 0

    def _safety_trash_sweep(self):
        """Quét dọn an toàn ngay sau khi kết thúc trận đánh"""
        time.sleep(0.8)
        self.sweep_trash()

    def _check_and_resummon_pet(self, force=False):
        """Kiểm tra và tự động xuất chiến lại Pet nếu bị đánh hết máu trong trận (C->S Op: 0x13 Sub: 0x01)"""
        time.sleep(0.5 if force else 0.9)
        try:
            if not self.script:
                return
            info = self.script.exports_sync.readpetinfo()
            if not info or not info.get("success"):
                return
            active_slot = info.get("activeSlot", 0)
            pets = info.get("pets", [])

            base_nick = self.name.lower().replace("alogin-", "").replace(".exe", "")
            target_pet_id = DEFAULT_COMBAT_PETS.get(base_nick)
            target_slot = DEFAULT_COMBAT_PET_SLOTS.get(base_nick)

            # Tìm pet tương ứng trong RAM: ưu tiên theo target_pet_id, hoặc theo UI idx (pIdx), hoặc theo RAM slot
            matched_pet = None
            if pets:
                if target_pet_id:
                    matched_pet = next((p for p in pets if p.get("id") == target_pet_id), None)
                if not matched_pet and target_slot:
                    matched_pet = next((p for p in pets if p.get("idx") == target_slot), None)
                if not matched_pet and target_slot:
                    matched_pet = next((p for p in pets if p.get("slot") == target_slot), None)

            if matched_pet:
                target_pet_id = matched_pet.get("id")
                target_slot_num = matched_pet.get("slot")
            elif not target_pet_id and pets:
                target_pet_id = pets[0].get("id")
                target_slot_num = pets[0].get("slot")
            else:
                target_slot_num = target_slot

            if not target_pet_id:
                return

            cur_active_pet = next((p for p in pets if p.get("slot") == active_slot), None) if active_slot > 0 else None

            if not force and active_slot > 0 and cur_active_pet:
                self.designated_pet_id = cur_active_pet.get("id")
                self.pet_needs_resummon = False
                return

            if force and cur_active_pet and cur_active_pet.get("id") == target_pet_id:
                hp_str = f" | HP: {cur_active_pet['curHp']}/{cur_active_pet['maxHp']}"
                self.manager.log_event("INFO", self.name, f"🐾 Pet đã ở đúng vị trí (ID: 0x{target_pet_id:04X}{hp_str})")
                return

            slot_desc = f"Slot {target_slot} (RAM Slot {target_slot_num})" if target_slot else "chỉ định"
            self.manager.log_event("WARNING", self.name, f"🐾 [XUẤT CHIẾN PET] Gửi lệnh gọi Pet {slot_desc} (ID: 0x{target_pet_id:04X})...")
            pkt = pack_wlo_packet(bytes([0x13, 0x01]) + struct.pack("<I", target_pet_id))
            self.script.exports_sync.sendraw(pkt.hex())
            time.sleep(0.4)

            info_after = self.script.exports_sync.readpetinfo()
            if info_after and info_after.get("success"):
                active_after = info_after.get("activeSlot", 0)
                if active_after > 0:
                    self.pet_needs_resummon = False
                    self.designated_pet_id = target_pet_id
                    p_found = next((p for p in info_after.get("pets", []) if p.get("slot") == active_after), None)
                    hp_str = f" | HP: {p_found['curHp']}/{p_found['maxHp']}" if p_found else ""
                    self.manager.log_event("SUCCESS", self.name, f"✨ [XUẤT CHIẾN THÀNH CÔNG] Đã gọi Pet trở lại đội hình chiến đấu (Slot {active_after}{hp_str})! Sẵn sàng cho tầng tiếp theo.")
        except Exception as e:
            self.manager.log_event("ERROR", self.name, f"Lỗi tự động xuất chiến Pet: {e}")

    def start(self):
        dev = frida.get_local_device()
        self.session = dev.attach(self.pid)
        self.script = self.session.create_script(FRIDA_PARTY_JS)
        self.script.on("message", self.on_message)
        self.script.load()
        try:
            self.active_socket = self.script.exports_sync.getsocket()
        except Exception:
            pass

    def stop(self):
        try:
            if self.script:
                self.script.unload()
            if self.session:
                self.session.detach()
        except Exception:
            pass

# ==============================================================================
# GIAO DIỆN CHÍNH TKINTER (WLO PARTY GUI)
# ==============================================================================
class WLOPartyGUI:
    def __init__(self, root, parent=None):
        self.root = root.winfo_toplevel() if hasattr(root, "winfo_toplevel") else root
        self.parent = parent if parent is not None else self.root
        if self.parent == self.root:
            self.root.title("WLO Auto-Party Manager v1.2 - Quản Lý, Tự Động Relog & Tổ Đội")
            self.root.geometry("1100x780")
            self.root.minsize(980, 680)
            self.root.configure(bg=THEME["bg_main"])

        self.event_queue = queue.Queue()
        self.nodes = {}  # name -> PartyClientNode
        self.leader_node = None
        self.known_chars = load_known_chars()
        self.account_overrides = {}  # pid -> {"account": "...", "password": "...", "slot": 1}

        # Biến điều khiển
        self.auto_accept_var = tk.BooleanVar(value=True)
        self.filter_party_only_var = tk.BooleanVar(value=False)

        # Trạng thái lộ trình tự động (MiniDragonfly -> Cursed Palace)
        self.auto_route_running = False
        self.auto_route_cancel = False
        self.auto_route_target = None
        self.btn_auto_palace = None
        self.already_at_athena_var = tk.BooleanVar(value=False)

        # Trạng thái tự động di chuyển đồ (Auto Move Items 50x / 200ms)
        self.auto_move_running = False
        self.auto_move_cancel = False
        self.auto_move_target = None
        self.btn_auto_move = None

        # Trạng thái tự động Quốc Bảo (National Treasure Auto Opener)
        self.auto_treasure_running = False
        self.auto_treasure_cancel = False
        self.auto_treasure_key_found = False
        self.auto_treasure_chests_unlocked = False
        self.auto_treasure_target = None
        self.btn_auto_treasure = None
        self.lbl_treasure_status = None
        self.in_battle = False
        self.combat_turn = 0

        self.setup_styles()
        self.create_main_frames()
        self.show_process_selection()

        self.root.after(50, self.process_event_queue)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=THEME["bg_main"], foreground=THEME["text_main"], font=("Segoe UI", 10))
        style.configure("Card.TFrame", background=THEME["bg_card"], relief="flat")
        style.configure("Dark.TFrame", background=THEME["bg_dark"], relief="flat")

        style.configure("Treeview",
                        background=THEME["bg_input"],
                        foreground=THEME["text_main"],
                        fieldbackground=THEME["bg_input"],
                        font=("Segoe UI", 10),
                        rowheight=28)
        style.map("Treeview", background=[("selected", THEME["bg_selected"])], foreground=[("selected", "#ffffff")])
        style.configure("Treeview.Heading",
                        background=THEME["bg_card"],
                        foreground=THEME["primary"],
                        font=("Segoe UI", 10, "bold"),
                        relief="flat")

    def create_main_frames(self):
        container = self.parent if hasattr(self, "parent") and self.parent else self.root
        self.header_frame = tk.Frame(container, bg=THEME["bg_dark"], height=60, padx=20, pady=10)
        self.header_frame.pack(fill=tk.X, side=tk.TOP)

        self.title_lbl = tk.Label(self.header_frame, text="🏰 WLO AUTO PARTY & RELOG MANAGER", 
                                  font=("Segoe UI", 15, "bold"), fg=THEME["primary"], bg=THEME["bg_dark"])
        self.title_lbl.pack(side=tk.LEFT)

        self.sub_title_lbl = tk.Label(self.header_frame, text=" | Hệ thống tự động Relog lấy Char ID & Lập tổ đội", 
                                      font=("Segoe UI", 10), fg=THEME["text_muted"], bg=THEME["bg_dark"])
        self.sub_title_lbl.pack(side=tk.LEFT, pady=(3, 0))

        self.content_container = tk.Frame(container, bg=THEME["bg_main"])
        self.content_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

    # ==========================================================================
    # MÀN HÌNH 1 & 2: CHỌN TIẾN TRÌNH & ĐỘI TRƯỞNG
    # ==========================================================================
    def show_process_selection(self):
        for widget in self.content_container.winfo_children():
            widget.destroy()

        self.stop_all_nodes()

        step1_card = tk.LabelFrame(self.content_container, text="  Bước 1: Chọn từ 2 đến 4 cửa sổ game WLO (alogin*.exe)  ", 
                                   font=("Segoe UI", 11, "bold"), fg=THEME["primary"], bg=THEME["bg_card"], 
                                   padx=15, pady=12, relief="solid", bd=1)
        step1_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        tree_frame = tk.Frame(step1_card, bg=THEME["bg_card"])
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 10))

        cols = ("select", "name", "pid", "account", "slot", "socket", "char_id")
        self.proc_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse", height=7)
        self.proc_tree.heading("select", text="Chọn", anchor=tk.CENTER)
        self.proc_tree.heading("name", text="Tên tiến trình", anchor=tk.W)
        self.proc_tree.heading("pid", text="PID", anchor=tk.CENTER)
        self.proc_tree.heading("account", text="Tài khoản (Tự nhận)", anchor=tk.CENTER)
        self.proc_tree.heading("slot", text="Slot NV", anchor=tk.CENTER)
        self.proc_tree.heading("socket", text="Socket Mạng", anchor=tk.CENTER)
        self.proc_tree.heading("char_id", text="Char ID (Đã biết)", anchor=tk.CENTER)

        self.proc_tree.column("select", width=65, anchor=tk.CENTER)
        self.proc_tree.column("name", width=150, anchor=tk.W)
        self.proc_tree.column("pid", width=85, anchor=tk.CENTER)
        self.proc_tree.column("account", width=160, anchor=tk.CENTER)
        self.proc_tree.column("slot", width=75, anchor=tk.CENTER)
        self.proc_tree.column("socket", width=150, anchor=tk.CENTER)
        self.proc_tree.column("char_id", width=140, anchor=tk.CENTER)

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.proc_tree.yview)
        self.proc_tree.configure(yscrollcommand=tree_scroll.set)

        self.proc_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.proc_tree.bind("<Button-1>", self.on_tree_click)
        self.proc_tree.bind("<Double-1>", self.on_tree_double_click)
        self.proc_tree.bind("<space>", self.on_tree_space)

        # Thanh công cụ bảng
        btn_bar = tk.Frame(step1_card, bg=THEME["bg_card"])
        btn_bar.pack(fill=tk.X, pady=(0, 5))

        tk.Button(btn_bar, text="🔄 Quét lại danh sách", font=("Segoe UI", 9, "bold"), 
                  bg=THEME["bg_input"], fg=THEME["primary"], relief="flat", padx=12, pady=5, 
                  command=self.refresh_process_list).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(btn_bar, text="✔ Chọn 4 đầu tiên", font=("Segoe UI", 9), 
                  bg=THEME["bg_input"], fg=THEME["text_main"], relief="flat", padx=10, pady=5,
                  command=self.select_first_4).pack(side=tk.LEFT, padx=4)

        tk.Button(btn_bar, text="✖ Bỏ chọn tất cả", font=("Segoe UI", 9), 
                  bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", padx=10, pady=5,
                  command=self.deselect_all).pack(side=tk.LEFT, padx=4)

        tk.Button(btn_bar, text="✏️ Đổi Tài khoản dòng chọn", font=("Segoe UI", 9), 
                  bg=THEME["bg_input"], fg=THEME["gold"], relief="flat", padx=10, pady=5,
                  command=self.edit_selected_account).pack(side=tk.LEFT, padx=8)

        self.count_lbl = tk.Label(btn_bar, text="Đã chọn: 0 / 4 tiến trình (Cần chọn từ 2 đến 4)", 
                                  font=("Segoe UI", 10, "bold"), fg=THEME["yellow"], bg=THEME["bg_card"])
        self.count_lbl.pack(side=tk.RIGHT)

        # Step 2 Frame: Chọn Đội trưởng
        step2_card = tk.LabelFrame(self.content_container, text="  Bước 2: Chọn Đội Trưởng (Party Leader)  ", 
                                   font=("Segoe UI", 11, "bold"), fg=THEME["gold"], bg=THEME["bg_card"], 
                                   padx=15, pady=12, relief="solid", bd=1)
        step2_card.pack(fill=tk.X, pady=(0, 15))

        step2_inner = tk.Frame(step2_card, bg=THEME["bg_card"])
        step2_inner.pack(fill=tk.X)

        tk.Label(step2_inner, text="👑 Chỉ định Đội Trưởng:", font=("Segoe UI", 10, "bold"), 
                 fg=THEME["text_main"], bg=THEME["bg_card"]).pack(side=tk.LEFT, padx=(0, 10))

        self.leader_combo = ttk.Combobox(step2_inner, state="readonly", width=25, font=("Segoe UI", 10))
        self.leader_combo.pack(side=tk.LEFT, padx=(0, 20))
        self.leader_combo.bind("<<ComboboxSelected>>", self.on_leader_selected)

        tk.Label(step2_inner, text="Mã Char ID Đội trưởng:", font=("Segoe UI", 10), 
                 fg=THEME["text_muted"], bg=THEME["bg_card"]).pack(side=tk.LEFT, padx=(0, 6))

        self.leader_char_entry = tk.Entry(step2_inner, width=16, font=("Segoe UI", 10, "bold"), 
                                          bg=THEME["bg_input"], fg=THEME["gold"], insertbackground="#fff", relief="flat")
        self.leader_char_entry.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(step2_inner, text="(Gợi ý: F02=0x2EC8, F04=0x2ECB, W03=0x2EE3, W04=0x2EE4)", 
                 font=("Segoe UI", 9, "italic"), fg=THEME["text_muted"], bg=THEME["bg_card"]).pack(side=tk.LEFT)

        # Bottom Bar
        bottom_bar = tk.Frame(self.content_container, bg=THEME["bg_main"])
        bottom_bar.pack(fill=tk.X)

        self.start_btn = tk.Button(bottom_bar, text="🚀 BẮT ĐẦU ĐIỀU KHIỂN TỔ ĐỘI  ➔", 
                                   font=("Segoe UI", 12, "bold"), bg=THEME["primary"], fg=THEME["bg_dark"],
                                   activebackground=THEME["primary_hover"], relief="flat", 
                                   padx=30, pady=10, cursor="hand2", command=self.start_party_dashboard)
        self.start_btn.pack(side=tk.RIGHT)

        self.selected_pids = set()
        self.detected_processes = []
        self.refresh_process_list()

    def refresh_process_list(self):
        self.proc_tree.delete(*self.proc_tree.get_children())
        self.detected_processes.clear()

        if not frida:
            messagebox.showerror("Lỗi", "Thư viện frida chưa được cài đặt!")
            return

        try:
            dev = frida.get_local_device()
            procs = dev.enumerate_processes()
        except Exception as e:
            messagebox.showerror("Lỗi Frida", f"Không thể quét tiến trình: {e}")
            return

        alogin_procs = [p for p in procs if "alogin" in p.name.lower()]
        alogin_procs.sort(key=lambda x: x.name.lower())

        for p in alogin_procs:
            plow = p.name.lower()
            char_hex = ""
            for k, v in self.known_chars.items():
                if k in plow:
                    char_hex = f"0x{v:08X}"
                    break

            acc_info = self.account_overrides.get(p.pid, {
                "account": get_default_account_from_proc_name(p.name),
                "password": "111111",
                "slot": 1
            })

            is_sel = p.pid in self.selected_pids
            mark = " [✔] " if is_sel else " [  ] "
            self.proc_tree.insert("", tk.END, iid=str(p.pid), values=(
                mark, p.name, p.pid, acc_info["account"], f"Slot {acc_info['slot']}", 
                "Sẵn sàng (Port 6414)", char_hex
            ))
            self.detected_processes.append(p)

        self.update_selection_state()

    def on_tree_click(self, event):
        region = self.proc_tree.identify("region", event.x, event.y)
        if region == "heading":
            return
        item_id = self.proc_tree.identify_row(event.y)
        if not item_id:
            return
        self.toggle_process_selection(int(item_id))

    def on_tree_double_click(self, event):
        item_id = self.proc_tree.identify_row(event.y)
        if item_id:
            self.edit_account_for_pid(int(item_id))

    def on_tree_space(self, event):
        sel = self.proc_tree.selection()
        if sel:
            self.toggle_process_selection(int(sel[0]))

    def toggle_process_selection(self, pid):
        if pid in self.selected_pids:
            self.selected_pids.remove(pid)
        else:
            if len(self.selected_pids) >= 4:
                messagebox.showwarning("Giới hạn", "Bạn chỉ được chọn tối đa 4 tiến trình!")
                return
            self.selected_pids.add(pid)

        mark = " [✔] " if pid in self.selected_pids else " [  ] "
        vals = list(self.proc_tree.item(str(pid), "values"))
        vals[0] = mark
        self.proc_tree.item(str(pid), values=vals)
        self.update_selection_state()

    def edit_selected_account(self):
        sel = self.proc_tree.selection()
        if not sel:
            messagebox.showinfo("Thông báo", "Vui lòng bấm chọn một dòng tiến trình trên bảng!")
            return
        self.edit_account_for_pid(int(sel[0]))

    def edit_account_for_pid(self, pid):
        curr_acc = self.account_overrides.get(pid, {}).get("account", "")
        for p in self.detected_processes:
            if p.pid == pid and not curr_acc:
                curr_acc = get_default_account_from_proc_name(p.name)

        new_acc = simpledialog.askstring("Chỉnh sửa tài khoản", f"Nhập tên tài khoản game cho PID {pid}:", 
                                         initialvalue=curr_acc, parent=self.root)
        if new_acc:
            new_acc = new_acc.strip()
            self.account_overrides[pid] = {
                "account": new_acc,
                "password": "111111",
                "slot": 1
            }
            vals = list(self.proc_tree.item(str(pid), "values"))
            vals[3] = new_acc
            self.proc_tree.item(str(pid), values=vals)

    def select_first_4(self):
        self.selected_pids.clear()
        for p in self.detected_processes[:4]:
            self.selected_pids.add(p.pid)
        for p in self.detected_processes:
            mark = " [✔] " if p.pid in self.selected_pids else " [  ] "
            vals = list(self.proc_tree.item(str(p.pid), "values"))
            vals[0] = mark
            self.proc_tree.item(str(p.pid), values=vals)
        self.update_selection_state()

    def deselect_all(self):
        self.selected_pids.clear()
        for p in self.detected_processes:
            vals = list(self.proc_tree.item(str(p.pid), "values"))
            vals[0] = " [  ] "
            self.proc_tree.item(str(p.pid), values=vals)
        self.update_selection_state()

    def update_selection_state(self):
        count = len(self.selected_pids)
        self.count_lbl.config(text=f"Đã chọn: {count} / 4 tiến trình (Yêu cầu: 2 - 4)")
        if 2 <= count <= 4:
            self.count_lbl.config(fg=THEME["green"])
            self.start_btn.config(state=tk.NORMAL, bg=THEME["primary"])
        else:
            self.count_lbl.config(fg=THEME["yellow"])
            self.start_btn.config(state=tk.DISABLED, bg="#45475a")

        selected_procs = [p for p in self.detected_processes if p.pid in self.selected_pids]
        names = [f"{p.name} (PID: {p.pid})" for p in selected_procs]
        self.leader_combo["values"] = names

        curr = self.leader_combo.get()
        if names:
            if curr not in names:
                f02_match = [n for n in names if "f02" in n.lower()]
                self.leader_combo.set(f02_match[0] if f02_match else names[0])
            self.on_leader_selected(None)
        else:
            self.leader_combo.set("")
            self.leader_char_entry.delete(0, tk.END)

    def on_leader_selected(self, event):
        val = self.leader_combo.get()
        if not val:
            return
        try:
            pid = int(val.split("PID:")[1].replace(")", "").strip())
            for p in self.detected_processes:
                if p.pid == pid:
                    plow = p.name.lower()
                    for k, cid in self.known_chars.items():
                        if k in plow:
                            self.leader_char_entry.delete(0, tk.END)
                            self.leader_char_entry.insert(0, f"0x{cid:08X}")
                            return
            self.leader_char_entry.delete(0, tk.END)
        except Exception:
            pass

    # ==========================================================================
    # BẮT ĐẦU ĐÍNH KÈM & CHUYỂN SANG BẢNG ĐIỀU KHIỂN
    # ==========================================================================
    def start_party_dashboard(self):
        if not (2 <= len(self.selected_pids) <= 4):
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn từ 2 đến 4 tiến trình để thiết lập tổ đội!")
            return

        leader_str = self.leader_combo.get()
        if not leader_str:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn Đội trưởng!")
            return

        leader_pid = int(leader_str.split("PID:")[1].replace(")", "").strip())

        lead_cid_str = self.leader_char_entry.get().strip()
        lead_cid = None
        if lead_cid_str:
            try:
                lead_cid = int(lead_cid_str, 16) if lead_cid_str.lower().startswith("0x") else int(lead_cid_str)
            except ValueError:
                pass

        self.nodes.clear()
        selected_procs = [p for p in self.detected_processes if p.pid in self.selected_pids]

        loading_popup = tk.Toplevel(self.root)
        loading_popup.title("Đang kết nối...")
        loading_popup.geometry("380x130")
        loading_popup.configure(bg=THEME["bg_card"])
        loading_popup.transient(self.root)
        loading_popup.grab_set()

        tk.Label(loading_popup, text="⏳ Đang đính kèm Frida & Quét Socket mạng...", 
                 font=("Segoe UI", 11, "bold"), fg=THEME["primary"], bg=THEME["bg_card"]).pack(pady=(20, 5))
        lbl_info = tk.Label(loading_popup, text="Vui lòng chờ trong giây lát...", 
                            font=("Segoe UI", 9), fg=THEME["text_muted"], bg=THEME["bg_card"])
        lbl_info.pack()
        loading_popup.update()

        errs = []
        for p in selected_procs:
            cid = None
            plow = p.name.lower()
            if p.pid == leader_pid and lead_cid:
                cid = lead_cid
            else:
                for k, v in self.known_chars.items():
                    if k in plow:
                        cid = v
                        break

            acc_info = self.account_overrides.get(p.pid, {
                "account": get_default_account_from_proc_name(p.name),
                "password": "111111",
                "slot": 1
            })

            node = PartyClientNode(p.name, p.pid, self, char_id=cid, 
                                   account=acc_info["account"], password=acc_info["password"], slot=acc_info["slot"])
            node.is_leader = (p.pid == leader_pid)
            try:
                lbl_info.config(text=f"Đang đính kèm: {p.name} (PID: {p.pid})...")
                loading_popup.update()
                node.start()
                self.nodes[p.name] = node
                if node.is_leader:
                    self.leader_node = node
            except Exception as e:
                errs.append(f"{p.name}: {e}")

        loading_popup.destroy()

        if errs:
            messagebox.showerror("Lỗi kết nối Frida", "Có lỗi xảy ra khi hook tiến trình:\n" + "\n".join(errs))
            if not self.nodes:
                return

        self.show_dashboard_view()

    # ==========================================================================
    # MÀN HÌNH 3: BẢNG ĐIỀU KHIỂN TỔ ĐỘI (PARTY DASHBOARD)
    # ==========================================================================
    def show_dashboard_view(self):
        for widget in self.content_container.winfo_children():
            widget.destroy()

        # Banner Đội trưởng
        leader_banner = tk.Frame(self.content_container, bg=THEME["bg_card"], padx=15, pady=10, relief="solid", bd=1)
        leader_banner.pack(fill=tk.X, pady=(0, 10))

        lead_name = self.leader_node.name if self.leader_node else "Chưa rõ"
        lead_pid = self.leader_node.pid if self.leader_node else 0
        lead_cid_txt = f"0x{self.leader_node.char_id:08X}" if (self.leader_node and self.leader_node.char_id) else "Chưa xác định"

        self.lead_title_lbl = tk.Label(leader_banner, 
                                       text=f"👑 ĐỘI TRƯỞNG: {lead_name} (PID: {lead_pid}) | Char ID: {lead_cid_txt}", 
                                       font=("Segoe UI", 12, "bold"), fg=THEME["gold"], bg=THEME["bg_card"])
        self.lead_title_lbl.pack(side=tk.LEFT)

        tk.Button(leader_banner, text="⚙️ Chọn lại tiến trình", font=("Segoe UI", 9, "bold"), 
                  bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", padx=12, pady=4,
                  command=self.show_process_selection).pack(side=tk.RIGHT)

        # KHUNG THẺ CLIENTS
        cards_frame = tk.Frame(self.content_container, bg=THEME["bg_main"])
        cards_frame.pack(fill=tk.X, pady=(0, 10))

        self.card_widgets = {}
        for idx, (name, node) in enumerate(self.nodes.items()):
            card = self.create_client_card(cards_frame, node)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0 if idx == 0 else 8, 0))
            self.card_widgets[name] = card

        # THANH CÔNG CỤ TỔNG
        master_bar = tk.LabelFrame(self.content_container, text="  Bảng Điều Khiển Lệnh Tổ Đội & Tự Động Relog  ", 
                                   font=("Segoe UI", 11, "bold"), fg=THEME["primary"], bg=THEME["bg_card"], 
                                   padx=15, pady=8, relief="solid", bd=1)
        master_bar.pack(fill=tk.X, pady=(0, 10))

        # HÀNG 1: CÁC LỆNH TỔ ĐỘI & RELOG
        row1 = tk.Frame(master_bar, bg=THEME["bg_card"])
        row1.pack(fill=tk.X, pady=(0, 6))

        tk.Button(row1, text="🔄 TỰ ĐỘNG RELOG TẤT CẢ (LẤY CHAR ID)", 
                  font=("Segoe UI", 9, "bold"), bg=THEME["gold"], fg="#11111b",
                  activebackground="#fcd34d", activeforeground="#11111b", relief="flat", padx=12, pady=6,
                  cursor="hand2", command=self.action_relog_all).pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(row1, text="⚡ TỰ ĐỘNG THIẾT LẬP TỔ ĐỘI (AUTO ALL)", 
                  font=("Segoe UI", 9, "bold"), bg=THEME["green"], fg="#11111b",
                  activebackground="#86efac", activeforeground="#11111b", relief="flat", padx=12, pady=6,
                  cursor="hand2", command=self.action_auto_party_all).pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(row1, text="🚪 Giải tán / Rời nhóm toàn bộ", 
                  font=("Segoe UI", 9), bg=THEME["bg_input"], fg=THEME["red"],
                  activebackground=THEME["bg_hover"], relief="flat", padx=10, pady=6,
                  cursor="hand2", command=self.action_leave_all).pack(side=tk.LEFT, padx=(0, 10))

        chk_accept = tk.Checkbutton(row1, text="Auto-Accept 100%", 
                                    variable=self.auto_accept_var, font=("Segoe UI", 9, "bold"),
                                    fg=THEME["text_main"], bg=THEME["bg_card"], selectcolor=THEME["bg_dark"],
                                    activebackground=THEME["bg_card"], activeforeground=THEME["primary"])
        chk_accept.pack(side=tk.LEFT, padx=5)

        # HÀNG 2: LỘ TRÌNH CURSED PALACE & TÙY CHỌN ĐÃ Ở ATHENA & CHUYỂN ĐỒ
        row2 = tk.Frame(master_bar, bg=THEME["bg_card"])
        row2.pack(fill=tk.X, pady=(4, 2))

        self.btn_auto_palace = tk.Button(row2, text="🏛️ ĐI ATHENA / CURSED PALACE (SONG SONG 4 ACC)", 
                                         font=("Segoe UI", 10, "bold"), bg=THEME["purple"], fg="#11111b",
                                         activebackground="#dcd7ba", activeforeground="#11111b", relief="flat", padx=16, pady=6,
                                         cursor="hand2", command=self.action_toggle_cursed_palace)
        self.btn_auto_palace.pack(side=tk.LEFT, padx=(0, 10))

        chk_athena = tk.Checkbutton(row2, text="☑ ĐÃ Ở ATHENA (Chỉ chạy bộ)", 
                                    variable=self.already_at_athena_var, font=("Segoe UI", 9, "bold"),
                                    fg=THEME["purple"], bg=THEME["bg_card"], selectcolor=THEME["bg_dark"],
                                    activebackground=THEME["bg_card"], activeforeground=THEME["purple"],
                                    cursor="hand2")
        chk_athena.pack(side=tk.LEFT, padx=(0, 15))

        self.btn_auto_move = tk.Button(row2, text="📦 TỰ ĐỘNG DỒN ĐỒ (RELOG & MERGE)", 
                                       font=("Segoe UI", 10, "bold"), bg=THEME["cyan"], fg="#11111b",
                                       activebackground="#a6e3a1", activeforeground="#11111b", relief="flat", padx=16, pady=6,
                                       cursor="hand2", command=self.action_toggle_auto_move_items)
        self.btn_auto_move.pack(side=tk.LEFT, padx=5)

        self.btn_call_pets = tk.Button(row2, text="🐾 XUẤT CHIẾN TẤT CẢ PET", 
                                       font=("Segoe UI", 10, "bold"), bg=THEME["primary"], fg="#11111b",
                                       activebackground="#b4befe", activeforeground="#11111b", relief="flat", padx=16, pady=6,
                                       cursor="hand2", command=self.action_resummon_all_pets)
        self.btn_call_pets.pack(side=tk.LEFT, padx=(10, 5))

        # HÀNG 3: TỰ ĐỘNG PHỤ BẢN ĐẶC BIỆT (QUỐC BẢO / THÁP / SỰ KIỆN)
        row3 = tk.Frame(master_bar, bg=THEME["bg_card"])
        row3.pack(fill=tk.X, pady=(4, 2))

        self.btn_auto_treasure = tk.Button(row3, text="💎 AUTO QUỐC BẢO (MỞ RƯƠNG & DỪNG KHI RA KHÓA)", 
                                           font=("Segoe UI", 10, "bold"), bg=THEME["gold"], fg="#11111b",
                                           activebackground="#fcd34d", activeforeground="#11111b", relief="flat", padx=16, pady=6,
                                           cursor="hand2", command=self.action_toggle_auto_national_treasure)
        self.btn_auto_treasure.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_sweep_all = tk.Button(row3, text="🧹 DỌN RÁC TÚI ĐỒ (TẤT CẢ ACC)",
                                       font=("Segoe UI", 10, "bold"), bg=THEME["red"], fg="#ffffff",
                                       activebackground="#f87171", activeforeground="#11111b", relief="flat", padx=16, pady=6,
                                       cursor="hand2", command=self.action_sweep_trash_all)
        self.btn_sweep_all.pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_treasure_status = tk.Label(row3, text="Trạng thái: Sẵn sàng", 
                                            font=("Segoe UI", 9, "italic"), fg=THEME["text_muted"], bg=THEME["bg_card"])
        self.lbl_treasure_status.pack(side=tk.LEFT, padx=5)

        # KHUNG LOG GÓI TIN THỜI GIAN THỰC
        log_frame = tk.LabelFrame(self.content_container, text="  Nhật ký Gói tin & Sự kiện Thời gian thực (Live Console)  ", 
                                  font=("Segoe UI", 11, "bold"), fg=THEME["primary"], bg=THEME["bg_card"], 
                                  padx=10, pady=8, relief="solid", bd=1)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = ScrolledText(log_frame, bg=THEME["bg_dark"], fg=THEME["text_main"], 
                                     font=("Consolas", 9), insertbackground="#fff", relief="flat", padx=8, pady=6)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.log_text.tag_config("time", foreground=THEME["text_muted"])
        self.log_text.tag_config("node", foreground=THEME["primary"], font=("Consolas", 9, "bold"))
        self.log_text.tag_config("c2s", foreground=THEME["cyan"])
        self.log_text.tag_config("s2c", foreground=THEME["green"])
        self.log_text.tag_config("party", foreground=THEME["gold"])
        self.log_text.tag_config("route", foreground=THEME["purple"], font=("Consolas", 9, "bold"))
        self.log_text.tag_config("warning", foreground=THEME["yellow"], font=("Consolas", 9, "bold"))
        self.log_text.tag_config("success", foreground=THEME["green"], font=("Consolas", 9, "bold"))
        self.log_text.tag_config("error", foreground=THEME["red"], font=("Consolas", 9, "bold"))

        log_ctrl = tk.Frame(log_frame, bg=THEME["bg_card"])
        log_ctrl.pack(fill=tk.X)

        tk.Checkbutton(log_ctrl, text="Chỉ lọc gói tin tổ đội (Opcode 0x0D)", variable=self.filter_party_only_var,
                       font=("Segoe UI", 9), fg=THEME["text_muted"], bg=THEME["bg_card"], selectcolor=THEME["bg_dark"],
                       activebackground=THEME["bg_card"]).pack(side=tk.LEFT)

        tk.Button(log_ctrl, text="🧹 Xóa Log", font=("Segoe UI", 9), bg=THEME["bg_input"], fg=THEME["text_muted"],
                  relief="flat", padx=10, pady=3, command=self.clear_log).pack(side=tk.RIGHT, padx=5)

        tk.Button(log_ctrl, text="📋 Sao chép Log", font=("Segoe UI", 9), bg=THEME["bg_input"], fg=THEME["text_muted"],
                  relief="flat", padx=10, pady=3, command=self.copy_log).pack(side=tk.RIGHT, padx=5)

        tk.Button(log_ctrl, text="💾 Lưu Log", font=("Segoe UI", 9), bg=THEME["bg_input"], fg=THEME["text_muted"],
                  relief="flat", padx=10, pady=3, command=self.save_log_to_file).pack(side=tk.RIGHT, padx=5)

        self.log_event("SUCCESS", "SYSTEM", "Bảng điều khiển tổ đội & Relog đã khởi chạy thành công! Sẵn sàng.")

    def create_client_card(self, parent, node):
        card = tk.Frame(parent, bg=THEME["bg_card"], padx=12, pady=10, relief="solid", bd=1)

        head = tk.Frame(card, bg=THEME["bg_card"])
        head.pack(fill=tk.X, pady=(0, 6))

        role_bg = THEME["gold"] if node.is_leader else THEME["primary"]
        role_txt = "👑 ĐỘI TRƯỞNG" if node.is_leader else "🛡️ THÀNH VIÊN"
        role_badge = tk.Label(head, text=role_txt, font=("Segoe UI", 8, "bold"), 
                              bg=role_bg, fg="#11111b", padx=6, pady=2)
        role_badge.pack(side=tk.LEFT)

        tk.Label(head, text=f" {node.name}", font=("Segoe UI", 10, "bold"), 
                 fg=THEME["text_main"], bg=THEME["bg_card"]).pack(side=tk.LEFT, padx=4)

        info_frame = tk.Frame(card, bg=THEME["bg_card"])
        info_frame.pack(fill=tk.X, pady=(0, 4))

        tk.Label(info_frame, text=f"PID: {node.pid} | TK: {node.account} (Slot {node.slot})", font=("Segoe UI", 9), 
                 fg=THEME["text_muted"], bg=THEME["bg_card"]).pack(anchor=tk.W)

        sock_txt = f"Socket: #{node.active_socket} (6414)" if node.active_socket > 0 else "Socket: Đang dò..."
        sock_color = THEME["green"] if node.active_socket > 0 else THEME["yellow"]
        sock_lbl = tk.Label(info_frame, text=sock_txt, font=("Segoe UI", 9, "bold"), 
                            fg=sock_color, bg=THEME["bg_card"])
        sock_lbl.pack(anchor=tk.W)
        card.sock_lbl = sock_lbl

        # Char ID
        cid_frame = tk.Frame(card, bg=THEME["bg_card"])
        cid_frame.pack(fill=tk.X, pady=(0, 6))

        cid_txt = f"Char ID: 0x{node.char_id:08X}" if node.char_id else "Char ID: Chưa nhận (Bấm Relog)"
        cid_color = THEME["cyan"] if node.char_id else THEME["yellow"]
        cid_lbl = tk.Label(cid_frame, text=cid_txt, font=("Segoe UI", 9, "bold"), 
                           fg=cid_color, bg=THEME["bg_card"])
        cid_lbl.pack(anchor=tk.W)
        card.cid_lbl = cid_lbl

        status_txt = "Trạng thái: ĐÃ VÀO ĐỘI" if node.in_party else "Trạng thái: Chưa vào đội"
        status_color = THEME["green"] if node.in_party else THEME["yellow"]
        status_lbl = tk.Label(card, text=status_txt, font=("Segoe UI", 9, "bold"), 
                              fg=status_color, bg=THEME["bg_card"])
        status_lbl.pack(anchor=tk.W, pady=(0, 6))
        card.status_lbl = status_lbl

        act_frame = tk.Frame(card, bg=THEME["bg_card"])
        act_frame.pack(fill=tk.X)

        # Nút Relog riêng từng client
        btn_relog = tk.Button(act_frame, text="🔄 Relog & Lấy Char ID", font=("Segoe UI", 8, "bold"), 
                              bg=THEME["bg_input"], fg=THEME["gold"], activebackground=THEME["bg_hover"],
                              relief="flat", pady=3, cursor="hand2", command=lambda n=node: n.do_relog())
        btn_relog.pack(fill=tk.X, pady=(0, 4))

        btn_sweep = tk.Button(act_frame, text="🧹 Dọn rác acc này", font=("Segoe UI", 8), 
                              bg=THEME["bg_input"], fg=THEME["red"], activebackground=THEME["bg_hover"],
                              relief="flat", pady=2, cursor="hand2", command=lambda n=node: self.action_sweep_trash_single(n))
        btn_sweep.pack(fill=tk.X, pady=(0, 4))

        if not node.is_leader:
            btn_join = tk.Button(act_frame, text="🙋 Xin vào nhóm", font=("Segoe UI", 9, "bold"), 
                                 bg=THEME["bg_input"], fg=THEME["primary"], activebackground=THEME["bg_hover"],
                                 relief="flat", pady=4, cursor="hand2",
                                 command=lambda n=node: self.action_member_join(n))
            btn_join.pack(fill=tk.X, pady=(0, 4))

            btn_leave = tk.Button(act_frame, text="Rời nhóm", font=("Segoe UI", 8), 
                                  bg=THEME["bg_input"], fg=THEME["red"], relief="flat", pady=2,
                                  command=lambda n=node: n.leave_party())
            btn_leave.pack(fill=tk.X)
        else:
            btn_transfer = tk.Button(act_frame, text="👑 Nhường Đội trưởng", font=("Segoe UI", 9), 
                                     bg=THEME["bg_input"], fg=THEME["gold"], activebackground=THEME["bg_hover"],
                                     relief="flat", pady=4, cursor="hand2",
                                     command=self.action_show_transfer_menu)
            btn_transfer.pack(fill=tk.X, pady=(0, 4))

            btn_disband = tk.Button(act_frame, text="Giải tán nhóm", font=("Segoe UI", 8), 
                                    bg=THEME["bg_input"], fg=THEME["red"], relief="flat", pady=2,
                                    command=lambda n=node: n.leave_party())
            btn_disband.pack(fill=tk.X)

        # Nút tự động chạy Cursed Palace riêng cho client này
        btn_palace = tk.Button(act_frame, text="🏛️ Đi Cursed Palace", font=("Segoe UI", 8, "bold"), 
                               bg=THEME["bg_input"], fg=THEME["purple"], activebackground=THEME["bg_hover"],
                               relief="flat", pady=3, cursor="hand2",
                               command=lambda n=node: self.action_toggle_cursed_palace(n))
        btn_palace.pack(fill=tk.X, pady=(4, 0))

        # Nút tự động chuyển đồ riêng cho client này
        btn_move = tk.Button(act_frame, text="📦 Dồn đồ xuống cuối", font=("Segoe UI", 8, "bold"), 
                             bg=THEME["bg_input"], fg=THEME["cyan"], activebackground=THEME["bg_hover"],
                             relief="flat", pady=3, cursor="hand2",
                             command=lambda n=node: self.action_toggle_auto_move_items(n))
        btn_move.pack(fill=tk.X, pady=(2, 0))

        return card

    # ==========================================================================
    # CÁC HÀNH ĐỘNG ĐIỀU KHIỂN TỔ ĐỘI & RELOG
    # ==========================================================================
    def action_relog_all(self):
        """Tự động Relog toàn bộ tiến trình để lấy Char ID."""
        self.log_event("PARTY", "MASTER", "🔄 BẮT ĐẦU TỰ ĐỘNG RELOG TẤT CẢ CÁC CỬA SỔ ĐỂ ĐỒNG BỘ CHAR ID...")
        def _run_all():
            for node in self.nodes.values():
                node.do_relog()
                time.sleep(1.0)
        threading.Thread(target=_run_all, daemon=True).start()

    def action_auto_party_all(self):
        """Lệnh thiết lập tổ đội tự động cho toàn bộ thành viên vào nhóm của Leader."""
        if not self.leader_node:
            messagebox.showwarning("Cảnh báo", "Chưa chỉ định Đội trưởng!")
            return

        lead_id = self.leader_node.char_id
        if not lead_id:
            messagebox.showwarning("Cảnh báo", f"Đội trưởng {self.leader_node.name} chưa có mã Char ID! Hãy bấm nút Relog hoặc nhập Char ID.")
            return

        self.log_event("PARTY", "MASTER", f"⚡ BẮT ĐẦU TỰ ĐỘNG THIẾT LẬP TỔ ĐỘI -> ĐỘI TRƯỞNG 0x{lead_id:08X}...")

        members = [n for n in self.nodes.values() if not n.is_leader]
        if not members:
            messagebox.showinfo("Thông báo", "Không có thành viên nào khác ngoài Đội trưởng!")
            return

        def run_all_joins():
            for m in members:
                self.log_event("C2S", m.name, f"Đang gửi lệnh xin gia nhập tổ đội của {self.leader_node.name}...")
                m.request_join_or_invite(lead_id)
                time.sleep(0.08)

        threading.Thread(target=run_all_joins, daemon=True).start()

    def action_member_join(self, member_node):
        if not self.leader_node:
            messagebox.showwarning("Cảnh báo", "Chưa chỉ định Đội trưởng!")
            return
        lead_id = self.leader_node.char_id
        if not lead_id:
            messagebox.showwarning("Cảnh báo", f"Đội trưởng {self.leader_node.name} chưa có mã Char ID! Bấm nút Relog để tự nhận diện.")
            return
        member_node.request_join_or_invite(lead_id)

    def action_leave_all(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc muốn cho tất cả thành viên rời khỏi tổ đội?"):
            for n in self.nodes.values():
                n.leave_party()

    def action_show_transfer_menu(self):
        members = [n for n in self.nodes.values() if not n.is_leader and n.char_id]
        if not members:
            messagebox.showinfo("Thông báo", "Không tìm thấy thành viên hợp lệ nào có Char ID để chuyển nhượng!")
            return

        top = tk.Toplevel(self.root)
        top.title("Chọn Đội Trưởng Mới")
        top.geometry("340x220")
        top.configure(bg=THEME["bg_card"])
        top.transient(self.root)

        tk.Label(top, text="Chọn thành viên để trao quyền Đội trưởng:", font=("Segoe UI", 10, "bold"), 
                 fg=THEME["text_main"], bg=THEME["bg_card"]).pack(pady=(15, 10))

        combo = ttk.Combobox(top, state="readonly", width=25, font=("Segoe UI", 10))
        combo["values"] = [f"{m.name} (ID: 0x{m.char_id:08X})" for m in members]
        combo.current(0)
        combo.pack(pady=10)

        def do_transfer():
            sel = combo.get()
            top.destroy()
            for m in members:
                if f"0x{m.char_id:08X}" in sel:
                    self.leader_node.transfer_leader(m.char_id)
                    break

        tk.Button(top, text="✔ Xác nhận chuyển nhượng", font=("Segoe UI", 10, "bold"), 
                  bg=THEME["gold"], fg="#11111b", relief="flat", padx=15, pady=6, command=do_transfer).pack(pady=15)

    def action_toggle_cursed_palace(self, target_node=None):
        """Kích hoạt hoặc dừng tự động chạy lộ trình MiniDragonfly -> Athena -> Cursed Palace (Hỗ trợ chạy SONG SONG tất cả acc)."""
        if self.auto_route_running:
            if messagebox.askyesno("Dừng lộ trình", "Lộ trình di chuyển đang thực hiện!\n\nBạn có muốn DỪNG LẠI ngay lập tức không?"):
                self.auto_route_cancel = True
                self.log_event("WARNING", "MASTER", "⏹️ Đang gửi tín hiệu dừng lộ trình cho tất cả acc...")
            return

        active_nodes = [n for n in self.nodes.values() if n.active_socket > 0]
        if not active_nodes:
            messagebox.showwarning("Cảnh báo", "Chưa có tiến trình nào kết nối game!\nVui lòng đăng nhập nhân vật vào game trước.")
            return

        single_target = target_node or self.leader_node or active_nodes[0]

        # HỘP THOẠI CHỌN CẤU HÌNH LỘ TRÌNH (HỖ TRỢ SONG SONG 4 ACC)
        dlg = tk.Toplevel(self.root)
        dlg.title("Cấu Hình Lộ Trình Cursed Palace / Athena (Xử Lý Song Song)")
        dlg.geometry("580x430")
        dlg.configure(bg=THEME["bg_card"])
        dlg.transient(self.root)
        dlg.grab_set()

        # Tiêu đề
        tk.Label(dlg, text="🏛️ TỰ ĐỘNG HÓA LỘ TRÌNH ĐẾN CURSED PALACE", font=("Segoe UI", 12, "bold"), 
                 fg=THEME["purple"], bg=THEME["bg_card"]).pack(pady=(14, 3))
        tk.Label(dlg, text="Hỗ trợ di chuyển ĐỒNG LOẠT SONG SONG cả 4 nhân vật cùng lúc", 
                 font=("Segoe UI", 9, "italic"), fg=THEME["text_muted"], bg=THEME["bg_card"]).pack(pady=(0, 10))

        # Khung 1: Chọn đối tượng thực hiện (TẤT CẢ SONG SONG vs RIÊNG 1 ACC)
        scope_box = tk.LabelFrame(dlg, text="  1. Chọn Nhân Vật Thực Hiện  ", font=("Segoe UI", 10, "bold"),
                                  fg=THEME["gold"], bg=THEME["bg_card"], padx=14, pady=8)
        scope_box.pack(fill=tk.X, padx=18, pady=(0, 10))

        scope_var = tk.IntVar(value=1)

        r_all = tk.Radiobutton(scope_box, 
                               text=f"👥 TẤT CẢ ACC KẾT NỐI (XỬ LÝ SONG SONG {len(active_nodes)} CLIENTS) [Khuyến nghị]\n   -> Cả 4 nhân vật sẽ bay & chạy bộ cùng lúc, tiết kiệm tối đa thời gian!",
                               variable=scope_var, value=1, font=("Segoe UI", 9, "bold"),
                               fg=THEME["green"], bg=THEME["bg_card"], selectcolor=THEME["bg_dark"],
                               activebackground=THEME["bg_card"], activeforeground=THEME["green"], justify=tk.LEFT)
        r_all.pack(anchor=tk.W, pady=(0, 6))

        r_single = tk.Radiobutton(scope_box, 
                                  text=f"👤 Chỉ chạy riêng cho nhân vật [{single_target.name}] (PID: {single_target.pid})",
                                  variable=scope_var, value=2, font=("Segoe UI", 9),
                                  fg=THEME["text_main"], bg=THEME["bg_card"], selectcolor=THEME["bg_dark"],
                                  activebackground=THEME["bg_card"], activeforeground=THEME["primary"], justify=tk.LEFT)
        r_single.pack(anchor=tk.W)

        # Khung 2: Chọn chế độ bắt đầu
        choice_box = tk.LabelFrame(dlg, text="  2. Chọn Điểm Xuất Phát  ", font=("Segoe UI", 10, "bold"),
                                   fg=THEME["primary"], bg=THEME["bg_card"], padx=14, pady=8)
        choice_box.pack(fill=tk.X, padx=18, pady=(0, 12))

        mode_var = tk.IntVar(value=2 if self.already_at_athena_var.get() else 1)

        r1 = tk.Radiobutton(choice_box, 
                            text="[1] 🛸 Lộ trình đầy đủ: Dùng MiniDragonfly (Slot 1) bay sang Athena\n    (Tự giải tán nhóm -> Bay Athena -> Đợi nạp map 2.5s -> Chạy bộ 14 điểm)",
                            variable=mode_var, value=1, font=("Segoe UI", 9),
                            fg=THEME["text_main"], bg=THEME["bg_card"], selectcolor=THEME["bg_dark"],
                            activebackground=THEME["bg_card"], activeforeground=THEME["primary"], justify=tk.LEFT)
        r1.pack(anchor=tk.W, pady=(0, 6))

        r2 = tk.Radiobutton(choice_box, 
                            text="[2] 📍 ĐÃ Ở ATHENA (Bỏ qua dùng item bay, chỉ chạy bộ tới NPC)\n    (Không dùng item bay, chạy bộ đồng loạt ngay từ cổng Athena)",
                            variable=mode_var, value=2, font=("Segoe UI", 9, "bold"),
                            fg=THEME["purple"], bg=THEME["bg_card"], selectcolor=THEME["bg_dark"],
                            activebackground=THEME["bg_card"], activeforeground=THEME["purple"], justify=tk.LEFT)
        r2.pack(anchor=tk.W)

        btn_box = tk.Frame(dlg, bg=THEME["bg_card"])
        btn_box.pack(fill=tk.X, padx=18, pady=(4, 10))

        def on_confirm():
            is_at_athena = (mode_var.get() == 2)
            self.already_at_athena_var.set(is_at_athena)
            targets = active_nodes if (scope_var.get() == 1) else [single_target]
            dlg.destroy()
            self._start_cursed_palace_execution(targets, is_at_athena)

        def on_cancel():
            dlg.destroy()

        tk.Button(btn_box, text="▶ BẮT ĐẦU CHẠY SONG SONG", font=("Segoe UI", 10, "bold"), 
                  bg=THEME["purple"], fg="#11111b", activebackground="#dcd7ba",
                  relief="flat", padx=20, pady=7, cursor="hand2", command=on_confirm).pack(side=tk.RIGHT, padx=(10, 0))

        tk.Button(btn_box, text="Hủy bỏ", font=("Segoe UI", 9), 
                  bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", padx=15, pady=7, 
                  cursor="hand2", command=on_cancel).pack(side=tk.RIGHT)

    def _run_single_node_route(self, target, already_at_athena):
        """Thực hiện lộ trình di chuyển độc lập cho một nhân vật cụ thể."""
        if already_at_athena:
            self.log_event("ROUTE", target.name, f"🏛️ [ĐÃ Ở ATHENA] Bắt đầu chạy bộ tới Cursed Palace...")
            steps_to_run = [s for s in ROUTE_STEPS if "PHASE 1" not in s.get("phase", "")]
        else:
            self.log_event("ROUTE", target.name, f"🏛️ [LỘ TRÌNH ĐẦY ĐỦ] Bắt đầu MiniDragonfly -> Athena -> Cursed Palace...")
            steps_to_run = ROUTE_STEPS

        target.npc_dialog_received = False
        target.voucher_deducted_received = False
        target.cursed_palace_map_received = False

        total_steps = len(steps_to_run)
        curr_phase = ""

        for idx, step in enumerate(steps_to_run, 1):
            if self.auto_route_cancel:
                self.log_event("WARNING", target.name, "⏹️ Lộ trình đã bị người dùng DỪNG LẠI.")
                return False

            if "phase" in step and step["phase"] != curr_phase:
                curr_phase = step["phase"]
                self.log_event("ROUTE", target.name, f"━━ {curr_phase} ━━")

            desc = step["desc"]
            pkt = step["packet"]
            delay = step["delay"]

            # Tự động nhận diện vị trí MiniDragonfly thực tế trong túi đồ
            if "Kích hoạt MiniDragonfly" in desc:
                target.read_bag_memory()
                fly_slots = [s for s, it in target.inventory.items() if it.get("code") == CODE_MINIDRAGONFLY]
                fly_slot = fly_slots[0] if fly_slots else 1
                pkt = bytes([0x17, 0x59, 0x1F, fly_slot, 0x02])
                desc = f"Kích hoạt MiniDragonfly tại Ô Slot {fly_slot:02d} (Menu GPS)"

            # Reset cờ thoại trước khi bắt đầu tương tác NPC Lính canh
            if "Kích hoạt đối thoại Lính canh" in desc or "Tương tác với NPC Lính canh" in desc:
                target.npc_dialog_received = False

            target.send_packet(pkt)
            self.log_event("ROUTE", target.name, f"[{idx:02d}/{total_steps:02d}] {desc} (Delay: {delay:4.2f}s)")

            # Nếu vừa đóng bảng bay sang Athena: Thông báo đang đợi map nạp
            if "Đóng hộp thoại bay" in desc:
                self.log_event("ROUTE", target.name, "⏳ Đang đợi 2.5s cho bản đồ Athena nạp hoàn tất trước khi bước đi...")

            # Kiểm tra phản hồi từ Server khi nói chuyện NPC Lính canh
            if "Lượt 1" in desc:
                self.log_event("ROUTE", target.name, "🔍 Đang kiểm tra phản hồi từ Server để xác nhận đã đến đúng NPC Lính canh...")
                wait_start = time.time()
                while time.time() - wait_start < 3.5:
                    if target.npc_dialog_received:
                        break
                    if self.auto_route_cancel:
                        return False
                    time.sleep(0.05)

                if not target.npc_dialog_received and not self.auto_route_cancel:
                    self.log_event("ERROR", target.name, "❌ LỖI: Server KHÔNG phản hồi đối thoại NPC Lính canh!")
                    self.log_event("WARNING", target.name, "⏹️ Nhân vật dừng lộ trình an toàn để tránh kẹt.")
                    return False
                else:
                    self.log_event("SUCCESS", target.name, "✔ XÁC NHẬN: Server ĐÃ PHẢN HỒI thoại NPC! Bắt đầu nộp vé vào Cursed Palace.")

            # Sleep ngắt quãng để hủy tức thì khi người dùng bấm Dừng
            end_time = time.time() + delay
            while time.time() < end_time:
                if self.auto_route_cancel:
                    return False
                time.sleep(0.04)

        if not self.auto_route_cancel:
            if target.voucher_deducted_received:
                self.log_event("SUCCESS", target.name, "✔ Đã trừ 2 vé RegisVoucher thành công!")
            self.log_event("SUCCESS", target.name, "★ ĐÃ HOÀN TẤT LỘ TRÌNH VÀO CURSED PALACE THÀNH CÔNG! ★")
            return True
        return False

    def _start_cursed_palace_execution(self, targets, already_at_athena):
        if not isinstance(targets, list):
            targets = [targets]

        def _run_parallel_routes():
            self.auto_route_running = True
            self.auto_route_cancel = False
            self.auto_route_targets = targets
            self.event_queue.put(("ROUTE_STATUS", "RUNNING", f"Song song ({len(targets)} acc)"))

            # 0. Nếu chạy từ Phase 1 (MiniDragonfly): giải tán tổ đội cho tất cả acc trước khi bay
            if not already_at_athena:
                self.log_event("ROUTE", "MASTER", f"🚀 [BẮT ĐẦU SONG SONG {len(targets)} ACC] Giải tán tổ đội trước khi dùng MiniDragonfly...")
                for t in targets:
                    if t.in_party or (self.leader_node and t.name == self.leader_node.name):
                        t.leave_party()
                time.sleep(1.0)
            else:
                self.log_event("ROUTE", "MASTER", f"🚀 [BẮT ĐẦU SONG SONG {len(targets)} ACC] Xuất phát đồng loạt từ Athena...")

            results = {}
            threads = []

            def _worker(node):
                try:
                    res = self._run_single_node_route(node, already_at_athena)
                    results[node.name] = res
                except Exception as e:
                    self.log_event("ERROR", node.name, f"Lỗi di chuyển: {e}")
                    results[node.name] = False

            # Khởi chạy đồng thời cho tất cả các acc với độ trễ siêu nhỏ 0.12s
            for node in targets:
                th = threading.Thread(target=_worker, args=(node,), daemon=True)
                threads.append(th)
                th.start()
                time.sleep(0.12)

            # Chờ tất cả acc hoàn tất
            for th in threads:
                th.join()

            succ_count = sum(1 for v in results.values() if v)
            if not self.auto_route_cancel:
                if succ_count == len(targets):
                    self.log_event("SUCCESS", "MASTER", f"🎉 [HOÀN TẤT SONG SONG] Toàn bộ {len(targets)} acc đã đến Cursed Palace thành công!")
                    messagebox.showinfo("Thành công", f"Toàn bộ {len(targets)} nhân vật đã hoàn tất lộ trình song song thành công!")
                else:
                    self.log_event("WARNING", "MASTER", f"⚠️ Có {succ_count}/{len(targets)} acc hoàn tất thành công.")
            else:
                self.log_event("WARNING", "MASTER", "⏹️ Lộ trình song song đã được hủy bởi người dùng.")

            self.auto_route_running = False
            self.auto_route_cancel = False
            self.auto_route_targets = []
            self.event_queue.put(("ROUTE_STATUS", "IDLE", None))

        threading.Thread(target=_run_parallel_routes, daemon=True).start()

    def action_resummon_all_pets(self):
        """Kiểm tra và gửi lệnh xuất chiến Pet cho toàn bộ thành viên đang kết nối."""
        self.log_event("INFO", "MASTER", "🐾 [LỆNH THỦ CÔNG] Đang kiểm tra và gửi lệnh Xuất chiến Pet cho toàn bộ thành viên...")
        count = 0
        for name, node in self.nodes.items():
            if node.active_socket > 0:
                threading.Thread(target=node._check_and_resummon_pet, args=(True,), daemon=True).start()
                count += 1
        if count == 0:
            messagebox.showinfo("Thông báo", "Chưa có nhân vật nào kết nối game để gọi Pet!")

    def action_sweep_trash_all(self):
        """Quét và dọn sạch rác túi đồ cho toàn bộ các client đang kết nối."""
        if not self.nodes:
            self.log_event("WARNING", "MASTER", "Chưa có nhân vật nào kết nối game để dọn rác!")
            return

        def _worker():
            self.log_event("PARTY", "MASTER", "🧹 [LỆNH DỌN RÁC] Bắt đầu quét RAM và dọn sạch túi đồ cho TẤT CẢ clients...")
            total = 0
            for name, node in self.nodes.items():
                if node.active_socket > 0:
                    cnt = node.sweep_trash()
                    total += cnt
            self.log_event("SUCCESS", "MASTER", f"✨ [HOÀN TẤT DỌN TÚI TẤT CẢ] Đã dọn xong. Tổng cộng đã vứt: {total} món rác!")

        threading.Thread(target=_worker, daemon=True).start()

    def action_sweep_trash_single(self, node):
        """Quét và dọn rác túi đồ cho riêng 1 client."""
        if not node or node.active_socket <= 0:
            self.log_event("WARNING", node.name if node else "SYSTEM", "Client này chưa kết nối game!")
            return
        self.log_event("INFO", node.name, "🧹 [LỆNH DỌN RÁC] Đang quét RAM và dọn túi đồ...")
        threading.Thread(target=node.sweep_trash, daemon=True).start()

    def action_toggle_auto_national_treasure(self):
        """Kích hoạt hoặc dừng tự động mở rương Quốc Bảo (1..30 -> Đánh quái -> Có chìa khóa thì dừng ngay)."""
        if self.auto_treasure_running:
            if messagebox.askyesno("Dừng Auto Quốc Bảo", "Đang tự động mở rương Quốc Bảo!\n\nBạn có muốn DỪNG LẠI ngay lập tức không?"):
                self.auto_treasure_cancel = True
                self.log_event("WARNING", "MASTER", "⏹️ Đang gửi tín hiệu dừng tự động mở rương Quốc Bảo...")
            return

        # Ưu tiên nhân vật F04 hoặc Leader
        target = None
        for n in self.nodes.values():
            if "f04" in n.name.lower() and n.active_socket > 0:
                target = n
                break
        if not target:
            target = self.leader_node
        if not target or target.active_socket <= 0:
            for n in self.nodes.values():
                if n.active_socket > 0:
                    target = n
                    break
        if not target or target.active_socket <= 0:
            messagebox.showwarning("Cảnh báo", "Chưa có nhân vật nào kết nối game để mở rương!")
            return

        self.auto_treasure_running = True
        self.auto_treasure_cancel = False
        self.auto_treasure_key_found = False
        self.auto_treasure_chests_unlocked = False
        self.auto_treasure_target = target

        threading.Thread(target=self._run_auto_national_treasure, daemon=True).start()

    def _auto_treasure_combat_loop(self):
        """Xử lý chiến đấu tự động khi mở trúng rương có quái vật trong Quốc Bảo"""
        time.sleep(1.2)
        while getattr(self, "in_battle", False) and getattr(self, "auto_treasure_running", False):
            self.combat_turn += 1
            self.log_event("INFO", "COMBAT", f"⚡ [QUỐC BẢO BATTLE] Đang thực hiện Hiệp {self.combat_turn}...")

            # 1. Tìm node F04
            f04_node = None
            for n in self.nodes.values():
                if "f04" in n.name.lower() and n.active_socket > 0:
                    f04_node = n
                    break

            # Sát thương chính F04
            if f04_node:
                target_slot, target_row = 1, 2
                # Pet F04 dùng 043b vào Hàng 3 (Slot 1 Row 3)
                pkt_f04_pet = bytes([0x32, 0x01, 0x04, 0x02, target_slot, 3]) + SKILL_PET_043B + bytes([0x00])
                f04_node.send_packet(pkt_f04_pet)
                # Char F04 dùng 1f3b vào Hàng 2 (Slot 1 Row 2)
                pkt_f04_char = bytes([0x32, 0x01, 0x03, 0x02, target_slot, target_row]) + SKILL_FIRE_1F3B + bytes([0x00])
                f04_node.send_packet(pkt_f04_char)

            # 2. Các thành viên khác: Hiệp 1 thủ (75ea), Hiệp sau pet tấn công (2d2b)
            for n in self.nodes.values():
                if f04_node and n.name == f04_node.name:
                    continue
                if n.active_socket <= 0:
                    continue

                row = 1
                if "w04" in n.name.lower():
                    row = 4
                elif "w03" in n.name.lower():
                    row = 3
                elif "wi01" in n.name.lower():
                    row = 1

                p_slot, c_slot = 4, 3
                if self.combat_turn == 1:
                    pkt_p = bytes([0x32, 0x01, p_slot, row, p_slot, row]) + SKILL_DEFEND + bytes([0x00])
                    pkt_c = bytes([0x32, 0x01, c_slot, row, c_slot, row]) + SKILL_DEFEND + bytes([0x00])
                else:
                    pkt_p = bytes([0x32, 0x01, p_slot, row, 1, 2]) + SKILL_PET_2D2B + bytes([0x00])
                    pkt_c = bytes([0x32, 0x01, c_slot, row, c_slot, row]) + SKILL_DEFEND + bytes([0x00])

                n.send_packet(pkt_p)
                n.send_packet(pkt_c)

            time.sleep(3.5)

    def _run_auto_national_treasure(self):
        """Vòng lặp mở từng rương từ 1..30, tự động dừng ngay lập tức khi xuất hiện Chìa Khóa Quốc Bảo"""
        target = self.auto_treasure_target
        nick = target.name.replace("alogin-", "").replace(".exe", "")
        self.log_event("SUCCESS", "TREASURE", f"🚀 BẮT ĐẦU AUTO QUỐC BẢO CHO [{target.name}]!")
        self.log_event("INFO", "TREASURE", "📌 Quy tắc: Mở từng rương (1..30) -> Gặp quái tự đánh -> Có CHÌA KHÓA thì DỪNG NGAY LẬP TỨC!")

        max_chests = 30
        for chest_idx in range(1, max_chests + 1):
            if self.auto_treasure_cancel:
                self.log_event("WARNING", "TREASURE", "⏹️ Tự động mở rương Quốc Bảo đã bị người dùng DỪNG LẠI.")
                break

            if self.auto_treasure_key_found or self.auto_treasure_chests_unlocked:
                self.log_event("SUCCESS", "TREASURE", "🎉 [HOÀN TẤT PHÒNG] Đã có Chìa khóa Quốc Bảo! Tất cả rương đã mở.")
                self.log_event("SUCCESS", "TREASURE", "👉 Vui lòng bước qua cổng dịch chuyển để sang phòng tiếp theo.")
                break

            # Nếu đang trong trận đánh -> Đợi trận kết thúc
            if getattr(self, "in_battle", False):
                self.log_event("INFO", "TREASURE", "⏳ Đang trong trận chiến, đợi dọn xong quái vật...")
                while getattr(self, "in_battle", False) and not self.auto_treasure_cancel:
                    time.sleep(1.0)
                time.sleep(1.2)  # Đồng bộ sau trận

            if self.auto_treasure_key_found or self.auto_treasure_chests_unlocked:
                break

            # Cập nhật trạng thái hiển thị
            self.event_queue.put(("TREASURE_STATUS", "RUNNING", chest_idx))
            self.log_event("INFO", "TREASURE", f"👉 [{nick}] Đang gửi lệnh mở Rương #{chest_idx:02d} (0x{chest_idx:04X})...")

            # Gửi C->S Op: 0x14 Sub: 0x01 [chest_idx 2B LE]
            body = bytes([0x14, 0x01]) + struct.pack("<H", chest_idx)
            target.send_packet(body)

            # Chờ phản hồi từ Server (2 giây)
            wait_start = time.time()
            while time.time() - wait_start < 2.0:
                if self.auto_treasure_cancel or self.auto_treasure_key_found or self.auto_treasure_chests_unlocked or getattr(self, "in_battle", False):
                    break
                time.sleep(0.1)

            # Nếu gặp quái nổ ra trận đánh
            if getattr(self, "in_battle", False):
                self.log_event("WARNING", "TREASURE", f"⚔️ Quái vật xuất hiện từ Rương #{chest_idx:02d}! Đang chiến đấu...")
                while getattr(self, "in_battle", False) and not self.auto_treasure_cancel:
                    time.sleep(1.0)
                time.sleep(1.5)  # Đồng bộ sau trận & tự động gọi pet

            if self.auto_treasure_key_found or self.auto_treasure_chests_unlocked:
                self.log_event("SUCCESS", "TREASURE", "🎉 [HOÀN TẤT PHÒNG] Đã nhận được Chìa khóa sau trận đánh!")
                break

            time.sleep(0.6)

        # Kết thúc vòng lặp phòng
        has_key = self.auto_treasure_key_found or self.auto_treasure_chests_unlocked
        if has_key:
            self.log_event("SUCCESS", "TREASURE", "★ ĐÃ HOÀN TẤT MỞ RƯƠNG PHÒNG HIỆN TẠI THÀNH CÔNG! SẴN SÀNG SANG PHÒNG KẾ TIẾP.")
            messagebox.showinfo("Quốc Bảo - Chìa Khóa!", "Đã nhận được Chìa khóa Quốc Bảo!\nTất cả rương trong phòng đã mở khóa.\nVui lòng di chuyển sang phòng tiếp theo.")
        elif not self.auto_treasure_cancel:
            self.log_event("INFO", "TREASURE", f"Đã mở hết {max_chests} rương trong phòng hiện tại.")

        self.auto_treasure_running = False
        self.auto_treasure_cancel = False
        self.event_queue.put(("TREASURE_STATUS", "IDLE", 0))

    def action_toggle_auto_move_items(self, target_node=None):
        """Kích hoạt hoặc dừng tự động dồn đồ & sắp xếp túi (Relog -> Merge trùng -> Dồn đáy túi)."""
        if self.auto_move_running:
            if messagebox.askyesno("Dừng dồn đồ", "Thao tác dồn đồ & sắp xếp túi đang diễn ra!\n\nBạn có muốn DỪNG LẠI ngay lập tức không?"):
                self.auto_move_cancel = True
                self.log_event("WARNING", "MASTER", "⏹️ Đang gửi tín hiệu dừng dồn đồ...")
            return

        target = target_node or self.leader_node
        if not target:
            for n in self.nodes.values():
                if n.active_socket > 0:
                    target = n
                    break
        if not target:
            messagebox.showwarning("Cảnh báo", "Chưa có nhân vật nào sẵn sàng để dồn đồ!")
            return

        if target.active_socket <= 0:
            messagebox.showwarning("Cảnh báo", f"Tiến trình {target.name} chưa có Socket kết nối game!\nVui lòng đăng nhập nhân vật vào game trước.")
            return

        # Hộp thoại cấu hình trực quan
        dlg = tk.Toplevel(self.root)
        dlg.title("Cấu Hình Tự Động Dồn Đồ & Sắp Xếp Túi")
        dlg.geometry("580x480")
        dlg.configure(bg=THEME["bg_card"])
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="📦 TỰ ĐỘNG DỒN ĐỒ & SẮP XẾP TÚI (SMART COMPACTOR)", 
                 font=("Segoe UI", 12, "bold"), fg=THEME["cyan"], bg=THEME["bg_card"]).pack(pady=(16, 6))

        proc_frame = tk.Frame(dlg, bg=THEME["bg_card"])
        proc_frame.pack(pady=(0, 10))
        tk.Label(proc_frame, text="Nhân vật thực hiện: ", font=("Segoe UI", 10), 
                 fg=THEME["text_muted"], bg=THEME["bg_card"]).pack(side=tk.LEFT)

        selected_proc_var = tk.StringVar(value=target.name)
        proc_combo = ttk.Combobox(proc_frame, textvariable=selected_proc_var, state="readonly", width=22)
        proc_combo["values"] = list(self.nodes.keys())
        proc_combo.pack(side=tk.LEFT, padx=5)

        # Khung lựa chọn hướng dồn đồ
        dir_box = tk.LabelFrame(dlg, text="  Hướng Dồn Túi Đồ  ", font=("Segoe UI", 10, "bold"),
                                fg=THEME["primary"], bg=THEME["bg_card"], padx=15, pady=8)
        dir_box.pack(fill=tk.X, padx=20, pady=(0, 8))

        mode_var = tk.StringVar(value="bottom")
        r_bottom = tk.Radiobutton(dir_box, text="⬇ Dồn xuống đáy túi (Ô 50, 49, 48... Khuyên dùng - Cố định Ô 01 & 02, Tiện nhận quà)",
                                  variable=mode_var, value="bottom", font=("Segoe UI", 9, "bold"),
                                  fg=THEME["orange"], bg=THEME["bg_card"], selectcolor=THEME["bg_dark"],
                                  activebackground=THEME["bg_card"], activeforeground=THEME["orange"])
        r_bottom.pack(anchor=tk.W, pady=(0, 3))

        r_top = tk.Radiobutton(dir_box, text="⬆ Dồn lên đầu túi (Ô 01, 02, 03... Liền mạch từ đầu đến cuối)",
                               variable=mode_var, value="top", font=("Segoe UI", 9),
                               fg=THEME["green"], bg=THEME["bg_card"], selectcolor=THEME["bg_dark"],
                               activebackground=THEME["bg_card"], activeforeground=THEME["green"])
        r_top.pack(anchor=tk.W)

        # Khung tùy chọn chức năng
        opt_box = tk.LabelFrame(dlg, text="  Tùy Chọn Thông Minh  ", font=("Segoe UI", 10, "bold"),
                                fg=THEME["primary"], bg=THEME["bg_card"], padx=15, pady=8)
        opt_box.pack(fill=tk.X, padx=20, pady=(0, 10))

        merge_var = tk.BooleanVar(value=True)
        chk_merge = tk.Checkbutton(opt_box, text="📦 Tự động gộp vật phẩm trùng lặp (Chỉ gộp vật phẩm cộng dồn, bỏ qua trang bị)",
                                   variable=merge_var, font=("Segoe UI", 9),
                                   fg=THEME["text_main"], bg=THEME["bg_card"], selectcolor=THEME["bg_dark"],
                                   activebackground=THEME["bg_card"], activeforeground=THEME["text_main"])
        chk_merge.pack(anchor=tk.W, pady=(0, 3))

        protect_var = tk.BooleanVar(value=True)
        chk_protect = tk.Checkbutton(opt_box, text="🛡️ Đặt MiniDragonfly ở Ô 01 & RegisVoucher ở Ô 02 (Chỉ khi dồn xuống đáy)",
                                     variable=protect_var, font=("Segoe UI", 9),
                                     fg=THEME["purple"], bg=THEME["bg_card"], selectcolor=THEME["bg_dark"],
                                     activebackground=THEME["bg_card"], activeforeground=THEME["purple"])
        chk_protect.pack(anchor=tk.W, pady=(0, 3))

        use_ram_var = tk.BooleanVar(value=True)
        chk_ram = tk.Checkbutton(opt_box, text="⚡ Đọc trực tiếp từ bộ nhớ RAM (Siêu tốc 0.05s, không cần Relog)",
                                 variable=use_ram_var, font=("Segoe UI", 8),
                                 fg=THEME["cyan"], bg=THEME["bg_card"], selectcolor=THEME["bg_dark"],
                                 activebackground=THEME["bg_card"], activeforeground=THEME["cyan"])
        chk_ram.pack(anchor=tk.W)

        # Khung thông tin tóm tắt quy trình
        info_frame = tk.Frame(dlg, bg=THEME["bg_input"], padx=15, pady=8)
        info_frame.pack(fill=tk.X, padx=20, pady=(0, 12))

        info_text = (
            "• Thuật toán Con Trỏ Kép (Two-Pointer): Luôn dời vào ô ĐANG TRỐNG, không swap nhầm.\n"
            "• Bộ lọc Stackable thông minh: Tuyệt đối không gộp trang bị / nón / vũ khí / vé số.\n"
            "• Cơ chế Multi-Pass: Tự động quét lại RAM và dọn sạch các ô sót do lag mạng."
        )
        tk.Label(info_frame, text=info_text, font=("Segoe UI", 8), justify=tk.LEFT,
                 fg=THEME["text_muted"], bg=THEME["bg_input"]).pack(anchor=tk.W)

        btn_box = tk.Frame(dlg, bg=THEME["bg_card"])
        btn_box.pack(fill=tk.X, padx=20, pady=(0, 10))

        def on_confirm():
            chosen_name = selected_proc_var.get()
            chosen_node = self.nodes.get(chosen_name, target)
            chosen_mode = mode_var.get()
            do_merge = merge_var.get()
            do_protect = protect_var.get()
            use_ram = use_ram_var.get()
            dlg.destroy()
            self._start_auto_move_execution(
                chosen_node, 
                mode=chosen_mode, 
                smart_merge=do_merge, 
                protect_special=do_protect, 
                use_ram=use_ram
            )

        def on_cancel():
            dlg.destroy()

        tk.Button(btn_box, text="▶ BẮT ĐẦU DỒN ĐỒ", font=("Segoe UI", 10, "bold"), 
                  bg=THEME["cyan"], fg="#11111b", activebackground="#a6e3a1",
                  relief="flat", padx=20, pady=7, cursor="hand2", command=on_confirm).pack(side=tk.RIGHT, padx=(10, 0))

        tk.Button(btn_box, text="Hủy bỏ", font=("Segoe UI", 9), 
                  bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", padx=15, pady=7, 
                  cursor="hand2", command=on_cancel).pack(side=tk.RIGHT)

    def _start_auto_move_execution(self, target, mode="bottom", smart_merge=True, protect_special=True, use_ram=True, delay=0.18):
        def _run_move():
            if getattr(target, "in_combat", False) or getattr(self, "in_battle", False):
                self.log_event("WARNING", target.name, "⚔️ Nhân vật đang trong trận đánh! Server WLO sẽ hoãn gói tin dời đồ cho đến khi hết trận.")

            self.auto_move_running = True
            self.auto_move_cancel = False
            self.auto_move_target = target
            self.event_queue.put(("MOVE_STATUS", "RUNNING", target.name))

            # BƯỚC 1: LẤY DỮ LIỆU TÚI ĐỒ (ƯU TIÊN QUÉT TRỰC TIẾP TỪ BỘ NHỚ RAM SIÊU TỐC)
            if use_ram:
                self.log_event("ROUTE", target.name, "🔍 [BƯỚC 1] Đang đọc túi đồ trực tiếp từ bộ nhớ RAM...")
                ok = target.read_bag_memory()
                if ok and len(target.inventory) > 0:
                    self.log_event("SUCCESS", target.name, f"★ Đã đọc thành công {len(target.inventory)}/50 ô đồ trực tiếp từ RAM!")
                else:
                    self.log_event("WARNING", target.name, "⚠️ Chưa quét được túi đồ từ RAM, thử kiểm tra lại...")

            if self.auto_move_cancel:
                self._finish_move(target)
                return

            if len(target.inventory) == 0:
                self.log_event("ERROR", target.name, "❌ Không có dữ liệu túi đồ (Túi rỗng hoặc chưa nạp được)!")
                def _show_err():
                    messagebox.showwarning("Cảnh báo", f"Không tìm thấy dữ liệu túi đồ của [{target.name}]!\nHãy chắc chắn nhân vật đã đăng nhập vào game.")
                self.root.after(0, _show_err)
                self._finish_move(target)
                return

            start_t = time.time()
            total_merged_moves = 0
            total_compact_moves = 0

            # GIAI ĐOẠN 1: GỘP CÁC VẬT PHẨM TRÙNG NHAU (SMART STACK MERGE)
            if smart_merge and not self.auto_move_cancel:
                self.log_event("ROUTE", target.name, "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self.log_event("ROUTE", target.name, "  [GIAI ĐOẠN 1/3] GỘP CÁC VẬT PHẨM TRÙNG NHAU (SMART STACK MERGE)")
                self.log_event("ROUTE", target.name, "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

                code_groups = {}
                for s, it in target.inventory.items():
                    code_groups.setdefault(it["code"], []).append(s)

                for code, slots in sorted(code_groups.items()):
                    if self.auto_move_cancel:
                        break
                    if len(slots) <= 1:
                        continue

                    max_qty_in_slots = max(target.inventory[s]["qty"] for s in slots)
                    if not is_stackable_item_global(code, max_qty_in_slots):
                        it_info = GLOBAL_ITEM_DB.get(f"0x{code:04X}", {})
                        it_name = it_info.get("name", f"0x{code:04X}")
                        self.log_event("ROUTE", target.name, f"  ℹ️ Bỏ qua gộp món trang bị/đạo cụ: {it_name} (Ô {slots})")
                        continue

                    # Sắp xếp chọn dest_slot:
                    # Nếu dồn lên đầu: gom về ô có số thứ tự nhỏ nhất
                    # Nếu dồn xuống đáy: gom về ô có số thứ tự lớn nhất
                    if mode == "top":
                        slots_sorted = sorted(slots)
                    else:
                        slots_sorted = sorted(slots, reverse=True)

                    dest_slot = slots_sorted[0]
                    src_slots = [s for s in slots_sorted if s != dest_slot]

                    for src_slot in src_slots:
                        if self.auto_move_cancel:
                            break
                        if dest_slot not in target.inventory or src_slot not in target.inventory:
                            continue

                        dest_qty = target.inventory[dest_slot]["qty"]
                        src_qty = target.inventory[src_slot]["qty"]
                        room = 50 - dest_qty
                        if room <= 0:
                            rem_dests = [s for s in src_slots if s in target.inventory and target.inventory[s]["qty"] < 50]
                            if not rem_dests:
                                break
                            dest_slot = rem_dests[0]
                            dest_qty = target.inventory[dest_slot]["qty"]
                            room = 50 - dest_qty

                        move_qty = min(src_qty, room)
                        if move_qty <= 0:
                            continue

                        it_info = GLOBAL_ITEM_DB.get(f"0x{code:04X}", {})
                        it_name = it_info.get("name", "")
                        self.log_event("ROUTE", target.name, f"  📦 Gộp 0x{code:04X} ({it_name}): Ô {src_slot:02d} (SL:{src_qty}) -> Ô {dest_slot:02d} (SL:{dest_qty}) [Gộp {move_qty}]...")
                        target.move_item(src_slot, move_qty, dest_slot)
                        
                        target.inventory[dest_slot]["qty"] += move_qty
                        target.inventory[src_slot]["qty"] -= move_qty
                        if target.inventory[src_slot]["qty"] == 0:
                            del target.inventory[src_slot]

                        total_merged_moves += 1
                        time.sleep(delay)

                if self.auto_move_cancel:
                    self._finish_move(target)
                    return

                self.log_event("SUCCESS", target.name, f"✔ Đã thực hiện {total_merged_moves} lệnh gộp vật phẩm trùng lặp.")
                time.sleep(0.35)
                target.read_bag_memory()

            # GIAI ĐOẠN 2: XẾP MINIDRAGONFLY LÊN Ô 01 & REGISVOUCHER LÊN Ô 02 (NẾU DỒN XUỐNG ĐÁY)
            fixed_special_slots = set()
            if mode == "bottom" and protect_special and not self.auto_move_cancel:
                fly_slots = [s for s, it in target.inventory.items() if it["code"] == CODE_MINIDRAGONFLY]
                vouch_slots = [s for s, it in target.inventory.items() if it["code"] == CODE_REGISVOUCHER]

                if fly_slots or vouch_slots:
                    self.log_event("ROUTE", target.name, "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                    self.log_event("ROUTE", target.name, "  [GIAI ĐOẠN 2/3] XẾP MINIDRAGONFLY (Ô 01) & REGISVOUCHER (Ô 02)")
                    self.log_event("ROUTE", target.name, "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

                    def _get_empty_bottom_temp():
                        for s in range(50, 2, -1):
                            if s not in target.inventory:
                                return s
                        return None

                    # 1. MiniDragonfly -> Ô 1
                    if fly_slots and fly_slots[0] != 1:
                        src_fly = fly_slots[0]
                        if 1 in target.inventory:
                            temp_s = _get_empty_bottom_temp()
                            if temp_s:
                                it_1 = target.inventory[1]
                                self.log_event("ROUTE", target.name, f"  🔄 Giải phóng Ô 01: Dời món 0x{it_1['code']:04X} -> Ô {temp_s:02d}...")
                                target.move_item(1, it_1["qty"], temp_s)
                                target.inventory[temp_s] = it_1
                                del target.inventory[1]
                                time.sleep(delay)
                        it_fly = target.inventory[src_fly]
                        self.log_event("ROUTE", target.name, f"  🛸 Xếp MiniDragonfly: Ô {src_fly:02d} -> Ô 01...")
                        target.move_item(src_fly, it_fly["qty"], 1)
                        target.inventory[1] = it_fly
                        del target.inventory[src_fly]
                        time.sleep(delay)

                    # 2. RegisVoucher -> Ô 2
                    vouch_slots = [s for s, it in target.inventory.items() if it["code"] == CODE_REGISVOUCHER]
                    if vouch_slots and vouch_slots[0] != 2:
                        src_vouch = vouch_slots[0]
                        if 2 in target.inventory:
                            temp_s = _get_empty_bottom_temp()
                            if temp_s:
                                it_2 = target.inventory[2]
                                self.log_event("ROUTE", target.name, f"  🔄 Giải phóng Ô 02: Dời món 0x{it_2['code']:04X} -> Ô {temp_s:02d}...")
                                target.move_item(2, it_2["qty"], temp_s)
                                target.inventory[temp_s] = it_2
                                del target.inventory[2]
                                time.sleep(delay)
                        it_vouch = target.inventory[src_vouch]
                        self.log_event("ROUTE", target.name, f"  🎫 Xếp RegisVoucher: Ô {src_vouch:02d} -> Ô 02...")
                        target.move_item(src_vouch, it_vouch["qty"], 2)
                        target.inventory[2] = it_vouch
                        del target.inventory[src_vouch]
                        time.sleep(delay)

                    time.sleep(0.35)
                    target.read_bag_memory()

                if 1 in target.inventory and target.inventory[1]["code"] == CODE_MINIDRAGONFLY:
                    fixed_special_slots.add(1)
                if 2 in target.inventory and target.inventory[2]["code"] == CODE_REGISVOUCHER:
                    fixed_special_slots.add(2)

            # GIAI ĐOẠN 3: TWO-POINTER COMPACTION VỚI MULTI-PASS VERIFICATION
            if not self.auto_move_cancel:
                self.log_event("ROUTE", target.name, "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                mode_title = "DỒN LÊN ĐẦU TÚI (TOP: 01, 02, 03...)" if mode == "top" else "DỒN XUỐNG ĐÁY TÚI (BOTTOM: 50, 49, 48...)"
                self.log_event("ROUTE", target.name, f"  [GIAI ĐOẠN 3/3] {mode_title}")
                self.log_event("ROUTE", target.name, "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

                max_passes = 8
                for pass_num in range(1, max_passes + 1):
                    if self.auto_move_cancel:
                        break

                    # Đọc lại RAM trước mỗi pass
                    target.read_bag_memory()

                    # Lập kế hoạch di chuyển
                    if mode == "top":
                        moves = generate_compaction_plan_to_top(target.inventory)
                    else:
                        moves = generate_compaction_plan_to_bottom(target.inventory, protect_slots=fixed_special_slots)

                    if not moves:
                        self.log_event("SUCCESS", target.name, f"✔ Túi đồ đã được dồn hoàn hảo 100% liền mạch (Đạt chuẩn ở Lượt {pass_num})!")
                        break

                    self.log_event("ROUTE", target.name, f"  ▶ [Lượt {pass_num}] Cần dời {len(moves)} món vào vị trí...")
                    for src, qty, dest, code in moves:
                        if self.auto_move_cancel:
                            break
                        it_info = GLOBAL_ITEM_DB.get(f"0x{code:04X}", {})
                        it_name = it_info.get("name", "")
                        self.log_event("ROUTE", target.name, f"  🚚 Dời: Ô {src:02d} -> Ô {dest:02d} (Mã 0x{code:04X} {it_name}, SL: {qty})...")
                        target.move_item(src, qty, dest)
                        total_compact_moves += 1
                        time.sleep(delay)

                    time.sleep(0.35)

            # BƯỚC 4: XÁC THỰC KẾT QUẢ CUỐI CÙNG TỪ RAM
            time.sleep(0.4)
            target.read_bag_memory()
            total_elapsed = time.time() - start_t

            if not self.auto_move_cancel:
                occupied = sorted(target.inventory.keys())
                empty_slots = [s for s in range(1, 51) if s not in target.inventory]

                self.log_event("SUCCESS", target.name, "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self.log_event("SUCCESS", target.name, f"★ ĐÃ HOÀN TẤT DỒN ĐỒ & SẮP XẾP TÚI CHO [{target.name}] ({total_elapsed:.1f}s)! ★")
                if 1 in target.inventory and target.inventory[1]["code"] == CODE_MINIDRAGONFLY:
                    self.log_event("SUCCESS", target.name, f"  • Ô 01 (🛸 MiniDragonfly): SL {target.inventory[1]['qty']}")
                if 2 in target.inventory and target.inventory[2]["code"] == CODE_REGISVOUCHER:
                    self.log_event("SUCCESS", target.name, f"  • Ô 02 (🎫 RegisVoucher) : SL {target.inventory[2]['qty']}")
                self.log_event("SUCCESS", target.name, f"  • Lệnh gộp trùng: {total_merged_moves} | Lệnh dời ô: {total_compact_moves}")
                if occupied:
                    self.log_event("SUCCESS", target.name, f"  • Vị trí các ô có đồ: Ô [{min(occupied):02d} .. {max(occupied):02d}] ({len(occupied)} ô)")
                if empty_slots:
                    self.log_event("SUCCESS", target.name, f"  • Vị trí các ô trống: Ô [{min(empty_slots):02d} .. {max(empty_slots):02d}] ({len(empty_slots)} ô trống)")
                self.log_event("SUCCESS", target.name, "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

                def _show_success():
                    fly_txt = f"• Ô 01: MiniDragonfly (SL: {target.inventory[1]['qty']})\n" if 1 in target.inventory and target.inventory[1]["code"] == CODE_MINIDRAGONFLY else ""
                    vouch_txt = f"• Ô 02: RegisVoucher (SL: {target.inventory[2]['qty']})\n" if 2 in target.inventory and target.inventory[2]["code"] == CODE_REGISVOUCHER else ""
                    range_txt = f"• Ô có đồ: [{min(occupied):02d} .. {max(occupied):02d}] ({len(occupied)} món)\n" if occupied else ""
                    empty_txt = f"• Ô trống: [{min(empty_slots):02d} .. {max(empty_slots):02d}] ({len(empty_slots)} ô)\n" if empty_slots else ""
                    direction_txt = "Dồn lên đầu túi (TOP)" if mode == "top" else "Dồn xuống đáy túi (BOTTOM)"
                    messagebox.showinfo(
                        "Dọn Túi Thành Công", 
                        f"Nhân vật [{target.name}] đã hoàn tất dồn đồ!\n\n"
                        f"• Chế độ: {direction_txt}\n"
                        f"{fly_txt}"
                        f"{vouch_txt}"
                        f"{range_txt}"
                        f"{empty_txt}"
                        f"• Lệnh gộp trùng: {total_merged_moves} | Lệnh dời ô: {total_compact_moves}\n"
                        f"• Thời gian: {total_elapsed:.1f}s"
                    )
                self.root.after(0, _show_success)

            self._finish_move(target)

        threading.Thread(target=_run_move, daemon=True).start()

    def _finish_move(self, target):
        self.auto_move_running = False
        self.auto_move_cancel = False
        self.auto_move_target = None
        self.event_queue.put(("MOVE_STATUS", "IDLE", None))

    # ==========================================================================
    # CẬP NHẬT TRẠNG THÁI & HÀNG ĐỢI SỰ KIỆN
    # ==========================================================================
    def register_char_id(self, node_name, char_id):
        self.known_chars[node_name.lower()] = char_id
        save_known_chars(self.known_chars)
        self.event_queue.put(("CHAR_ID", node_name, char_id))

    def learn_char_id(self, sender_id, exclude_name=""):
        for name, node in self.nodes.items():
            if name != exclude_name and not node.char_id:
                node.char_id = sender_id
                self.register_char_id(name, sender_id)
                break

    def update_leader_by_id(self, new_leader_id):
        for name, node in self.nodes.items():
            if node.char_id == new_leader_id:
                for other in self.nodes.values():
                    other.is_leader = False
                node.is_leader = True
                self.leader_node = node
                self.notify_state_changed()
                break

    def notify_state_changed(self):
        self.event_queue.put(("STATE_CHANGED", None, None))

    def log_packet(self, direction, node_name, opcode, subcode, hex_data):
        if self.filter_party_only_var.get() and opcode != 0x0D:
            return
        now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        sub_str = f" Sub:0x{subcode:02X}" if subcode is not None else ""
        msg = f"[{now_str}] [{node_name:<11} | {direction}] Op:0x{opcode:02X}{sub_str} | Hex: {hex_data}\n"
        self.event_queue.put(("LOG", direction.lower().replace("->", "2").replace("<-", "2"), msg))

    def log_event(self, tag, node_name, message):
        now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        msg = f"[{now_str}] [{node_name:<11}] {message}\n"
        self.event_queue.put(("LOG", tag.lower(), msg))

    def process_event_queue(self):
        try:
            while True:
                item = self.event_queue.get_nowait()
                ev_type = item[0]
                if ev_type == "LOG":
                    tag, text = item[1], item[2]
                    if hasattr(self, "log_text") and self.log_text:
                        self.log_text.insert(tk.END, text, tag)
                        self.log_text.see(tk.END)
                    else:
                        print(text, end="")
                elif ev_type in ("STATE_CHANGED", "CHAR_ID"):
                    self.refresh_cards_ui()
                elif ev_type == "ROUTE_STATUS":
                    status, target_name = item[1], item[2]
                    if hasattr(self, "btn_auto_palace") and self.btn_auto_palace:
                        if status == "RUNNING":
                            self.btn_auto_palace.config(text=f"⏹️ DỪNG LỘ TRÌNH ({target_name})", 
                                                        bg=THEME["red"], fg="#ffffff")
                        else:
                            self.btn_auto_palace.config(text="🏛️ ĐI ATHENA / CURSED PALACE (SONG SONG 4 ACC)", 
                                                        bg=THEME["purple"], fg="#11111b")
                elif ev_type == "MOVE_STATUS":
                    status, target_name = item[1], item[2]
                    if hasattr(self, "btn_auto_move") and self.btn_auto_move:
                        if status == "RUNNING":
                            self.btn_auto_move.config(text=f"⏹️ DỪNG DỒN ĐỒ ({target_name})", 
                                                      bg=THEME["red"], fg="#ffffff")
                        else:
                            self.btn_auto_move.config(text="📦 TỰ ĐỘNG DỒN ĐỒ (RELOG & MERGE)", 
                                                      bg=THEME["cyan"], fg="#11111b")
                elif ev_type == "TREASURE_STATUS":
                    status, chest_idx = item[1], item[2]
                    if hasattr(self, "btn_auto_treasure") and self.btn_auto_treasure:
                        if status == "RUNNING":
                            self.btn_auto_treasure.config(
                                text=f"⏹️ DỪNG QUỐC BẢO (RƯƠNG #{chest_idx:02d})",
                                bg=THEME["red"], fg="#ffffff"
                            )
                            if hasattr(self, "lbl_treasure_status") and self.lbl_treasure_status:
                                self.lbl_treasure_status.config(
                                    text=f"⚡ Đang mở Rương #{chest_idx:02d}...",
                                    fg=THEME["gold"]
                                )
                        else:
                            self.btn_auto_treasure.config(
                                text="💎 AUTO QUỐC BẢO (MỞ RƯƠNG & DỪNG KHI RA KHÓA)",
                                bg=THEME["gold"], fg="#11111b"
                            )
                            if hasattr(self, "lbl_treasure_status") and self.lbl_treasure_status:
                                self.lbl_treasure_status.config(
                                    text="Trạng thái: Sẵn sàng",
                                    fg=THEME["text_muted"]
                                )
        except queue.Empty:
            pass
        finally:
            self.root.after(50, self.process_event_queue)

    def refresh_cards_ui(self):
        if not hasattr(self, "card_widgets"):
            return

        if self.leader_node and hasattr(self, "lead_title_lbl"):
            lead_name = self.leader_node.name
            lead_pid = self.leader_node.pid
            lead_cid = f"0x{self.leader_node.char_id:08X}" if self.leader_node.char_id else "Chưa rõ"
            self.lead_title_lbl.config(text=f"👑 ĐỘI TRƯỞNG: {lead_name} (PID: {lead_pid}) | Char ID: {lead_cid}")

        for name, node in self.nodes.items():
            card = self.card_widgets.get(name)
            if not card:
                continue
            if hasattr(card, "sock_lbl"):
                sock_txt = f"Socket: #{node.active_socket} (6414)" if node.active_socket > 0 else "Socket: Đang dò..."
                sock_color = THEME["green"] if node.active_socket > 0 else THEME["yellow"]
                card.sock_lbl.config(text=sock_txt, fg=sock_color)
            if hasattr(card, "cid_lbl"):
                cid_txt = f"Char ID: 0x{node.char_id:08X}" if node.char_id else "Char ID: Chưa nhận (Bấm Relog)"
                cid_color = THEME["cyan"] if node.char_id else THEME["yellow"]
                card.cid_lbl.config(text=cid_txt, fg=cid_color)
            if hasattr(card, "status_lbl"):
                status_txt = "Trạng thái: ĐÃ VÀO ĐỘI" if node.in_party else "Trạng thái: Chưa vào đội"
                status_color = THEME["green"] if node.in_party else THEME["yellow"]
                card.status_lbl.config(text=status_txt, fg=status_color)

    def clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def copy_log(self):
        text = self.log_text.get("1.0", tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("Thành công", "Đã sao chép toàn bộ nội dung nhật ký vào Clipboard!")

    def save_log_to_file(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", 
                                                 filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                                                 title="Lưu file nhật ký gói tin")
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(self.log_text.get("1.0", tk.END))
            messagebox.showinfo("Thành công", f"Đã lưu nhật ký vào:\n{file_path}")

    def stop_all_nodes(self):
        for node in self.nodes.values():
            node.stop()
        self.nodes.clear()
        self.leader_node = None

    def on_closing(self):
        self.stop_all_nodes()
        self.root.destroy()

# ==============================================================================
# HÀM CHẠY CHÍNH
# ==============================================================================
def main():
    root = tk.Tk()
    app = WLOPartyGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
