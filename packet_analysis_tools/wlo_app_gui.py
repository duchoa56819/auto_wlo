#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO COMPANION APP - GIAO DIỆN ĐỒ HỌA TRỰC QUAN TOÀN DIỆN
=========================================================
Ứng dụng máy tính hợp nhất toàn bộ công cụ Wonderland Online (WLO):
1. 🎁 Thu Thập & Mở Quà (Gift & Discard Item Collector)
2. 📦 Quản Lý Kho Vật Phẩm (Item Database Manager)
3. 🗑️ Tự Động Vứt Đồ & Blacklist (Auto-Discard & WPE Pro Popup Confirm)
4. 🎒 Túi Đồ 50 Ô Trực Quan (Live 50-Slot Bag Grid Visualizer)
5. 📡 Soi & Phân Tích Gói Tin (Network Packet Sniffer & Inspector)
"""

import os
import sys
import time
import json
import queue
import struct
import threading
from datetime import datetime

# GUI Tkinter & TTK
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
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

# ==============================================================================
# BẢNG MÀU GIAO DIỆN HIỆN ĐẠI (CATPPUCCIN / DARK THEME)
# ==============================================================================
THEME = {
    "bg_dark": "#181825",       # Nền sâu nhất (Header, Statusbar)
    "bg_main": "#1e1e2e",       # Nền chính cửa sổ
    "bg_card": "#262738",       # Nền các khung Card, Container
    "bg_hover": "#313244",      # Khi rê chuột
    "bg_selected": "#45475a",   # Khi chọn dòng trong bảng
    "text_main": "#cdd6f4",     # Chữ sáng chính
    "text_muted": "#a6adc8",    # Chữ mờ, phụ đề
    "cyan": "#89dceb",          # Điểm nhấn Cyan / C->S
    "blue": "#89b4fa",          # Tiêu đề, Nút chính
    "green": "#a6e3a1",         # Thành công, Ô có đồ, Đã kết nối
    "yellow": "#f9e2af",        # Cảnh báo, Vứt đồ
    "red": "#f38ba8",           # Nguy hiểm, Blacklist, Ngắt kết nối
    "magenta": "#cba6f7",       # Mở quà, Tính năng đặc biệt
    "gray_empty": "#333446",    # Màu ô trống túi đồ
    "border": "#313244",        # Màu viền
}

OPCODE_MAP = {
    0x01: "SYSTEM_HANDSHAKE",
    0x02: "ACCOUNT_CHAR_LIST",
    0x03: "CHANNEL_INFO",
    0x04: "SKILL_EFFECT",
    0x05: "LOGIN_AUTH",
    0x06: "COMBAT_ACTION",
    0x07: "TEAM_FORMATION",
    0x08: "PING_HEARTBEAT",
    0x0A: "TRADE_STALL",
    0x0B: "INVENTORY_ITEM",
    0x0C: "FRIEND_MAIL",
    0x0E: "PET_ACTION",
    0x0F: "PET_STATUS",
    0x10: "TENT_FURNITURE",
    0x13: "SYNTHESIS_COMPOUND",
    0x14: "CHAT_MESSAGE",
    0x16: "QUEST_MISSION",
    0x17: "CHAR_ATTRIBUTES",
    0x18: "SHORTCUT_BAR",
    0x20: "NPC_DIALOG",
    0x32: "PLAYER_MOVE",
    0x35: "MAP_WARP_SCENE",
    0x3E: "WEATHER_EFFECT",
    0x55: "DUNGEON_LOBBY",
}

def format_item_code(code_int):
    """Định dạng số nguyên 2-byte server thành chuỗi Hex chuẩn 0xXXXX."""
    return f"0x{code_int:04X}"

def parse_code_input(user_str):
    """Phân tích chuỗi nhập (0x84D8, 84D8, 34008) thành số nguyên."""
    if not user_str:
        return None
    user_str = str(user_str).strip()
    if user_str.lower().startswith("0x"):
        try:
            return int(user_str, 16)
        except ValueError:
            return None
    if all(c in "0123456789abcdefABCDEF" for c in user_str) and len(user_str) == 4:
        try:
            return int(user_str, 16)
        except ValueError:
            return None
    if user_str.isdigit():
        return int(user_str)
    return None

def pack_wlo_packet(body_bytes):
    """Đóng gói Magic Header 0xF4 0x44, Length (uint16 LE) và XOR 0xAD."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain_packet = header + body_bytes
    return bytes(b ^ 0xAD for b in plain_packet)

# ==============================================================================
# BỘ GIẢI MÃ DÒNG TCP (STREAM DISSECTOR)
# ==============================================================================
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
# FRIDA JAVASCRIPT HOOK (SOCKET RECV/SEND & DELPHI MEMORY BAG SCANNER)
# ==============================================================================
FRIDA_JS = """
var activeSocket = -1;
var isInjected = false;
var cachedBagBase = null;

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
                        send({dir: 'recv', len: len, sock: this.sock, from: modName}, buf);
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
                        send({dir: 'send', len: len, sock: sock, from: modName}, buf);
                    } catch(e) {}
                }
            }
        });
    } catch(e) {}
}

hookRecv('wsock32.dll');
hookRecv('ws2_32.dll');
hookSend('ws2_32.dll');

var ws2 = Process.getModuleByName('ws2_32.dll');
var sendPtr = ws2.getExportByName('send');
var sendFunc = new NativeFunction(sendPtr, 'int', ['int', 'pointer', 'int', 'int']);

function findBagBase() {
    if (cachedBagBase) {
        try {
            if (cachedBagBase.readU32() === 0x88000100 &&
                cachedBagBase.add(0x48).readU32() === 0x88000200) {
                return cachedBagBase;
            }
        } catch(e) {
            cachedBagBase = null;
        }
    }
    var ranges = Process.enumerateRanges('rw-');
    for (var i = 0; i < ranges.length; i++) {
        var r = ranges[i];
        if (r.size < 4096 || r.size > 20 * 1024 * 1024) continue;
        try {
            var matches = Memory.scanSync(r.base, r.size, "00 01 00 88");
            for (var j = 0; j < matches.length; j++) {
                var p = matches[j].address;
                try {
                    if (p.add(0x48 * 1).readU32() === 0x88000200 &&
                        p.add(0x48 * 2).readU32() === 0x88000300 &&
                        p.add(0x48 * 3).readU32() === 0x88000400) {
                        cachedBagBase = p;
                        return p;
                    }
                } catch(e) {}
            }
        } catch(e) {}
    }
    return null;
}

function dumpMemoryBag() {
    var base = findBagBase();
    if (!base) return {found: false};
    var slots = [];
    for (var s = 0; s < 50; s++) {
        var slotPtr = base.add(s * 0x48);
        var val1 = slotPtr.add(4).readU32();
        var isEmpty = (val1 === 0 || val1 === 0x0c00 || val1 === 3072);
        slots.push({
            slot: s + 1,
            isEmpty: isEmpty,
            val1: val1,
            val1_hex: "0x" + val1.toString(16).toUpperCase()
        });
    }
    return {found: true, base: base.toString(), slots: slots};
}

rpc.exports = {
    getsocket: function() { return activeSocket; },
    dumpbag: function() { return dumpMemoryBag(); },
    sendraw: function(hexStr) {
        if (activeSocket <= 0) return {success: false, error: 'Chưa có socket mạng hoạt động!'};
        try {
            var raw = [];
            for (var i = 0; i < hexStr.length; i += 2) {
                raw.push(parseInt(hexStr.substr(i, 2), 16));
            }
            var buf = Memory.alloc(raw.length);
            buf.writeByteArray(raw);
            isInjected = true;
            var sent = sendFunc(activeSocket, buf, raw.length, 0);
            isInjected = false;
            return {success: sent > 0, bytes_sent: sent};
        } catch(e) {
            isInjected = false;
            return {success: false, error: e.toString()};
        }
    }
};
"""

# ==============================================================================
# GIAO DIỆN CHÍNH (MAIN APPLICATION GUI)
# ==============================================================================
class WLOAppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Wonderland Online Companion - Quản Lý & Tự Động Túi Đồ")
        self.root.geometry("1180x760")
        self.root.minsize(1050, 680)
        self.root.configure(bg=THEME["bg_main"])

        # Đường dẫn file dữ liệu
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_file = os.path.join(self.script_dir, "wlo_items_database.json")
        self.txt_file = os.path.join(self.script_dir, "wlo_items_database.txt")
        self.cfg_file = os.path.join(self.script_dir, "wlo_auto_discard_config.json")
        self.log_file = os.path.join(self.script_dir, "wlo_app_gui.log")

        # Hàng đợi đồng bộ thread-safe với Tkinter GUI
        self.gui_queue = queue.Queue()
        self.packet_queue = queue.Queue()

        # Stream dissectors
        self.c2s_dissector = WLOStreamDissector()
        self.s2c_dissector = WLOStreamDissector()

        # Dữ liệu bộ nhớ & cấu hình
        self.database = self.load_database()
        self.config = self.load_config()
        self.blacklist = self.config.get("blacklist", {})

        # Trạng thái mạng & túi đồ
        self.inventory_cache = {}      # Slot 1..50 từ Op:0x17 Sub:0x05
        self.memory_bag_cache = []     # 50 slot từ Delphi memory scan
        self.active_socket = -1
        self.packet_count = 0
        self.last_open_slot = 0
        self.last_discard_event = None
        self.last_discard_req = None

        # Trạng thái kết nối Frida
        self.session = None
        self.script = None
        self.is_attached = False
        self.target_pid = None
        self.target_pname = None

        # Thiết lập Style hiện đại
        self.setup_styles()

        # Xây dựng toàn bộ giao diện
        self.create_widgets()

        # Bắt đầu vòng lặp đồng bộ hàng đợi GUI
        self.root.after(50, self.poll_gui_queue)

        # Quét tự động danh sách cửa sổ game
        self.refresh_process_list()

        # Đọc dữ liệu ban đầu lên các bảng
        self.refresh_database_table()
        self.refresh_blacklist_table()

    # --------------------------------------------------------------------------
    # THIẾT LẬP STYLE
    # --------------------------------------------------------------------------
    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Cấu hình màu sắc chung
        self.style.configure(".", background=THEME["bg_main"], foreground=THEME["text_main"],
                             font=("Segoe UI", 10))

        # Notebook (Tabs)
        self.style.configure("TNotebook", background=THEME["bg_dark"], borderwidth=0)
        self.style.configure("TNotebook.Tab", background=THEME["bg_card"], foreground=THEME["text_muted"],
                             padding=[18, 8], font=("Segoe UI", 10, "bold"), borderwidth=0)
        self.style.map("TNotebook.Tab",
                       background=[("selected", THEME["bg_main"])],
                       foreground=[("selected", THEME["cyan"])])

        # Frames
        self.style.configure("Card.TFrame", background=THEME["bg_card"], relief="flat")
        self.style.configure("Header.TFrame", background=THEME["bg_dark"], relief="flat")

        # Treeview (Tables)
        self.style.configure("Treeview", background=THEME["bg_card"], foreground=THEME["text_main"],
                             fieldbackground=THEME["bg_card"], rowheight=28, borderwidth=0,
                             font=("Consolas", 9))
        self.style.configure("Treeview.Heading", background=THEME["bg_dark"], foreground=THEME["cyan"],
                             font=("Segoe UI", 10, "bold"), borderwidth=1, relief="flat")
        self.style.map("Treeview",
                       background=[("selected", THEME["bg_selected"])],
                       foreground=[("selected", THEME["text_main"])])

        # Buttons
        self.style.configure("TButton", background=THEME["bg_card"], foreground=THEME["text_main"],
                             padding=[12, 6], borderwidth=1, relief="flat", font=("Segoe UI", 9, "bold"))
        self.style.map("TButton",
                       background=[("active", THEME["bg_hover"]), ("pressed", THEME["bg_selected"])],
                       foreground=[("active", THEME["cyan"])])

        self.style.configure("Primary.TButton", background=THEME["blue"], foreground="#11111b",
                             font=("Segoe UI", 9, "bold"))
        self.style.map("Primary.TButton",
                       background=[("active", THEME["cyan"])])

        self.style.configure("Danger.TButton", background=THEME["red"], foreground="#11111b",
                             font=("Segoe UI", 9, "bold"))
        self.style.map("Danger.TButton",
                       background=[("active", "#eba0ac")])

        # Checkbuttons
        self.style.configure("TCheckbutton", background=THEME["bg_card"], foreground=THEME["text_main"],
                             font=("Segoe UI", 9))
        self.style.map("TCheckbutton",
                       background=[("active", THEME["bg_card"])],
                       foreground=[("active", THEME["cyan"])])

        # Combobox
        self.style.configure("TCombobox", fieldbackground=THEME["bg_card"], background=THEME["bg_dark"],
                             foreground=THEME["text_main"], borderwidth=1)

    # --------------------------------------------------------------------------
    # KHỞI TẠO CÁC WIDGETS
    # --------------------------------------------------------------------------
    def create_widgets(self):
        # 1. THANH TIÊU ĐỀ & KẾT NỐI (TOP HEADER BAR)
        self.header_frame = ttk.Frame(self.root, style="Header.TFrame", padding=[15, 10])
        self.header_frame.pack(side="top", fill="x")

        # Logo / Title
        lbl_app_title = tk.Label(self.header_frame, text="⚔ WLO COMPANION",
                                 bg=THEME["bg_dark"], fg=THEME["cyan"], font=("Segoe UI", 12, "bold"))
        lbl_app_title.pack(side="left", padx=(0, 20))

        # Chọn tiến trình game
        lbl_proc = tk.Label(self.header_frame, text="Cửa sổ game:",
                            bg=THEME["bg_dark"], fg=THEME["text_muted"], font=("Segoe UI", 9))
        lbl_proc.pack(side="left", padx=(0, 6))

        self.cb_processes = ttk.Combobox(self.header_frame, width=28, state="readonly")
        self.cb_processes.pack(side="left", padx=(0, 6))

        self.btn_refresh_proc = ttk.Button(self.header_frame, text="🔄 Quét lại", command=self.refresh_process_list)
        self.btn_refresh_proc.pack(side="left", padx=(0, 15))

        # Nút Đính kèm / Ngắt
        self.btn_attach = ttk.Button(self.header_frame, text="⚡ Đính Kèm", style="Primary.TButton",
                                     command=self.toggle_attach)
        self.btn_attach.pack(side="left", padx=(0, 15))

        # Đèn báo trạng thái kết nối
        self.lbl_status_badge = tk.Label(self.header_frame, text="○ Chưa kết nối",
                                         bg=THEME["bg_dark"], fg=THEME["text_muted"], font=("Segoe UI", 9, "bold"))
        self.lbl_status_badge.pack(side="left", padx=(0, 15))

        # Thông tin socket & gói tin bên phải
        self.lbl_socket_info = tk.Label(self.header_frame, text="Socket: -- | Gói tin: 0",
                                        bg=THEME["bg_dark"], fg=THEME["text_muted"], font=("Consolas", 9))
        self.lbl_socket_info.pack(side="right")

        # 2. NOTEBOOK CHÍNH (5 TABS)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(6, 10))

        # Khởi tạo các Tabs
        self.create_tab_collector()
        self.create_tab_database()
        self.create_tab_auto_discard()
        self.create_tab_bag_grid()
        self.create_tab_sniffer()

    # --------------------------------------------------------------------------
    # TAB 1: THU THẬP & MỞ QUÀ (COLLECTOR)
    # --------------------------------------------------------------------------
    def create_tab_collector(self):
        tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=15)
        self.notebook.add(tab, text="  🎁 Mở Quà & Thu Thập  ")

        # Top Bar: Công tắc và thống kê
        top_bar = ttk.Frame(tab, style="Card.TFrame")
        top_bar.pack(fill="x", pady=(0, 10))

        self.var_collect_open = tk.BooleanVar(value=True)
        cb_collect_open = ttk.Checkbutton(top_bar, text="Tự động thu thập khi MỞ QUÀ (Sub: 0x06)",
                                            variable=self.var_collect_open)
        cb_collect_open.pack(side="left", padx=(0, 20))

        self.var_collect_discard = tk.BooleanVar(value=True)
        cb_collect_discard = ttk.Checkbutton(top_bar, text="Tự động thu thập khi VỨT ĐỒ (Sub: 0xD4 / 0x1A)",
                                               variable=self.var_collect_discard)
        cb_collect_discard.pack(side="left", padx=(0, 20))

        # Thống kê nhanh bên phải
        self.lbl_collect_stats = tk.Label(top_bar, text="Đã lưu: 0 loại | Mở: 0 lần | Vứt: 0 lần",
                                          bg=THEME["bg_card"], fg=THEME["green"], font=("Segoe UI", 9, "bold"))
        self.lbl_collect_stats.pack(side="right")

        # KHUNG ĐẶT TÊN NHANH KHI PHÁT HIỆN MÓN MỚI (BANNER THÔNG MINH)
        self.frame_new_item_prompt = tk.Frame(tab, bg="#2a283e", highlightbackground=THEME["yellow"],
                                              highlightthickness=1, padx=12, pady=10)
        # Ẩn ban đầu, chỉ hiện khi có món mới
        self.lbl_new_item_msg = tk.Label(self.frame_new_item_prompt, text="",
                                         bg="#2a283e", fg=THEME["yellow"], font=("Segoe UI", 10, "bold"))
        self.lbl_new_item_msg.pack(side="left", padx=(0, 10))

        self.entry_new_item_name = tk.Entry(self.frame_new_item_prompt, bg=THEME["bg_card"],
                                            fg=THEME["text_main"], insertbackground=THEME["text_main"],
                                            font=("Segoe UI", 10), width=24)
        self.entry_new_item_name.pack(side="left", padx=(0, 8))
        self.entry_new_item_name.bind("<Return>", lambda e: self.confirm_new_item_name())

        self.btn_save_item_name = ttk.Button(self.frame_new_item_prompt, text="💾 Lưu Tên",
                                             style="Primary.TButton", command=self.confirm_new_item_name)
        self.btn_save_item_name.pack(side="left", padx=(0, 6))

        self.btn_skip_item_name = ttk.Button(self.frame_new_item_prompt, text="✕ Bỏ qua",
                                             command=self.dismiss_new_item_prompt)
        self.btn_skip_item_name.pack(side="left")

        # KHUNG NHẬT KÝ SỰ KIỆN THỜI GIAN THỰC (LIVE EVENT FEED)
        lbl_feed_title = tk.Label(tab, text="Nhật Ký Sự Kiện Thu Thập Trực Tiếp:",
                                  bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 9, "bold"))
        lbl_feed_title.pack(anchor="w", pady=(8, 4))

        self.txt_collector_feed = ScrolledText(tab, bg=THEME["bg_dark"], fg=THEME["text_main"],
                                               font=("Consolas", 10), borderwidth=0, padx=10, pady=8)
        self.txt_collector_feed.pack(fill="both", expand=True)

        # Thiết lập các tag màu sắc cho nhật ký
        self.txt_collector_feed.tag_config("TIME", foreground=THEME["text_muted"])
        self.txt_collector_feed.tag_config("OPEN", foreground=THEME["magenta"], font=("Consolas", 10, "bold"))
        self.txt_collector_feed.tag_config("REWARD", foreground=THEME["green"], font=("Consolas", 10, "bold"))
        self.txt_collector_feed.tag_config("DISCARD", foreground=THEME["yellow"], font=("Consolas", 10, "bold"))
        self.txt_collector_feed.tag_config("NEW_ITEM", foreground="#f9e2af", background="#3e3820", font=("Consolas", 10, "bold"))
        self.txt_collector_feed.tag_config("SYNC", foreground=THEME["cyan"])

        # Bottom Bar: Nút xóa nhật ký
        bottom_bar = ttk.Frame(tab, style="Card.TFrame")
        bottom_bar.pack(fill="x", pady=(6, 0))
        btn_clear_feed = ttk.Button(bottom_bar, text="🧹 Xóa nhật ký", command=lambda: self.txt_collector_feed.delete("1.0", tk.END))
        btn_clear_feed.pack(side="left")

    # --------------------------------------------------------------------------
    # TAB 2: KHO VẬT PHẨM (ITEMS DATABASE)
    # --------------------------------------------------------------------------
    def create_tab_database(self):
        tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=15)
        self.notebook.add(tab, text="  📦 Kho Vật Phẩm  ")

        # Thanh tìm kiếm trên cùng
        search_frame = ttk.Frame(tab, style="Card.TFrame")
        search_frame.pack(fill="x", pady=(0, 10))

        lbl_search = tk.Label(search_frame, text="🔍 Tìm kiếm:",
                              bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 9, "bold"))
        lbl_search.pack(side="left", padx=(0, 6))

        self.entry_db_search = tk.Entry(search_frame, bg=THEME["bg_dark"], fg=THEME["text_main"],
                                        insertbackground=THEME["text_main"], font=("Segoe UI", 10), width=32)
        self.entry_db_search.pack(side="left", padx=(0, 10))
        self.entry_db_search.bind("<KeyRelease>", lambda e: self.filter_database_table())

        btn_clear_search = ttk.Button(search_frame, text="✕ Xóa lọc", command=self.clear_db_search)
        btn_clear_search.pack(side="left", padx=(0, 20))

        self.lbl_db_count = tk.Label(search_frame, text="Tổng số: 0 vật phẩm",
                                     bg=THEME["bg_card"], fg=THEME["cyan"], font=("Segoe UI", 9, "bold"))
        self.lbl_db_count.pack(side="right")

        # Bảng hiển thị danh sách (Treeview)
        cols = ("hex", "dec", "name", "stats", "note", "first", "last")
        self.tree_db = ttk.Treeview(tab, columns=cols, show="headings", selectmode="browse")

        self.tree_db.heading("hex", text="Mã Hex", anchor="center")
        self.tree_db.heading("dec", text="Mã Dec", anchor="center")
        self.tree_db.heading("name", text="Tên Vật Phẩm", anchor="w")
        self.tree_db.heading("stats", text="Thống Kê", anchor="center")
        self.tree_db.heading("note", text="Ô Gần Nhất", anchor="center")
        self.tree_db.heading("first", text="Lần Đầu Thấy", anchor="center")
        self.tree_db.heading("last", text="Lần Gần Nhất", anchor="center")

        self.tree_db.column("hex", width=90, anchor="center")
        self.tree_db.column("dec", width=80, anchor="center")
        self.tree_db.column("name", width=220, anchor="w")
        self.tree_db.column("stats", width=140, anchor="center")
        self.tree_db.column("note", width=100, anchor="center")
        self.tree_db.column("first", width=140, anchor="center")
        self.tree_db.column("last", width=140, anchor="center")

        # Thanh cuộn bảng
        sb_db = ttk.Scrollbar(tab, orient="vertical", command=self.tree_db.yview)
        self.tree_db.configure(yscrollcommand=sb_db.set)

        self.tree_db.pack(side="top", fill="both", expand=True)
        sb_db.pack(side="right", fill="y", before=self.tree_db)

        # Thanh công cụ bên dưới bảng
        action_bar = ttk.Frame(tab, style="Card.TFrame")
        action_bar.pack(fill="x", pady=(10, 0))

        btn_rename = ttk.Button(action_bar, text="✏️ Đổi Tên", command=self.action_rename_item)
        btn_rename.pack(side="left", padx=(0, 8))

        btn_add_bl = ttk.Button(action_bar, text="⛔ Thêm Vào Blacklist", command=self.action_add_selected_to_blacklist)
        btn_add_bl.pack(side="left", padx=(0, 8))

        btn_delete = ttk.Button(action_bar, text="🗑️ Xóa Khỏi Database", command=self.action_delete_item)
        btn_delete.pack(side="left", padx=(0, 8))

        btn_export = ttk.Button(action_bar, text="📄 Xuất File TXT", command=self.action_export_txt)
        btn_export.pack(side="left", padx=(0, 8))

        btn_reload = ttk.Button(action_bar, text="🔄 Tải Lại", command=self.action_reload_database)
        btn_reload.pack(side="right")

    # --------------------------------------------------------------------------
    # TAB 3: TỰ ĐỘNG VỨT ĐỒ & BLACKLIST
    # --------------------------------------------------------------------------
    def create_tab_auto_discard(self):
        tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=15)
        self.notebook.add(tab, text="  🗑️ Tự Động Vứt Đồ  ")

        # Khung công tắc chế độ
        switches_frame = tk.LabelFrame(tab, text=" Thiết Lập Vứt Đồ Tự Động ", bg=THEME["bg_card"],
                                      fg=THEME["cyan"], font=("Segoe UI", 10, "bold"), padx=12, pady=8)
        switches_frame.pack(fill="x", pady=(0, 10))

        self.var_auto_discard = tk.BooleanVar(value=self.config.get("auto_discard_enabled", True))
        cb_auto_discard = ttk.Checkbutton(switches_frame,
                                          text="Bật Tự Động Xác Nhận Popup Vứt Đồ (WPE Pro Sub: 0x7C sau 0.04s)",
                                          variable=self.var_auto_discard, command=self.save_config)
        cb_auto_discard.grid(row=0, column=0, sticky="w", pady=4)

        self.var_auto_open_discard = tk.BooleanVar(value=self.config.get("auto_discard_on_open", False))
        cb_auto_open_discard = ttk.Checkbutton(switches_frame,
                                               text="Tự Động Vứt Đồ Rác Ngay Khi Mở Quà (Quét túi Delphi, bảo vệ ô đồ)",
                                               variable=self.var_auto_open_discard, command=self.save_config)
        cb_auto_open_discard.grid(row=1, column=0, sticky="w", pady=4)

        self.var_dry_run = tk.BooleanVar(value=self.config.get("dry_run", False))
        cb_dry_run = ttk.Checkbutton(switches_frame,
                                     text="Chế Độ Thử Nghiệm (Dry-Run - Không gửi lệnh vứt thật)",
                                     variable=self.var_dry_run, command=self.save_config)
        cb_dry_run.grid(row=2, column=0, sticky="w", pady=4)

        # Khung thêm nhanh vào Blacklist
        add_frame = ttk.Frame(tab, style="Card.TFrame")
        add_frame.pack(fill="x", pady=(0, 8))

        lbl_code = tk.Label(add_frame, text="Mã Hex/Dec:", bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 9))
        lbl_code.pack(side="left", padx=(0, 4))
        self.entry_bl_code = tk.Entry(add_frame, bg=THEME["bg_dark"], fg=THEME["text_main"],
                                      insertbackground=THEME["text_main"], font=("Segoe UI", 9), width=10)
        self.entry_bl_code.pack(side="left", padx=(0, 8))

        lbl_name = tk.Label(add_frame, text="Tên Gợi Nhớ:", bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 9))
        lbl_name.pack(side="left", padx=(0, 4))
        self.entry_bl_name = tk.Entry(add_frame, bg=THEME["bg_dark"], fg=THEME["text_main"],
                                      insertbackground=THEME["text_main"], font=("Segoe UI", 9), width=22)
        self.entry_bl_name.pack(side="left", padx=(0, 10))

        btn_add_bl = ttk.Button(add_frame, text="➕ Thêm Vào Blacklist", command=self.action_add_to_blacklist_manual)
        btn_add_bl.pack(side="left", padx=(0, 10))

        self.lbl_bl_count = tk.Label(add_frame, text="Blacklist: 0 vật phẩm",
                                     bg=THEME["bg_card"], fg=THEME["red"], font=("Segoe UI", 9, "bold"))
        self.lbl_bl_count.pack(side="right")

        # Bảng danh sách Blacklist
        bl_cols = ("hex", "dec", "name", "enabled", "count")
        self.tree_bl = ttk.Treeview(tab, columns=bl_cols, show="headings", selectmode="browse", height=8)

        self.tree_bl.heading("hex", text="Mã Hex", anchor="center")
        self.tree_bl.heading("dec", text="Mã Dec", anchor="center")
        self.tree_bl.heading("name", text="Tên Vật Phẩm", anchor="w")
        self.tree_bl.heading("enabled", text="Trạng Thái", anchor="center")
        self.tree_bl.heading("count", text="Số Lần Đã Vứt", anchor="center")

        self.tree_bl.column("hex", width=100, anchor="center")
        self.tree_bl.column("dec", width=90, anchor="center")
        self.tree_bl.column("name", width=260, anchor="w")
        self.tree_bl.column("enabled", width=120, anchor="center")
        self.tree_bl.column("count", width=120, anchor="center")

        sb_bl = ttk.Scrollbar(tab, orient="vertical", command=self.tree_bl.yview)
        self.tree_bl.configure(yscrollcommand=sb_bl.set)

        self.tree_bl.pack(side="top", fill="both", expand=True)
        sb_bl.pack(side="right", fill="y", before=self.tree_bl)

        # Nút thao tác Blacklist
        bl_actions = ttk.Frame(tab, style="Card.TFrame")
        bl_actions.pack(fill="x", pady=(8, 0))

        btn_toggle_bl = ttk.Button(bl_actions, text="⏯ Bật / Tắt Mục Đã Chọn", command=self.action_toggle_blacklist_item)
        btn_toggle_bl.pack(side="left", padx=(0, 8))

        btn_del_bl = ttk.Button(bl_actions, text="❌ Xóa Khỏi Blacklist", command=self.action_remove_from_blacklist)
        btn_del_bl.pack(side="left", padx=(0, 8))

    # --------------------------------------------------------------------------
    # TAB 4: TÚI ĐỒ 50 Ô TRỰC QUAN (VISUAL 50-SLOT BAG GRID)
    # --------------------------------------------------------------------------
    def create_tab_bag_grid(self):
        tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=15)
        self.notebook.add(tab, text="  🎒 Túi Đồ 50 Ô  ")

        # Thanh điều khiển quét túi
        ctrl_bar = ttk.Frame(tab, style="Card.TFrame")
        ctrl_bar.pack(fill="x", pady=(0, 10))

        btn_scan_mem = ttk.Button(ctrl_bar, text="🔍 Quét Bộ Nhớ Delphi Ngay", style="Primary.TButton",
                                  command=self.action_scan_memory_bag)
        btn_scan_mem.pack(side="left", padx=(0, 15))

        self.lbl_bag_summary = tk.Label(ctrl_bar, text="Đang có: -- món | Ô trống: -- | Ô trống đầu tiên: --",
                                        bg=THEME["bg_card"], fg=THEME["cyan"], font=("Segoe UI", 9, "bold"))
        self.lbl_bag_summary.pack(side="left")

        self.lbl_bag_sync_time = tk.Label(ctrl_bar, text="Lần đồng bộ cuối: Chưa có",
                                          bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 9))
        self.lbl_bag_sync_time.pack(side="right")

        # Chú thích màu sắc (Legend)
        legend_frame = ttk.Frame(tab, style="Card.TFrame")
        legend_frame.pack(fill="x", pady=(0, 8))

        def make_legend_item(parent, color, text):
            f = tk.Frame(parent, bg=THEME["bg_card"])
            f.pack(side="left", padx=(0, 15))
            b = tk.Label(f, text="  ", bg=color, width=2, relief="flat")
            b.pack(side="left", padx=(0, 4))
            l = tk.Label(f, text=text, bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 8))
            l.pack(side="left")

        make_legend_item(legend_frame, THEME["gray_empty"], "Ô Trống")
        make_legend_item(legend_frame, "#1e3a5f", "Có Đồ (Bình Thường)")
        make_legend_item(legend_frame, "#5c2b2b", "Có Đồ (Trong Blacklist)")
        make_legend_item(legend_frame, THEME["green"], "Ô Trống Nhận Quà (Lowest Empty)")

        # Lưới 50 ô (5 hàng x 10 cột)
        self.grid_container = tk.Frame(tab, bg=THEME["bg_dark"], padx=8, pady=8)
        self.grid_container.pack(fill="both", expand=True)

        self.slot_widgets = {}  # slot_num -> dict(frame, lbl_num, lbl_name, lbl_code)

        for s in range(1, 51):
            row = (s - 1) // 10
            col = (s - 1) % 10

            slot_frame = tk.Frame(self.grid_container, bg=THEME["gray_empty"],
                                  highlightbackground=THEME["border"], highlightthickness=1,
                                  padx=4, pady=3, width=95, height=72)
            slot_frame.grid(row=row, column=col, padx=3, pady=3, sticky="nsew")
            slot_frame.grid_propagate(False)

            lbl_num = tk.Label(slot_frame, text=f"{s:02d}", bg=slot_frame["bg"],
                               fg=THEME["text_muted"], font=("Segoe UI", 7, "bold"), anchor="nw")
            lbl_num.pack(anchor="nw")

            lbl_name = tk.Label(slot_frame, text="(Trống)", bg=slot_frame["bg"],
                                fg=THEME["text_muted"], font=("Segoe UI", 8, "bold"), wraplength=85, justify="center")
            lbl_name.pack(expand=True)

            lbl_code = tk.Label(slot_frame, text="", bg=slot_frame["bg"],
                                fg=THEME["text_muted"], font=("Consolas", 7))
            lbl_code.pack(anchor="se")

            # Sự kiện click vào ô
            def make_click_handler(slot_idx):
                return lambda e: self.on_slot_clicked(slot_idx)

            slot_frame.bind("<Button-1>", make_click_handler(s))
            lbl_num.bind("<Button-1>", make_click_handler(s))
            lbl_name.bind("<Button-1>", make_click_handler(s))
            lbl_code.bind("<Button-1>", make_click_handler(s))

            self.slot_widgets[s] = {
                "frame": slot_frame,
                "num": lbl_num,
                "name": lbl_name,
                "code": lbl_code
            }

        for c in range(10):
            self.grid_container.grid_columnconfigure(c, weight=1)
        for r in range(5):
            self.grid_container.grid_rowconfigure(r, weight=1)

    # --------------------------------------------------------------------------
    # TAB 5: SOI GÓI TIN MẠNG (SNIFFER & INSPECTOR)
    # --------------------------------------------------------------------------
    def create_tab_sniffer(self):
        tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=15)
        self.notebook.add(tab, text="  📡 Soi Gói Tin  ")

        # Bộ lọc trên cùng
        sniff_top = ttk.Frame(tab, style="Card.TFrame")
        sniff_top.pack(fill="x", pady=(0, 8))

        lbl_filter = tk.Label(sniff_top, text="Lọc gói tin:", bg=THEME["bg_card"],
                              fg=THEME["text_muted"], font=("Segoe UI", 9, "bold"))
        lbl_filter.pack(side="left", padx=(0, 6))

        self.cb_sniff_filter = ttk.Combobox(sniff_top, width=22, state="readonly",
                                            values=["Tất cả gói tin", "Chỉ gói Túi đồ (0x17)", "Chỉ Mở quà & Vứt đồ"])
        self.cb_sniff_filter.current(0)
        self.cb_sniff_filter.pack(side="left", padx=(0, 15))

        self.var_autoscroll = tk.BooleanVar(value=True)
        cb_autoscroll = ttk.Checkbutton(sniff_top, text="Tự cuộn xuống dòng mới", variable=self.var_autoscroll)
        cb_autoscroll.pack(side="left", padx=(0, 15))

        btn_clear_sniff = ttk.Button(sniff_top, text="🧹 Xóa nhật ký", command=self.action_clear_sniffer)
        btn_clear_sniff.pack(side="left", padx=(0, 8))

        self.lbl_sniff_count = tk.Label(sniff_top, text="Bắt được: 0 gói", bg=THEME["bg_card"],
                                        fg=THEME["cyan"], font=("Consolas", 9))
        self.lbl_sniff_count.pack(side="right")

        # Bảng gói tin
        p_cols = ("time", "dir", "opcode", "subcode", "len", "info", "hex")
        self.tree_sniff = ttk.Treeview(tab, columns=p_cols, show="headings", selectmode="browse")

        self.tree_sniff.heading("time", text="Thời Gian", anchor="center")
        self.tree_sniff.heading("dir", text="Chiều", anchor="center")
        self.tree_sniff.heading("opcode", text="Opcode", anchor="center")
        self.tree_sniff.heading("subcode", text="Subcode", anchor="center")
        self.tree_sniff.heading("len", text="Dài", anchor="center")
        self.tree_sniff.heading("info", text="Ý Nghĩa Gói Tin", anchor="w")
        self.tree_sniff.heading("hex", text="Payload Hex", anchor="w")

        self.tree_sniff.column("time", width=85, anchor="center")
        self.tree_sniff.column("dir", width=55, anchor="center")
        self.tree_sniff.column("opcode", width=75, anchor="center")
        self.tree_sniff.column("subcode", width=70, anchor="center")
        self.tree_sniff.column("len", width=55, anchor="center")
        self.tree_sniff.column("info", width=280, anchor="w")
        self.tree_sniff.column("hex", width=260, anchor="w")

        sb_sniff = ttk.Scrollbar(tab, orient="vertical", command=self.tree_sniff.yview)
        self.tree_sniff.configure(yscrollcommand=sb_sniff.set)

        self.tree_sniff.pack(side="top", fill="both", expand=True)
        sb_sniff.pack(side="right", fill="y", before=self.tree_sniff)

    # --------------------------------------------------------------------------
    # QUẢN LÝ TIẾN TRÌNH & ĐÍNH KÈM FRIDA
    # --------------------------------------------------------------------------
    def refresh_process_list(self):
        """Quét tìm các tiến trình alogin*.exe đang chạy."""
        procs = []
        if frida:
            try:
                device = frida.get_local_device()
                for p in device.enumerate_processes():
                    if "alogin" in p.name.lower():
                        procs.append(f"{p.name} (PID: {p.pid})")
            except Exception:
                pass

        self.cb_processes["values"] = procs
        if procs:
            self.cb_processes.current(0)
        else:
            self.cb_processes.set("Không tìm thấy alogin*.exe")

    def toggle_attach(self):
        """Đính kèm hoặc ngắt kết nối với tiến trình game."""
        if self.is_attached:
            self.detach_from_game()
        else:
            self.attach_to_game()

    def attach_to_game(self):
        sel = self.cb_processes.get()
        if not sel or "PID:" not in sel:
            messagebox.showwarning("Cảnh Báo", "Vui lòng mở game WLO (alogin.exe) và chọn tiến trình!")
            return

        try:
            pid_str = sel.split("PID:")[1].split(")")[0].strip()
            target_pid = int(pid_str)
            target_name = sel.split()[0].strip()

            device = frida.get_local_device()
            self.session = device.attach(target_pid)
            self.script = self.session.create_script(FRIDA_JS)
            self.script.on("message", self.on_frida_message)
            self.script.load()

            self.is_attached = True
            self.target_pid = target_pid
            self.target_pname = target_name

            # Cập nhật giao diện
            self.btn_attach.configure(text="⏹ Ngắt Kết Nối", style="Danger.TButton")
            self.lbl_status_badge.configure(text=f"● Đã kết nối PID: {target_pid} ({target_name})",
                                            fg=THEME["green"])

            # Khởi chạy luồng xử lý gói tin
            t = threading.Thread(target=self.packet_worker, daemon=True)
            t.start()

            # Quét nhanh túi đồ ban đầu từ bộ nhớ Delphi
            self.root.after(400, self.action_scan_memory_bag)

            self.append_collector_feed("SYNC", f"Đã đính kèm thành công vào {target_name} (PID: {target_pid})!")

        except Exception as e:
            messagebox.showerror("Lỗi Đính Kèm", f"Không thể đính kèm vào game: {e}")

    def detach_from_game(self):
        try:
            if self.script:
                self.script.unload()
            if self.session:
                self.session.detach()
        except Exception:
            pass

        self.is_attached = False
        self.script = None
        self.session = None
        self.btn_attach.configure(text="⚡ Đính Kèm", style="Primary.TButton")
        self.lbl_status_badge.configure(text="○ Chưa kết nối", fg=THEME["text_muted"])
        self.append_collector_feed("SYNC", "Đã ngắt kết nối với game an toàn.")

    # --------------------------------------------------------------------------
    # XỬ LÝ MẠNG VÀ PACKET DISSECTOR
    # --------------------------------------------------------------------------
    def on_frida_message(self, message, raw_data):
        if raw_data:
            self.packet_queue.put((message, raw_data))

    def packet_worker(self):
        """Luồng bóc tách gói tin chạy ngầm."""
        while self.is_attached:
            try:
                message, raw_data = self.packet_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                payload = message.get("payload", {})
                dir_name = payload.get("dir", "recv")
                sock = payload.get("sock", -1)
                if sock > 0:
                    self.active_socket = sock

                is_send = (dir_name == "send")
                direction_str = "C->S" if is_send else "S->C"
                dissector = self.c2s_dissector if is_send else self.s2c_dissector
                packets = dissector.feed(raw_data)

                for opcode, subcode, data, raw_pkt in packets:
                    self.handle_parsed_packet(direction_str, opcode, subcode, data)

            except Exception as e:
                pass
            finally:
                self.packet_queue.task_done()

    def handle_parsed_packet(self, direction, opcode, subcode, data):
        """Phân tích các gói tin WLO và đẩy sự kiện về GUI queue."""
        self.packet_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S")

        op_name = OPCODE_MAP.get(opcode, f"0x{opcode:02X}" if opcode is not None else "--")
        sub_str = f"0x{subcode:02X}" if subcode is not None else "--"
        hex_preview = data.hex()

        interp = ""

        # GÓI TIN MỞ QUÀ (C->S Op: 0x17 Sub: 0x4B)
        if direction == "C->S" and opcode == 0x17 and subcode == 0x4B:
            slot = data[0] if len(data) > 0 else 0
            self.last_open_slot = slot
            interp = f"Mở quà tại Ô {slot}"
            self.gui_queue.put(("OPEN_GIFT", {"slot": slot, "time": timestamp}))

        # GÓI TIN SERVER TRẢ PHẦN THƯỞNG (S->C Op: 0x17 Sub: 0x06)
        elif direction == "S->C" and opcode == 0x17 and subcode == 0x06:
            if len(data) >= 3:
                raw_code = struct.unpack("<H", data[0:2])[0]
                qty = data[2]
                code_hex = format_item_code(raw_code)
                interp = f"Server trả quà: {qty}x {self.get_item_name(raw_code)} ({code_hex})"
                self.gui_queue.put(("REWARD_ITEM", {
                    "code_int": raw_code, "code_hex": code_hex, "qty": qty,
                    "open_slot": self.last_open_slot, "time": timestamp
                }))

        # GÓI TIN YÊU CẦU VỨT ĐỒ (C->S Op: 0x17 Sub: 0x03)
        elif direction == "C->S" and opcode == 0x17 and subcode == 0x03:
            slot = data[0] if len(data) > 0 else 0
            qty = data[1] if len(data) > 1 else 1
            self.last_discard_req = {"slot": slot, "qty": qty, "time": time.time()}
            interp = f"Yêu cầu vứt: Ô {slot} (SL: {qty})"

        # GÓI TIN SERVER POPUP XÁC NHẬN VỨT (S->C Op: 0x17 Sub: 0xD4)
        elif direction == "S->C" and opcode == 0x17 and subcode == 0xD4:
            if len(data) >= 5:
                slot = data[1]
                raw_code = struct.unpack("<H", data[2:4])[0]
                qty = data[4]
                code_hex = format_item_code(raw_code)
                interp = f"Popup vứt: Ô {slot} ({qty}x {self.get_item_name(raw_code)})"
                self.gui_queue.put(("DISCARD_POPUP", {
                    "code_int": raw_code, "code_hex": code_hex, "qty": qty,
                    "slot": slot, "time": timestamp
                }))

        # GÓI TIN SERVER XÁC NHẬN VỨT XONG (S->C Op: 0x17 Sub: 0x1A)
        elif direction == "S->C" and opcode == 0x17 and subcode == 0x1A:
            if len(data) >= 3:
                raw_code = struct.unpack("<H", data[0:2])[0]
                qty = data[2]
                code_hex = format_item_code(raw_code)
                slot = self.last_discard_req.get("slot", -1) if self.last_discard_req else -1
                interp = f"Xác nhận vứt xong: {qty}x {code_hex}"
                self.gui_queue.put(("DISCARD_CONFIRMED", {
                    "code_int": raw_code, "code_hex": code_hex, "qty": qty,
                    "slot": slot, "time": timestamp
                }))

        # GÓI TIN ĐỒNG BỘ TÚI ĐỒ (S->C Op: 0x17 Sub: 0x05)
        elif direction == "S->C" and opcode == 0x17 and subcode == 0x05:
            entry_len = 31
            num_entries = len(data) // entry_len
            inv = {}
            for i in range(num_entries):
                entry = data[i * entry_len : (i + 1) * entry_len]
                s = entry[0]
                c = struct.unpack("<H", entry[1:3])[0]
                q = entry[3]
                inv[s] = {"code": c, "qty": q}
            self.inventory_cache = inv
            interp = f"Đồng bộ túi đồ: {len(inv)} món đồ"
            self.gui_queue.put(("INVENTORY_SYNC", {"count": len(inv), "time": timestamp}))

        # GÓI TIN CẬP NHẬT SỐ LƯỢNG Ô (S->C Op: 0x17 Sub: 0x09)
        elif direction == "S->C" and opcode == 0x17 and subcode == 0x09:
            if len(data) >= 2:
                s = data[0]
                rem = data[1]
                if s in self.inventory_cache:
                    if rem == 0:
                        del self.inventory_cache[s]
                    else:
                        self.inventory_cache[s]["qty"] = rem
                interp = f"Cập nhật Ô {s} còn lại: {rem}"
                self.gui_queue.put(("SLOT_UPDATE", {"slot": s, "remain": rem}))

        # Đẩy gói tin sang tab Sniffer
        self.gui_queue.put(("PACKET_LOG", {
            "time": timestamp, "dir": direction, "opcode": f"0x{opcode:02X} ({op_name})" if opcode is not None else "--",
            "subcode": sub_str, "len": len(data), "info": interp, "hex": hex_preview[:40]
        }))

    # --------------------------------------------------------------------------
    # VÒNG LẶP ĐỒNG BỘ GUI (POLL GUI QUEUE)
    # --------------------------------------------------------------------------
    def poll_gui_queue(self):
        """Xử lý toàn bộ sự kiện từ luồng ngầm gửi về cho Tkinter."""
        while not self.gui_queue.empty():
            try:
                ev_type, payload = self.gui_queue.get_nowait()
            except queue.Empty:
                break

            # Cập nhật số gói tin và socket
            self.lbl_socket_info.configure(text=f"Socket: {self.active_socket} | Gói tin: {self.packet_count}")

            if ev_type == "OPEN_GIFT":
                slot = payload["slot"]
                self.append_collector_feed("OPEN", f"[{payload['time']}] Người chơi mở vật phẩm tại Ô {slot}")

            elif ev_type == "REWARD_ITEM":
                self.on_gui_reward_item(payload)

            elif ev_type == "DISCARD_POPUP":
                self.on_gui_discard_item(payload, source="popup")

            elif ev_type == "DISCARD_CONFIRMED":
                self.on_gui_discard_item(payload, source="confirm")

            elif ev_type == "INVENTORY_SYNC":
                self.append_collector_feed("SYNC", f"[{payload['time']}] Đã đồng bộ {payload['count']} món đồ từ Server!")
                self.update_bag_grid_from_network()

            elif ev_type == "SLOT_UPDATE":
                self.update_bag_grid_from_network()

            elif ev_type == "PACKET_LOG":
                self.add_packet_to_sniffer(payload)

        self.root.after(50, self.poll_gui_queue)

    # --------------------------------------------------------------------------
    # SỰ KIỆN MỞ QUÀ & VỨT ĐỒ TRÊN GUI
    # --------------------------------------------------------------------------
    def on_gui_reward_item(self, data):
        """Xử lý khi nhận quà từ hộp quà."""
        if not self.var_collect_open.get():
            return

        code_hex = data["code_hex"]
        raw_code = data["code_int"]
        qty = data["qty"]
        t_str = data["time"]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Quét ô trống đầu tiên
        landing_slot = self.get_first_empty_slot()

        if code_hex in self.database:
            item = self.database[code_hex]
            item["times_received"] = item.get("times_received", 0) + 1
            item["last_seen"] = now_str
            item["last_qty"] = qty
            item["landing_slot"] = landing_slot
            self.save_database()
            name = item.get("name") or "(Chưa đặt tên)"
            self.append_collector_feed("REWARD", f"[{t_str}] [NHẬN QUÀ] {name} ({code_hex}) x{qty} -> Rơi vào Ô {landing_slot} (Đã mở {item['times_received']} lần)")
        else:
            # Món mới hoàn toàn!
            new_entry = {
                "code_hex": code_hex, "code_dec": raw_code,
                "raw_bytes": f"{raw_code & 0xFF:02X} {(raw_code >> 8) & 0xFF:02X}",
                "name": "", "first_seen": now_str, "last_seen": now_str,
                "times_received": 1, "times_discarded": 0, "last_qty": qty,
                "landing_slot": landing_slot, "source": "gift_open", "note": ""
            }
            self.database[code_hex] = new_entry
            self.save_database()

            self.append_collector_feed("NEW_ITEM", f"[{t_str}] ★ MÓN MỚI MỞ ĐƯỢC: {code_hex} (Dec: {raw_code}) x{qty} -> Rơi vào Ô {landing_slot}")
            self.show_new_item_prompt(code_hex, raw_code, qty, landing_slot, "Mở quà")

        self.refresh_database_table()
        self.update_collector_stats()

        # KIỂM TRA CHẾ ĐỘ TỰ VỨT RÁC KHI MỞ QUÀ
        if self.is_in_blacklist(raw_code) and self.var_auto_open_discard.get():
            open_slot = data.get("open_slot", 0)
            item_name = self.get_item_name(raw_code) or code_hex
            if landing_slot <= 0 or landing_slot > 50:
                self.append_collector_feed("DISCARD", f"[CẢNH BÁO AN TOÀN] Không xác định được ô rơi ({landing_slot}), hủy lệnh vứt để bảo vệ đồ!")
            elif landing_slot == open_slot:
                self.append_collector_feed("DISCARD", f"[CẢNH BÁO AN TOÀN] Ô rơi {landing_slot} trùng ô đang mở {open_slot}, từ chối vứt!")
            elif self.var_dry_run.get():
                self.append_collector_feed("DISCARD", f"[DRY-RUN] Phát hiện rác {item_name} rơi vào Ô {landing_slot}, bỏ qua lệnh vứt")
            else:
                try:
                    time.sleep(0.05)
                    body_discard = bytes([0x17, 0x03, landing_slot, qty, 0x01])
                    enc = pack_wlo_packet(body_discard)
                    if self.script:
                        self.script.exports_sync.sendraw(enc.hex())
                    self.append_collector_feed("DISCARD", f"[TỰ VỨT KHI MỞ] Đã gửi lệnh vứt rác: {item_name} tại Ô {landing_slot}")
                except Exception as e:
                    pass

    def on_gui_discard_item(self, data, source="popup"):
        """Xử lý khi người chơi vứt đồ."""
        if not self.var_collect_discard.get():
            return

        raw_code = data["code_int"]
        code_hex = data["code_hex"]
        qty = data["qty"]
        slot = data["slot"]
        t_str = data["time"]
        now = time.time()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Debounce chống trùng lặp giữa Sub 0xD4 và Sub 0x1A trong 2.0s
        if self.last_discard_event:
            l_code = self.last_discard_event.get("code")
            l_time = self.last_discard_event.get("time", 0)
            if l_code == raw_code and (now - l_time) < 2.0:
                return

        self.last_discard_event = {"code": raw_code, "qty": qty, "slot": slot, "time": now}

        # Nếu đang bật chế độ WPE Pro Auto-Confirm và món nằm trong Blacklist -> tự động xác nhận popup!
        is_junk = self.is_in_blacklist(raw_code)
        if source == "popup" and is_junk and self.var_auto_discard.get():
            self.trigger_wpe_auto_confirm(slot, qty, raw_code)

        if code_hex in self.database:
            item = self.database[code_hex]
            item["times_discarded"] = item.get("times_discarded", 0) + 1
            item["last_seen"] = now_str
            item["last_discarded_from_slot"] = slot
            item["last_discarded_qty"] = qty
            self.save_database()
            name = item.get("name") or "(Chưa đặt tên)"
            self.append_collector_feed("DISCARD", f"[{t_str}] [VỨT ĐỒ] {name} ({code_hex}) x{qty} tại Ô {slot} (Đã vứt {item['times_discarded']} lần)")
        else:
            # Món mới phát hiện từ thao tác vứt đồ!
            new_entry = {
                "code_hex": code_hex, "code_dec": raw_code,
                "raw_bytes": f"{raw_code & 0xFF:02X} {(raw_code >> 8) & 0xFF:02X}",
                "name": "", "first_seen": now_str, "last_seen": now_str,
                "times_received": 0, "times_discarded": 1, "last_qty": qty,
                "last_discarded_from_slot": slot, "source": "discard", "note": ""
            }
            self.database[code_hex] = new_entry
            self.save_database()

            self.append_collector_feed("NEW_ITEM", f"[{t_str}] ★ MÓN MỚI KHI VỨT: {code_hex} (Dec: {raw_code}) x{qty} tại Ô {slot}")
            self.show_new_item_prompt(code_hex, raw_code, qty, slot, "Vứt đồ")

        self.refresh_database_table()
        self.update_collector_stats()

    def trigger_wpe_auto_confirm(self, slot, qty, raw_code):
        """Bắn packet xác nhận popup vứt đồ tự động (WPE Pro)."""
        if self.var_dry_run.get():
            self.append_collector_feed("DISCARD", f"[DRY-RUN] Bỏ qua lệnh xác nhận popup Ô {slot}")
            return
        try:
            time.sleep(0.04)
            body = bytes([0x17, 0x7C, slot, qty, 0x02])
            enc = pack_wlo_packet(body)
            if self.script:
                res = self.script.exports_sync.sendraw(enc.hex())
                name = self.get_item_name(raw_code)
                self.append_collector_feed("DISCARD", f"[WPE AUTO-CONFIRM] Đã tự xác nhận vứt: {name} tại Ô {slot}")
        except Exception as e:
            pass

    # --------------------------------------------------------------------------
    # BANNER ĐẶT TÊN MÓN MỚI TRỰC TIẾP TRÊN GIAO DIỆN
    # --------------------------------------------------------------------------
    def show_new_item_prompt(self, code_hex, code_dec, qty, slot, action_name):
        self.pending_new_code = code_hex
        self.lbl_new_item_msg.configure(
            text=f"★ PHÁT HIỆN VẬT PHẨM MỚI TỪ {action_name.upper()}: [{code_hex}] (Dec: {code_dec}) x{qty}! Nhập tên gợi nhớ:"
        )
        self.entry_new_item_name.delete(0, tk.END)
        self.frame_new_item_prompt.pack(fill="x", pady=(0, 8), before=self.txt_collector_feed)
        self.entry_new_item_name.focus_set()

    def confirm_new_item_name(self):
        if not hasattr(self, "pending_new_code") or not self.pending_new_code:
            return
        code_hex = self.pending_new_code
        chosen_name = self.entry_new_item_name.get().strip()
        if not chosen_name:
            chosen_name = f"Vật phẩm_{code_hex}"

        if code_hex in self.database:
            self.database[code_hex]["name"] = chosen_name
            self.save_database()
            self.refresh_database_table()
            self.append_collector_feed("REWARD", f"[✓] Đã lưu tên '{chosen_name}' cho mã {code_hex}!")

        self.dismiss_new_item_prompt()

    def dismiss_new_item_prompt(self):
        self.pending_new_code = None
        self.frame_new_item_prompt.pack_forget()

    # --------------------------------------------------------------------------
    # QUẢN LÝ DỮ LIỆU KHO ĐỒ (DATABASE TAB)
    # --------------------------------------------------------------------------
    def refresh_database_table(self):
        """Cập nhật lại bảng Database."""
        query = self.entry_db_search.get().strip().lower()
        self.tree_db.delete(*self.tree_db.get_children())

        count = 0
        for hex_id, item in sorted(self.database.items()):
            name = item.get("name") or "(Chưa đặt tên)"
            dec = str(item.get("code_dec", 0))
            if query and (query not in hex_id.lower() and query not in dec and query not in name.lower()):
                continue

            times_rec = item.get("times_received", 0)
            times_disc = item.get("times_discarded", 0)
            if times_rec > 0 and times_disc > 0:
                stats = f"{times_rec} nhận / {times_disc} vứt"
            elif times_rec > 0:
                stats = f"{times_rec} lần nhận"
            elif times_disc > 0:
                stats = f"{times_disc} lần vứt"
            else:
                stats = "1 lần"

            source = item.get("source", "")
            if source == "discard" or (times_disc > 0 and times_rec == 0):
                note = f"Vứt Ô {item.get('last_discarded_from_slot', '?')}"
            else:
                note = f"Rơi Ô {item.get('landing_slot', '?')}"

            first = item.get("first_seen", "")
            last = item.get("last_seen", "")

            self.tree_db.insert("", "end", iid=hex_id, values=(
                hex_id, dec, name, stats, note, first, last
            ))
            count += 1

        self.lbl_db_count.configure(text=f"Hiển thị: {count} / {len(self.database)} vật phẩm")

    def filter_database_table(self):
        self.refresh_database_table()

    def clear_db_search(self):
        self.entry_db_search.delete(0, tk.END)
        self.refresh_database_table()

    def action_rename_item(self):
        sel = self.tree_db.selection()
        if not sel:
            messagebox.showinfo("Thông Báo", "Vui lòng bấm chọn một vật phẩm trong bảng trước!")
            return
        hex_id = sel[0]
        cur_name = self.database.get(hex_id, {}).get("name", "")
        new_name = simpledialog.askstring("Đổi Tên Vật Phẩm", f"Nhập tên mới cho {hex_id}:",
                                          initialvalue=cur_name, parent=self.root)
        if new_name is not None and new_name.strip():
            self.database[hex_id]["name"] = new_name.strip()
            self.save_database()
            self.refresh_database_table()
            messagebox.showinfo("Thành Công", f"Đã cập nhật tên '{new_name.strip()}' cho {hex_id}!")

    def action_add_selected_to_blacklist(self):
        sel = self.tree_db.selection()
        if not sel:
            messagebox.showinfo("Thông Báo", "Vui lòng bấm chọn một vật phẩm trong bảng trước!")
            return
        hex_id = sel[0]
        item = self.database.get(hex_id, {})
        name = item.get("name") or hex_id
        dec = item.get("code_dec", 0)

        self.blacklist[hex_id] = {
            "name": name,
            "code_dec": dec,
            "enabled": True,
            "discard_count": 0
        }
        self.save_config()
        self.refresh_blacklist_table()
        messagebox.showinfo("Thành Công", f"Đã thêm [{name}] ({hex_id}) vào Blacklist tự động vứt!")

    def action_delete_item(self):
        sel = self.tree_db.selection()
        if not sel:
            return
        hex_id = sel[0]
        if messagebox.askyesno("Xác Nhận Xóa", f"Bạn có chắc chắn muốn xóa vật phẩm {hex_id} khỏi database?"):
            del self.database[hex_id]
            self.save_database()
            self.refresh_database_table()

    def action_export_txt(self):
        self.export_text_report()
        messagebox.showinfo("Thành Công", f"Đã xuất báo cáo đẹp mắt ra file:\n{self.txt_file}")

    def action_reload_database(self):
        self.database = self.load_database()
        self.refresh_database_table()
        self.update_collector_stats()

    # --------------------------------------------------------------------------
    # QUẢN LÝ BLACKLIST (AUTO-DISCARD TAB)
    # --------------------------------------------------------------------------
    def refresh_blacklist_table(self):
        self.tree_bl.delete(*self.tree_bl.get_children())
        for hex_id, info in sorted(self.blacklist.items()):
            name = info.get("name", "")
            dec = str(info.get("code_dec", ""))
            en_str = "BẬT" if info.get("enabled", True) else "TẮT"
            count = str(info.get("discard_count", 0))
            self.tree_bl.insert("", "end", iid=hex_id, values=(hex_id, dec, name, en_str, count))
        self.lbl_bl_count.configure(text=f"Blacklist: {len(self.blacklist)} vật phẩm")

    def action_add_to_blacklist_manual(self):
        code_raw = self.entry_bl_code.get().strip()
        name = self.entry_bl_name.get().strip()
        code_int = parse_code_input(code_raw)
        if code_int is None:
            messagebox.showerror("Lỗi", "Mã không hợp lệ! Nhập dạng 0xXXXX, XXXX hoặc số thập phân.")
            return

        hex_id = format_item_code(code_int)
        if not name:
            name = self.get_item_name(code_int) or hex_id

        self.blacklist[hex_id] = {
            "name": name,
            "code_dec": code_int,
            "enabled": True,
            "discard_count": 0
        }
        self.save_config()
        self.refresh_blacklist_table()
        self.entry_bl_code.delete(0, tk.END)
        self.entry_bl_name.delete(0, tk.END)

    def action_toggle_blacklist_item(self):
        sel = self.tree_bl.selection()
        if not sel:
            return
        hex_id = sel[0]
        cur = self.blacklist.get(hex_id, {}).get("enabled", True)
        self.blacklist[hex_id]["enabled"] = not cur
        self.save_config()
        self.refresh_blacklist_table()

    def action_remove_from_blacklist(self):
        sel = self.tree_bl.selection()
        if not sel:
            return
        hex_id = sel[0]
        if messagebox.askyesno("Xóa Blacklist", f"Xóa {hex_id} khỏi Blacklist?"):
            del self.blacklist[hex_id]
            self.save_config()
            self.refresh_blacklist_table()

    # --------------------------------------------------------------------------
    # QUẢN LÝ LƯỚI TÚI ĐỒ 50 Ô (VISUAL BAG TAB)
    # --------------------------------------------------------------------------
    def action_scan_memory_bag(self):
        """Quét mảng túi đồ Delphi thật trực tiếp từ bộ nhớ game qua Frida RPC."""
        if not self.is_attached or not self.script:
            messagebox.showwarning("Chưa Kết Nối", "Vui lòng đính kèm vào tiến trình game trước!")
            return

        try:
            res = self.script.exports_sync.dumpbag()
            if not res.get("found"):
                messagebox.showwarning("Chưa Tìm Thấy", "Chưa quét được mảng túi đồ trong bộ nhớ. Hãy di chuyển hoặc mở 1 món trong game rồi thử lại.")
                return

            slots = res["slots"]
            self.memory_bag_cache = slots
            now_str = datetime.now().strftime("%H:%M:%S")

            occupied_count = 0
            empty_slots = []

            for item in slots:
                s = item["slot"]
                is_empty = item["isEmpty"]
                w = self.slot_widgets.get(s)
                if not w:
                    continue

                if is_empty:
                    empty_slots.append(s)
                    w["frame"].configure(bg=THEME["gray_empty"], highlightbackground=THEME["border"], highlightthickness=1)
                    w["num"].configure(bg=THEME["gray_empty"], fg=THEME["text_muted"])
                    w["name"].configure(text="(Trống)", bg=THEME["gray_empty"], fg=THEME["text_muted"])
                    w["code"].configure(text="", bg=THEME["gray_empty"])
                else:
                    occupied_count += 1
                    # Kiểm tra xem có trong network cache không
                    code_val = None
                    qty_val = None
                    if s in self.inventory_cache:
                        code_val = self.inventory_cache[s]["code"]
                        qty_val = self.inventory_cache[s]["qty"]

                    code_hex = format_item_code(code_val) if code_val else item["val1_hex"]
                    item_name = self.get_item_name(code_val) if code_val else f"Món {s}"
                    is_junk = self.is_in_blacklist(code_val) if code_val else False

                    bg_color = "#5c2b2b" if is_junk else "#1e3a5f"
                    fg_name = THEME["yellow"] if is_junk else THEME["cyan"]

                    w["frame"].configure(bg=bg_color, highlightbackground=THEME["border"], highlightthickness=1)
                    w["num"].configure(bg=bg_color, fg="#ffffff")
                    w["name"].configure(text=item_name, bg=bg_color, fg=fg_name)
                    qty_text = f"x{qty_val} " if qty_val else ""
                    w["code"].configure(text=f"{qty_text}{code_hex}", bg=bg_color, fg=THEME["text_muted"])

            # Đánh dấu viền ô trống đầu tiên
            first_empty = empty_slots[0] if empty_slots else None
            if first_empty and first_empty in self.slot_widgets:
                self.slot_widgets[first_empty]["frame"].configure(highlightbackground=THEME["green"], highlightthickness=2)
                self.slot_widgets[first_empty]["name"].configure(text="★ Ô RƠI QUÀ", fg=THEME["green"])

            self.lbl_bag_summary.configure(
                text=f"Đang có: {occupied_count} món | Ô trống: {len(empty_slots)} | Ô trống đầu tiên: Ô {first_empty if first_empty else 'Hết'}"
            )
            self.lbl_bag_sync_time.configure(text=f"Quét bộ nhớ lúc: {now_str}")

        except Exception as e:
            messagebox.showerror("Lỗi Quét Bộ Nhớ", f"Lỗi: {e}")

    def update_bag_grid_from_network(self):
        """Cập nhật trạng thái 50 ô từ gói tin mạng Op:0x17 Sub:0x05."""
        if not self.inventory_cache:
            return

        occupied_count = len(self.inventory_cache)
        empty_slots = [s for s in range(1, 51) if s not in self.inventory_cache]
        first_empty = empty_slots[0] if empty_slots else None
        now_str = datetime.now().strftime("%H:%M:%S")

        for s in range(1, 51):
            w = self.slot_widgets.get(s)
            if not w:
                continue

            if s in self.inventory_cache:
                info = self.inventory_cache[s]
                code = info["code"]
                qty = info["qty"]
                hex_id = format_item_code(code)
                name = self.get_item_name(code) or f"Vật phẩm {hex_id}"
                is_junk = self.is_in_blacklist(code)

                bg_color = "#5c2b2b" if is_junk else "#1e3a5f"
                fg_name = THEME["yellow"] if is_junk else THEME["cyan"]

                w["frame"].configure(bg=bg_color, highlightbackground=THEME["border"], highlightthickness=1)
                w["num"].configure(bg=bg_color, fg="#ffffff")
                w["name"].configure(text=name, bg=bg_color, fg=fg_name)
                w["code"].configure(text=f"x{qty} {hex_id}", bg=bg_color, fg=THEME["text_muted"])
            else:
                w["frame"].configure(bg=THEME["gray_empty"], highlightbackground=THEME["border"], highlightthickness=1)
                w["num"].configure(bg=THEME["gray_empty"], fg=THEME["text_muted"])
                w["name"].configure(text="(Trống)", bg=THEME["gray_empty"], fg=THEME["text_muted"])
                w["code"].configure(text="", bg=THEME["gray_empty"])

        # Viền ô trống đầu tiên
        if first_empty and first_empty in self.slot_widgets:
            self.slot_widgets[first_empty]["frame"].configure(highlightbackground=THEME["green"], highlightthickness=2)
            self.slot_widgets[first_empty]["name"].configure(text="★ Ô RƠI QUÀ", fg=THEME["green"])

        self.lbl_bag_summary.configure(
            text=f"Đang có: {occupied_count} món | Ô trống: {len(empty_slots)} | Ô trống đầu tiên: Ô {first_empty if first_empty else 'Hết'}"
        )
        self.lbl_bag_sync_time.configure(text=f"Đồng bộ mạng lúc: {now_str}")

    def on_slot_clicked(self, slot_num):
        """Hiển thị hộp thoại chi tiết khi click vào một ô trong túi đồ."""
        if slot_num in self.inventory_cache:
            info = self.inventory_cache[slot_num]
            code = info["code"]
            qty = info["qty"]
            hex_id = format_item_code(code)
            name = self.get_item_name(code) or "(Chưa có tên trong database)"
            is_junk = self.is_in_blacklist(code)
            junk_str = "CÓ TRONG BLACKLIST" if is_junk else "An toàn"

            msg = f"Ô {slot_num:02d} ĐANG CHỨA:\n" \
                  f"• Tên vật phẩm : {name}\n" \
                  f"• Mã Server    : {hex_id} (Dec: {code})\n" \
                  f"• Số lượng     : {qty}\n" \
                  f"• Trạng thái   : {junk_str}"

            if messagebox.askyesno(f"Chi Tiết Ô {slot_num}", f"{msg}\n\nBạn có muốn thêm món này vào Blacklist không?"):
                self.blacklist[hex_id] = {
                    "name": name if name != "(Chưa có tên trong database)" else hex_id,
                    "code_dec": code, "enabled": True, "discard_count": 0
                }
                self.save_config()
                self.refresh_blacklist_table()
                self.update_bag_grid_from_network()
        else:
            messagebox.showinfo(f"Ô {slot_num:02d}", f"Ô {slot_num:02d} hiện đang TRỐNG.")

    # --------------------------------------------------------------------------
    # TAB 5: SOI GÓI TIN MẠNG (SNIFFER)
    # --------------------------------------------------------------------------
    def add_packet_to_sniffer(self, p):
        filter_mode = self.cb_sniff_filter.get()
        if filter_mode == "Chỉ gói Túi đồ (0x17)" and "0x17" not in p["opcode"]:
            return
        if filter_mode == "Chỉ Mở quà & Vứt đồ" and not p["info"]:
            return

        self.tree_sniff.insert("", "end", values=(
            p["time"], p["dir"], p["opcode"], p["subcode"], p["len"], p["info"], p["hex"]
        ))

        # Giới hạn 500 dòng
        children = self.tree_sniff.get_children()
        if len(children) > 500:
            self.tree_sniff.delete(children[0])

        if self.var_autoscroll.get() and children:
            self.tree_sniff.see(children[-1])

        self.lbl_sniff_count.configure(text=f"Bắt được: {len(children)} gói")

    def action_clear_sniffer(self):
        self.tree_sniff.delete(*self.tree_sniff.get_children())
        self.lbl_sniff_count.configure(text="Bắt được: 0 gói")

    # --------------------------------------------------------------------------
    # CÁC HÀM TIỆN ÍCH
    # --------------------------------------------------------------------------
    def get_item_name(self, code_int):
        """Lấy tên vật phẩm từ Blacklist hoặc Database (100% không Item.Dat)."""
        if not code_int:
            return ""
        code_hex = format_item_code(code_int)
        if code_hex in self.blacklist and self.blacklist[code_hex].get("name"):
            return self.blacklist[code_hex]["name"]
        if code_hex in self.database and self.database[code_hex].get("name"):
            return self.database[code_hex]["name"]
        return ""

    def is_in_blacklist(self, code_int):
        if not code_int:
            return False
        code_hex = format_item_code(code_int)
        return code_hex in self.blacklist and self.blacklist[code_hex].get("enabled", True)

    def get_first_empty_slot(self):
        try:
            if self.script:
                res = self.script.exports_sync.dumpbag()
                if res.get("found"):
                    for s in res["slots"]:
                        if s["isEmpty"]:
                            return s["slot"]
        except Exception:
            pass
        if self.inventory_cache:
            for s in range(1, 51):
                if s not in self.inventory_cache:
                    return s
        return -1

    def append_collector_feed(self, tag, text):
        self.txt_collector_feed.insert(tk.END, text + "\n", tag)
        self.txt_collector_feed.see(tk.END)

    def update_collector_stats(self):
        total_types = len(self.database)
        total_open = sum(i.get("times_received", 0) for i in self.database.values())
        total_disc = sum(i.get("times_discarded", 0) for i in self.database.values())
        self.lbl_collect_stats.configure(
            text=f"Đã lưu: {total_types} loại | Mở: {total_open} lần | Vứt: {total_disc} lần"
        )

    def load_database(self):
        if os.path.isfile(self.db_file):
            try:
                with open(self.db_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return {}

    def save_database(self):
        try:
            with open(self.db_file, "w", encoding="utf-8") as f:
                json.dump(self.database, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        self.export_text_report()

    def export_text_report(self):
        try:
            with open(self.txt_file, "w", encoding="utf-8") as f:
                f.write("=" * 105 + "\n")
                f.write(f"           CƠ SỞ DỮ LIỆU VẬT PHẨM WLO - TỔNG CỘNG: {len(self.database)} VẬT PHẨM\n")
                f.write(f"           Thời gian cập nhật: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 105 + "\n")
                f.write(f"{'Mã Hex':<10} | {'Mã Dec':<8} | {'Tên Vật Phẩm':<30} | {'Thống Kê':<16} | {'Ghi Chú':<12} | {'Lần Đầu Thấy'}\n")
                f.write("-" * 105 + "\n")
                for hex_id, item in sorted(self.database.items()):
                    name = item.get("name") or "(Chưa đặt tên)"
                    dec = item.get("code_dec", 0)
                    times_rec = item.get("times_received", 0)
                    times_disc = item.get("times_discarded", 0)

                    if times_rec > 0 and times_disc > 0:
                        stats = f"{times_rec} nhận / {times_disc} vứt"
                    elif times_rec > 0:
                        stats = f"{times_rec} lần nhận"
                    elif times_disc > 0:
                        stats = f"{times_disc} lần vứt"
                    else:
                        stats = "1 lần"

                    source = item.get("source", "")
                    if source == "discard" or (times_disc > 0 and times_rec == 0):
                        note = f"Vứt Ô {item.get('last_discarded_from_slot', '?')}"
                    else:
                        note = f"Rơi Ô {item.get('landing_slot', '?')}"
                    first = item.get("first_seen", "")
                    f.write(f"{hex_id:<10} | {dec:<8} | {name:<30} | {stats:<16} | {note:<12} | {first}\n")
                f.write("=" * 105 + "\n")
        except Exception:
            pass

    def load_config(self):
        if os.path.isfile(self.cfg_file):
            try:
                with open(self.cfg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return {
            "auto_discard_enabled": True,
            "auto_discard_on_open": False,
            "dry_run": False,
            "blacklist": {}
        }

    def save_config(self):
        self.config["auto_discard_enabled"] = self.var_auto_discard.get()
        self.config["auto_discard_on_open"] = self.var_auto_open_discard.get()
        self.config["dry_run"] = self.var_dry_run.get()
        self.config["blacklist"] = self.blacklist
        try:
            with open(self.cfg_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

# ==============================================================================
# HÀM CHÍNH
# ==============================================================================
def main():
    root = tk.Tk()
    app = WLOAppGUI(root)

    def on_closing():
        if app.is_attached:
            app.detach_from_game()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
