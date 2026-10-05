#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO AUTO INSTANCE 30009 - QUẢN LÝ PHỤ BẢN 30009 TỰ ĐỘNG
======================================================
Ứng dụng đồ họa tự động hóa 100% quy trình đi Phụ Bản ID 30009 (0x7539):
1. Tự động nhận diện và kết nối Frida Hook tới cửa sổ game (alogin-*.exe).
2. Tự động vào Sảnh Phụ Bản (Lobby), chọn Ải 30009, bấm 'go' và bắt đầu.
3. Vượt qua liên tiếp 5 Ải:
   - Ải 1 (Tiền đồn): Đi tới (1242, 895) -> Menu Option 9 -> Chiến đấu tự động đến khi hết trận.
   - Ải 2: Đi tới (1662, 935) -> Menu Option 8 -> Chiến đấu tự động đến khi hết trận.
   - Ải 3: Đi tới (2382, 1015) -> Menu Option 15 -> Chiến đấu tự động đến khi hết trận.
   - Ải 4: Đi tới (1642, 455) -> Menu Option 13 -> Chiến đấu tự động đến khi hết trận.
   - Ải 5 (Boss): Đi tới (1902, 535) -> Menu Option 14 -> Tiêu diệt Boss đến khi hết trận.
4. Tự động nhận trọn bộ phần thưởng (Nhẫn BronzeRing 0x63FE, Capsule2, vật phẩm).
5. Tự động cắn thuốc hồi phục HP/SP theo ô chỉ định sau mỗi vòng.
6. Lặp lại tự động nhiều vòng liên tục kèm bảng thống kê thời gian thực.
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
from tkinter import ttk, messagebox, scrolledtext

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
# HẰNG SỐ & GIAO DIỆN DARK THEME (CATPPUCCIN MACCHIATO)
# ==============================================================================
THEME = {
    "bg_dark": "#181825",
    "bg_main": "#1e1e2e",
    "bg_card": "#24273a",
    "bg_sub": "#313244",
    "bg_hover": "#45475a",
    "bg_selected": "#585b70",
    "text_main": "#cdd6f4",
    "text_muted": "#a6adc8",
    "primary": "#89b4fa",
    "primary_hover": "#b4befe",
    "green": "#a6e3a1",
    "yellow": "#f9e2af",
    "gold": "#fab387",
    "orange": "#fab387",
    "red": "#f38ba8",
    "cyan": "#89dceb",
    "magenta": "#f5c2e7",
    "purple": "#cba6f7",
    "border": "#45475a",
}

FONT_FAMILY = "Segoe UI"
FONT_TITLE = (FONT_FAMILY, 13, "bold")
FONT_HEADER = (FONT_FAMILY, 10, "bold")
FONT_BODY = (FONT_FAMILY, 9)
FONT_BODY_BOLD = (FONT_FAMILY, 9, "bold")
FONT_MONO = ("Consolas", 9)
FONT_MONO_SMALL = ("Consolas", 8)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SYNC_DIRS = [
    os.path.join(os.path.dirname(SCRIPT_DIR), "WLO"),
    os.path.join(os.path.dirname(SCRIPT_DIR), "WLOI - Eng"),
]

ITEM_DB_FILE = os.path.join(SCRIPT_DIR, "wlo_items_database.json")
ITEM_DB = {}
if os.path.exists(ITEM_DB_FILE):
    try:
        with open(ITEM_DB_FILE, "r", encoding="utf-8") as f:
            ITEM_DB = json.load(f)
    except Exception:
        pass

KNOWN_REWARDS = {
    0x63FE: "💍 Nhẫn Phụ Bản (BronzeRingInstance)",
    0x8561: "💊 Viên Nhộng 2 (Capsule2)",
    0x854C: "📜 Cuộn Giấy (0x854C)",
    0xCBCE: "📦 Gói Vật Phẩm (0xCBCE)",
    0x8620: "🎁 Thưởng Dự Phòng (0x8620)",
}

def get_item_name(code_int):
    if code_int in KNOWN_REWARDS:
        return KNOWN_REWARDS[code_int]
    code_hex = f"0x{code_int:04X}"
    if code_hex in ITEM_DB:
        return ITEM_DB[code_hex].get("name", code_hex)
    return code_hex

# ==============================================================================
# HÀM MÃ HÓA & ĐÓNG GÓI GIAO THỨC WLO
# ==============================================================================
def pack_wlo_packet(body_bytes):
    """Đóng gói Magic Header 0xF4 0x44, uint16 LE Length và XOR 0xAD."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain = header + body_bytes
    return bytes(b ^ 0xAD for b in plain)

def unpack_wlo_stream(raw_bytes, buffer):
    """Giải mã luồng dữ liệu mạng WLO bằng XOR 0xAD và bóc tách gói."""
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

# ==============================================================================
# FRIDA JAVASCRIPT CODE (NATIVE HOOK & PACKET SENDER)
# ==============================================================================
FRIDA_JS = """
var activeSocket = -1;
var isInjected = false;

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
    return activeSocket;
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
                this.buf = args[1];
                this.sock = sock;
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
    if (activeSocket <= 0) scanActiveSocket();
    if (activeSocket <= 0) return {success: false, error: "Chưa tìm thấy active socket"};
    if (!sendFunc) return {success: false, error: "Không tìm thấy send trong ws2_32.dll"};

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

function readBagMemory() {
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
                            candidates.push({ base: base, count: cnt, items: items });
                        }
                    }
                }
            } catch(e) {}
        }
        if (candidates.length > 0) break;
    }

    if (candidates.length === 0) return {success: false, items: {}};
    candidates.sort(function(a, b) {
        if (b.count !== a.count) return b.count - a.count;
        return b.base.compare(a.base);
    });
    return {success: true, items: candidates[0].items};
}

rpc.exports = {
    getsocket: function() { return scanActiveSocket(); },
    sendraw: function(hex) { return doSendRaw(hex); },
    readbag: function() { return readBagMemory(); }
};
"""

# ==============================================================================
# LỚP ĐIỀU KHIỂN CHÍNH CỦA GIAO DIỆN (MAIN APPLICATION)
# ==============================================================================
class WLODungeon30009App:
    def __init__(self, root):
        self.root = root
        self.root.title("WLO AUTO INSTANCE 30009 - QUẢN LÝ PHỤ BẢN TỰ ĐỘNG")
        self.root.geometry("1020x820")
        self.root.minsize(940, 720)
        self.root.configure(bg=THEME["bg_dark"])

        # Biến điều khiển phiên làm việc
        self.frida_session = None
        self.frida_script = None
        self.selected_pid = None
        self.selected_proc_name = ""
        self.active_socket = -1
        self.char_id = None

        # Bộ đệm bóc tách gói tin
        self.c2s_buf = bytearray()
        self.s2c_buf = bytearray()
        self.last_packet_sig = None
        self.last_packet_time = 0

        # Sự kiện máy trạng thái (State Machine Events)
        self.in_combat = False
        self.combat_started_event = threading.Event()
        self.combat_ended_event = threading.Event()
        self.combat_event = self.combat_ended_event  # Tương thích ngược
        self.map_loaded_event = threading.Event()
        self.reward_received_event = threading.Event()

        # Biến điều khiển tiến trình tự động
        self.auto_running = False
        self.stop_requested = False
        self.auto_thread = None

        # Thống kê phần thưởng & lượt chạy
        self.stats_rounds_completed = 0
        self.stats_total_rounds = 1
        self.stats_start_time = None
        self.stats_round_start = None
        self.stats_rewards = {
            0x63FE: 0, # BronzeRingInstance
            0x8561: 0, # Capsule2
            0xCBCE: 0,
            0x854C: 0,
        }

        # Thiết lập giao diện người dùng
        self._setup_styles()
        self._build_ui()

        # Quét danh sách tiến trình lúc mở app
        self.root.after(300, self.action_refresh_processes)

    # --------------------------------------------------------------------------
    # THIẾT KẾ GIAO DIỆN (UI STYLES & BUILD)
    # --------------------------------------------------------------------------
    def _setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.style.configure(".", background=THEME["bg_main"], foreground=THEME["text_main"], font=FONT_BODY)
        self.style.configure("TFrame", background=THEME["bg_main"])
        self.style.configure("Card.TFrame", background=THEME["bg_card"], relief="flat")
        self.style.configure("TLabelframe", background=THEME["bg_card"], foreground=THEME["primary"], relief="groove")
        self.style.configure("TLabelframe.Label", background=THEME["bg_card"], foreground=THEME["primary"], font=FONT_HEADER)

        self.style.configure("TLabel", background=THEME["bg_main"], foreground=THEME["text_main"], font=FONT_BODY)
        self.style.configure("Card.TLabel", background=THEME["bg_card"], foreground=THEME["text_main"], font=FONT_BODY)
        self.style.configure("Muted.TLabel", background=THEME["bg_card"], foreground=THEME["text_muted"], font=FONT_BODY)
        self.style.configure("Title.TLabel", background=THEME["bg_dark"], foreground=THEME["primary"], font=FONT_TITLE)

        self.style.configure("Primary.TButton", background=THEME["primary"], foreground=THEME["bg_dark"], font=FONT_BODY_BOLD, padding=(10, 5))
        self.style.map("Primary.TButton", background=[("active", THEME["primary_hover"])])

        self.style.configure("Start.TButton", background=THEME["green"], foreground=THEME["bg_dark"], font=(FONT_FAMILY, 10, "bold"), padding=(12, 6))
        self.style.map("Start.TButton", background=[("active", "#c3e88d")])

        self.style.configure("Stop.TButton", background=THEME["red"], foreground=THEME["bg_dark"], font=(FONT_FAMILY, 10, "bold"), padding=(12, 6))
        self.style.map("Stop.TButton", background=[("active", "#ff757f")])

        self.style.configure("TCombobox", fieldbackground=THEME["bg_sub"], background=THEME["bg_card"], foreground=THEME["text_main"])

    def _build_ui(self):
        # 1. HEADER BAR
        header_frame = tk.Frame(self.root, bg=THEME["bg_dark"], pady=8, padx=12)
        header_frame.pack(fill="x", side="top")

        lbl_title = tk.Label(header_frame, text="⚡ WLO AUTO PHỤ BẢN 30009 - QUẢN LÝ TỰ ĐỘNG", font=FONT_TITLE, fg=THEME["primary"], bg=THEME["bg_dark"])
        lbl_title.pack(side="left")

        lbl_sub = tk.Label(header_frame, text="Bản quyền Engine Frida v16 | Lộ trình 5 Ải Tự Động", font=FONT_BODY, fg=THEME["text_muted"], bg=THEME["bg_dark"])
        lbl_sub.pack(side="right", padx=5)

        # 2. KHUNG CHỌN TIẾN TRÌNH & TRẠNG THÁI (PROCESS SELECTION)
        proc_frame = tk.LabelFrame(self.root, text="  🖥️ KẾT NỐI TIẾN TRÌNH CLIENT GAME  ", bg=THEME["bg_card"], fg=THEME["primary"], font=FONT_HEADER, padx=10, pady=8)
        proc_frame.pack(fill="x", padx=12, pady=(6, 4))

        tk.Label(proc_frame, text="Chọn Cửa Sổ Game:", bg=THEME["bg_card"], fg=THEME["text_main"]).grid(row=0, column=0, sticky="w", padx=4, pady=2)
        self.combo_procs = ttk.Combobox(proc_frame, state="readonly", width=32, font=FONT_MONO)
        self.combo_procs.grid(row=0, column=1, padx=4, pady=2)

        self.btn_refresh = tk.Button(proc_frame, text="🔄 Làm Mới", bg=THEME["bg_sub"], fg=THEME["text_main"], relief="flat", padx=8, pady=2, command=self.action_refresh_processes)
        self.btn_refresh.grid(row=0, column=2, padx=4, pady=2)

        self.btn_attach = tk.Button(proc_frame, text="⚡ Kết Nối (Attach)", bg=THEME["primary"], fg=THEME["bg_dark"], font=FONT_BODY_BOLD, relief="flat", padx=12, pady=2, command=self.action_toggle_attach)
        self.btn_attach.grid(row=0, column=3, padx=6, pady=2)

        # Trạng thái kết nối
        self.lbl_status_sock = tk.Label(proc_frame, text="● Chưa kết nối", bg=THEME["bg_card"], fg=THEME["red"], font=FONT_BODY_BOLD)
        self.lbl_status_sock.grid(row=0, column=4, sticky="w", padx=12, pady=2)

        self.lbl_char_info = tk.Label(proc_frame, text="Nhân vật: Chưa nhận diện", bg=THEME["bg_card"], fg=THEME["text_muted"])
        self.lbl_char_info.grid(row=0, column=5, sticky="w", padx=6, pady=2)

        # 3. BẢNG THEO DÕI 5 ẢI CHIẾN ĐẤU (STAGE TRACKER CARDS)
        stages_box = tk.LabelFrame(self.root, text="  🗺️ TIẾN ĐỘ 5 ẢI PHỤ BẢN 30009  ", bg=THEME["bg_card"], fg=THEME["primary"], font=FONT_HEADER, padx=8, pady=8)
        stages_box.pack(fill="x", padx=12, pady=4)

        self.stage_cards = []
        stages_data = [
            {"num": 1, "name": "Ải 1: Tiền Đồn", "pos": "(1242, 895)", "opt": "Opt 9", "rounds": "Auto hiệp"},
            {"num": 2, "name": "Ải 2: Cổng Trước", "pos": "(1662, 935)", "opt": "Opt 8", "rounds": "Auto hiệp"},
            {"num": 3, "name": "Ải 3: Sân Sau", "pos": "(2382, 1015)", "opt": "Opt 15", "rounds": "Auto hiệp"},
            {"num": 4, "name": "Ải 4: Hành Lang", "pos": "(1642, 455)", "opt": "Opt 13", "rounds": "Auto hiệp"},
            {"num": 5, "name": "Ải 5: BOSS", "pos": "(1902, 535)", "opt": "Opt 14", "rounds": "Auto Boss"},
        ]

        for i, s in enumerate(stages_data):
            card = tk.Frame(stages_box, bg=THEME["bg_sub"], relief="ridge", bd=1, padx=6, pady=6)
            card.grid(row=0, column=i, sticky="nsew", padx=4, pady=2)
            stages_box.columnconfigure(i, weight=1)

            lbl_name = tk.Label(card, text=s["name"], bg=THEME["bg_sub"], fg=THEME["text_main"], font=FONT_BODY_BOLD)
            lbl_name.pack(anchor="w")

            lbl_subinfo = tk.Label(card, text=f"Tọa độ: {s['pos']}\nMenu: {s['opt']} | {s['rounds']}", bg=THEME["bg_sub"], fg=THEME["text_muted"], font=FONT_MONO_SMALL, justify="left")
            lbl_subinfo.pack(anchor="w", pady=(2, 4))

            lbl_badge = tk.Label(card, text="Chờ...", bg=THEME["bg_card"], fg=THEME["text_muted"], font=FONT_BODY_BOLD, padx=6, pady=2)
            lbl_badge.pack(fill="x")

            self.stage_cards.append({
                "frame": card,
                "badge": lbl_badge,
                "data": s
            })

        # 4. KHUNG CẤU HÌNH & THỐNG KÊ (SPLIT 2 CỘT)
        mid_container = tk.Frame(self.root, bg=THEME["bg_dark"])
        mid_container.pack(fill="x", padx=12, pady=4)
        mid_container.columnconfigure(0, weight=1)
        mid_container.columnconfigure(1, weight=1)

        # CỘT TRÁI: CẤU HÌNH THÔNG MINH
        cfg_box = tk.LabelFrame(mid_container, text="  ⚙️ CẤU HÌNH THÔNG MINH  ", bg=THEME["bg_card"], fg=THEME["primary"], font=FONT_HEADER, padx=10, pady=6)
        cfg_box.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        # Số vòng chạy
        r_grid = 0
        tk.Label(cfg_box, text="Số vòng lặp (Loops):", bg=THEME["bg_card"], fg=THEME["text_main"]).grid(row=r_grid, column=0, sticky="w", pady=3)
        self.spin_loops = tk.Spinbox(cfg_box, from_=1, to=999, width=8, bg=THEME["bg_sub"], fg=THEME["text_main"], font=FONT_BODY_BOLD)
        self.spin_loops.delete(0, "end")
        self.spin_loops.insert(0, "1")
        self.spin_loops.grid(row=r_grid, column=1, sticky="w", padx=6, pady=3)

        tk.Label(cfg_box, text="(1 = Chạy 1 lần, 99 = Cày cuốc)", bg=THEME["bg_card"], fg=THEME["text_muted"], font=FONT_MONO_SMALL).grid(row=r_grid, column=2, sticky="w")

        # Tốc độ di chuyển (Hệ số tăng tốc)
        r_grid += 1
        tk.Label(cfg_box, text="Tốc độ di chuyển:", bg=THEME["bg_card"], fg=THEME["text_main"]).grid(row=r_grid, column=0, sticky="w", pady=3)
        self.combo_move_speed = ttk.Combobox(cfg_box, state="readonly", width=14, font=FONT_BODY_BOLD,
                                              values=["3.0x (Siêu tốc - x3)", "2.0x (Nhanh - x2)", "1.0x (Chuẩn - x1)"])
        self.combo_move_speed.current(0)  # Mặc định 3.0x theo yêu cầu
        self.combo_move_speed.grid(row=r_grid, column=1, sticky="w", padx=6, pady=3)
        tk.Label(cfg_box, text="⚡ Giảm 3 lần delay di chuyển", bg=THEME["bg_card"], fg=THEME["green"], font=FONT_MONO_SMALL).grid(row=r_grid, column=2, sticky="w")

        # Tự động cắn thuốc hồi phục
        r_grid += 1
        self.var_auto_heal = tk.BooleanVar(value=True)
        chk_heal = tk.Checkbutton(cfg_box, text="Tự động cắn thuốc hồi phục", variable=self.var_auto_heal, bg=THEME["bg_card"], fg=THEME["text_main"], selectcolor=THEME["bg_dark"], activebackground=THEME["bg_card"], activeforeground=THEME["primary"])
        chk_heal.grid(row=r_grid, column=0, sticky="w", pady=3)

        heal_frame = tk.Frame(cfg_box, bg=THEME["bg_card"])
        heal_frame.grid(row=r_grid, column=1, columnspan=2, sticky="w")

        tk.Label(heal_frame, text="Ô đồ #:", bg=THEME["bg_card"], fg=THEME["text_main"]).pack(side="left")
        self.spin_heal_slot = tk.Spinbox(heal_frame, from_=1, to=50, width=4, bg=THEME["bg_sub"], fg=THEME["text_main"], font=FONT_BODY_BOLD)
        self.spin_heal_slot.delete(0, "end")
        self.spin_heal_slot.insert(0, "4")
        self.spin_heal_slot.pack(side="left", padx=3)

        tk.Label(heal_frame, text="Số lần:", bg=THEME["bg_card"], fg=THEME["text_main"]).pack(side="left", padx=(6, 0))
        self.spin_heal_count = tk.Spinbox(heal_frame, from_=1, to=5, width=4, bg=THEME["bg_sub"], fg=THEME["text_main"], font=FONT_BODY_BOLD)
        self.spin_heal_count.delete(0, "end")
        self.spin_heal_count.insert(0, "2")
        self.spin_heal_count.pack(side="left", padx=3)

        # Tùy chỉnh chiêu thức (Skill Hex)
        r_grid += 1
        tk.Label(cfg_box, text="Mã chiêu Char:", bg=THEME["bg_card"], fg=THEME["text_main"]).grid(row=r_grid, column=0, sticky="w", pady=3)
        self.entry_char_skill = tk.Entry(cfg_box, width=8, bg=THEME["bg_sub"], fg=THEME["gold"], font=FONT_MONO, insertbackground=THEME["text_main"])
        self.entry_char_skill.insert(0, "1f3b")
        self.entry_char_skill.grid(row=r_grid, column=1, sticky="w", padx=6, pady=3)
        tk.Label(cfg_box, text="1F3B (Hỏa Long Kích)", bg=THEME["bg_card"], fg=THEME["text_muted"], font=FONT_MONO_SMALL).grid(row=r_grid, column=2, sticky="w")

        r_grid += 1
        tk.Label(cfg_box, text="Mã chiêu Pet:", bg=THEME["bg_card"], fg=THEME["text_main"]).grid(row=r_grid, column=0, sticky="w", pady=3)
        self.entry_pet_skill = tk.Entry(cfg_box, width=8, bg=THEME["bg_sub"], fg=THEME["gold"], font=FONT_MONO, insertbackground=THEME["text_main"])
        self.entry_pet_skill.insert(0, "212b")
        self.entry_pet_skill.grid(row=r_grid, column=1, sticky="w", padx=6, pady=3)
        tk.Label(cfg_box, text="212B (Kỹ Năng Quét Pet)", bg=THEME["bg_card"], fg=THEME["text_muted"], font=FONT_MONO_SMALL).grid(row=r_grid, column=2, sticky="w")

        # CỘT PHẢI: BẢNG THỐNG KÊ & PHẦN THƯỞNG (REWARDS MONITOR)
        stats_box = tk.LabelFrame(mid_container, text="  🎁 THỐNG KÊ PHẦN THƯỞNG & VÒNG CHẠY  ", bg=THEME["bg_card"], fg=THEME["primary"], font=FONT_HEADER, padx=10, pady=6)
        stats_box.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        stat_left = tk.Frame(stats_box, bg=THEME["bg_card"])
        stat_left.pack(side="left", fill="both", expand=True)

        self.lbl_stat_rounds = tk.Label(stat_left, text="Tiến độ: Vòng 0 / 1", bg=THEME["bg_card"], fg=THEME["primary"], font=FONT_BODY_BOLD)
        self.lbl_stat_rounds.pack(anchor="w", pady=2)

        self.lbl_stat_time = tk.Label(stat_left, text="Thời gian chạy: 00:00 (TB: --)", bg=THEME["bg_card"], fg=THEME["text_muted"], font=FONT_MONO_SMALL)
        self.lbl_stat_time.pack(anchor="w", pady=2)

        stat_right = tk.Frame(stats_box, bg=THEME["bg_card"])
        stat_right.pack(side="right", fill="both", expand=True)

        self.lbl_stat_ring = tk.Label(stat_right, text="💍 Nhẫn BronzeRing: 0", bg=THEME["bg_card"], fg=THEME["green"], font=FONT_BODY_BOLD)
        self.lbl_stat_ring.pack(anchor="w", pady=1)

        self.lbl_stat_capsule = tk.Label(stat_right, text="💊 Capsule2 (0x8561): 0", bg=THEME["bg_card"], fg=THEME["gold"], font=FONT_BODY)
        self.lbl_stat_capsule.pack(anchor="w", pady=1)

        self.lbl_stat_items = tk.Label(stat_right, text="📦 Vật phẩm khác: 0", bg=THEME["bg_card"], fg=THEME["text_muted"], font=FONT_BODY)
        self.lbl_stat_items.pack(anchor="w", pady=1)

        # 5. THANH ĐIỀU KHIỂN CHÍNH (BIG ACTION BUTTONS)
        ctl_bar = tk.Frame(self.root, bg=THEME["bg_dark"], pady=4)
        ctl_bar.pack(fill="x", padx=12, pady=4)

        self.btn_start = tk.Button(ctl_bar, text="▶  BẮT ĐẦU AUTO PHỤ BẢN 30009", bg=THEME["green"], fg=THEME["bg_dark"], font=(FONT_FAMILY, 11, "bold"), relief="flat", padx=16, pady=6, command=self.action_start_auto)
        self.btn_start.pack(side="left", padx=4)

        self.btn_stop = tk.Button(ctl_bar, text="⏹  DỪNG LẠI (STOP)", bg=THEME["red"], fg=THEME["bg_dark"], font=(FONT_FAMILY, 11, "bold"), relief="flat", padx=16, pady=6, state="disabled", command=self.action_stop_auto)
        self.btn_stop.pack(side="left", padx=4)

        self.btn_lobby = tk.Button(ctl_bar, text="🚪 Vào Sảnh (Lobby)", bg=THEME["bg_sub"], fg=THEME["cyan"], font=FONT_BODY_BOLD, relief="flat", padx=10, pady=6, command=self.action_enter_lobby_manual)
        self.btn_lobby.pack(side="left", padx=4)

        self.btn_urn = tk.Button(ctl_bar, text="🏺 Mở Chiếc Lu", bg=THEME["bg_sub"], fg=THEME["magenta"], font=FONT_BODY_BOLD, relief="flat", padx=10, pady=6, command=self.action_click_urn_manual)
        self.btn_urn.pack(side="left", padx=4)

        self.btn_scan_bag = tk.Button(ctl_bar, text="🎒 Kiểm Tra Túi Đồ", bg=THEME["bg_sub"], fg=THEME["text_main"], font=FONT_BODY, relief="flat", padx=10, pady=6, command=self.action_scan_bag)
        self.btn_scan_bag.pack(side="left", padx=4)

        self.btn_clear_log = tk.Button(ctl_bar, text="🧹 Xóa Log", bg=THEME["bg_sub"], fg=THEME["text_muted"], font=FONT_BODY, relief="flat", padx=8, pady=6, command=self.action_clear_log)
        self.btn_clear_log.pack(side="right", padx=4)

        # 6. NHẬT KÝ THỜI GIAN THỰC (REAL-TIME CONSOLE LOG)
        log_box = tk.LabelFrame(self.root, text="  📜 NHẬT KÝ HOẠT ĐỘNG THỜI GIAN THỰC  ", bg=THEME["bg_card"], fg=THEME["primary"], font=FONT_HEADER, padx=8, pady=6)
        log_box.pack(fill="both", expand=True, padx=12, pady=(2, 10))

        self.txt_log = scrolledtext.ScrolledText(log_box, bg=THEME["bg_dark"], fg=THEME["text_main"], font=FONT_MONO, insertbackground=THEME["text_main"], relief="flat", height=12)
        self.txt_log.pack(fill="both", expand=True)

        # Định nghĩa màu sắc các nhãn tag trong log
        self.txt_log.tag_config("TIME", foreground=THEME["text_muted"])
        self.txt_log.tag_config("INFO", foreground=THEME["text_main"])
        self.txt_log.tag_config("PRIMARY", foreground=THEME["primary"])
        self.txt_log.tag_config("SUCCESS", foreground=THEME["green"])
        self.txt_log.tag_config("WARN", foreground=THEME["yellow"])
        self.txt_log.tag_config("ERROR", foreground=THEME["red"])
        self.txt_log.tag_config("COMBAT", foreground=THEME["orange"])
        self.txt_log.tag_config("STAGE", foreground=THEME["purple"])
        self.txt_log.tag_config("REWARD", foreground=THEME["magenta"])
        self.txt_log.tag_config("WALK", foreground=THEME["cyan"])

        self.log("INFO", "Chào mừng đến với WLO Auto Instance 30009 Manager!")
        self.log("INFO", "Sẵn sàng đính kèm Frida vào client để bắt đầu quy trình.")

    # --------------------------------------------------------------------------
    # GHI LOG THỜI GIAN THỰC (THREAD-SAFE LOGGING)
    # --------------------------------------------------------------------------
    def log(self, tag, message):
        """Ghi dòng nhật ký lên khung văn bản (hỗ trợ gọi từ luồng nền)."""
        def _append():
            ts = datetime.now().strftime("%H:%M:%S")
            self.txt_log.insert("end", f"[{ts}] ", "TIME")
            tag_name = tag.upper()
            if tag_name not in ["TIME", "INFO", "PRIMARY", "SUCCESS", "WARN", "ERROR", "COMBAT", "STAGE", "REWARD", "WALK"]:
                tag_name = "INFO"
            self.txt_log.insert("end", f"{message}\n", tag_name)
            self.txt_log.see("end")

        if threading.current_thread() is threading.main_thread():
            _append()
        else:
            self.root.after(0, _append)

    def action_clear_log(self):
        self.txt_log.delete("1.0", "end")

    # --------------------------------------------------------------------------
    # QUẢN LÝ TIẾN TRÌNH & ĐÍNH KÈM FRIDA (PROCESS & FRIDA ATTACH)
    # --------------------------------------------------------------------------
    def action_refresh_processes(self):
        """Quét toàn bộ tiến trình alogin-*.exe đang chạy."""
        if not frida:
            self.log("ERROR", "Thư viện 'frida' chưa được cài đặt (pip install frida).")
            return

        try:
            dev = frida.get_local_device()
            procs = [p for p in dev.enumerate_processes() if "alogin" in p.name.lower()]
            self.combo_procs["values"] = [f"{p.name} (PID: {p.pid})" for p in procs]

            if procs:
                # Ưu tiên alogin-f02 nếu có
                f02_idx = 0
                for idx, p in enumerate(procs):
                    if "f02" in p.name.lower():
                        f02_idx = idx
                        break
                self.combo_procs.current(f02_idx)
                self.log("SUCCESS", f"Đã tìm thấy {len(procs)} cửa sổ game WLO đang hoạt động.")
            else:
                self.combo_procs.set("")
                self.log("WARN", "Không tìm thấy tiến trình alogin-*.exe nào đang chạy.")
        except Exception as e:
            self.log("ERROR", f"Lỗi khi quét tiến trình game: {e}")

    def action_toggle_attach(self):
        """Bật / Tắt kết nối Frida Hook tới tiến trình đã chọn."""
        if self.frida_session:
            # Ngắt kết nối
            try:
                if self.frida_script:
                    self.frida_script.unload()
                self.frida_session.detach()
            except Exception:
                pass
            self.frida_session = None
            self.frida_script = None
            self.active_socket = -1
            self.btn_attach.config(text="⚡ Kết Nối (Attach)", bg=THEME["primary"])
            self.lbl_status_sock.config(text="● Chưa kết nối", fg=THEME["red"])
            self.log("WARN", f"Đã ngắt kết nối khỏi {self.selected_proc_name}.")
            return

        # Bắt đầu kết nối
        sel = self.combo_procs.get()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Vui lòng chọn cửa sổ game cần kết nối!")
            return

        try:
            pid = int(sel.split("PID:")[1].replace(")", "").strip())
            name = sel.split("(PID:")[0].strip()
            self.selected_pid = pid
            self.selected_proc_name = name

            dev = frida.get_local_device()
            self.frida_session = dev.attach(pid)
            self.frida_script = self.frida_session.create_script(FRIDA_JS)
            self.frida_script.on("message", self._on_frida_message)
            self.frida_script.load()

            # Quét socket
            res_sock = self.frida_script.exports_sync.getsocket()
            self.active_socket = res_sock
            if res_sock > 0:
                self.lbl_status_sock.config(text=f"● Socket: #{res_sock} (Port 6414)", fg=THEME["cyan"])
                self.btn_attach.config(text="🔌 Ngắt Kết Nối", bg=THEME["bg_sub"])
                self.log("SUCCESS", f"Đã đính kèm Frida vào {name} (PID: {pid}) - Socket #{res_sock}!")

                # Dự đoán Char ID từ tên tiến trình
                if "f02" in name.lower():
                    self.char_id = 0x00002EC8
                    self.lbl_char_info.config(text="Nhân vật: alogin-F02 (0x2EC8)")
                elif "f04" in name.lower():
                    self.char_id = 0x00002ECB
                    self.lbl_char_info.config(text="Nhân vật: alogin-F04 (0x2ECB)")
                else:
                    self.lbl_char_info.config(text=f"Nhân vật: {name}")
            else:
                self.lbl_status_sock.config(text="● Chờ socket gửi/nhận", fg=THEME["yellow"])
                self.btn_attach.config(text="🔌 Ngắt Kết Nối", bg=THEME["bg_sub"])
                self.log("WARN", f"Đã đính kèm {name} nhưng chưa có socket mạng active. Socket sẽ tự nhận khi thao tác.")
        except Exception as e:
            self.log("ERROR", f"Không thể đính kèm Frida vào tiến trình: {e}")

    def _on_frida_message(self, message, data):
        """Xử lý gói tin mạng nhận được từ Frida Hook."""
        if message.get("type") != "send" or not data:
            return

        payload = message.get("payload", {})
        direction = payload.get("dir", "")
        sock = payload.get("sock", -1)
        if sock > 0:
            self.active_socket = sock

        buf = self.s2c_buf if direction == "recv" else self.c2s_buf
        packets = unpack_wlo_stream(data, buf)

        now = time.time()
        for opcode, subcode, pdata, pkt_raw in packets:
            # Chống trùng lặp gói tin xuất hiện đồng thời từ 2 hook DLL
            sig = (direction, opcode, subcode, pdata[:8])
            if sig == self.last_packet_sig and (now - self.last_packet_time) < 0.05:
                continue
            self.last_packet_sig = sig
            self.last_packet_time = now

            self._process_game_event(direction, opcode, subcode, pdata)

    def _process_game_event(self, direction, opcode, subcode, data):
        """Phân tích ngữ nghĩa sự kiện game."""
        # 1. Trận đánh: Vào trận / Kết thúc
        if opcode == 0x0B:
            if subcode in (0xFA, 0x02):
                self.in_combat = True
                self.combat_started_event.set()
                self.combat_ended_event.clear()
                self.combat_event.clear()
                self.log("COMBAT", "⚡ [VÀO TRẬN ĐÁNH] Đã nhận tín hiệu bắt đầu trận đấu (Op: 0x0B)!")
            elif subcode == 0x00:
                self.in_combat = False
                self.combat_ended_event.set()
                self.combat_started_event.clear()
                self.combat_event.set()
                self.log("SUCCESS", "🏁 [CHIẾN THẮNG] Trận đánh đã hoàn tất thành công!")

        # 2. Chuyển cảnh / Nạp Map
        elif opcode == 0x16 and subcode == 0x04:
            self.map_loaded_event.set()
            if self.in_combat:
                self.in_combat = False
                self.combat_ended_event.set()
                self.combat_started_event.clear()
                self.combat_event.set()
                self.log("SUCCESS", "🏁 [RỜI TRẬN] Bản đồ mới nạp -> Kết thúc trận đấu!")
            self.log("STAGE", f"🗺️ [NẠP BẢN ĐỒ] Map Data ({len(data)} bytes) hoàn tất!")

        # 3. Nhận phần thưởng phụ bản (Op: 0x17 Sub: 0x06)
        elif opcode == 0x17 and subcode == 0x06:
            self.reward_received_event.set()
            # Bóc tách vật phẩm nhận được: Mỗi slot 4 bytes (Code LE 2B, Qty LE 2B)
            i = 0
            while i + 4 <= len(data):
                code = struct.unpack("<H", data[i:i+2])[0]
                qty = struct.unpack("<H", data[i+2:i+4])[0]
                if code > 0 and qty > 0:
                    item_name = get_item_name(code)
                    self.log("REWARD", f"🎁 [NHẬN THƯỞNG] {item_name} x{qty}!")
                    if code in self.stats_rewards:
                        self.stats_rewards[code] += qty
                    else:
                        self.stats_rewards[0xCBCE] += qty
                i += 4
            self._update_stats_ui()

    def send_wlo_packet(self, body_bytes):
        """Gửi gói tin WLO thô qua Frida rpc.exports.sendraw."""
        if not self.frida_script:
            self.log("ERROR", "Chưa kết nối Frida! Không thể gửi gói tin.")
            return False

        enc = pack_wlo_packet(body_bytes)
        try:
            res = self.frida_script.exports_sync.sendraw(enc.hex())
            if isinstance(res, dict) and not res.get("success"):
                self.log("WARN", f"Gửi gói tin thất bại: {res.get('error')}")
                return False
            return True
        except Exception as e:
            self.log("ERROR", f"Lỗi gọi Frida sendraw: {e}")
            return False

    def action_scan_bag(self):
        """Quét bộ nhớ túi đồ nhân vật hiển thị lên console."""
        if not self.frida_script:
            messagebox.showwarning("Chưa kết nối", "Vui lòng kết nối Frida trước khi quét túi đồ!")
            return

        try:
            res = self.frida_script.exports_sync.readbag()
            if res.get("success"):
                items = res.get("items", {})
                self.log("PRIMARY", f"🎒 [TÚI ĐỒ] Quét thấy {len(items)} vật phẩm đang có trong túi:")
                for slot in sorted([int(k) for k in items.keys()]):
                    it = items[str(slot)]
                    code = it["code"]
                    qty = it["qty"]
                    name = get_item_name(code)
                    self.log("INFO", f"   • Ô #{slot:02d}: {name} (Mã: 0x{code:04X}) x{qty}")
            else:
                self.log("WARN", "Không tìm thấy mảng túi đồ trong bộ nhớ RAM.")
        except Exception as e:
            self.log("ERROR", f"Lỗi quét túi đồ: {e}")

    # --------------------------------------------------------------------------
    # THAO TÁC THỦ CÔNG & TIỆN ÍCH (MANUAL ACTIONS)
    # --------------------------------------------------------------------------
    def action_enter_lobby_manual(self):
        """Bấm nút vào Sảnh Phụ Bản 30009 thủ công."""
        if not self.frida_script:
            messagebox.showwarning("Chưa kết nối", "Vui lòng kết nối Frida trước!")
            return

        def _worker():
            self.log("PRIMARY", "🚪 Đang mở Sảnh Phụ Bản 30009...")
            self.send_wlo_packet(bytes.fromhex("5501"))
            time.sleep(0.8)
            self.send_wlo_packet(bytes.fromhex("5503397500"))
            time.sleep(0.8)
            self.send_wlo_packet(bytes.fromhex("5501"))
            time.sleep(0.8)
            self.send_wlo_packet(bytes.fromhex("0202676f"))
            time.sleep(0.8)
            self.send_wlo_packet(bytes.fromhex("550201"))
            self.log("SUCCESS", "Đã gửi toàn bộ gói tin vào phụ bản 30009!")

        threading.Thread(target=_worker, daemon=True).start()

    def action_click_urn_manual(self):
        """Bấm Chiếc Lu thủ công để nhận thưởng phụ bản (14011300)."""
        if not self.frida_script:
            messagebox.showwarning("Chưa kết nối", "Vui lòng kết nối Frida trước!")
            return

        def _worker():
            self.log("REWARD", "🏺 [CHIẾC LU] Đang bấm Chiếc Lu thủ công (14011300)...")
            self.send_wlo_packet(bytes.fromhex("14011300"))
            time.sleep(0.4)
            self.send_wlo_packet(bytes.fromhex("1406"))
            time.sleep(0.3)
            self.send_wlo_packet(bytes.fromhex("1406"))
            time.sleep(0.5)
            self.send_wlo_packet(bytes.fromhex("20020e"))
            time.sleep(0.3)
            self.send_wlo_packet(bytes.fromhex("0c01"))
            time.sleep(0.2)
            self.send_wlo_packet(bytes.fromhex("1406"))
            time.sleep(0.2)
            self.send_wlo_packet(bytes.fromhex("20020e"))
            time.sleep(0.3)
            self.send_wlo_packet(bytes.fromhex("1736"))
            self.log("SUCCESS", "🏺 Đã gửi chuỗi gói tin nhận thưởng Chiếc Lu!")

        threading.Thread(target=_worker, daemon=True).start()

    def _sleep_interruptible(self, seconds):
        """Tạm dừng có thể bị ngắt ngay lập tức khi người dùng bấm Stop."""
        step = 0.05
        elapsed = 0.0
        while elapsed < seconds:
            if self.stop_requested or not self.auto_running:
                return False
            time.sleep(min(step, seconds - elapsed))
            elapsed += step
        return True

    def _sleep_move(self, seconds):
        """Tạm dừng khi di chuyển bước đi có áp dụng hệ số tốc độ (Mặc định x3)."""
        mult = 3.0
        if hasattr(self, 'combo_move_speed') and self.combo_move_speed:
            speed_text = self.combo_move_speed.get()
            try:
                mult = float(speed_text.split("x")[0].strip())
            except Exception:
                mult = 3.0
        mult = max(0.5, mult)
        # Giảm thời gian chờ di chuyển theo hệ số, tối thiểu 0.2s để đảm bảo mạng mượt
        adjusted_sec = max(0.2, seconds / mult)
        return self._sleep_interruptible(adjusted_sec)

    def _wait_for_combat_start(self, stage_name, timeout=12.0, retry_func=None):
        """
        Kiểm tra và chờ tín hiệu bắt đầu trận đấu (Op: 0x0B Sub: 0xFA / 0x02).
        Định kỳ gửi lại lệnh kích hoạt thoại NPC mỗi 2.0s nếu chưa vào trận.
        """
        self.log("INFO", f"[{stage_name}] ⏳ Đang kiểm tra & chờ tín hiệu bắt đầu trận đấu...")
        start_wait = time.time()
        last_retry = start_wait

        while (time.time() - start_wait) < timeout:
            if self.stop_requested or not self.auto_running:
                return False

            if self.in_combat or self.combat_started_event.is_set():
                self.in_combat = True
                self.combat_ended_event.clear()
                self.log("SUCCESS", f"[{stage_name}] ⚡ Đã nhận tín hiệu bắt đầu trận đấu (in_combat=True)! Bắt đầu ra chiêu...")
                return True

            # Thử gửi lại lệnh thoại định kỳ mỗi 2.0s nếu server chưa vào trận
            now = time.time()
            if retry_func and (now - last_retry) >= 2.0:
                self.log("WARN", f"[{stage_name}] Chưa thấy tín hiệu vào trận sau {now - start_wait:.1f}s, đang gửi lại lệnh thoại NPC...")
                try:
                    retry_func()
                except Exception as e:
                    self.log("ERROR", f"Lỗi gửi lại thoại NPC: {e}")
                last_retry = now

            time.sleep(0.08)

        if self.in_combat or self.combat_started_event.is_set():
            self.in_combat = True
            self.combat_ended_event.clear()
            return True

        self.log("ERROR", f"[{stage_name}] ❌ Quá thời gian ({timeout}s) không nhận được tín hiệu bắt đầu trận đấu!")
        return False

    def _execute_combat_loop(self, card_idx, stage_name, round_plans, char_skill, pet_skill, max_turns=100):
        """
        Vòng lặp ra chiêu chiến đấu tự động:
        Chừng nào chưa nhận được tín hiệu kết thúc combat (self.in_combat == True và not self.combat_ended_event.is_set()),
        thì vẫn tiếp tục gửi tín hiệu ra chiêu cho hiệp tiếp theo, hoàn toàn không phụ thuộc vào số lượng hiệp.
        """
        turn = 1
        while self.in_combat and not self.combat_ended_event.is_set():
            if self.stop_requested or not self.auto_running:
                return False

            if turn > max_turns:
                self.log("WARN", f"[{stage_name}] ⚠️ Đã vượt quá giới hạn an toàn {max_turns} hiệp chiến đấu!")
                break

            # Lấy thông tin mục tiêu và đuôi gói tin cho hiệp hiện tại
            # Nếu số hiệp vượt quá danh sách kế hoạch mẫu, tiếp tục dùng kế hoạch của hiệp cuối cùng
            plan_idx = min(turn - 1, len(round_plans) - 1)
            plan = round_plans[plan_idx]

            target_hex = plan.get("target", "0102")
            pet_tail = plan.get("pet_tail", "000000")
            char_tail = plan.get("char_tail", "000000")
            desc = plan.get("desc", f"Target {target_hex}")

            self._update_card_badge(card_idx, f"Hiệp {turn}...", THEME["orange"])
            self.log("COMBAT", f"[{stage_name}] ⚔️ Ra đòn Hiệp {turn} ({desc})...")

            pkt_pet = bytes.fromhex(f"32010402{target_hex}{pet_skill}{pet_tail}")
            pkt_char = bytes.fromhex(f"32010302{target_hex}{char_skill}{char_tail}")

            self.send_wlo_packet(pkt_pet)
            if not self._sleep_interruptible(0.15):
                return False
            self.send_wlo_packet(pkt_char)

            # Chờ hoạt ảnh của hiệp này và theo dõi tín hiệu kết thúc combat (tối đa ~4.2s mỗi hiệp)
            # Nếu quái chết hoặc nhận được tín hiệu kết thúc combat thì ngắt ngay lập tức
            for _ in range(42):
                if not self._sleep_interruptible(0.1):
                    return False
                if not self.in_combat or self.combat_ended_event.is_set():
                    break

            turn += 1

        # Đảm bảo đồng bộ tín hiệu kết thúc
        self.combat_ended_event.wait(timeout=1.0)
        return True

    # --------------------------------------------------------------------------
    # TIẾN TRÌNH AUTO CHÍNH (THE 6-PHASE STATE MACHINE ENGINE)
    # --------------------------------------------------------------------------
    def action_start_auto(self):
        """Bắt đầu chạy tự động phụ bản theo số vòng cấu hình."""
        if not self.frida_script:
            messagebox.showwarning("Chưa kết nối", "Vui lòng kết nối Frida tới game trước!")
            return

        if self.auto_running:
            return

        try:
            total_loops = int(self.spin_loops.get().strip())
        except ValueError:
            total_loops = 1

        self.stats_total_rounds = total_loops
        self.stats_rounds_completed = 0
        self.stats_start_time = time.time()
        self.auto_running = True
        self.stop_requested = False

        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self._reset_stage_badges()

        self.auto_thread = threading.Thread(target=self._run_auto_loop, daemon=True)
        self.auto_thread.start()

    def action_stop_auto(self):
        """Dừng tiến trình tự động an toàn."""
        if not self.auto_running:
            return
        self.stop_requested = True
        self.log("WARN", "⚠️ Đã nhận lệnh dừng lại! Đang ngắt tiến trình tự động...")
        self.btn_stop.config(state="disabled")

    def _run_auto_loop(self):
        """Vòng lặp chạy nhiều lần phụ bản 30009."""
        total = self.stats_total_rounds
        self.log("PRIMARY", f"🚀 KHỞI ĐỘNG TIẾN TRÌNH AUTO PHỤ BẢN 30009 ({total} VÒNG)")

        for current_round in range(1, total + 1):
            if self.stop_requested:
                break

            self.stats_round_start = time.time()
            self._update_round_label(current_round, total)
            self._reset_stage_badges()
            self.log("STAGE", f"\n=======================================================")
            self.log("STAGE", f"▶ BẮT ĐẦU VÒNG {current_round}/{total}")
            self.log("STAGE", f"=======================================================")

            # Lấy mã chiêu thức tùy chỉnh
            char_skill_hex = self.entry_char_skill.get().strip() or "1f3b"
            pet_skill_hex = self.entry_pet_skill.get().strip() or "212b"

            # ------------------------------------------------------------------
            # GIAI ĐOẠN 0: VÀO SẢNH & NẠP PHỤ BẢN 30009
            # ------------------------------------------------------------------
            self.log("INFO", "[BƯỚC 0] Mở sảnh phụ bản và gửi lệnh bắt đầu...")
            self.map_loaded_event.clear()
            self.send_wlo_packet(bytes.fromhex("5501"))
            if not self._sleep_interruptible(0.8): break
            self.send_wlo_packet(bytes.fromhex("5503397500"))
            if not self._sleep_interruptible(0.8): break
            self.send_wlo_packet(bytes.fromhex("5501"))
            if not self._sleep_interruptible(0.8): break
            self.send_wlo_packet(bytes.fromhex("0202676f"))
            if not self._sleep_interruptible(0.8): break
            self.send_wlo_packet(bytes.fromhex("550201"))

            # Chờ nạp bản đồ phụ bản (Op: 0x16 Sub: 0x04) hoặc timeout 3s
            self.log("INFO", "[BƯỚC 0] Đang chờ nạp bản đồ phụ bản...")
            self.map_loaded_event.wait(timeout=3.5)
            if not self._sleep_interruptible(0.8): break

            # Hộp thoại mở đầu phụ bản
            self.send_wlo_packet(bytes.fromhex("0c01"))
            if not self._sleep_interruptible(0.2): break
            self.send_wlo_packet(bytes.fromhex("1406"))
            if not self._sleep_interruptible(0.2): break
            self.send_wlo_packet(bytes.fromhex("20020a")) # Chọn Option 10
            if not self._sleep_interruptible(0.4): break
            self.send_wlo_packet(bytes.fromhex("1736"))
            if not self._sleep_interruptible(0.3): break
            self.send_wlo_packet(bytes.fromhex("2003")) # Đóng thoại
            if not self._sleep_interruptible(0.6): break

            # ------------------------------------------------------------------
            # GIAI ĐOẠN 1: ẢI 1 (TIỀN ĐỒN - 1 HIỆP)
            # ------------------------------------------------------------------
            if not self._execute_stage_1(char_skill_hex, pet_skill_hex):
                break

            # ------------------------------------------------------------------
            # GIAI ĐOẠN 2: ẢI 2 (2 HIỆP)
            # ------------------------------------------------------------------
            if not self._execute_stage_2(char_skill_hex, pet_skill_hex):
                break

            # ------------------------------------------------------------------
            # GIAI ĐOẠN 3: ẢI 3 (3 HIỆP)
            # ------------------------------------------------------------------
            if not self._execute_stage_3(char_skill_hex, pet_skill_hex):
                break

            # ------------------------------------------------------------------
            # GIAI ĐOẠN 4: ẢI 4 (3 HIỆP)
            # ------------------------------------------------------------------
            if not self._execute_stage_4(char_skill_hex, pet_skill_hex):
                break

            # ------------------------------------------------------------------
            # GIAI ĐOẠN 5: ẢI 5 (BOSS - 3 HIỆP & NHẬN THƯỞNG)
            # ------------------------------------------------------------------
            if not self._execute_stage_5(char_skill_hex, pet_skill_hex):
                break

            # ------------------------------------------------------------------
            # GIAI ĐOẠN 6: HỒI PHỤC HP/SP & CHUẨN BỊ VÒNG TIẾP THEO
            # ------------------------------------------------------------------
            self.stats_rounds_completed += 1
            round_elapsed = time.time() - self.stats_round_start
            self.log("SUCCESS", f"✨ HOÀN TẤT VÒNG {current_round}/{total} TRONG {round_elapsed:.1f} GIÂY!")
            self._update_stats_ui()

            if self.var_auto_heal.get():
                self._execute_auto_heal()

            if current_round < total and not self.stop_requested:
                self.log("INFO", "Nghỉ 2.5 giây trước khi vào vòng tiếp theo...")
                if not self._sleep_interruptible(2.5): break

        self._on_auto_finished()

    # --------------------------------------------------------------------------
    # CHI TIẾT CÁC ẢI CHIẾN ĐẤU (STAGES 1 TO 5)
    # --------------------------------------------------------------------------
    def _execute_stage_1(self, char_skill, pet_skill):
        self._update_card_badge(0, "Đang đi...", THEME["yellow"])
        self.log("WALK", "[ẢI 1] Di chuyển đến tọa độ (1242, 895)...")
        self.send_wlo_packet(bytes.fromhex("060100da047f03b0fa"))
        if not self._sleep_move(1.8): return False

        self._update_card_badge(0, "Đối thoại...", THEME["primary"])
        self.in_combat = False
        self.combat_started_event.clear()
        self.combat_ended_event.clear()

        def _trigger_npc_1():
            self.send_wlo_packet(bytes.fromhex("14010200"))
            time.sleep(0.3)
            self.send_wlo_packet(bytes.fromhex("200209")) # Option 9
            time.sleep(0.3)
            self.send_wlo_packet(bytes.fromhex("1406"))
            time.sleep(0.25)
            self.send_wlo_packet(bytes.fromhex("1406"))

        _trigger_npc_1()

        # KIỂM TRA TÍN HIỆU BẮT ĐẦU TRẬN ĐẤU TRƯỚC KHI TIẾP TỤC
        self._update_card_badge(0, "Chờ vào trận...", THEME["yellow"])
        if not self._wait_for_combat_start("ẢI 1", timeout=12.0, retry_func=_trigger_npc_1):
            self._update_card_badge(0, "Lỗi vào trận", THEME["red"])
            return False

        # VÒNG LẶP RA CHIÊU ĐẾN KHI KẾT THÚC COMBAT
        plans_1 = [
            {"target": "0102", "pet_tail": "d8b300", "char_tail": "8c4b00", "desc": "Hàng 2 Cột 1 (0102)"}
        ]
        if not self._execute_combat_loop(0, "ẢI 1", plans_1, char_skill, pet_skill):
            return False

        self.send_wlo_packet(bytes.fromhex("1406"))
        if not self._sleep_interruptible(0.25): return False
        self.send_wlo_packet(bytes.fromhex("1406"))
        if not self._sleep_interruptible(0.3): return False
        self.send_wlo_packet(bytes.fromhex("2003"))
        if not self._sleep_interruptible(0.5): return False

        self._update_card_badge(0, "Hoàn tất ✓", THEME["green"])
        return True

    def _execute_stage_2(self, char_skill, pet_skill):
        self._update_card_badge(1, "Đang đi...", THEME["yellow"])
        self.log("WALK", "[ẢI 2] Di chuyển chặng 1 đến (1502, 915)...")
        self.send_wlo_packet(bytes.fromhex("060106de059303b0d8"))
        if not self._sleep_move(1.2): return False

        self.log("WALK", "[ẢI 2] Di chuyển chặng 2 đến (1662, 935)...")
        self.send_wlo_packet(bytes.fromhex("0601067e06a703b0d6"))
        if not self._sleep_move(1.5): return False

        self._update_card_badge(1, "Đối thoại...", THEME["primary"])
        self.in_combat = False
        self.combat_started_event.clear()
        self.combat_ended_event.clear()

        def _trigger_npc_2():
            self.send_wlo_packet(bytes.fromhex("14010100"))
            time.sleep(0.3)
            self.send_wlo_packet(bytes.fromhex("200208")) # Option 8
            time.sleep(0.3)
            self.send_wlo_packet(bytes.fromhex("1406"))
            time.sleep(0.25)
            self.send_wlo_packet(bytes.fromhex("1406"))

        _trigger_npc_2()

        # KIỂM TRA TÍN HIỆU BẮT ĐẦU TRẬN ĐẤU TRƯỚC KHI TIẾP TỤC
        self._update_card_badge(1, "Chờ vào trận...", THEME["yellow"])
        if not self._wait_for_combat_start("ẢI 2", timeout=12.0, retry_func=_trigger_npc_2):
            self._update_card_badge(1, "Lỗi vào trận", THEME["red"])
            return False

        # VÒNG LẶP RA CHIÊU ĐẾN KHI KẾT THÚC COMBAT
        plans_2 = [
            {"target": "0102", "pet_tail": "53ae00", "char_tail": "bbbf00", "desc": "Hàng 2 Cột 1 (0102)"},
            {"target": "0203", "pet_tail": "0cc300", "char_tail": "555900", "desc": "Hàng 3 Cột 2 (0203)"},
        ]
        if not self._execute_combat_loop(1, "ẢI 2", plans_2, char_skill, pet_skill):
            return False

        self.send_wlo_packet(bytes.fromhex("1406"))
        if not self._sleep_interruptible(0.25): return False
        self.send_wlo_packet(bytes.fromhex("1406"))
        if not self._sleep_interruptible(0.3): return False
        self.send_wlo_packet(bytes.fromhex("2003"))
        if not self._sleep_interruptible(0.5): return False

        self._update_card_badge(1, "Hoàn tất ✓", THEME["green"])
        return True

    def _execute_stage_3(self, char_skill, pet_skill):
        self._update_card_badge(2, "Đang đi...", THEME["yellow"])
        self.log("WALK", "[ẢI 3] Di chuyển chặng 1-4 đến (2382, 1015)...")
        self.send_wlo_packet(bytes.fromhex("060105aa07f703b0e1"))
        if not self._sleep_move(1.0): return False
        self.send_wlo_packet(bytes.fromhex("0601054a084704b0ed"))
        if not self._sleep_move(1.0): return False
        self.send_wlo_packet(bytes.fromhex("060106d6081f04b0e1"))
        if not self._sleep_move(1.0): return False
        self.send_wlo_packet(bytes.fromhex("0601064e09f703b0e9"))
        if not self._sleep_move(1.5): return False

        self._update_card_badge(2, "Đối thoại...", THEME["primary"])
        self.in_combat = False
        self.combat_started_event.clear()
        self.combat_ended_event.clear()

        def _trigger_npc_3():
            self.send_wlo_packet(bytes.fromhex("14010400"))
            time.sleep(0.3)
            self.send_wlo_packet(bytes.fromhex("20020f")) # Option 15
            time.sleep(0.3)
            self.send_wlo_packet(bytes.fromhex("1406"))
            time.sleep(0.25)
            self.send_wlo_packet(bytes.fromhex("1406"))

        _trigger_npc_3()

        # KIỂM TRA TÍN HIỆU BẮT ĐẦU TRẬN ĐẤU TRƯỚC KHI TIẾP TỤC
        self._update_card_badge(2, "Chờ vào trận...", THEME["yellow"])
        if not self._wait_for_combat_start("ẢI 3", timeout=12.0, retry_func=_trigger_npc_3):
            self._update_card_badge(2, "Lỗi vào trận", THEME["red"])
            return False

        # VÒNG LẶP RA CHIÊU ĐẾN KHI KẾT THÚC COMBAT
        plans_3 = [
            {"target": "0102", "pet_tail": "293900", "char_tail": "4d6900", "desc": "Hàng 2 Cột 1 (0102)"},
            {"target": "0102", "pet_tail": "63bd00", "char_tail": "2f6b00", "desc": "Hàng 2 Cột 1 (0102)"},
            {"target": "0203", "pet_tail": "7ecb00", "char_tail": "046200", "desc": "Hàng 3 Cột 2 (0203)"},
        ]
        if not self._execute_combat_loop(2, "ẢI 3", plans_3, char_skill, pet_skill):
            return False

        self.send_wlo_packet(bytes.fromhex("1406"))
        if not self._sleep_interruptible(0.25): return False
        self.send_wlo_packet(bytes.fromhex("1406"))
        if not self._sleep_interruptible(0.3): return False
        self.send_wlo_packet(bytes.fromhex("2003"))
        if not self._sleep_interruptible(0.5): return False

        self._update_card_badge(2, "Hoàn tất ✓", THEME["green"])
        return True

    def _execute_stage_4(self, char_skill, pet_skill):
        self._update_card_badge(3, "Đang đi...", THEME["yellow"])
        self.log("WALK", "[ẢI 4] Di chuyển chặng 1-5 đến (1642, 455)...")
        self.send_wlo_packet(bytes.fromhex("0601010e08f703b0cd"))
        if not self._sleep_move(1.5): return False
        self.send_wlo_packet(bytes.fromhex("0601005a074303b0f1"))
        if not self._sleep_move(2.2): return False
        self.send_wlo_packet(bytes.fromhex("060100aa077b02b0e8"))
        if not self._sleep_move(1.2): return False
        self.send_wlo_packet(bytes.fromhex("06010132070302b0eb"))
        if not self._sleep_move(1.2): return False
        self.send_wlo_packet(bytes.fromhex("0601016a06c701b0fc"))
        if not self._sleep_move(1.8): return False

        self._update_card_badge(3, "Đối thoại...", THEME["primary"])
        self.in_combat = False
        self.combat_started_event.clear()
        self.combat_ended_event.clear()

        def _trigger_npc_4():
            self.send_wlo_packet(bytes.fromhex("14010500"))
            time.sleep(0.3)
            self.send_wlo_packet(bytes.fromhex("20020d")) # Option 13
            time.sleep(0.3)
            self.send_wlo_packet(bytes.fromhex("1406"))
            time.sleep(0.25)
            self.send_wlo_packet(bytes.fromhex("1406"))

        _trigger_npc_4()

        # KIỂM TRA TÍN HIỆU BẮT ĐẦU TRẬN ĐẤU TRƯỚC KHI TIẾP TỤC
        self._update_card_badge(3, "Chờ vào trận...", THEME["yellow"])
        if not self._wait_for_combat_start("ẢI 4", timeout=12.0, retry_func=_trigger_npc_4):
            self._update_card_badge(3, "Lỗi vào trận", THEME["red"])
            return False

        # VÒNG LẶP RA CHIÊU ĐẾN KHI KẾT THÚC COMBAT
        plans_4 = [
            {"target": "0102", "pet_tail": "117100", "char_tail": "098200", "desc": "Hàng 2 Cột 1 (0102)"},
            {"target": "0104", "pet_tail": "5c7200", "char_tail": "2bab00", "desc": "Hàng 4 Cột 1 (0104)"},
            {"target": "0104", "pet_tail": "6d6a00", "char_tail": "53bd00", "desc": "Hàng 4 Cột 1 (0104)"},
        ]
        if not self._execute_combat_loop(3, "ẢI 4", plans_4, char_skill, pet_skill):
            return False

        self.send_wlo_packet(bytes.fromhex("1406"))
        if not self._sleep_interruptible(0.25): return False
        self.send_wlo_packet(bytes.fromhex("1406"))
        if not self._sleep_interruptible(0.3): return False
        self.send_wlo_packet(bytes.fromhex("2003"))
        if not self._sleep_interruptible(0.5): return False

        self._update_card_badge(3, "Hoàn tất ✓", THEME["green"])
        return True

    def _execute_stage_5(self, char_skill, pet_skill):
        self._update_card_badge(4, "Đang đi...", THEME["yellow"])
        self.log("WALK", "[ẢI 5 - BOSS] Tiến vào phòng Boss (1902, 535)...")
        self.send_wlo_packet(bytes.fromhex("0601066e071702b0e4"))
        if not self._sleep_move(2.2): return False

        self._update_card_badge(4, "Khiêu chiến...", THEME["primary"])
        self.in_combat = False
        self.combat_started_event.clear()
        self.combat_ended_event.clear()

        def _trigger_npc_5():
            self.send_wlo_packet(bytes.fromhex("14010600"))
            time.sleep(0.3)
            self.send_wlo_packet(bytes.fromhex("20020e")) # Option 14
            time.sleep(0.3)
            self.send_wlo_packet(bytes.fromhex("1406"))
            time.sleep(0.25)
            self.send_wlo_packet(bytes.fromhex("1406"))

        _trigger_npc_5()

        # KIỂM TRA TÍN HIỆU BẮT ĐẦU TRẬN ĐẤU TRƯỚC KHI TIẾP TỤC
        self._update_card_badge(4, "Chờ vào trận...", THEME["yellow"])
        if not self._wait_for_combat_start("ẢI 5 - BOSS", timeout=12.0, retry_func=_trigger_npc_5):
            self._update_card_badge(4, "Lỗi vào trận", THEME["red"])
            return False

        # VÒNG LẶP RA CHIÊU ĐẾN KHI KẾT THÚC COMBAT
        plans_5 = [
            {"target": "0101", "pet_tail": "5a2f00", "char_tail": "a97200", "desc": "Boss Hàng 1 Cột 1 (0101)"},
            {"target": "0101", "pet_tail": "407500", "char_tail": "183d00", "desc": "Boss Hàng 1 Cột 1 (0101)"},
            {"target": "0101", "pet_tail": "838200", "char_tail": "adf600", "desc": "Dứt điểm Boss (0101)"},
        ]
        if not self._execute_combat_loop(4, "ẢI 5 - BOSS", plans_5, char_skill, pet_skill):
            return False

        self.log("SUCCESS", "[ẢI 5 - BOSS] 🏁 Đã tiêu diệt Boss cuối thành công!")
        self._update_card_badge(4, "Đóng thoại...", THEME["yellow"])

        # 1. Đóng hộp thoại kết quả trận đấu (gửi 3 lần 1406 như log thực tế)
        for _ in range(3):
            self.send_wlo_packet(bytes.fromhex("1406"))
            if not self._sleep_interruptible(0.35): return False

        if not self._sleep_interruptible(0.8): return False

        # 2. Bấm vào "Chiếc Lu" (14011300) để nhận phần thưởng phụ bản
        self._update_card_badge(4, "Bấm Chiếc Lu...", THEME["magenta"])
        self.log("REWARD", "🏺 [CHIẾC LU] Đang bấm vào Chiếc Lu (14011300) để nhận thưởng phụ bản...")
        self.reward_received_event.clear()
        self.map_loaded_event.clear()

        # Thử bấm Chiếc Lu (tối đa 3 lượt nếu mạng delay chưa thấy quà rơi)
        for attempt in range(1, 4):
            self.send_wlo_packet(bytes.fromhex("14011300"))
            if not self._sleep_interruptible(0.4): return False
            self.send_wlo_packet(bytes.fromhex("1406"))
            if not self._sleep_interruptible(0.3): return False
            self.send_wlo_packet(bytes.fromhex("1406"))

            # Chờ gói phần thưởng S->C Op: 0x17 Sub: 0x06 (BronzeRing, Capsule...)
            if self.reward_received_event.wait(timeout=2.5):
                self.log("SUCCESS", f"🏺 [CHIẾC LU] Đã nhận phần thưởng thành công từ Chiếc Lu (Lượt {attempt})!")
                break
            else:
                self.log("WARN", f"🏺 [CHIẾC LU] Chưa nhận được tín hiệu quà rơi, đang thử bấm lại Chiếc Lu lần {attempt + 1}...")

        # 3. Game tự động đưa nhân vật rời khỏi Instance (Map Warp Out - Op: 0x16 Sub: 0x04)
        self.log("INFO", "🚪 [TỰ ĐỘNG THOÁT] Đang chờ game tự động đưa nhân vật rời khỏi phụ bản...")
        self.map_loaded_event.wait(timeout=4.0)
        if not self._sleep_interruptible(0.8): return False

        # 4. Gửi chuỗi đồng bộ cảnh sau khi ra ngoài sảnh map
        self.send_wlo_packet(bytes.fromhex("20020e"))
        if not self._sleep_interruptible(0.3): return False
        self.send_wlo_packet(bytes.fromhex("0c01"))
        if not self._sleep_interruptible(0.2): return False
        self.send_wlo_packet(bytes.fromhex("1406"))
        if not self._sleep_interruptible(0.2): return False
        self.send_wlo_packet(bytes.fromhex("20020e"))
        if not self._sleep_interruptible(0.4): return False
        self.send_wlo_packet(bytes.fromhex("1736"))
        if not self._sleep_interruptible(1.2): return False

        self.log("SUCCESS", "✨ [HOÀN TẤT PHỤ BẢN] Đã nhận trọn vẹn quà từ Chiếc Lu và ra ngoài sảnh thành công!")
        self._update_card_badge(4, "Thắng & Nhận Lu ✓", THEME["green"])
        return True

    def _execute_auto_heal(self):
        """Tự động dùng thuốc hồi HP/SP sau khi kết thúc ải."""
        try:
            slot_num = int(self.spin_heal_slot.get().strip())
            count = int(self.spin_heal_count.get().strip())
        except ValueError:
            slot_num = 4
            count = 2

        slot_hex = f"{slot_num:02x}"
        self.log("PRIMARY", f"💊 [HỒI PHỤC] Đang cắn thuốc tại Ô #{slot_num:02d} ({count} lần)...")

        for _ in range(count):
            if self.stop_requested: break
            # Cắn thuốc cho Nhân vật (0000)
            self.send_wlo_packet(bytes.fromhex(f"170f{slot_hex}010000"))
            self._sleep_interruptible(0.3)
            # Cắn thuốc cho Pet (0300)
            self.send_wlo_packet(bytes.fromhex(f"170f{slot_hex}010300"))
            self._sleep_interruptible(0.3)

    # --------------------------------------------------------------------------
    # CẬP NHẬT GIAO DIỆN & TRẠNG THÁI (UI UPDATE HELPERS)
    # --------------------------------------------------------------------------
    def _update_card_badge(self, index, text, color):
        def _update():
            if 0 <= index < len(self.stage_cards):
                card = self.stage_cards[index]
                card["badge"].config(text=text, fg=color)
        self.root.after(0, _update)

    def _reset_stage_badges(self):
        def _reset():
            for card in self.stage_cards:
                card["badge"].config(text="Chờ...", fg=THEME["text_muted"])
        self.root.after(0, _reset)

    def _update_round_label(self, current, total):
        def _update():
            self.lbl_stat_rounds.config(text=f"Tiến độ: Vòng {current} / {total}")
        self.root.after(0, _update)

    def _update_stats_ui(self):
        def _update():
            elapsed = time.time() - self.stats_start_time if self.stats_start_time else 0
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            avg = (elapsed / self.stats_rounds_completed) if self.stats_rounds_completed > 0 else 0
            avg_m = int(avg // 60)
            avg_s = int(avg % 60)

            self.lbl_stat_time.config(text=f"Thời gian: {mins:02d}:{secs:02d} (TB: {avg_m:02d}:{avg_s:02d}/vòng)")
            self.lbl_stat_ring.config(text=f"💍 Nhẫn BronzeRing: {self.stats_rewards.get(0x63FE, 0)}")
            self.lbl_stat_capsule.config(text=f"💊 Capsule2: {self.stats_rewards.get(0x8561, 0)}")
            other = self.stats_rewards.get(0xCBCE, 0) + self.stats_rewards.get(0x854C, 0)
            self.lbl_stat_items.config(text=f"📦 Đạo cụ khác: {other}")
        self.root.after(0, _update)

    def _on_auto_finished(self):
        def _finish():
            self.auto_running = False
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")
            self.log("PRIMARY", f"🏁 Phiên Auto Phụ Bản 30009 đã dừng lại. Tổng cộng hoàn tất: {self.stats_rounds_completed} vòng.")
        self.root.after(0, _finish)


# ==============================================================================
# HÀM KHỞI CHẠY CHÍNH (ENTRY POINT)
# ==============================================================================
def main():
    root = tk.Tk()
    app = WLODungeon30009App(root)

    def on_closing():
        if app.auto_running:
            if messagebox.askyesno("Đang chạy", "Tiến trình Auto đang hoạt động. Bạn có chắc muốn dừng và thoát?"):
                app.action_stop_auto()
                root.destroy()
        else:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
