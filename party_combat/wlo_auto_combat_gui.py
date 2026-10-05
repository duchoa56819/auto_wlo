#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO MULTI-PROCESS AUTO COMBAT & TARGET MANAGER (4 CLIENTS)
===========================================================
Giao diện Tự Động Ra Chiêu Chiến Đấu 4 Tiến Trình Độc Lập cho Wonderland Online.
- Chia UI thành 4 phần (2x2 Grid) tương ứng với 4 Process (Slot 1 -> Slot 4).
- Mục tiêu tách biệt 2 loại:
  1. Chọn theo hàng (Hàng 1, 2, 3, 4 - trước hay sau đều được).
  2. Chọn vị trí cụ thể (8 ô số 1-8).
  3. Kèm mục tiêu phe ta (Bản thân / Đồng đội).
- Bật/Tắt Auto độc lập từng slot hoặc đồng loạt cả 4 client.
- Tự động nhận diện quái còn sống (Smart target fallback).
"""

import os
import sys
import time
import json
import struct
import threading
import queue
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    frida = None

# ==============================================================================
# BẢNG MÀU CATPPUCCIN MOCHA / DARK GAMING THEME
# ==============================================================================
THEME = {
    "bg_dark": "#11111b",       # Header, statusbar
    "bg_main": "#181825",       # Nền chính
    "bg_card": "#1e1e2e",       # Khung slot
    "bg_card_inner": "#252538", # Khung con
    "bg_input": "#313244",      # Ô nhập liệu / combobox
    "border": "#45475a",
    "text_main": "#cdd6f4",     # Chữ sáng
    "text_muted": "#a6adc8",    # Chữ ghi chú
    "primary": "#89b4fa",       # Xanh dương
    "primary_active": "#1d4ed8",
    "green": "#a6e3a1",         # Bật auto / Healing
    "green_dark": "#1a3826",
    "red": "#f38ba8",           # Tắt auto / Sát thương
    "red_dark": "#3d1b24",
    "yellow": "#f9e2af",        # Cảnh báo / Pet
    "yellow_dark": "#3d3216",
    "yellow_active": "#d97706",
    "mauve": "#cba6f7",         # Char
    "mauve_dark": "#2d1f3f",
    "cyan": "#89dceb",          # Băng
    "cyan_dark": "#162f36",
    "peach": "#fab387",         # Lửa
    "peach_dark": "#3d2218",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DB_FILE = os.path.join(SCRIPT_DIR, "wlo_skills_database.json")

# Bản đồ 8 vị trí quái sàn đấu (Pos 1..8 -> Slot, Row)
# Slot 1 = Hàng trước (Front), Slot 2 = Hàng sau (Back)
POS_MAP = {
    1: (1, 1), 2: (1, 2), 3: (1, 3), 4: (1, 4),  # Hàng trước
    5: (2, 1), 6: (2, 2), 7: (2, 3), 8: (2, 4),  # Hàng sau
}

# Danh sách kỹ năng đầy đủ
CHAR_SKILLS = [
    # Hệ Nước
    ("[2B2B] Freeze - Băng Đông (Đóng Băng)", "2B2B"),
    ("[092F] Sleep - Thuật Gây Mê (Ngủ)", "092F"),
    ("[543B] Shrink - Thu Nhỏ Đối Thủ", "543B"),
    ("[C23A] Recover - Hồi Phục / Giải Trừ", "C23A"),
    ("[222B] Healing - Thuật Hồi Máu", "222B"),
    ("[7342] Water Fairy - Nữ Thần Thủy", "7342"),
    ("[793B] Water Dragon - Băng Long (Rồng Nước)", "793B"),
    # Hệ Hỏa
    ("[043B] BlazeBeating 3 - Liệt Hỏa Đả Kích 3 (Đấm Lửa)", "043B"),
    ("[332B] FireStoneBead 3 - Hỏa Đạn 3 (Đạn Lửa)", "332B"),
    ("[553B] Hot Fire - Nhiệt Hỏa Biệt Kỹ (Buff Công)", "553B"),
    ("[EB61] Fire Dragon - Hỏa Long (Rồng Lửa)", "EB61"),
    ("[7B42] Fire Fairy - Nữ Thần Hỏa", "7B42"),
    ("[C43A] Hagendis - Ma Thần Hagendis (CS Hỏa)", "C43A"),
    # Dùng chung
    ("[1427] Normal Attack - Đánh Thường", "1427"),
    ("[75EA] Defend - Phòng Thủ", "75EA"),
    ("[89EA] Flee - Bỏ Chạy", "89EA"),
]

PET_SKILLS = [
    # Pet Niss
    ("[1F3B] Thunder - Sấm Sét (Niss)", "1F3B"),
    ("[E33A] ManaBuff - Hồi SP cho Char (Niss)", "E33A"),
    # Pet Eva
    ("[FB2A] Mess - Hỗn Loạn Tâm Trí (Eva)", "FB2A"),
    ("[D861] GhostFire - Ma Hỏa / Quỷ Hỏa (Eva)", "D861"),
    # Dùng chung
    ("[1227] Normal Attack - Đánh Thường", "1227"),
    ("[75EA] Defend - Phòng Thủ", "75EA"),
    ("[89EA] Flee - Bỏ Chạy", "89EA"),
]

def pack_wlo_packet(body_bytes: bytes) -> bytes:
    """Đóng gói Magic Header 0xF4 0x44, uint16 LE Length và XOR 0xAD."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain = header + body_bytes
    return bytes(b ^ 0xAD for b in plain)

def build_combat_action_packet(actor_slot: int, actor_row: int,
                               target_slot: int, target_row: int,
                               skill_code_bytes: bytes) -> bytes:
    """
    Xây dựng gói tin Opcode 0x32 Subcode 0x01 gửi lên Server.
    Cấu trúc: [0x32, 0x01, ActorSlot, ActorRow, TargetSlot, TargetRow, SkillLE_0, SkillLE_1, 0x00, 0x00, 0x00]
    """
    body = bytearray([
        0x32, 0x01,
        actor_slot, actor_row,
        target_slot, target_row,
        skill_code_bytes[0], skill_code_bytes[1],
        0x00, 0x00, 0x00
    ])
    return pack_wlo_packet(bytes(body))

# ==============================================================================
# FRIDA HOOK SCRIPT: GẮN VÀO TỪNG CLIENT
# ==============================================================================
FRIDA_HOOK_JS = """
var activeSocket = -1;
var sendFunc = null;

function scanActiveSocket() {
    var p = Process.findModuleByName('ws2_32.dll');
    if (!p) p = Process.findModuleByName('wsock32.dll');
    if (!p) return -1;
    var getpeername = p.findExportByName('getpeername');
    var getsockname = p.findExportByName('getsockname');
    if (!getpeername || !getsockname) return -1;

    var fn_getpeername = new NativeFunction(getpeername, 'int', ['int', 'pointer', 'pointer']);
    var buf = Memory.alloc(32);
    var len = Memory.alloc(4);

    for (var s = 1; s < 4096; s++) {
        len.writeInt(32);
        if (fn_getpeername(s, buf, len) === 0) {
            var fam = buf.readU16();
            if (fam === 2) { // AF_INET
                activeSocket = s;
                send({type: 'socket_found', sock: s});
                return s;
            }
        }
    }
    return activeSocket;
}

function hookRecv(modName) {
    try {
        var m = Process.findModuleByName(modName);
        if (!m) return;
        var recvAddr = m.findExportByName('recv');
        if (!recvAddr) return;

        Interceptor.attach(recvAddr, {
            onEnter: function(args) {
                this.sock = args[0].toInt32();
                this.buf = args[1];
                this.len = args[2].toInt32();
            },
            onLeave: function(retval) {
                var bytesRecv = retval.toInt32();
                if (bytesRecv > 0) {
                    if (activeSocket <= 0) activeSocket = this.sock;
                    var copyBuf = this.buf.readByteArray(bytesRecv);
                    send({dir: 'recv', sock: this.sock, len: bytesRecv}, copyBuf);
                }
            }
        });
    } catch(e) {}
}

function hookSend(modName) {
    try {
        var m = Process.findModuleByName(modName);
        if (!m) return;
        var sAddr = m.findExportByName('send');
        if (!sAddr) return;
        sendFunc = new NativeFunction(sAddr, 'int', ['int', 'pointer', 'int', 'int']);

        Interceptor.attach(sAddr, {
            onEnter: function(args) {
                var s = args[0].toInt32();
                var len = args[2].toInt32();
                if (len > 0) {
                    if (activeSocket <= 0) activeSocket = s;
                    var copyBuf = args[1].readByteArray(len);
                    send({dir: 'send', sock: s, len: len}, copyBuf);
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
    if (activeSocket <= 0) scanActiveSocket();
    if (activeSocket <= 0) return {success: false, error: 'Chua tim thay socket ket noi'};
    if (!sendFunc) return {success: false, error: 'Khong tim thay ham send ws2_32'};

    var raw = [];
    for (var i = 0; i < hexBytes.length; i += 2) {
        raw.push(parseInt(hexBytes.substr(i, 2), 16));
    }
    var buf = Memory.alloc(raw.length);
    buf.writeByteArray(raw);
    try {
        var ret = sendFunc(activeSocket, buf, raw.length, 0);
        return {success: true, ret: ret, sock: activeSocket};
    } catch(e) {
        return {success: false, error: e.toString()};
    }
}

rpc.exports = {
    getsocket: function() { return scanActiveSocket(); },
    sendraw: function(hex) { return doSendRaw(hex); }
};
"""

class WLOStreamDissector:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, raw_bytes):
        decrypted = bytearray(b ^ 0xAD for b in raw_bytes)
        self.buffer.extend(decrypted)
        packets = []
        while len(self.buffer) >= 4:
            if self.buffer[0] != 0xF4 or self.buffer[1] != 0x44:
                idx = self.buffer.find(b'\xF4\x44')
                if idx == -1:
                    self.buffer.clear()
                    break
                self.buffer = self.buffer[idx:]
                if len(self.buffer) < 4:
                    break

            payload_len = struct.unpack("<H", self.buffer[2:4])[0]
            total_pkt_len = 4 + payload_len

            if len(self.buffer) < total_pkt_len:
                break

            pkt_raw = bytes(self.buffer[:total_pkt_len])
            body = pkt_raw[4:]
            self.buffer = self.buffer[total_pkt_len:]

            opcode = body[0] if len(body) > 0 else None
            subcode = body[1] if len(body) > 1 else None
            data = body[2:] if len(body) > 2 else b''

            packets.append((opcode, subcode, data, pkt_raw))
        return packets


# ==============================================================================
# CLASS PROCESS COMBAT SLOT (QUẢN LÝ 1 TRONG 4 TIẾN TRÌNH CLIENT)
# ==============================================================================
class ProcessCombatSlot:
    def __init__(self, slot_id: int, app, parent_frame: tk.Frame):
        self.slot_id = slot_id  # 0, 1, 2, 3 (Hiển thị Slot 1..4)
        self.app = app
        self.parent = parent_frame

        # Frida connection
        self.session = None
        self.script = None
        self.pid = None
        self.proc_name = ""

        # Mạng & Packet Dissector
        self.c2s_dissector = WLOStreamDissector()
        self.s2c_dissector = WLOStreamDissector()
        self.msg_queue = queue.Queue()

        # Trạng thái trận đấu
        self.in_battle = False
        self.turn_count = 0
        self.battle_phase = "IDLE"
        self.entities_hp = {}  # (slot, row) -> int
        self.entities_sp = {}  # (slot, row) -> int
        self.pending_turn_timer = None
        self.pending_cast_timer = None

        # Trạng thái Auto
        self.auto_combat_enabled = False

        # Lựa chọn Kỹ Năng & Mục Tiêu Char
        self.char_skill = "2B2B"  # Mặc định Freeze
        self.char_target_type = "row"  # "row", "pos", "ally"
        self.char_target_val = 2       # Hàng 2

        # Lựa chọn Kỹ Năng & Mục Tiêu Pet
        self.pet_skill = "1F3B"   # Mặc định Thunder
        self.pet_target_type = "row"  # "row", "pos", "ally"
        self.pet_target_val = 2       # Hàng 2

        # Registries nút bấm
        self.char_row_btns = {}
        self.char_pos_btns = {}
        self.char_ally_btns = {}

        self.pet_row_btns = {}
        self.pet_pos_btns = {}
        self.pet_ally_btns = {}

        # Xây dựng UI
        self.build_ui()

    def build_ui(self):
        """Xây dựng khung giao diện card cho Slot này."""
        self.card = tk.LabelFrame(self.parent, text=f" 🎮 SLOT #{self.slot_id + 1}: CHƯA KẾT NỐI ",
                                  bg=THEME["bg_card"], fg=THEME["primary"], font=("Segoe UI", 10, "bold"),
                                  padx=8, pady=6, bd=1, relief="ridge")
        self.card.pack(fill="both", expand=True)

        # ----------------------------------------------------------------------
        # 1. THANH TIÊU ĐỀ SLOT: CHỌN PROCESS, BÁO TRẬN, NÚT AUTO
        # ----------------------------------------------------------------------
        bar_top = tk.Frame(self.card, bg=THEME["bg_card"])
        bar_top.pack(fill="x", pady=(0, 6))

        self.cb_proc = ttk.Combobox(bar_top, state="readonly", font=("Segoe UI", 9), width=24)
        self.cb_proc.pack(side="left", padx=(0, 4))

        btn_attach = tk.Button(bar_top, text="🔗 Gắn", font=("Segoe UI", 8, "bold"),
                               bg=THEME["bg_input"], fg=THEME["primary"], relief="flat", padx=6, pady=2,
                               cursor="hand2", command=self.on_attach_clicked)
        btn_attach.pack(side="left", padx=(0, 8))

        # Đèn báo trạng thái trận
        self.lbl_battle_badge = tk.Label(bar_top, text="💤 NGOÀI TRẬN", font=("Segoe UI", 8, "bold"),
                                         bg=THEME["bg_input"], fg=THEME["text_muted"], padx=6, pady=2)
        self.lbl_battle_badge.pack(side="left", padx=(0, 6))

        # Chỉ số HP/SP
        self.lbl_stats = tk.Label(bar_top, text="🧙‍♂️ -- | 🧚‍♀️ --", font=("Segoe UI", 8),
                                  bg=THEME["bg_card_inner"], fg=THEME["text_muted"], padx=6, pady=2)
        self.lbl_stats.pack(side="left", padx=(0, 8))

        # Nút Auto của slot
        self.btn_auto = tk.Button(bar_top, text="▶ BẬT AUTO", font=("Segoe UI", 9, "bold"),
                                  bg=THEME["green"], fg="#11111b", relief="flat", padx=8, pady=2,
                                  cursor="hand2", command=self.toggle_auto)
        self.btn_auto.pack(side="right")

        # ----------------------------------------------------------------------
        # 2. KHUNG ĐIỀU KHIỂN CHÍNH (CHIA ĐÔI: CỘT CHAR - CỘT PET)
        # ----------------------------------------------------------------------
        f_body = tk.Frame(self.card, bg=THEME["bg_card"])
        f_body.pack(fill="both", expand=True)

        f_char_box = tk.LabelFrame(f_body, text=" 🧙‍♂️ Nhân Vật ", bg=THEME["bg_card_inner"],
                                   fg=THEME["mauve"], font=("Segoe UI", 9, "bold"), padx=6, pady=4)
        f_char_box.pack(side="left", fill="both", expand=True, padx=(0, 3))

        f_pet_box = tk.LabelFrame(f_body, text=" 🧚‍♀️ Pet Đồng Đội ", bg=THEME["bg_card_inner"],
                                  fg=THEME["yellow"], font=("Segoe UI", 9, "bold"), padx=6, pady=4)
        f_pet_box.pack(side="right", fill="both", expand=True, padx=(3, 0))

        # ==================== CỘT NHÂN VẬT (CHAR) ====================
        # Kỹ năng
        row_c_sk = tk.Frame(f_char_box, bg=THEME["bg_card_inner"])
        row_c_sk.pack(fill="x", pady=(0, 4))
        tk.Label(row_c_sk, text="Chiêu:", font=("Segoe UI", 8, "bold"),
                 bg=THEME["bg_card_inner"], fg=THEME["text_main"]).pack(side="left", padx=(0, 4))
        self.cb_char_skill = ttk.Combobox(row_c_sk, values=[s[0] for s in CHAR_SKILLS], state="readonly", font=("Segoe UI", 8))
        self.cb_char_skill.current(0)  # Freeze
        self.cb_char_skill.pack(side="left", fill="x", expand=True)
        self.cb_char_skill.bind("<<ComboboxSelected>>", self.on_char_skill_combo_changed)

        # Mục tiêu Loại 1: Chọn theo hàng (Hàng 1, 2, 3, 4 - trước hay sau đều được)
        row_c_row = tk.Frame(f_char_box, bg=THEME["bg_card_inner"])
        row_c_row.pack(fill="x", pady=1)
        tk.Label(row_c_row, text="Hàng (Trước/Sau):", font=("Segoe UI", 8),
                 bg=THEME["bg_card_inner"], fg=THEME["cyan"]).pack(side="left", padx=(0, 2))
        for r in [1, 2, 3, 4]:
            btn = tk.Button(row_c_row, text=f"H{r}", font=("Segoe UI", 8, "bold"),
                            bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", width=3,
                            cursor="hand2", command=lambda row_idx=r: self.select_char_target("row", row_idx))
            btn.pack(side="left", fill="x", expand=True, padx=1)
            self.char_row_btns[r] = btn

        # Mục tiêu Loại 2: Chọn vị trí cụ thể (8 ô số 1-8)
        row_c_pos_label = tk.Frame(f_char_box, bg=THEME["bg_card_inner"])
        row_c_pos_label.pack(fill="x", pady=(2, 0))
        tk.Label(row_c_pos_label, text="Vị trí cụ thể (1-8):", font=("Segoe UI", 8),
                 bg=THEME["bg_card_inner"], fg=THEME["primary"]).pack(side="left")

        row_c_pos1 = tk.Frame(f_char_box, bg=THEME["bg_card_inner"])
        row_c_pos1.pack(fill="x", pady=1)
        for p in [1, 2, 3, 4]:  # Hàng trước
            btn = tk.Button(row_c_pos1, text=str(p), font=("Segoe UI", 8, "bold"),
                            bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", width=3,
                            cursor="hand2", command=lambda pos_idx=p: self.select_char_target("pos", pos_idx))
            btn.pack(side="left", fill="x", expand=True, padx=1)
            self.char_pos_btns[p] = btn

        row_c_pos2 = tk.Frame(f_char_box, bg=THEME["bg_card_inner"])
        row_c_pos2.pack(fill="x", pady=1)
        for p in [5, 6, 7, 8]:  # Hàng sau
            btn = tk.Button(row_c_pos2, text=str(p), font=("Segoe UI", 8, "bold"),
                            bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", width=3,
                            cursor="hand2", command=lambda pos_idx=p: self.select_char_target("pos", pos_idx))
            btn.pack(side="left", fill="x", expand=True, padx=1)
            self.char_pos_btns[p] = btn

        # Mục tiêu Phe Ta (Hỗ trợ)
        row_c_ally = tk.Frame(f_char_box, bg=THEME["bg_card_inner"])
        row_c_ally.pack(fill="x", pady=(2, 0))
        btn_self = tk.Button(row_c_ally, text="🛡️ Bản Thân", font=("Segoe UI", 8, "bold"),
                             bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat",
                             cursor="hand2", command=lambda: self.select_char_target("ally", "self"))
        btn_self.pack(side="left", fill="x", expand=True, padx=1)
        self.char_ally_btns["self"] = btn_self

        btn_pet = tk.Button(row_c_ally, text="🧚 Pet", font=("Segoe UI", 8, "bold"),
                            bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat",
                            cursor="hand2", command=lambda: self.select_char_target("ally", "pet"))
        btn_pet.pack(side="left", fill="x", expand=True, padx=1)
        self.char_ally_btns["pet"] = btn_pet

        # ==================== CỘT PET ĐỒNG ĐỘI ====================
        # Kỹ năng
        row_p_sk = tk.Frame(f_pet_box, bg=THEME["bg_card_inner"])
        row_p_sk.pack(fill="x", pady=(0, 4))
        tk.Label(row_p_sk, text="Chiêu:", font=("Segoe UI", 8, "bold"),
                 bg=THEME["bg_card_inner"], fg=THEME["text_main"]).pack(side="left", padx=(0, 4))
        self.cb_pet_skill = ttk.Combobox(row_p_sk, values=[s[0] for s in PET_SKILLS], state="readonly", font=("Segoe UI", 8))
        self.cb_pet_skill.current(0)  # Thunder
        self.cb_pet_skill.pack(side="left", fill="x", expand=True)
        self.cb_pet_skill.bind("<<ComboboxSelected>>", self.on_pet_skill_combo_changed)

        # Mục tiêu Loại 1: Chọn theo hàng (Hàng 1, 2, 3, 4 - trước hay sau đều được)
        row_p_row = tk.Frame(f_pet_box, bg=THEME["bg_card_inner"])
        row_p_row.pack(fill="x", pady=1)
        tk.Label(row_p_row, text="Hàng (Trước/Sau):", font=("Segoe UI", 8),
                 bg=THEME["bg_card_inner"], fg=THEME["yellow"]).pack(side="left", padx=(0, 2))
        for r in [1, 2, 3, 4]:
            btn = tk.Button(row_p_row, text=f"H{r}", font=("Segoe UI", 8, "bold"),
                            bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", width=3,
                            cursor="hand2", command=lambda row_idx=r: self.select_pet_target("row", row_idx))
            btn.pack(side="left", fill="x", expand=True, padx=1)
            self.pet_row_btns[r] = btn

        # Mục tiêu Loại 2: Chọn vị trí cụ thể (8 ô số 1-8)
        row_p_pos_label = tk.Frame(f_pet_box, bg=THEME["bg_card_inner"])
        row_p_pos_label.pack(fill="x", pady=(2, 0))
        tk.Label(row_p_pos_label, text="Vị trí cụ thể (1-8):", font=("Segoe UI", 8),
                 bg=THEME["bg_card_inner"], fg=THEME["peach"]).pack(side="left")

        row_p_pos1 = tk.Frame(f_pet_box, bg=THEME["bg_card_inner"])
        row_p_pos1.pack(fill="x", pady=1)
        for p in [1, 2, 3, 4]:
            btn = tk.Button(row_p_pos1, text=str(p), font=("Segoe UI", 8, "bold"),
                            bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", width=3,
                            cursor="hand2", command=lambda pos_idx=p: self.select_pet_target("pos", pos_idx))
            btn.pack(side="left", fill="x", expand=True, padx=1)
            self.pet_pos_btns[p] = btn

        row_p_pos2 = tk.Frame(f_pet_box, bg=THEME["bg_card_inner"])
        row_p_pos2.pack(fill="x", pady=1)
        for p in [5, 6, 7, 8]:
            btn = tk.Button(row_p_pos2, text=str(p), font=("Segoe UI", 8, "bold"),
                            bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", width=3,
                            cursor="hand2", command=lambda pos_idx=p: self.select_pet_target("pos", pos_idx))
            btn.pack(side="left", fill="x", expand=True, padx=1)
            self.pet_pos_btns[p] = btn

        # Mục tiêu Phe Ta
        row_p_ally = tk.Frame(f_pet_box, bg=THEME["bg_card_inner"])
        row_p_ally.pack(fill="x", pady=(2, 0))
        btn_char = tk.Button(row_p_ally, text="🧙‍♂️ Chủ Nhân", font=("Segoe UI", 8, "bold"),
                             bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat",
                             cursor="hand2", command=lambda: self.select_pet_target("ally", "char"))
        btn_char.pack(side="left", fill="x", expand=True, padx=1)
        self.pet_ally_btns["char"] = btn_char

        btn_pet_self = tk.Button(row_p_ally, text="🛡️ Bản Thân", font=("Segoe UI", 8, "bold"),
                                 bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat",
                                 cursor="hand2", command=lambda: self.select_pet_target("ally", "self"))
        btn_pet_self.pack(side="left", fill="x", expand=True, padx=1)
        self.pet_ally_btns["self"] = btn_pet_self

        # ----------------------------------------------------------------------
        # 3. DƯỚI CÙNG SLOT: PHÍM TIỆN ÍCH & LOG MINI
        # ----------------------------------------------------------------------
        f_bottom = tk.Frame(self.card, bg=THEME["bg_card"])
        f_bottom.pack(fill="x", pady=(6, 0))

        btn_def = tk.Button(f_bottom, text="🛡️ Cả 2 Thủ", font=("Segoe UI", 8),
                            bg=THEME["bg_input"], fg=THEME["primary"], relief="flat", padx=4, pady=2,
                            command=self.set_both_defend)
        btn_def.pack(side="left", fill="x", expand=True, padx=1)

        btn_atk = tk.Button(f_bottom, text="⚔️ Cả 2 Đánh", font=("Segoe UI", 8),
                            bg=THEME["bg_input"], fg=THEME["text_main"], relief="flat", padx=4, pady=2,
                            command=self.set_both_normal_attack)
        btn_atk.pack(side="left", fill="x", expand=True, padx=1)

        btn_flee = tk.Button(f_bottom, text="🏃 Chạy", font=("Segoe UI", 8),
                             bg=THEME["red_dark"], fg=THEME["red"], relief="flat", padx=4, pady=2,
                             command=self.set_both_flee)
        btn_flee.pack(side="left", fill="x", expand=True, padx=1)

        btn_now = tk.Button(f_bottom, text="⚡ Ra Chiêu Ngay", font=("Segoe UI", 8, "bold"),
                            bg=THEME["cyan_dark"], fg=THEME["cyan"], relief="flat", padx=4, pady=2,
                            command=self.cast_now_immediate)
        btn_now.pack(side="left", fill="x", expand=True, padx=1)

        # Dòng trạng thái log mini của slot
        self.lbl_mini_log = tk.Label(self.card, text="Trạng thái: Chưa gắn tiến trình game",
                                     font=("Segoe UI", 8), bg=THEME["bg_card"], fg=THEME["text_muted"], anchor="w")
        self.lbl_mini_log.pack(fill="x", pady=(4, 0))

        # Khởi tạo highlight mặc định
        self.update_char_target_ui()
        self.update_pet_target_ui()

    # --------------------------------------------------------------------------
    # CHỌN MỤC TIÊU CHAR & PET
    # --------------------------------------------------------------------------
    def select_char_target(self, target_type: str, val):
        self.char_target_type = target_type
        self.char_target_val = val
        self.update_char_target_ui()
        t_str = self.get_target_desc_str("char")
        self.log(f"🧙‍♂️ Mục tiêu Char: {t_str}")

    def update_char_target_ui(self):
        # Reset toàn bộ nút Hàng Char
        for r, btn in self.char_row_btns.items():
            if self.char_target_type == "row" and self.char_target_val == r:
                btn.config(bg="#1d4ed8", fg="#ffffff", relief="solid", bd=1)
            else:
                btn.config(bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", bd=0)

        # Reset toàn bộ 8 ô số Char
        for p, btn in self.char_pos_btns.items():
            if self.char_target_type == "pos" and self.char_target_val == p:
                btn.config(bg="#1d4ed8", fg="#ffffff", relief="solid", bd=1)
            else:
                btn.config(bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", bd=0)

        # Reset nút Phe Ta
        for a, btn in self.char_ally_btns.items():
            if self.char_target_type == "ally" and self.char_target_val == a:
                btn.config(bg="#15803d", fg="#ffffff", relief="solid", bd=1)
            else:
                btn.config(bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", bd=0)

    def select_pet_target(self, target_type: str, val):
        self.pet_target_type = target_type
        self.pet_target_val = val
        self.update_pet_target_ui()
        t_str = self.get_target_desc_str("pet")
        self.log(f"🧚‍♀️ Mục tiêu Pet: {t_str}")

    def update_pet_target_ui(self):
        # Reset nút Hàng Pet
        for r, btn in self.pet_row_btns.items():
            if self.pet_target_type == "row" and self.pet_target_val == r:
                btn.config(bg="#b45309", fg="#ffffff", relief="solid", bd=1)
            else:
                btn.config(bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", bd=0)

        # Reset 8 ô số Pet
        for p, btn in self.pet_pos_btns.items():
            if self.pet_target_type == "pos" and self.pet_target_val == p:
                btn.config(bg="#b45309", fg="#ffffff", relief="solid", bd=1)
            else:
                btn.config(bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", bd=0)

        # Reset nút Phe Ta
        for a, btn in self.pet_ally_btns.items():
            if self.pet_target_type == "ally" and self.pet_target_val == a:
                btn.config(bg="#15803d", fg="#ffffff", relief="solid", bd=1)
            else:
                btn.config(bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", bd=0)

    def on_char_skill_combo_changed(self, event=None):
        val = self.cb_char_skill.get()
        if "[" in val and "]" in val:
            self.char_skill = val.split("]")[0].replace("[", "").strip().upper()
            # Tự động gợi ý mục tiêu theo loại chiêu
            s_info = self.app.skills_db.get(f"0x{self.char_skill}", {})
            t_type = s_info.get("target_type", "Enemy")
            if t_type == "Ally" and self.char_target_type != "ally":
                self.select_char_target("ally", "pet")
            elif t_type == "Self" and self.char_target_type != "ally":
                self.select_char_target("ally", "self")
            elif t_type == "Enemy" and self.char_target_type == "ally":
                self.select_char_target("row", 2)
            self.log(f"🧙‍♂️ Đã chọn chiêu: {val.split('-')[0].strip()}")

    def on_pet_skill_combo_changed(self, event=None):
        val = self.cb_pet_skill.get()
        if "[" in val and "]" in val:
            self.pet_skill = val.split("]")[0].replace("[", "").strip().upper()
            s_info = self.app.skills_db.get(f"0x{self.pet_skill}", {})
            t_type = s_info.get("target_type", "Enemy")
            if t_type == "Ally" and self.pet_target_type != "ally":
                self.select_pet_target("ally", "char")
            elif t_type == "Self" and self.pet_target_type != "ally":
                self.select_pet_target("ally", "self")
            elif t_type == "Enemy" and self.pet_target_type == "ally":
                self.select_pet_target("row", 2)
            self.log(f"🧚‍♀️ Đã chọn chiêu: {val.split('-')[0].strip()}")

    def get_target_desc_str(self, actor: str) -> str:
        t_type = self.char_target_type if actor == "char" else self.pet_target_type
        t_val = self.char_target_val if actor == "char" else self.pet_target_val
        if t_type == "row":
            return f"Hàng {t_val} (Trước/Sau)"
        elif t_type == "pos":
            return f"Vị trí ô số {t_val}"
        elif t_type == "ally":
            if t_val == "self":
                return "Bản thân"
            return "Pet Đồng Đội" if actor == "char" else "Chủ Nhân Char"
        return "Mục tiêu mặc định"

    # --------------------------------------------------------------------------
    # THUẬT TOÁN TÍNH TOÁN VỊ TRÍ MỤC TIÊU THỰC TẾ
    # --------------------------------------------------------------------------
    def resolve_target(self, actor: str):
        """
        Tính toán chính xác (target_slot, target_row, target_desc)
        dựa vào loại mục tiêu và HP của các đối tượng trên sân.
        """
        is_char = (actor == "char")
        t_type = self.char_target_type if is_char else self.pet_target_type
        t_val = self.char_target_val if is_char else self.pet_target_val

        # 1. Phe Ta (Ally / Self)
        if t_type == "ally":
            if t_val == "self":
                return ((4, 2, "Bản thân Char") if is_char else (3, 2, "Bản thân Pet"))
            else:
                return ((3, 2, "Pet Đồng Đội") if is_char else (4, 2, "Chủ Nhân Char"))

        # 2. Loại 1: Chọn theo hàng (Hàng 1, 2, 3, 4 - trước hay sau đều được)
        if t_type == "row":
            r = int(t_val)
            front_slot, front_row = 1, r
            back_slot, back_row = 2, r

            hp_front = self.entities_hp.get((front_slot, front_row), 1)
            hp_back = self.entities_hp.get((back_slot, back_row), 1)

            # Ưu tiên quái trước nếu còn sống
            if hp_front > 0:
                return front_slot, front_row, f"Hàng {r} (Trước - Pos {r})"
            # Nếu quái trước đã chết -> Tự chuyển sang quái sau cùng hàng
            elif hp_back > 0:
                return back_slot, back_row, f"Hàng {r} (Sau - Pos {r + 4})"
            else:
                # Cả hàng đều đã chết -> Quét tìm quái còn sống ở các hàng khác
                for alt_r in [2, 1, 3, 4]:
                    if self.entities_hp.get((1, alt_r), 1) > 0:
                        return 1, alt_r, f"Hàng {alt_r} (Trước - Pos {alt_r}) [Đổi Hàng]"
                    if self.entities_hp.get((2, alt_r), 1) > 0:
                        return 2, alt_r, f"Hàng {alt_r} (Sau - Pos {alt_r + 4}) [Đổi Hàng]"
                return front_slot, front_row, f"Hàng {r} (Pos {r})"

        # 3. Loại 2: Chọn vị trí cụ thể (8 ô số 1-8)
        if t_type == "pos":
            pos = int(t_val)
            slot, row = POS_MAP.get(pos, (1, 2))
            hp_val = self.entities_hp.get((slot, row), 1)

            if hp_val > 0:
                return slot, row, f"Ô số {pos}"
            else:
                # Quái ở vị trí cụ thể này đã chết -> Tự chuyển sang quái còn sống gần nhất
                for alt_p in [2, 6, 3, 7, 1, 5, 4, 8]:
                    s, r = POS_MAP[alt_p]
                    if self.entities_hp.get((s, r), 1) > 0:
                        return s, r, f"Ô {alt_p} [Tự Đổi vì Ô {pos} đã tử trận]"
                return slot, row, f"Ô số {pos}"

        return 1, 2, "Pos 2 (Mặc định)"

    # --------------------------------------------------------------------------
    # THAO TÁC FRIDA VÀ XUẤT CHIÊU
    # --------------------------------------------------------------------------
    def on_attach_clicked(self):
        val = self.cb_proc.get()
        if not val or "PID:" not in val:
            return
        try:
            pid = int(val.split("PID:")[1].replace(")", "").strip())
            name = val.split("(")[0].strip()
            self.attach_process(pid, name)
        except Exception as e:
            self.log(f"[!] Lỗi kết nối: {e}")

    def attach_process(self, pid: int, name: str):
        if not frida:
            self.log("[!] Chưa cài đặt thư viện frida")
            return
        self.detach()

        try:
            self.session = frida.attach(pid)
            self.script = self.session.create_script(FRIDA_HOOK_JS)
            self.script.on("message", self.on_frida_message)
            self.script.load()

            self.pid = pid
            self.proc_name = name
            self.card.config(text=f" 🎮 SLOT #{self.slot_id + 1}: {name} (PID {pid}) ", fg=THEME["green"])
            self.log(f"[+] Đã kết nối vào {name} (PID {pid})")
        except Exception as e:
            self.log(f"[!] Lỗi gắn tiến trình: {e}")

    def detach(self):
        if self.session:
            try:
                self.session.detach()
            except Exception:
                pass
            self.session = None
            self.script = None
            self.pid = None

    def on_frida_message(self, message, raw_data):
        if raw_data:
            self.msg_queue.put((message, raw_data))

    def process_network_queue(self):
        while not self.msg_queue.empty():
            try:
                msg, raw_data = self.msg_queue.get_nowait()
                payload = msg.get("payload", {})
                dir_name = payload.get("dir", "send")
                dissector = self.c2s_dissector if dir_name == "send" else self.s2c_dissector
                packets = dissector.feed(raw_data)
                for opcode, subcode, data, raw_pkt in packets:
                    self.handle_packet(dir_name, opcode, subcode, data)
            except Exception:
                break

    def handle_packet(self, dir_name: str, opcode: int, subcode: int, data: bytes):
        if opcode == 0x08:
            return

        # 1. BẮT ĐẦU TRẬN ĐẤU (Op 0x0B Sub 0xFA hoặc 0x02)
        if dir_name == "recv" and opcode == 0x0B and subcode in (0xFA, 0x02):
            if self.pending_turn_timer:
                try:
                    self.app.root.after_cancel(self.pending_turn_timer)
                except Exception:
                    pass
                self.pending_turn_timer = None

            self.in_battle = True
            self.turn_count = 1
            self.battle_phase = "WAITING_COMMAND"
            self.entities_hp.clear()
            self.entities_sp.clear()

            self.lbl_battle_badge.config(text="⚔️ LƯỢT #1", bg=THEME["red_dark"], fg=THEME["red"])
            self.log("⚔️ [TRẬN MỚI] Vào sàn đấu -> Bắt đầu Lượt #1")

            if self.auto_combat_enabled:
                delay = self.app.scale_delay.get()
                self.pending_cast_timer = self.app.root.after(delay, self.trigger_auto_cast)

        # 2. CẬP NHẬT HP / SP (Op 0x33 Sub 0x01)
        elif dir_name == "recv" and opcode == 0x33 and subcode == 0x01:
            if len(data) >= 7:
                e_slot, e_row, stat_type = data[0], data[1], data[2]
                val = struct.unpack("<I", data[3:7])[0]
                if stat_type == 0x19:  # HP
                    self.entities_hp[(e_slot, e_row)] = val
                elif stat_type == 0x1A:  # SP
                    self.entities_sp[(e_slot, e_row)] = val
                self.update_stats_display()

            # Debounce kích hoạt lượt mới sau hoạt ảnh
            if self.in_battle and self.battle_phase == "ANIMATING":
                if self.pending_turn_timer:
                    try:
                        self.app.root.after_cancel(self.pending_turn_timer)
                    except Exception:
                        pass
                self.pending_turn_timer = self.app.root.after(200, self.on_turn_resolved)

        # 3. HOẠT ẢNH RA CHIÊU (Op 0x32 Sub 0x06 / 0x01)
        elif dir_name == "recv" and opcode == 0x32:
            if self.in_battle and subcode in (0x01, 0x06):
                self.battle_phase = "ANIMATING"

        # 4. KẾT THÚC TRẬN ĐẤU (Op 0x0B Sub 0x00 HOẶC WARP Op 0x35)
        elif (dir_name == "recv" and opcode == 0x0B and subcode == 0x00) or \
             (dir_name == "recv" and opcode == 0x35 and subcode in (0x01, 0x02, 0x03)):
            if self.in_battle:
                self.in_battle = False
                self.battle_phase = "IDLE"
                self.turn_count = 0
                if self.pending_turn_timer:
                    try:
                        self.app.root.after_cancel(self.pending_turn_timer)
                    except Exception:
                        pass
                    self.pending_turn_timer = None
                if self.pending_cast_timer:
                    try:
                        self.app.root.after_cancel(self.pending_cast_timer)
                    except Exception:
                        pass
                    self.pending_cast_timer = None

                self.lbl_battle_badge.config(text="💤 NGOÀI TRẬN", bg=THEME["bg_input"], fg=THEME["text_muted"])
                self.lbl_stats.config(text="🧙‍♂️ -- | 🧚‍♀️ --")
                self.log("🏆 Trận đấu kết thúc.")

    def on_turn_resolved(self):
        self.pending_turn_timer = None
        if not self.in_battle:
            return
        self.turn_count += 1
        self.battle_phase = "WAITING_COMMAND"
        self.lbl_battle_badge.config(text=f"⚔️ LƯỢT #{self.turn_count}")
        self.log(f"🔔 Bắt đầu Lượt #{self.turn_count}")

        if self.auto_combat_enabled:
            delay = self.app.scale_delay.get()
            self.pending_cast_timer = self.app.root.after(delay, self.trigger_auto_cast)

    def trigger_auto_cast(self):
        self.pending_cast_timer = None
        if not self.in_battle:
            return
        self.battle_phase = "COMMAND_SENT"

        # Pet xuất chiêu trước
        p_slot, p_row, p_desc = self.resolve_target("pet")
        p_info = self.app.skills_db.get(f"0x{self.pet_skill.upper()}", {})
        p_name = p_info.get("name_vi") or p_info.get("name_en") or self.pet_skill
        self.send_action_raw(3, 2, p_slot, p_row, self.pet_skill, f"Pet [{p_name}] -> {p_desc}")

        time.sleep(0.06)

        # Char xuất chiêu sau
        c_slot, c_row, c_desc = self.resolve_target("char")
        c_info = self.app.skills_db.get(f"0x{self.char_skill.upper()}", {})
        c_name = c_info.get("name_vi") or c_info.get("name_en") or self.char_skill
        self.send_action_raw(4, 2, c_slot, c_row, self.char_skill, f"Char [{c_name}] -> {c_desc}")

    def send_action_raw(self, actor_slot: int, actor_row: int,
                        target_slot: int, target_row: int,
                        skill_code_str: str, desc: str) -> bool:
        if not self.script:
            self.log("[!] Chưa gắn game!")
            return False

        try:
            val = int(skill_code_str, 16)
            skill_bytes = struct.pack("<H", val)
        except Exception:
            skill_bytes = b"\x2b\x2b"

        pkt = build_combat_action_packet(actor_slot, actor_row, target_slot, target_row, skill_bytes)
        try:
            res = self.script.exports_sync.sendraw(pkt.hex())
            if res and res.get("success"):
                self.log(f"💥 {desc}")
                return True
            else:
                self.log(f"[!] Lỗi bắn chiêu: {res.get('error')}")
                return False
        except Exception as e:
            self.log(f"[!] Ngoại lệ gửi gói: {e}")
            return False

    def cast_now_immediate(self):
        if not self.script:
            self.log("[!] Chưa gắn game!")
            return
        if not self.in_battle:
            self.log("[!] Hiện không trong trận đấu!")
            return
        self.log("⚡ Ra chiêu lập tức cho lượt này...")
        self.trigger_auto_cast()

    def toggle_auto(self):
        self.auto_combat_enabled = not self.auto_combat_enabled
        if self.auto_combat_enabled:
            self.btn_auto.config(text="⏹ TẮT AUTO", bg=THEME["red"], fg="#ffffff")
            self.log("▶ BẬT Tự Động Ra Chiêu cho slot này.")
            if self.in_battle and self.battle_phase == "WAITING_COMMAND":
                delay = self.app.scale_delay.get()
                self.pending_cast_timer = self.app.root.after(delay, self.trigger_auto_cast)
        else:
            self.btn_auto.config(text="▶ BẬT AUTO", bg=THEME["green"], fg="#11111b")
            self.log("⏹ ĐÃ TẮT Tự Động Ra Chiêu.")

    def set_both_defend(self):
        self.char_skill = "75EA"
        self.char_target_type = "ally"
        self.char_target_val = "self"
        self.pet_skill = "75EA"
        self.pet_target_type = "ally"
        self.pet_target_val = "self"
        self.update_char_target_ui()
        self.update_pet_target_ui()
        self.log("🛡️ Cả 2 cùng chọn PHÒNG THỦ mỗi lượt.")

    def set_both_normal_attack(self):
        self.char_skill = "1427"
        self.char_target_type = "row"
        self.char_target_val = 2
        self.pet_skill = "1227"
        self.pet_target_type = "row"
        self.pet_target_val = 2
        self.update_char_target_ui()
        self.update_pet_target_ui()
        self.log("⚔️ Cả 2 cùng chọn ĐÁNH THƯỜNG mỗi lượt.")

    def set_both_flee(self):
        self.char_skill = "89EA"
        self.pet_skill = "89EA"
        self.log("🏃 Cả 2 cùng chọn BỎ CHẠY.")

    def update_stats_display(self):
        c_hp = self.entities_hp.get((4, 2), "--")
        c_sp = self.entities_sp.get((4, 2), "--")
        p_hp = self.entities_hp.get((3, 2), "--")
        p_sp = self.entities_sp.get((3, 2), "--")
        self.lbl_stats.config(text=f"🧙‍♂️ {c_hp}/{c_sp} | 🧚‍♀️ {p_hp}/{p_sp}")

    def log(self, text: str):
        t_str = datetime.now().strftime("%H:%M:%S")
        self.lbl_mini_log.config(text=f"[{t_str}] {text}")


# ==============================================================================
# CLASS MAIN: ỨNG DỤNG QUẢN LÝ 4 PROCESS COMBAT
# ==============================================================================
class WLOAutoCombatApp:
    def __init__(self, root, parent=None):
        self.root = root.winfo_toplevel() if hasattr(root, "winfo_toplevel") else root
        self.parent = parent if parent is not None else self.root
        if self.parent == self.root:
            self.root.title("⚔️ WLO Multi-Process Auto Combat - Quản Lý Tự Động Ra Chiêu 4 Client")
            self.root.geometry("1400x900")
            self.root.minsize(1200, 780)
            self.root.configure(bg=THEME["bg_main"])

        # CSDL Kỹ năng
        self.skills_db = {}
        self.load_skills_database()

        # Tạo thanh điều khiển Master
        self.create_master_header()

        # Tạo lưới 4 Slot (2x2 Grid)
        self.create_slots_grid()

        # Quét và tự gán 4 tiến trình khi khởi chạy
        self.root.after(300, self.scan_and_auto_assign_procs)

        # Vòng lặp lắng nghe gói tin từ cả 4 slot
        self.root.after(60, self.poll_all_slots_network)

    def load_skills_database(self):
        if os.path.exists(SKILLS_DB_FILE):
            try:
                with open(SKILLS_DB_FILE, "r", encoding="utf-8") as f:
                    self.skills_db = json.load(f)
            except Exception:
                pass

    def create_master_header(self):
        container = self.parent if hasattr(self, "parent") and self.parent else self.root
        header = tk.Frame(container, bg=THEME["bg_dark"], height=52, padx=12, pady=6)
        header.pack(fill="x", side="top")

        tk.Label(header, text="⚔️ WLO 4-CLIENT AUTO COMBAT", font=("Segoe UI", 12, "bold"),
                 bg=THEME["bg_dark"], fg=THEME["primary"]).pack(side="left", padx=(0, 16))

        # Nút Quét & Tự Gán
        btn_scan = tk.Button(header, text="🔍 Quét & Tự Gán 4 Acc", font=("Segoe UI", 9, "bold"),
                             bg=THEME["bg_input"], fg=THEME["primary"], relief="flat", padx=10, pady=4,
                             cursor="hand2", command=self.scan_and_auto_assign_procs)
        btn_scan.pack(side="left", padx=(0, 8))

        # Nút Bật tất cả
        btn_all_on = tk.Button(header, text="▶ BẬT AUTO CẢ 4 ACC", font=("Segoe UI", 9, "bold"),
                               bg=THEME["green"], fg="#11111b", relief="flat", padx=10, pady=4,
                               cursor="hand2", command=self.turn_on_all_auto)
        btn_all_on.pack(side="left", padx=(0, 6))

        # Nút Tắt tất cả
        btn_all_off = tk.Button(header, text="⏹ TẮT TẤT CẢ", font=("Segoe UI", 9, "bold"),
                                bg=THEME["red"], fg="#ffffff", relief="flat", padx=10, pady=4,
                                cursor="hand2", command=self.turn_off_all_auto)
        btn_all_off.pack(side="left", padx=(0, 16))

        # Thanh chỉnh delay
        tk.Label(header, text="⏱️ Độ trễ ra chiêu (ms):", font=("Segoe UI", 9),
                 bg=THEME["bg_dark"], fg=THEME["text_muted"]).pack(side="left", padx=(0, 4))
        self.scale_delay = tk.Scale(header, from_=100, to=1000, resolution=50, orient="horizontal",
                                    bg=THEME["bg_dark"], fg=THEME["primary"], highlightthickness=0,
                                    length=150, font=("Segoe UI", 8))
        self.scale_delay.set(300)
        self.scale_delay.pack(side="left")

        self.lbl_master_status = tk.Label(header, text="Đang khởi tạo...", font=("Segoe UI", 9),
                                          bg=THEME["bg_dark"], fg=THEME["text_muted"])
        self.lbl_master_status.pack(side="right", padx=(0, 8))

    def create_slots_grid(self):
        container_parent = self.parent if hasattr(self, "parent") and self.parent else self.root
        container = tk.Frame(container_parent, bg=THEME["bg_main"], padx=6, pady=6)
        container.pack(fill="both", expand=True)

        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        self.slots = []

        # Tạo 4 khung con cho 4 quadrant
        for idx in range(4):
            r = idx // 2
            c = idx % 2
            f = tk.Frame(container, bg=THEME["bg_main"], padx=3, pady=3)
            f.grid(row=r, column=c, sticky="nsew")
            slot = ProcessCombatSlot(idx, self, f)
            self.slots.append(slot)

    def scan_and_auto_assign_procs(self):
        if not frida:
            self.lbl_master_status.config(text="[!] Chưa cài đặt frida", fg=THEME["red"])
            return

        procs = []
        try:
            device = frida.get_local_device()
            for p in device.enumerate_processes():
                if "alogin" in p.name.lower():
                    procs.append((p.pid, p.name))
        except Exception as e:
            self.lbl_master_status.config(text=f"[!] Lỗi quét tiến trình: {e}", fg=THEME["red"])
            return

        # Sắp xếp W01, F04...
        procs.sort(key=lambda x: x[1].lower())
        proc_labels = [f"{p[1]} (PID: {p[0]})" for p in procs]

        # Cập nhật danh sách combobox cho cả 4 slot
        for i, slot in enumerate(self.slots):
            slot.cb_proc["values"] = proc_labels
            if i < len(procs):
                target_pid, target_name = procs[i]
                slot.cb_proc.current(i)
                # Tự động gán nếu slot chưa kết nối
                if slot.pid != target_pid:
                    slot.attach_process(target_pid, target_name)
            else:
                if not proc_labels:
                    slot.cb_proc["values"] = ["Không tìm thấy alogin"]

        self.lbl_master_status.config(text=f"Đã tìm thấy {len(procs)} tiến trình alogin*.exe", fg=THEME["green"])

    def turn_on_all_auto(self):
        for slot in self.slots:
            if slot.script and not slot.auto_combat_enabled:
                slot.toggle_auto()

    def turn_off_all_auto(self):
        for slot in self.slots:
            if slot.auto_combat_enabled:
                slot.toggle_auto()

    def poll_all_slots_network(self):
        for slot in self.slots:
            slot.process_network_queue()
        self.root.after(60, self.poll_all_slots_network)

    def stop_all(self):
        for slot in getattr(self, "slots", []):
            try:
                slot.detach()
            except Exception:
                pass


def main():
    root = tk.Tk()
    app = WLOAutoCombatApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.stop_all(), root.destroy()))
    root.mainloop()

if __name__ == "__main__":
    main()
