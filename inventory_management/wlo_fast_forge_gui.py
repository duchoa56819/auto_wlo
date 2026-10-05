#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO FAST FORGE & ENHANCE MANAGER (GUI)
=====================================
Giao diện trực quan cường hóa trang bị & khảm ngọc siêu tốc cho Wonderland Online (WLO):
1. Tự động nhận diện mọi client alogin*.exe (alogin-w01, w03, f02...).
2. Quét RAM siêu tốc 50 ô túi đồ (0.05s) - Phân loại Trang bị, Cuộn rèn, Ngọc khảm.
3. Chế độ Cường hóa 1-Click (Single-step): Gửi gói tin tức thì qua socket game.
4. Chế độ Cường hóa Tự Động / Liên Tục (Auto Batch): Tùy chỉnh số lượt, delay an toàn (200-1500ms).
5. Kịch bản Combo Nâng Đồ (Recipe / Sequence Macro): Hỗ trợ chuỗi nâng nhiều bước (VD combo 7 bước).
6. Bắt và giải mã gói tin Server phản hồi (Sub: 0xD2, Sub: 0xD6, Sub: 0x09) theo thời gian thực.
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
from tkinter import ttk, messagebox, filedialog

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    frida = None

# ==============================================================================
# BẢNG MÀU CATPPUCCIN MOCHA / DARK THEME
# ==============================================================================
THEME = {
    "bg_dark": "#11111b",       # Header, statusbar
    "bg_main": "#181825",       # Main background
    "bg_card": "#1e1e2e",       # Card container
    "bg_input": "#313244",      # Input field
    "border": "#45475a",
    "text_main": "#cdd6f4",     # Primary text
    "text_muted": "#a6adc8",    # Secondary text
    "primary": "#89b4fa",       # Blue accent
    "primary_active": "#b4befe",
    "green": "#a6e3a1",         # Success / Gems
    "green_dark": "#1a3826",
    "red": "#f38ba8",           # Danger / Stop / Red Scroll
    "red_dark": "#3d1b24",
    "yellow": "#f9e2af",        # Warning / Gold
    "yellow_dark": "#3d3216",
    "peach": "#fab387",         # White forge / orange
    "mauve": "#cba6f7",         # Equipment accent
    "mauve_dark": "#2d1f3f",
    "cyan": "#89dceb",          # Diamond / Gem
    "slot_empty": "#161622",    # Empty slot
    "slot_equip": "#281b3b",    # Equipment
    "slot_scroll": "#38171f",   # Scroll
    "slot_gem": "#162e24",      # Gem / Saphire
    "slot_other": "#222330",    # Other items
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "wlo_items_database.json")
PRESETS_FILE = os.path.join(SCRIPT_DIR, "forge_presets.json")

def pack_wlo_packet(body_bytes: bytes) -> bytes:
    """Đóng gói Magic Header 0xF4 0x44, uint16 LE Length và XOR 0xAD."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain = header + body_bytes
    return bytes(b ^ 0xAD for b in plain)

# ==============================================================================
# MÃ JAVASCRIPT FRIDA HOOK & MEMORY SCANNER
# ==============================================================================
FRIDA_HOOK_JS = """
var activeSocket = -1;
var cachedBagBase = null;

var ws2 = Process.getModuleByName('ws2_32.dll');
var sendPtr = ws2 ? ws2.getExportByName('send') : null;
var getpeernamePtr = ws2 ? ws2.getExportByName('getpeername') : null;

var sendFunc = sendPtr ? new NativeFunction(sendPtr, 'int', ['int', 'pointer', 'int', 'int']) : null;
var getpeernameFunc = getpeernamePtr ? new NativeFunction(getpeernamePtr, 'int', ['pointer', 'pointer', 'pointer']) : null;

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
    return -1;
}

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

function readBagMemory() {
    if (cachedBagBase) {
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
                        var ratio50 = count50 / cnt;
                        if (ratio50 < 0.70) {
                            candidates.push({base: base, count: cnt, items: items});
                        }
                    }
                }
            } catch(e) {}
        }
        if (candidates.length > 0) break;
    }

    if (candidates.length === 0) return {success: false, items: {}};

    candidates.sort(function(a, b) { return b.base.compare(a.base); });
    var best = candidates[0];
    cachedBagBase = best.base;
    return {success: true, cached: false, items: best.items};
}

function doSendRaw(hexBytes) {
    if (activeSocket <= 0) scanActiveSocket();
    if (activeSocket <= 0) return {success: false, error: 'Chua co socket hoat dong'};
    if (!sendFunc) return {success: false, error: 'Khong co ham send'};

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
    readbag: function() { return readBagMemory(); },
    sendraw: function(hex) { return doSendRaw(hex); }
};
"""

# ==============================================================================
# BỘ TÁI GHÉP LUỒNG TCP (STREAM DISSECTOR)
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
# CLASS GIAO DIỆN CHÍNH: WLO FAST FORGE GUI
# ==============================================================================
class WLOFastForgeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("⚡ WLO Fast Forge & Enhance Manager - Cường Hóa & Khảm Ngọc Siêu Tốc")
        self.root.geometry("1300x860")
        self.root.minsize(1160, 760)
        self.root.configure(bg=THEME["bg_main"])

        # Frida Session & Script
        self.session = None
        self.script = None
        self.active_pid = None
        self.active_proc_name = ""

        # Luồng TCP Sniffer
        self.c2s_dissector = WLOStreamDissector()
        self.s2c_dissector = WLOStreamDissector()
        self.msg_queue = queue.Queue()

        # Dữ liệu túi đồ & CSDL
        self.bag_items = {}       # {slot: {"code": int, "qty": int}}
        self.db = {}              # {hex_code: {"name": str, ...}}
        self.load_database()

        # Lựa chọn hiện tại
        self.selected_equip_slot = 3       # Mặc định ô 3
        self.selected_material_slot = None  # Ô chứa cuộn hoặc ngọc

        # Trạng thái tự động
        self.auto_running = False
        self.auto_thread = None

        # Thống kê
        self.stat_total_ops = 0
        self.stat_success_ops = 0
        self.stat_materials_used = 0

        # Kịch bản Combo
        self.combo_steps = []
        self.load_default_combo()

        # Xây dựng giao diện
        self.setup_styles()
        self.create_header()
        self.create_main_content()
        self.create_statusbar()

        # Quét tiến trình khi khởi chạy
        self.refresh_process_list()

        # Lắng nghe hàng đợi gói tin
        self.root.after(100, self.process_packet_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_window_close)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=THEME["bg_main"], borderwidth=0)
        style.configure("TNotebook.Tab", background=THEME["bg_card"], foreground=THEME["text_muted"],
                        font=("Segoe UI", 10, "bold"), padding=[16, 7])
        style.map("TNotebook.Tab",
                  background=[("selected", THEME["bg_dark"])],
                  foreground=[("selected", THEME["primary"])])

        style.configure("Treeview",
                        background=THEME["bg_input"],
                        foreground=THEME["text_main"],
                        fieldbackground=THEME["bg_input"],
                        font=("Segoe UI", 9),
                        rowheight=26)
        style.map("Treeview", background=[("selected", THEME["primary"])], foreground=[("selected", "#11111b")])
        style.configure("Treeview.Heading",
                        background=THEME["bg_card"],
                        foreground=THEME["primary"],
                        font=("Segoe UI", 9, "bold"),
                        padding=[6, 4])

    def load_database(self):
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    self.db = json.load(f)
            except Exception:
                self.db = {}

    def get_item_name(self, code: int) -> str:
        hex_code = f"0x{code:04X}"
        return self.db.get(hex_code, {}).get("name", "") or f"Item_{hex_code}"

    def classify_item(self, code: int, qty: int):
        """
        Phân loại vật phẩm:
        - 'equip': Trang bị
        - 'scroll': Cuộn rèn (Forge Scroll)
        - 'gem': Ngọc khảm (Sapphire, Spar, Diamond)
        - 'other': Vật phẩm khác
        """
        hex_code = f"0x{code:04X}"
        name = self.get_item_name(code).lower()

        # Cuộn rèn
        if any(k in name for k in ["scroll", "forge"]) or hex_code in ["0x85BF", "0x86CB", "0x86D0", "0x85C4", "0x85CF"]:
            return "scroll"

        # Ngọc / Đá khảm
        if any(k in name for k in ["saphire", "sapphire", "spar", "diamond", "crystal"]) or hex_code in ["0xEE86", "0xEE87", "0xEE97", "0xEE98", "0xEE53"]:
            return "gem"

        # Trang bị (thường là số lượng 1, không phải vé, bình máu, lều, remote)
        ignored = ["remote", "tent", "voucher", "potion", "bottle", "dragonfly", "pill", "lottery", "feather", "pizza"]
        if qty == 1 and not any(k in name for k in ignored):
            return "equip"

        return "other"

    # --------------------------------------------------------------------------
    # HEADER
    # --------------------------------------------------------------------------
    def create_header(self):
        header = tk.Frame(self.root, bg=THEME["bg_dark"], height=68, padx=16, pady=10)
        header.pack(fill="x")

        left = tk.Frame(header, bg=THEME["bg_dark"])
        left.pack(side="left")

        title = tk.Label(left, text="⚡ WLO FAST FORGE & ENHANCE MANAGER",
                         bg=THEME["bg_dark"], fg=THEME["primary"], font=("Segoe UI", 13, "bold"))
        title.pack(anchor="w")

        sub = tk.Label(left, text="Cường hóa Cuộn rèn (Sub 0x79) • Khảm Ngọc & Sapphire (Sub 0x7F) • Kịch bản Combo Siêu Tốc",
                       bg=THEME["bg_dark"], fg=THEME["text_muted"], font=("Segoe UI", 9))
        sub.pack(anchor="w")

        right = tk.Frame(header, bg=THEME["bg_dark"])
        right.pack(side="right")

        tk.Label(right, text="Game:", bg=THEME["bg_dark"], fg=THEME["text_muted"], font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 5))

        self.cb_procs = ttk.Combobox(right, state="readonly", width=22, font=("Segoe UI", 9))
        self.cb_procs.pack(side="left", padx=(0, 8))
        self.cb_procs.bind("<<ComboboxSelected>>", self.on_process_selected)

        btn_find = tk.Button(right, text="🔍 Tìm Game", font=("Segoe UI", 9, "bold"),
                             bg=THEME["bg_input"], fg=THEME["primary"], relief="flat", padx=10, pady=4,
                             cursor="hand2", command=self.refresh_process_list)
        btn_find.pack(side="left", padx=(0, 8))

        btn_scan = tk.Button(right, text="⚡ QUÉT TÚI ĐỒ (0.05s)", font=("Segoe UI", 9, "bold"),
                             bg=THEME["green"], fg="#11111b", relief="flat", padx=14, pady=4,
                             cursor="hand2", command=self.action_scan_bag)
        btn_scan.pack(side="left")

    # --------------------------------------------------------------------------
    # MAIN CONTENT (3 CỘT: TÚI ĐỒ -> ĐIỀU KHIỂN -> NHẬT KÝ)
    # --------------------------------------------------------------------------
    def create_main_content(self):
        main = tk.Frame(self.root, bg=THEME["bg_main"], padx=10, pady=8)
        main.pack(fill="both", expand=True)

        # CỘT 1: Lưới 50 ô túi đồ (Trái)
        col_bag = tk.Frame(main, bg=THEME["bg_card"], padx=10, pady=10, relief="flat", bd=1)
        col_bag.pack(side="left", fill="both", expand=False, padx=(0, 8))

        lbl_bag = tk.Label(col_bag, text="🎒 TÚI ĐỒ 50 Ô (CLICK CHỌN MỤC TIÊU)",
                           bg=THEME["bg_card"], fg=THEME["primary"], font=("Segoe UI", 10, "bold"))
        lbl_bag.pack(anchor="w", pady=(0, 6))

        # Khung chú thích màu sắc
        legend = tk.Frame(col_bag, bg=THEME["bg_card"])
        legend.pack(fill="x", pady=(0, 8))

        self.create_legend_badge(legend, "Trang bị", THEME["mauve"], THEME["mauve_dark"])
        self.create_legend_badge(legend, "Cuộn rèn", THEME["red"], THEME["red_dark"])
        self.create_legend_badge(legend, "Ngọc khảm", THEME["green"], THEME["green_dark"])

        # Grid 50 ô (5 hàng x 10 cột)
        self.grid_frame = tk.Frame(col_bag, bg=THEME["bg_card"])
        self.grid_frame.pack(fill="both", expand=True)
        self.slot_buttons = {}

        for row in range(10):
            for col in range(5):
                slot_idx = row * 5 + col + 1
                btn = tk.Button(self.grid_frame, text=f"#{slot_idx}\nTrống", font=("Segoe UI", 8),
                                width=10, height=2, bg=THEME["slot_empty"], fg=THEME["text_muted"],
                                relief="flat", activebackground=THEME["primary_active"],
                                cursor="hand2", command=lambda s=slot_idx: self.on_slot_clicked(s))
                btn.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")
                btn.bind("<Button-3>", lambda event, s=slot_idx: self.on_slot_right_clicked(s))
                self.slot_buttons[slot_idx] = btn

        for c in range(5):
            self.grid_frame.grid_columnconfigure(c, weight=1)

        # Nút hỗ trợ chọn nhanh
        btn_box = tk.Frame(col_bag, bg=THEME["bg_card"], pady=6)
        btn_box.pack(fill="x")

        tk.Button(btn_box, text="🎯 Chọn Trang Bị (Click Trái)", font=("Segoe UI", 8, "bold"),
                  bg=THEME["mauve_dark"], fg=THEME["mauve"], relief="flat", padx=6, pady=3,
                  command=self.set_target_from_selected).pack(side="left", padx=2)
        tk.Button(btn_box, text="💎 Chọn Cuộn/Ngọc (Click Phải)", font=("Segoe UI", 8, "bold"),
                  bg=THEME["green_dark"], fg=THEME["green"], relief="flat", padx=6, pady=3,
                  command=self.set_material_from_selected).pack(side="left", padx=2)

        # CỘT 2: Trung tâm điều khiển cường hóa (Giữa)
        col_ctrl = tk.Frame(main, bg=THEME["bg_card"], padx=12, pady=10, relief="flat", bd=1)
        col_ctrl.pack(side="left", fill="both", expand=True, padx=(0, 8))

        # Hộp hiển thị lựa chọn hiện tại (Target & Material Banner)
        banner = tk.Frame(col_ctrl, bg=THEME["bg_dark"], padx=10, pady=8, relief="flat")
        banner.pack(fill="x", pady=(0, 8))

        row_t = tk.Frame(banner, bg=THEME["bg_dark"])
        row_t.pack(fill="x", pady=2)
        tk.Label(row_t, text="🎯 TRANG BỊ MỤC TIÊU:", bg=THEME["bg_dark"], fg=THEME["mauve"], font=("Segoe UI", 9, "bold")).pack(side="left")
        self.lbl_curr_equip = tk.Label(row_t, text="Ô 3: Chưa chọn", bg=THEME["bg_dark"], fg=THEME["text_main"], font=("Segoe UI", 9, "bold"))
        self.lbl_curr_equip.pack(side="left", padx=8)

        row_m = tk.Frame(banner, bg=THEME["bg_dark"])
        row_m.pack(fill="x", pady=2)
        tk.Label(row_m, text="💎 CUỘN / NGỌC ÉP :", bg=THEME["bg_dark"], fg=THEME["green"], font=("Segoe UI", 9, "bold")).pack(side="left")
        self.lbl_curr_material = tk.Label(row_m, text="Chưa chọn", bg=THEME["bg_dark"], fg=THEME["text_main"], font=("Segoe UI", 9, "bold"))
        self.lbl_curr_material.pack(side="left", padx=8)

        # Notebook chứa 3 chế độ: Cường Hóa 1-Click | Tự Động Batch | Kịch Bản Combo
        self.notebook = ttk.Notebook(col_ctrl)
        self.notebook.pack(fill="both", expand=True)

        self.tab_single = tk.Frame(self.notebook, bg=THEME["bg_card"], padx=10, pady=12)
        self.tab_auto = tk.Frame(self.notebook, bg=THEME["bg_card"], padx=10, pady=12)
        self.tab_combo = tk.Frame(self.notebook, bg=THEME["bg_card"], padx=10, pady=12)

        self.notebook.add(self.tab_single, text="⚡ CƯỜNG HÓA 1 LẦN")
        self.notebook.add(self.tab_auto, text="🔄 TỰ ĐỘNG LIÊN TỤC")
        self.notebook.add(self.tab_combo, text="📜 KỊCH BẢN COMBO")

        self.build_tab_single()
        self.build_tab_auto()
        self.build_tab_combo()

        # CỘT 3: Nhật ký thời gian thực & Thống kê (Phải)
        col_log = tk.Frame(main, bg=THEME["bg_card"], padx=10, pady=10, relief="flat", bd=1)
        col_log.pack(side="right", fill="both", expand=True)

        # Thống kê nhanh
        stat_bar = tk.Frame(col_log, bg=THEME["bg_dark"], padx=8, pady=6)
        stat_bar.pack(fill="x", pady=(0, 6))

        self.lbl_stats = tk.Label(stat_bar, text="📊 Đã thực hiện: 0  |  Thành công: 0  |  Nguyên liệu dùng: 0",
                                  bg=THEME["bg_dark"], fg=THEME["primary"], font=("Segoe UI", 9, "bold"))
        self.lbl_stats.pack(anchor="w")

        # Hộp văn bản Console Log
        log_head = tk.Frame(col_log, bg=THEME["bg_card"])
        log_head.pack(fill="x", pady=(0, 4))
        tk.Label(log_head, text="📜 NHẬT KÝ GÓI TIN THỜI GIAN THỰC", bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 9, "bold")).pack(side="left")

        btn_clear = tk.Button(log_head, text="🧹 Xóa", font=("Segoe UI", 8), bg=THEME["bg_input"], fg=THEME["text_muted"],
                              relief="flat", padx=6, pady=2, command=self.clear_log)
        btn_clear.pack(side="right")

        self.txt_log = tk.Text(col_log, bg=THEME["bg_dark"], fg=THEME["text_main"],
                               font=("Consolas", 9), relief="flat", wrap="none")
        self.txt_log.pack(fill="both", expand=True)

        # Tags màu cho log
        self.txt_log.tag_config("send", foreground=THEME["primary"], font=("Consolas", 9, "bold"))
        self.txt_log.tag_config("recv", foreground=THEME["green"])
        self.txt_log.tag_config("warn", foreground=THEME["yellow"])
        self.txt_log.tag_config("err", foreground=THEME["red"], font=("Consolas", 9, "bold"))
        self.txt_log.tag_config("time", foreground=THEME["text_muted"])

    def create_legend_badge(self, parent, text, fg, bg):
        b = tk.Label(parent, text=text, font=("Segoe UI", 8, "bold"), fg=fg, bg=bg, padx=6, pady=2)
        b.pack(side="left", padx=2)

    # --------------------------------------------------------------------------
    # NỘI DUNG TAB 1: CƯỜNG HÓA 1 LẦN (SINGLE)
    # --------------------------------------------------------------------------
    def build_tab_single(self):
        desc = tk.Label(self.tab_single,
                        text="Thực hiện nâng 1 bước duy nhất bằng Cuộn rèn hoặc Khảm ngọc vào Trang bị mục tiêu.",
                        bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 9), justify="left")
        desc.pack(anchor="w", pady=(0, 16))

        box_action = tk.Frame(self.tab_single, bg=THEME["bg_card"])
        box_action.pack(fill="x", pady=20)

        self.btn_single_forge = tk.Button(box_action, text="⚡ CƯỜNG HÓA NGAY (1-CLICK)",
                                          font=("Segoe UI", 12, "bold"),
                                          bg=THEME["primary"], fg="#11111b",
                                          activebackground=THEME["primary_active"],
                                          relief="flat", padx=20, pady=14, cursor="hand2",
                                          command=self.action_single_forge)
        self.btn_single_forge.pack(fill="x")

        tip = tk.Label(self.tab_single,
                       text="• Nếu chọn Cuộn rèn: Gửi Op 0x17 Sub 0x79 [Cuộn] [TrangBị]\n• Nếu chọn Ngọc khảm: Gửi Op 0x17 Sub 0x7F [TrangBị] [Ngọc]\n• Kết quả trả về ngay trong 1-2 ms!",
                       bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 8), justify="left")
        tip.pack(anchor="w", pady=(15, 0))

    # --------------------------------------------------------------------------
    # NỘI DUNG TAB 2: TỰ ĐỘNG LIÊN TỤC (AUTO BATCH)
    # --------------------------------------------------------------------------
    def build_tab_auto(self):
        desc = tk.Label(self.tab_auto,
                        text="Tự động lặp lại việc cường hóa bằng loại Cuộn/Ngọc đã chọn cho đến khi đạt số lần hoặc hết đồ.",
                        bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 9), justify="left")
        desc.pack(anchor="w", pady=(0, 10))

        # Cấu hình số lần & delay
        cfg_frame = tk.Frame(self.tab_auto, bg=THEME["bg_card"], pady=6)
        cfg_frame.pack(fill="x")

        # Số lần
        r1 = tk.Frame(cfg_frame, bg=THEME["bg_card"])
        r1.pack(fill="x", pady=4)
        tk.Label(r1, text="Số lần nâng:", bg=THEME["bg_card"], fg=THEME["text_main"], font=("Segoe UI", 9, "bold"), width=14, anchor="w").pack(side="left")
        self.sp_repeat_count = tk.Spinbox(r1, from_=1, to=100, width=8, font=("Segoe UI", 10), bg=THEME["bg_input"], fg=THEME["text_main"], relief="flat")
        self.sp_repeat_count.delete(0, "end")
        self.sp_repeat_count.insert(0, "5")
        self.sp_repeat_count.pack(side="left", padx=4)

        self.var_until_empty = tk.BooleanVar(value=False)
        cb_empty = tk.Checkbutton(r1, text="Hoặc nâng đến khi HẾT nguyên liệu", variable=self.var_until_empty,
                                  bg=THEME["bg_card"], fg=THEME["yellow"], selectcolor=THEME["bg_dark"],
                                  activebackground=THEME["bg_card"], font=("Segoe UI", 9))
        cb_empty.pack(side="left", padx=10)

        # Delay
        r2 = tk.Frame(cfg_frame, bg=THEME["bg_card"])
        r2.pack(fill="x", pady=4)
        tk.Label(r2, text="Độ trễ an toàn:", bg=THEME["bg_card"], fg=THEME["text_main"], font=("Segoe UI", 9, "bold"), width=14, anchor="w").pack(side="left")

        self.scale_delay = tk.Scale(r2, from_=200, to=1500, resolution=50, orient="horizontal",
                                    bg=THEME["bg_card"], fg=THEME["primary"], highlightthickness=0,
                                    length=180, font=("Segoe UI", 8))
        self.scale_delay.set(400)
        self.scale_delay.pack(side="left", padx=4)
        tk.Label(r2, text="ms (Mặc định 400ms)", bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 8)).pack(side="left")

        # Nút Bắt đầu / Dừng
        btn_row = tk.Frame(self.tab_auto, bg=THEME["bg_card"], pady=14)
        btn_row.pack(fill="x")

        self.btn_start_auto = tk.Button(btn_row, text="▶ BẮT ĐẦU CƯỜNG HÓA TỰ ĐỘNG",
                                        font=("Segoe UI", 10, "bold"),
                                        bg=THEME["green"], fg="#11111b",
                                        activebackground="#86efac",
                                        relief="flat", padx=14, pady=10, cursor="hand2",
                                        command=self.action_start_auto)
        self.btn_start_auto.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_stop_auto = tk.Button(btn_row, text="⏹ DỪNG NGAY",
                                       font=("Segoe UI", 10, "bold"),
                                       bg=THEME["red"], fg="#ffffff",
                                       activebackground="#f38ba8",
                                       relief="flat", padx=14, pady=10, cursor="hand2",
                                       state="disabled", command=self.action_stop_auto)
        self.btn_stop_auto.pack(side="left", fill="x", expand=True)

    # --------------------------------------------------------------------------
    # NỘI DUNG TAB 3: KỊCH BẢN COMBO (RECIPE / PRESETS)
    # --------------------------------------------------------------------------
    def build_tab_combo(self):
        top_bar = tk.Frame(self.tab_combo, bg=THEME["bg_card"])
        top_bar.pack(fill="x", pady=(0, 6))

        tk.Label(top_bar, text="Danh sách chuỗi bước nâng theo kịch bản combo:",
                 bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 9)).pack(side="left")

        btn_default = tk.Button(top_bar, text="⭐ Tải Combo 7 Bước Chuẩn", font=("Segoe UI", 8, "bold"),
                                bg=THEME["bg_input"], fg=THEME["primary"], relief="flat", padx=6, pady=2,
                                command=self.load_default_combo)
        btn_default.pack(side="right")

        # Treeview danh sách các bước
        cols = ("step", "type", "slot", "name")
        self.tree_combo = ttk.Treeview(self.tab_combo, columns=cols, show="headings", height=6)
        self.tree_combo.heading("step", text="Bước")
        self.tree_combo.heading("type", text="Thao tác")
        self.tree_combo.heading("slot", text="Ô Túi")
        self.tree_combo.heading("name", text="Nguyên Liệu")

        self.tree_combo.column("step", width=50, anchor="center")
        self.tree_combo.column("type", width=90, anchor="center")
        self.tree_combo.column("slot", width=60, anchor="center")
        self.tree_combo.column("name", width=180, anchor="w")
        self.tree_combo.pack(fill="both", expand=True, pady=4)

        # Thanh công cụ combo
        c_bar = tk.Frame(self.tab_combo, bg=THEME["bg_card"], pady=4)
        c_bar.pack(fill="x")

        tk.Button(c_bar, text="+ Thêm từ Ô đang chọn", font=("Segoe UI", 8, "bold"),
                  bg=THEME["bg_input"], fg=THEME["green"], relief="flat", padx=6, pady=3,
                  command=self.combo_add_from_selected).pack(side="left", padx=2)
        tk.Button(c_bar, text="- Xóa bước", font=("Segoe UI", 8),
                  bg=THEME["bg_input"], fg=THEME["red"], relief="flat", padx=6, pady=3,
                  command=self.combo_remove_step).pack(side="left", padx=2)
        tk.Button(c_bar, text="🧹 Xóa hết", font=("Segoe UI", 8),
                  bg=THEME["bg_input"], fg=THEME["text_muted"], relief="flat", padx=6, pady=3,
                  command=self.combo_clear_all).pack(side="left", padx=2)

        # Nút chạy combo
        self.btn_run_combo = tk.Button(self.tab_combo, text="🚀 CHẠY KỊCH BẢN COMBO TOÀN BỘ",
                                       font=("Segoe UI", 10, "bold"),
                                       bg=THEME["mauve"], fg="#11111b",
                                       activebackground="#d5bdfc",
                                       relief="flat", padx=14, pady=8, cursor="hand2",
                                       command=self.action_run_combo)
        self.btn_run_combo.pack(fill="x", pady=(8, 0))

    def load_default_combo(self):
        """Tải mẫu kịch bản combo 7 bước chuẩn mà người chơi vừa thực hiện thành công."""
        self.combo_steps = [
            {"type": "scroll", "slot": 4, "name": "RedScroll_1 (Ô 4)"},
            {"type": "scroll", "slot": 5, "name": "RedScroll (Ô 5)"},
            {"type": "scroll", "slot": 6, "name": "WhiteForgeScroll (Ô 6)"},
            {"type": "gem",    "slot": 7, "name": "RedSaphire (Khảm Lỗ 1 - Ô 7)"},
            {"type": "gem",    "slot": 8, "name": "OrangeSaphire (Khảm Lỗ 2 - Ô 8)"},
            {"type": "scroll", "slot": 9, "name": "ForgeScroll80_NT (Ô 9)"},
            {"type": "scroll", "slot": 11, "name": "GreyScroll (Ô 11)"},
        ]
        self.refresh_combo_tree()

    def refresh_combo_tree(self):
        if hasattr(self, "tree_combo"):
            for item in self.tree_combo.get_children():
                self.tree_combo.delete(item)
            for idx, step in enumerate(self.combo_steps, 1):
                t_label = "Cuộn rèn" if step["type"] == "scroll" else "Khảm ngọc"
                self.tree_combo.insert("", "end", values=(idx, t_label, f"Ô {step['slot']}", step["name"]))

    def combo_add_from_selected(self):
        if not self.selected_material_slot:
            messagebox.showwarning("Chú ý", "Vui lòng click chọn một ô Cuộn rèn hoặc Ngọc trong túi trước!")
            return
        slot = self.selected_material_slot
        info = self.bag_items.get(slot, {})
        code = info.get("code", 0)
        name = self.get_item_name(code) or f"Item_0x{code:04X}"
        m_type = self.classify_item(code, info.get("qty", 1))
        if m_type not in ["scroll", "gem"]:
            m_type = "scroll"
        self.combo_steps.append({"type": m_type, "slot": slot, "name": f"{name} (Ô {slot})"})
        self.refresh_combo_tree()

    def combo_remove_step(self):
        sel = self.tree_combo.selection()
        if sel:
            idx = self.tree_combo.index(sel[0])
            if 0 <= idx < len(self.combo_steps):
                self.combo_steps.pop(idx)
                self.refresh_combo_tree()

    def combo_clear_all(self):
        self.combo_steps.clear()
        self.refresh_combo_tree()

    # --------------------------------------------------------------------------
    # STATUSBAR
    # --------------------------------------------------------------------------
    def create_statusbar(self):
        statusbar = tk.Frame(self.root, bg=THEME["bg_dark"], height=26, padx=12, pady=4)
        statusbar.pack(fill="x", side="bottom")

        self.lbl_status = tk.Label(statusbar, text="Đang khởi tạo...",
                                   bg=THEME["bg_dark"], fg=THEME["text_muted"], font=("Segoe UI", 9))
        self.lbl_status.pack(side="left")

        self.lbl_sock = tk.Label(statusbar, text="Socket: Chưa kết nối",
                                 bg=THEME["bg_dark"], fg=THEME["text_muted"], font=("Segoe UI", 9))
        self.lbl_sock.pack(side="right")

    # --------------------------------------------------------------------------
    # XỬ LÝ SỰ KIỆN TÚI ĐỒ & CHỌN Ô
    # --------------------------------------------------------------------------
    def on_slot_clicked(self, slot: int):
        """Click chuột trái: Đặt làm Trang bị mục tiêu"""
        self.selected_equip_slot = slot
        self.update_selection_banners()
        self.refresh_grid_display()

    def on_slot_right_clicked(self, slot: int):
        """Click chuột phải: Đặt làm Cuộn rèn hoặc Ngọc khảm"""
        if slot in self.bag_items:
            self.selected_material_slot = slot
            self.update_selection_banners()
            self.refresh_grid_display()

    def set_target_from_selected(self):
        if self.selected_material_slot:
            self.selected_equip_slot = self.selected_material_slot
            self.update_selection_banners()
            self.refresh_grid_display()

    def set_material_from_selected(self):
        if self.selected_equip_slot:
            self.selected_material_slot = self.selected_equip_slot
            self.update_selection_banners()
            self.refresh_grid_display()

    def update_selection_banners(self):
        # Banner Trang bị
        if self.selected_equip_slot:
            info = self.bag_items.get(self.selected_equip_slot, {})
            code = info.get("code", 0)
            name = self.get_item_name(code) if code else "(Trống)"
            self.lbl_curr_equip.config(text=f"Ô {self.selected_equip_slot}: {name} (0x{code:04X})")
        else:
            self.lbl_curr_equip.config(text="Chưa chọn")

        # Banner Nguyên liệu
        if self.selected_material_slot:
            info = self.bag_items.get(self.selected_material_slot, {})
            code = info.get("code", 0)
            qty = info.get("qty", 0)
            name = self.get_item_name(code) if code else "(Trống)"
            m_type = self.classify_item(code, qty)
            type_str = "Cuộn rèn" if m_type == "scroll" else ("Ngọc khảm" if m_type == "gem" else "Vật phẩm")
            self.lbl_curr_material.config(text=f"Ô {self.selected_material_slot}: {name} (Còn {qty}) — Loại: {type_str}")
        else:
            self.lbl_curr_material.config(text="Chưa chọn (Hãy click chuột phải vào 1 ô)")

    def refresh_grid_display(self):
        for slot in range(1, 51):
            btn = self.slot_buttons.get(slot)
            if not btn:
                continue

            info = self.bag_items.get(slot)
            if not info or info.get("code", 0) == 0 or info.get("qty", 0) == 0:
                btn.config(text=f"#{slot}\nTrống", bg=THEME["slot_empty"], fg=THEME["text_muted"])
                continue

            code = info["code"]
            qty = info["qty"]
            name = self.get_item_name(code) or f"0x{code:04X}"
            short_name = name[:10] + ".." if len(name) > 11 else name

            c_type = self.classify_item(code, qty)

            # Màu nền theo phân loại
            if slot == self.selected_equip_slot:
                bg_color = THEME["mauve_dark"]
                fg_color = THEME["mauve"]
                border_txt = f"#{slot} [🎯]\n{short_name}"
            elif slot == self.selected_material_slot:
                bg_color = THEME["green_dark"]
                fg_color = THEME["green"]
                border_txt = f"#{slot} [💎]\n{short_name} x{qty}"
            elif c_type == "scroll":
                bg_color = THEME["slot_scroll"]
                fg_color = THEME["red"]
                border_txt = f"#{slot} [Cuộn]\n{short_name} x{qty}"
            elif c_type == "gem":
                bg_color = THEME["slot_gem"]
                fg_color = THEME["green"]
                border_txt = f"#{slot} [Ngọc]\n{short_name} x{qty}"
            elif c_type == "equip":
                bg_color = THEME["slot_equip"]
                fg_color = THEME["mauve"]
                border_txt = f"#{slot} [Đồ]\n{short_name}"
            else:
                bg_color = THEME["slot_other"]
                fg_color = THEME["text_main"]
                border_txt = f"#{slot}\n{short_name} x{qty}"

            btn.config(text=border_txt, bg=bg_color, fg=fg_color)

    # --------------------------------------------------------------------------
    # FRIDA KẾT NỐI & QUẢN LÝ TIẾN TRÌNH
    # --------------------------------------------------------------------------
    def refresh_process_list(self):
        if not frida:
            self.lbl_status.config(text="[!] Chưa cài đặt frida (pip install frida)", fg=THEME["red"])
            return

        procs = []
        try:
            device = frida.get_local_device()
            for p in device.enumerate_processes():
                if "alogin" in p.name.lower():
                    procs.append((p.pid, p.name))
        except Exception as e:
            self.lbl_status.config(text=f"[!] Lỗi tìm tiến trình: {e}", fg=THEME["red"])
            return

        if not procs:
            self.cb_procs["values"] = ["Không tìm thấy game alogin*.exe"]
            self.cb_procs.current(0)
            self.lbl_status.config(text="Không tìm thấy game. Hãy mở Wonderland Online!", fg=THEME["yellow"])
            return

        # Sắp xếp ưu tiên alogin-w01
        procs.sort(key=lambda x: 0 if "w01" in x[1].lower() else 1)
        proc_labels = [f"{p[1]} (PID: {p[0]})" for p in procs]
        self.cb_procs["values"] = proc_labels
        self.cb_procs.current(0)

        target_pid, target_name = procs[0]
        self.attach_to_process(target_pid, target_name)

    def on_process_selected(self, event=None):
        val = self.cb_procs.get()
        if "PID:" in val:
            try:
                pid = int(val.split("PID:")[1].replace(")", "").strip())
                name = val.split("(")[0].strip()
                self.attach_to_process(pid, name)
            except Exception:
                pass

    def attach_to_process(self, pid: int, name: str):
        if self.session:
            try:
                self.session.detach()
            except Exception:
                pass

        self.log(f"[*] Đang đính kèm vào {name} (PID {pid})...", "warn")
        try:
            self.session = frida.attach(pid)
            self.script = self.session.create_script(FRIDA_HOOK_JS)
            self.script.on("message", self.on_frida_message)
            self.script.load()

            self.active_pid = pid
            self.active_proc_name = name
            self.lbl_status.config(text=f"Đã đính kèm: {name} (PID {pid})", fg=THEME["green"])
            self.log(f"[+] Kết nối Hook thành công vào {name}!", "recv")

            # Quét túi đồ ngay
            self.action_scan_bag()
        except Exception as e:
            self.lbl_status.config(text=f"[!] Lỗi đính kèm: {e}", fg=THEME["red"])
            self.log(f"[!] Lỗi đính kèm: {e}", "err")

    def action_scan_bag(self):
        if not self.script:
            messagebox.showwarning("Chú ý", "Chưa kết nối tới game!")
            return

        try:
            res = self.script.exports_sync.readbag()
            if res and res.get("success"):
                raw_items = res.get("items", {})
                self.bag_items = {int(k): v for k, v in raw_items.items()}
                self.refresh_grid_display()
                self.update_selection_banners()
                self.log(f"[i] Đã quét túi đồ RAM thành công: {len(self.bag_items)} món trong túi.", "recv")
            else:
                self.log("[!] Quét RAM chưa tìm thấy mảng túi đồ. Hãy mở túi đồ trong game (nhấn I/B) rồi thử lại!", "warn")
        except Exception as e:
            self.log(f"[!] Lỗi khi quét RAM túi đồ: {e}", "err")

    # --------------------------------------------------------------------------
    # NHẬN VÀ PHÂN TÍCH GÓI TIN TỪ GAME
    # --------------------------------------------------------------------------
    def on_frida_message(self, message, raw_data):
        if raw_data:
            self.msg_queue.put((message, raw_data))

    def process_packet_queue(self):
        while not self.msg_queue.empty():
            try:
                msg, raw_data = self.msg_queue.get_nowait()
                payload = msg.get("payload", {})
                dir_name = payload.get("dir", "send")
                sock = payload.get("sock", -1)
                if sock > 0:
                    self.lbl_sock.config(text=f"Socket: {sock} (Online)", fg=THEME["green"])

                dissector = self.c2s_dissector if dir_name == "send" else self.s2c_dissector
                packets = dissector.feed(raw_data)
                for opcode, subcode, data, raw_pkt in packets:
                    self.handle_game_packet(dir_name, opcode, subcode, data)
            except Exception:
                break
        self.root.after(100, self.process_packet_queue)

    def handle_game_packet(self, dir_name, opcode, subcode, data):
        # Bỏ qua Ping
        if opcode == 0x08:
            return

        t_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # S->C Op: 0x17 Sub: 0xD2: Kết quả Cường Hóa Cuộn Rèn
        if dir_name == "recv" and opcode == 0x17 and subcode == 0xD2:
            self.stat_total_ops += 1
            self.stat_success_ops += 1
            equip_slot = data[1] if len(data) > 1 else 0
            hex_data = data.hex()
            self.log(f"[{t_str}] [KẾT QUẢ CUỘN RÈN] Server xác nhận thành công Trang bị Ô {equip_slot} | Hex: {hex_data}", "recv")
            self.update_stats_display()

        # S->C Op: 0x17 Sub: 0xD6: Kết quả Khảm Ngọc / Đá Quý
        elif dir_name == "recv" and opcode == 0x17 and subcode == 0xD6:
            self.stat_total_ops += 1
            self.stat_success_ops += 1
            sock_idx = data[1] if len(data) > 1 else 0
            equip_slot = data[2] if len(data) > 2 else 0
            gem_id = struct.unpack("<H", data[3:5])[0] if len(data) >= 5 else 0
            self.log(f"[{t_str}] [KẾT QUẢ KHẢM NGỌC] Đã khảm thành công vào LỖ {sock_idx} (Trang bị Ô {equip_slot}) | Mã ngọc: 0x{gem_id:04X}", "recv")
            self.update_stats_display()

        # S->C Op: 0x17 Sub: 0x09: Server cập nhật trừ nguyên liệu
        elif dir_name == "recv" and opcode == 0x17 and subcode == 0x09:
            if len(data) >= 2:
                slot = data[0]
                # Cập nhật số lượng trong cache
                if slot in self.bag_items:
                    # Trong packet: data[1] là số lượng trừ, hoặc số lượng còn lại
                    # Quét lại nhẹ nhàng để đồng bộ
                    self.stat_materials_used += 1
                    self.action_scan_bag()
            self.update_stats_display()

    def update_stats_display(self):
        self.lbl_stats.config(text=f"📊 Đã thực hiện: {self.stat_total_ops}  |  Thành công: {self.stat_success_ops}  |  Nguyên liệu dùng: {self.stat_materials_used}")

    # --------------------------------------------------------------------------
    # CƠ CHẾ GỬI LỆNH CƯỜNG HÓA QUA SOCKET
    # --------------------------------------------------------------------------
    def send_forge_scroll(self, scroll_slot: int, equip_slot: int) -> bool:
        """Gửi lệnh cường hóa Cuộn rèn: C->S Op: 0x17 Sub: 0x79 [ScrollSlot] [EquipSlot]"""
        if not self.script:
            return False
        body = bytes([0x17, 0x79, scroll_slot, equip_slot])
        pkt = pack_wlo_packet(body)
        res = self.script.exports_sync.sendraw(pkt.hex())
        t_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        if res and res.get("success"):
            self.log(f"[{t_str}] C->S Cường hóa Cuộn rèn Ô {scroll_slot} -> Trang bị Ô {equip_slot} (Op 0x17 Sub 0x79)", "send")
            return True
        else:
            self.log(f"[{t_str}] [!] Lỗi gửi gói Cuộn rèn: {res.get('error')}", "err")
            return False

    def send_socket_gem(self, gem_slot: int, equip_slot: int) -> bool:
        """Gửi lệnh khảm Ngọc / Đá: C->S Op: 0x17 Sub: 0x7F [EquipSlot] [GemSlot]"""
        if not self.script:
            return False
        # Chú ý thứ tự byte: EquipSlot trước, GemSlot sau
        body = bytes([0x17, 0x7F, equip_slot, gem_slot])
        pkt = pack_wlo_packet(body)
        res = self.script.exports_sync.sendraw(pkt.hex())
        t_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        if res and res.get("success"):
            self.log(f"[{t_str}] C->S Khảm Ngọc Ô {gem_slot} -> Trang bị Ô {equip_slot} (Op 0x17 Sub 0x7F)", "send")
            return True
        else:
            self.log(f"[{t_str}] [!] Lỗi gửi gói Khảm ngọc: {res.get('error')}", "err")
            return False

    # --------------------------------------------------------------------------
    # THAO TÁC CƯỜNG HÓA 1 LẦN (SINGLE STEP)
    # --------------------------------------------------------------------------
    def action_single_forge(self):
        if not self.selected_equip_slot:
            messagebox.showwarning("Chú ý", "Vui lòng click chọn Trang bị mục tiêu trong túi!")
            return
        if not self.selected_material_slot:
            messagebox.showwarning("Chú ý", "Vui lòng click chọn Cuộn rèn hoặc Ngọc trong túi!")
            return

        mat_info = self.bag_items.get(self.selected_material_slot)
        if not mat_info or mat_info.get("qty", 0) <= 0:
            messagebox.showerror("Hết nguyên liệu", f"Ô {self.selected_material_slot} không còn nguyên liệu để nâng!")
            return

        m_type = self.classify_item(mat_info["code"], mat_info["qty"])

        if m_type == "gem":
            self.send_socket_gem(self.selected_material_slot, self.selected_equip_slot)
        else:
            self.send_forge_scroll(self.selected_material_slot, self.selected_equip_slot)

    # --------------------------------------------------------------------------
    # THAO TÁC CƯỜNG HÓA TỰ ĐỘNG (AUTO BATCH)
    # --------------------------------------------------------------------------
    def action_start_auto(self):
        if self.auto_running:
            return
        if not self.selected_equip_slot or not self.selected_material_slot:
            messagebox.showwarning("Chú ý", "Vui lòng chọn cả Trang bị và Cuộn/Ngọc trước khi bắt đầu!")
            return

        try:
            repeats = int(self.sp_repeat_count.get())
        except ValueError:
            repeats = 5

        until_empty = self.var_until_empty.get()
        delay_ms = self.scale_delay.get()

        self.auto_running = True
        self.btn_start_auto.config(state="disabled")
        self.btn_stop_auto.config(state="normal")
        self.btn_single_forge.config(state="disabled")
        self.btn_run_combo.config(state="disabled")

        self.auto_thread = threading.Thread(target=self.auto_forge_worker,
                                            args=(self.selected_material_slot, self.selected_equip_slot, repeats, until_empty, delay_ms),
                                            daemon=True)
        self.auto_thread.start()

    def action_stop_auto(self):
        self.auto_running = False
        self.log("[*] Đang dừng quá trình tự động...", "warn")

    def auto_forge_worker(self, mat_slot: int, equip_slot: int, max_repeats: int, until_empty: bool, delay_ms: int):
        self.log(f"[▶] Bắt đầu Cường Hóa Tự Động: Ô nguyên liệu {mat_slot} -> Ô trang bị {equip_slot} (Delay: {delay_ms}ms)", "warn")

        count = 0
        while self.auto_running:
            # Kiểm tra số lượng còn lại
            info = self.bag_items.get(mat_slot)
            if not info or info.get("qty", 0) <= 0:
                self.log(f"[!] Hết nguyên liệu tại Ô {mat_slot}. Dừng tự động!", "warn")
                break

            m_type = self.classify_item(info["code"], info["qty"])
            if m_type == "gem":
                ok = self.send_socket_gem(mat_slot, equip_slot)
            else:
                ok = self.send_forge_scroll(mat_slot, equip_slot)

            if not ok:
                break

            count += 1
            if not until_empty and count >= max_repeats:
                self.log(f"[+] Hoàn thành đủ {max_repeats} lượt nâng!", "recv")
                break

            time.sleep(delay_ms / 1000.0)

        self.auto_running = False
        self.root.after(0, self.on_auto_finished)

    def on_auto_finished(self):
        self.btn_start_auto.config(state="normal")
        self.btn_stop_auto.config(state="disabled")
        self.btn_single_forge.config(state="normal")
        self.btn_run_combo.config(state="normal")
        self.action_scan_bag()

    # --------------------------------------------------------------------------
    # THAO TÁC CHẠY KỊCH BẢN COMBO
    # --------------------------------------------------------------------------
    def action_run_combo(self):
        if self.auto_running:
            return
        if not self.combo_steps:
            messagebox.showwarning("Chú ý", "Kịch bản combo hiện đang trống!")
            return
        if not self.selected_equip_slot:
            messagebox.showwarning("Chú ý", "Vui lòng chọn Trang bị mục tiêu trước!")
            return

        delay_ms = self.scale_delay.get()
        self.auto_running = True
        self.btn_run_combo.config(state="disabled")
        self.btn_start_auto.config(state="disabled")
        self.btn_stop_auto.config(state="normal")

        thread = threading.Thread(target=self.combo_worker, args=(self.selected_equip_slot, delay_ms), daemon=True)
        thread.start()

    def combo_worker(self, equip_slot: int, delay_ms: int):
        self.log(f"[🚀] Bắt đầu chạy Kịch Bản Combo gồm {len(self.combo_steps)} bước vào Trang bị Ô {equip_slot}...", "warn")

        for idx, step in enumerate(self.combo_steps, 1):
            if not self.auto_running:
                self.log("[!] Người chơi đã bấm dừng kịch bản combo!", "warn")
                break

            s_slot = step["slot"]
            s_type = step["type"]
            s_name = step["name"]

            # Kiểm tra ô túi đồ
            info = self.bag_items.get(s_slot)
            if not info or info.get("qty", 0) <= 0:
                self.log(f"[!] [Bước {idx}/{len(self.combo_steps)}] Ô {s_slot} ({s_name}) đã hết! Bỏ qua hoặc dừng.", "warn")
                continue

            self.log(f"[+] [Bước {idx}/{len(self.combo_steps)}] Đang thực hiện: {s_name}...", "recv")
            if s_type == "gem":
                self.send_socket_gem(s_slot, equip_slot)
            else:
                self.send_forge_scroll(s_slot, equip_slot)

            time.sleep(delay_ms / 1000.0)

        self.auto_running = False
        self.root.after(0, self.on_auto_finished)

    # --------------------------------------------------------------------------
    # CONSOLE LOG HELPER
    # --------------------------------------------------------------------------
    def log(self, text: str, tag: str = "text"):
        self.txt_log.insert("end", text + "\n", tag)
        self.txt_log.see("end")

    def clear_log(self):
        self.txt_log.delete("1.0", "end")

    def on_window_close(self):
        self.auto_running = False
        if self.session:
            try:
                self.session.detach()
            except Exception:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = WLOFastForgeApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
