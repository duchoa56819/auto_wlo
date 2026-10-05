#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO ITEM NAMER & DISCARD MANAGER GUI
=====================================
Giao diện trực quan quản lý Túi Đồ 50 Ô, Đặt Tên Vật Phẩm & Cấu Hình Vứt Đồ:
1. Tự động nhận diện mọi tiến trình alogin*.exe đang mở (alogin-W04, W03, F04, Wi01...).
2. Quét siêu tốc 50 ô túi đồ trực tiếp từ RAM game (0.05s) - KHÔNG CẦN RELOG!
3. Lưới 50 ô trực quan với mã màu phân loại:
   - Xanh lá: Ô có đồ ĐÃ ĐẶT TÊN
   - Vàng đất: Ô có đồ CHƯA ĐẶT TÊN (nổi bật để điền)
   - Đỏ viền: Ô có đồ trong DANH SÁCH VỨT (Blacklist)
   - Tối: Ô trống
4. Nhấp vào bất kỳ ô nào:
   - Điền tên vật phẩm -> Bấm [Enter] hoặc [Lưu & Ô Tiếp Theo] để tự động nhảy sang ô chưa có tên!
   - Đánh dấu / Hủy đánh dấu món này vào Blacklist Vứt.
   - Nút [🗑️ Vứt Ngay Món Này]: Gửi gói tin vứt trực tiếp trong game (Op: 0x17 Sub: 0x03 & 0x7C).
   - Nút [🧹 Vứt Sạch Mọi Món Rác Trong Túi]: Quét và dọn sạch toàn bộ món Blacklist trong 1 cú click!
5. Quản lý toàn diện Cơ sở dữ liệu vật phẩm (wlo_items_database.json) & Cấu hình vứt đồ (wlo_auto_discard_config.json).
6. Tự động đồng bộ 100% dữ liệu sang cả 3 thư mục WLOI, WLO, WLOI - Eng.
"""

import os
import sys
import time
import json
import glob
import struct
import threading
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

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
# BẢNG MÀU DARK THEME (CATPPUCCIN MOCHA / NAVY)
# ==============================================================================
THEME = {
    "bg_dark": "#11111b",       # Nền sâu nhất (Header, Statusbar, Grid)
    "bg_main": "#181825",       # Nền chính cửa sổ
    "bg_card": "#1e1e2e",       # Nền các card, container
    "bg_input": "#313244",      # Nền ô nhập liệu
    "text_main": "#cdd6f4",     # Chữ sáng chính
    "text_muted": "#a6adc8",    # Chữ ghi chú xám
    "border": "#45475a",        # Viền chia khung
    "primary": "#89b4fa",       # Xanh dương điểm nhấn
    "primary_active": "#b4befe",
    "green": "#a6e3a1",         # Đã đặt tên / thành công
    "yellow": "#f9e2af",        # Cảnh báo / Chưa đặt tên
    "orange": "#fab387",        # Cần chú ý
    "red": "#f38ba8",           # Blacklist / Xóa / Vứt
    "cyan": "#89dceb",          # Mã Hex
    "magenta": "#f5c2e7",       # Đặc biệt
    "slot_empty": "#161622",    # Ô trống
    "slot_named": "#162e24",    # Ô có đồ đã đặt tên (nền xanh rêu)
    "slot_unnamed": "#382d12",  # Ô có đồ chưa đặt tên (nền vàng đất nổi bật)
    "slot_trash": "#38171f",    # Ô nằm trong Blacklist vứt (nền đỏ đậm)
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "wlo_items_database.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "wlo_auto_discard_config.json")

SYNC_DIRS = [
    os.path.join(os.path.dirname(SCRIPT_DIR), "WLO"),
    os.path.join(os.path.dirname(SCRIPT_DIR), "WLOI - Eng"),
]

def normalize_code_hex(code):
    """Chuẩn hóa mã vật phẩm về dạng chuẩn 0xXXXX (Hex in HOA)."""
    if code is None:
        return ""
    if isinstance(code, int):
        return f"0x{code:04X}"
    s = str(code).strip()
    if s.lower().startswith("0x"):
        s = s[2:]
    try:
        val = int(s, 16)
        return f"0x{val:04X}"
    except ValueError:
        return f"0x{s.upper()}"

def pack_wlo_packet(body_bytes: bytes) -> bytes:
    """Đóng gói Magic Header 0xF4 0x44, uint16 LE Length và XOR 0xAD."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain = header + body_bytes
    return bytes(b ^ 0xAD for b in plain)


# ==============================================================================
# FRIDA HOOK JAVASCRIPT
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
            }
        });
    } catch(e) {}
}

hookRecv('wsock32.dll');
hookRecv('ws2_32.dll');
hookSend('wsock32.dll');
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

    // Bộ quét RAM phổ quát thông minh: Loại bỏ 100% Tủ Đồ Lều và Snapshot cũ
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

    // Sắp xếp các candidates hợp lệ theo địa chỉ bộ nhớ giảm dần:
    // Vùng nhớ mới nhất trong Heap (được cấp phát sau cùng) là Active Buffer hiện tại
    candidates.sort(function(a, b) {
        return b.base.compare(a.base);
    });

    var best = candidates[0];
    cachedBagBase = best.base;
    return {success: true, cached: false, items: best.items};
}

function doSendRaw(hexBytes) {
    if (activeSocket <= 0) scanActiveSocket();
    if (activeSocket <= 0) return {success: false, error: 'No active socket'};
    if (!sendFunc) return {success: false, error: 'No send function'};

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


class WLOItemNamerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🏷️ WLO Item Namer & Discard Manager - Quản Lý Túi Đồ & Đặt Tên Vật Phẩm")
        self.root.geometry("1280x860")
        self.root.minsize(1120, 750)
        self.root.configure(bg=THEME["bg_main"])

        # Quản lý kết nối Frida Client
        self.session = None
        self.script = None
        self.active_pid = None
        self.active_proc_name = ""

        # Dữ liệu
        self.database = {}
        self.discard_config = {"auto_discard_enabled": True, "blacklist": {}}
        self.current_bag_slots = {}  # slot_num (1..50) -> {"code_hex": "...", "code_dec": ..., "qty": ..., "name": "..."}
        self.selected_slot = None

        self.setup_styles()
        self.load_database()
        self.load_discard_config()

        self.create_header()
        self.create_main_content()
        self.create_statusbar()

        # Quét và tự động đính kèm client đang chạy
        self.refresh_process_list()
        self.update_status_counts()

        self.root.protocol("WM_DELETE_WINDOW", self.on_window_close)

    def on_window_close(self):
        if self.session:
            try:
                self.session.detach()
            except Exception:
                pass
        self.root.destroy()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TNotebook", background=THEME["bg_main"], borderwidth=0)
        style.configure("TNotebook.Tab", background=THEME["bg_card"], foreground=THEME["text_muted"],
                        font=("Segoe UI", 10, "bold"), padding=[16, 8])
        style.map("TNotebook.Tab",
                  background=[("selected", THEME["bg_dark"])],
                  foreground=[("selected", THEME["primary"])])

        style.configure("Treeview",
                        background=THEME["bg_input"],
                        foreground=THEME["text_main"],
                        fieldbackground=THEME["bg_input"],
                        font=("Segoe UI", 10),
                        rowheight=28)
        style.map("Treeview", background=[("selected", THEME["primary"])], foreground=[("selected", "#11111b")])
        style.configure("Treeview.Heading",
                        background=THEME["bg_card"],
                        foreground=THEME["primary"],
                        font=("Segoe UI", 10, "bold"),
                        padding=[8, 6])

    def load_database(self):
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    self.database = json.load(f)
            except Exception:
                self.database = {}
        else:
            self.database = {}

    def save_database(self):
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(self.database, f, indent=2, ensure_ascii=False)

            for s_dir in SYNC_DIRS:
                if os.path.isdir(s_dir):
                    t_file = os.path.join(s_dir, "wlo_items_database.json")
                    try:
                        with open(t_file, "w", encoding="utf-8") as f:
                            json.dump(self.database, f, indent=2, ensure_ascii=False)
                    except Exception:
                        pass
            self.update_status_counts()
            return True
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể lưu database: {e}")
            return False

    def load_discard_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.discard_config = json.load(f)
            except Exception:
                pass
        if "blacklist" not in self.discard_config:
            self.discard_config["blacklist"] = {}

    def save_discard_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.discard_config, f, indent=2, ensure_ascii=False)

            for s_dir in SYNC_DIRS:
                if os.path.isdir(s_dir):
                    t_file = os.path.join(s_dir, "wlo_auto_discard_config.json")
                    try:
                        with open(t_file, "w", encoding="utf-8") as f:
                            json.dump(self.discard_config, f, indent=2, ensure_ascii=False)
                    except Exception:
                        pass
            return True
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể lưu cấu hình Blacklist: {e}")
            return False

    def is_in_blacklist(self, hex_code: str) -> bool:
        norm = normalize_code_hex(hex_code)
        bl = self.discard_config.get("blacklist", {})
        return norm in bl and bl[norm].get("enabled", True)

    # --------------------------------------------------------------------------
    # HEADER: CHỌN CỬA SỔ CLIENT & NÚT THAO TÁC NHANH
    # --------------------------------------------------------------------------
    def create_header(self):
        header = tk.Frame(self.root, bg=THEME["bg_dark"], height=70, padx=16, pady=10)
        header.pack(fill="x")

        # Cột trái: Tiêu đề
        left_box = tk.Frame(header, bg=THEME["bg_dark"])
        left_box.pack(side="left")

        lbl_title = tk.Label(left_box, text="🏷️ WLO ITEM NAMER & DISCARD MANAGER",
                             bg=THEME["bg_dark"], fg=THEME["primary"], font=("Segoe UI", 13, "bold"))
        lbl_title.pack(anchor="w")

        lbl_sub = tk.Label(left_box, text="Quét RAM 50 ô trực tiếp • Đặt tên tiếng Việt • Chọn món vứt ngay trong game",
                           bg=THEME["bg_dark"], fg=THEME["text_muted"], font=("Segoe UI", 9))
        lbl_sub.pack(anchor="w")

        # Cột phải: Chọn tiến trình & Các nút thao tác nhanh
        right_box = tk.Frame(header, bg=THEME["bg_dark"])
        right_box.pack(side="right")

        lbl_sel = tk.Label(right_box, text="Cửa sổ Game:", bg=THEME["bg_dark"], fg=THEME["text_muted"], font=("Segoe UI", 9, "bold"))
        lbl_sel.pack(side="left", padx=(0, 6))

        self.cb_procs = ttk.Combobox(right_box, state="readonly", width=22, font=("Segoe UI", 9))
        self.cb_procs.pack(side="left", padx=(0, 8))
        self.cb_procs.bind("<<ComboboxSelected>>", self.on_process_selected)

        btn_rescan_proc = tk.Button(right_box, text="🔍 Tìm Game", font=("Segoe UI", 9, "bold"),
                                    bg=THEME["bg_input"], fg=THEME["primary"], relief="flat", padx=10, pady=4,
                                    cursor="hand2", command=self.refresh_process_list)
        btn_rescan_proc.pack(side="left", padx=(0, 8))

        btn_scan_ram = tk.Button(right_box, text="⚡ QUÉT TÚI ĐỒ TỪ RAM (0.05s)", font=("Segoe UI", 10, "bold"),
                                 bg=THEME["green"], fg="#11111b", activebackground="#86efac", relief="flat", padx=14, pady=5,
                                 cursor="hand2", command=self.action_scan_bag_from_ram)
        btn_scan_ram.pack(side="left", padx=(0, 8))

        btn_sweep_trash = tk.Button(right_box, text="🧹 VỨT CÁC MÓN BLACKLIST", font=("Segoe UI", 10, "bold"),
                                    bg=THEME["red"], fg="#ffffff", activebackground="#f38ba8", relief="flat", padx=14, pady=5,
                                    cursor="hand2", command=self.action_sweep_all_blacklist_items)
        btn_sweep_trash.pack(side="left")

    def refresh_process_list(self):
        """Tìm tất cả tiến trình game alogin*.exe đang chạy trên máy"""
        procs = []
        # 1. Quét qua Frida
        if frida:
            try:
                device = frida.get_local_device()
                for p in device.enumerate_processes():
                    name_l = p.name.lower()
                    if "alogin" in name_l:
                        procs.append((p.name, p.pid))
            except Exception:
                pass

        # 2. Quét qua psutil (Dự phòng)
        if not procs:
            try:
                import psutil
                for p in psutil.process_iter(["pid", "name"]):
                    name_l = (p.info.get("name") or "").lower()
                    if "alogin" in name_l:
                        procs.append((p.info["name"], p.info["pid"]))
            except Exception:
                pass

        # 3. Quét qua tasklist CMD (Dự phòng)
        if not procs:
            try:
                import subprocess
                res = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True)
                for row in res.stdout.strip().splitlines():
                    parts = row.replace('"', '').split(',')
                    if len(parts) >= 2:
                        pname = parts[0]
                        if "alogin" in pname.lower():
                            try:
                                procs.append((pname, int(parts[1])))
                            except ValueError:
                                pass
            except Exception:
                pass

        if not procs:
            self.cb_procs.configure(values=["(Không tìm thấy game)"])
            self.cb_procs.set("(Không tìm thấy game)")
            return

        items = [f"{name} (PID: {pid})" for name, pid in procs]
        self.cb_procs.configure(values=items)

        # Ưu tiên chọn alogin-W04.exe nếu có
        w04_idx = next((i for i, (name, _) in enumerate(procs) if "w04" in name.lower()), 0)
        self.cb_procs.current(w04_idx)
        self.on_process_selected(None)

    def on_process_selected(self, event):
        val = self.cb_procs.get()
        if not val or "Không tìm thấy" in val:
            return

        try:
            pid = int(val.split("PID:")[1].replace(")", "").strip())
            pname = val.split("(")[0].strip()
        except Exception:
            return

        if self.active_pid == pid and self.session:
            return

        if self.session:
            try:
                self.session.detach()
            except Exception:
                pass

        try:
            self.session = frida.attach(pid)
            self.script = self.session.create_script(FRIDA_HOOK_JS)
            self.script.load()
            self.active_pid = pid
            self.active_proc_name = pname
            # Tự động quét túi đồ ngay khi gắn kết
            self.action_scan_bag_from_ram(silent=True)
        except Exception as e:
            messagebox.showerror("Lỗi Frida", f"Không thể đính kèm vào {pname} (PID: {pid}): {e}")

    # --------------------------------------------------------------------------
    # NỘI DUNG CHÍNH (NOTEBOOK TABS)
    # --------------------------------------------------------------------------
    def create_main_content(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(10, 6))

        self.create_tab_bag_grid()
        self.create_tab_database_table()
        self.create_tab_blacklist_manager()

    # --------------------------------------------------------------------------
    # --------------------------------------------------------------------------
    # TAB 1: LƯỚI 50 Ô TÚI ĐỒ (BAG GRID - 5 CỘT x 10 HÀNG)
    # --------------------------------------------------------------------------
    def create_tab_bag_grid(self):
        tab = tk.Frame(self.notebook, bg=THEME["bg_main"], padx=10, pady=8)
        self.notebook.add(tab, text="  🎒 Túi Đồ 50 Ô Trực Quan & Thao Tác  ")

        top_info = tk.Frame(tab, bg=THEME["bg_card"], padx=12, pady=6)
        top_info.pack(fill="x", pady=(0, 6))

        self.lbl_client_info = tk.Label(top_info, text="Đang xem: Chưa kết nối",
                                        bg=THEME["bg_card"], fg=THEME["cyan"], font=("Segoe UI", 9, "bold"))
        self.lbl_client_info.pack(side="left")

        lbl_legend = tk.Label(top_info, text="🟩 Đã đặt tên  |  🟨 CHƯA ĐẶT TÊN (Cần điền)  |  🟥 Món Rác (Blacklist)",
                              bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 9))
        lbl_legend.pack(side="right")

        # KHUNG CHÍNH CHIA 2 CỘT (SIDE-BY-SIDE): TRÁI = LƯỚI 5x10, PHẢI = EDITOR & TRASH
        content_split = tk.Frame(tab, bg=THEME["bg_main"])
        content_split.pack(fill="both", expand=True)

        # -------------------------------------------------------------
        # CỘT TRÁI: LƯỚI 50 Ô TÚI ĐỒ (ĐÚNG CHUẨN 5 CỘT x 10 HÀNG)
        # -------------------------------------------------------------
        left_panel = tk.Frame(content_split, bg=THEME["bg_dark"], padx=6, pady=6,
                              highlightbackground=THEME["border"], highlightthickness=1)
        left_panel.pack(side="left", fill="both", expand=False)

        lbl_grid_title = tk.Label(left_panel, text="🎒 TÚI ĐỒ NHÂN VẬT (5 CỘT x 10 HÀNG)",
                                  bg=THEME["bg_dark"], fg=THEME["primary"], font=("Segoe UI", 10, "bold"), pady=2)
        lbl_grid_title.pack(anchor="w", padx=4, pady=(0, 4))

        grid_outer = tk.Frame(left_panel, bg=THEME["bg_dark"])
        grid_outer.pack(fill="both", expand=True)

        self.slot_widgets = {}
        for s in range(1, 51):
            row = (s - 1) // 5   # Hàng từ 0 đến 9
            col = (s - 1) % 5    # Cột từ 0 đến 4

            sf = tk.Frame(grid_outer, bg=THEME["slot_empty"],
                          highlightbackground=THEME["border"], highlightthickness=1,
                          padx=3, pady=2, width=116, height=54)
            sf.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")
            sf.grid_propagate(False)

            top_row = tk.Frame(sf, bg=sf["bg"])
            top_row.pack(fill="x")

            ln = tk.Label(top_row, text=f"{s:02d}", bg=sf["bg"], fg=THEME["text_muted"], font=("Segoe UI", 8, "bold"))
            ln.pack(side="left")

            lq = tk.Label(top_row, text="", bg=sf["bg"], fg=THEME["text_muted"], font=("Segoe UI", 8, "bold"))
            lq.pack(side="right")

            lname = tk.Label(sf, text="(Trống)", bg=sf["bg"], fg=THEME["text_muted"],
                             font=("Segoe UI", 8, "bold"), wraplength=108, justify="center")
            lname.pack(expand=True)

            lc = tk.Label(sf, text="", bg=sf["bg"], fg=THEME["cyan"], font=("Consolas", 7))
            lc.pack(anchor="se")

            def make_handler(slot_idx):
                return lambda e: self.on_slot_selected(slot_idx)

            for w in (sf, ln, lq, lname, lc, top_row):
                w.bind("<Button-1>", make_handler(s))

            self.slot_widgets[s] = {
                "frame": sf, "num": ln, "qty": lq, "name": lname, "code": lc, "top": top_row
            }

        for c in range(5):
            grid_outer.grid_columnconfigure(c, weight=1)
        for r in range(10):
            grid_outer.grid_rowconfigure(r, weight=1)

        # -------------------------------------------------------------
        # CỘT PHẢI: BẢNG ĐIỀU KHIỂN CHI TIẾT (EDITOR, TRASH & STATS)
        # -------------------------------------------------------------
        right_panel = tk.Frame(content_split, bg=THEME["bg_main"], padx=8, pady=0)
        right_panel.pack(side="left", fill="both", expand=True)

        # CARD 1: KHUNG CHỈNH SỬA & HÀNH ĐỘNG CHO Ô ĐANG CHỌN (SLOT EDITOR CARD)
        self.editor_frame = tk.Frame(right_panel, bg=THEME["bg_card"], padx=14, pady=12,
                                     highlightbackground=THEME["primary"], highlightthickness=1)
        self.editor_frame.pack(fill="x", pady=(0, 10))

        # Tiêu đề Card 1 & Trạng thái
        ed_header = tk.Frame(self.editor_frame, bg=THEME["bg_card"])
        ed_header.pack(fill="x", pady=(0, 8))

        self.lbl_ed_slot_title = tk.Label(ed_header, text="Đang chọn: Chưa chọn ô nào (Nhấp vào ô túi đồ bên trái)",
                                          bg=THEME["bg_card"], fg=THEME["primary"], font=("Segoe UI", 11, "bold"))
        self.lbl_ed_slot_title.pack(side="left")

        self.lbl_ed_status = tk.Label(ed_header, text="", bg=THEME["bg_card"], font=("Segoe UI", 9, "bold"))
        self.lbl_ed_status.pack(side="right")

        # Dòng mã Hex và Dec
        ed_codes_row = tk.Frame(self.editor_frame, bg=THEME["bg_card"])
        ed_codes_row.pack(fill="x", pady=(0, 10))

        self.lbl_ed_codes = tk.Label(ed_codes_row, text="", bg=THEME["bg_card"], fg=THEME["cyan"], font=("Consolas", 10, "bold"))
        self.lbl_ed_codes.pack(side="left")

        # Dòng nhập tên vật phẩm
        ed_input_row = tk.Frame(self.editor_frame, bg=THEME["bg_card"])
        ed_input_row.pack(fill="x", pady=(0, 10))

        lbl_name_prompt = tk.Label(ed_input_row, text="Điền Tên Vật Phẩm:", bg=THEME["bg_card"],
                                   fg=THEME["text_main"], font=("Segoe UI", 10, "bold"))
        lbl_name_prompt.pack(side="left", padx=(0, 10))

        self.entry_item_name = tk.Entry(ed_input_row, bg=THEME["bg_input"], fg=THEME["text_main"],
                                        insertbackground=THEME["text_main"], font=("Segoe UI", 11), width=32)
        self.entry_item_name.pack(side="left", fill="x", expand=True)
        self.entry_item_name.bind("<Return>", lambda e: self.action_save_current_slot(next_slot=True))
        self.entry_item_name.bind("<Control-s>", lambda e: self.action_save_current_slot(next_slot=False))

        # Hàng các nút bấm hành động
        ed_btns_row = tk.Frame(self.editor_frame, bg=THEME["bg_card"])
        ed_btns_row.pack(fill="x", pady=(0, 6))

        btn_save = tk.Button(ed_btns_row, text="💾 Lưu Tên", font=("Segoe UI", 9, "bold"),
                             bg=THEME["primary"], fg="#11111b", relief="flat", padx=12, pady=5,
                             cursor="hand2", command=lambda: self.action_save_current_slot(next_slot=False))
        btn_save.pack(side="left", padx=(0, 6))

        btn_save_next = tk.Button(ed_btns_row, text="⏭ Lưu & Ô Chưa Tên (Enter)", font=("Segoe UI", 9, "bold"),
                                  bg=THEME["green"], fg="#11111b", relief="flat", padx=12, pady=5,
                                  cursor="hand2", command=lambda: self.action_save_current_slot(next_slot=True))
        btn_save_next.pack(side="left", padx=(0, 10))

        self.btn_toggle_blacklist = tk.Button(ed_btns_row, text="⛔ Thêm Vào Blacklist Vứt", font=("Segoe UI", 9, "bold"),
                                              bg=THEME["orange"], fg="#11111b", relief="flat", padx=10, pady=5,
                                              cursor="hand2", command=self.action_toggle_current_blacklist)
        self.btn_toggle_blacklist.pack(side="left", padx=(0, 8))

        self.btn_discard_direct = tk.Button(ed_btns_row, text="🗑️ VỨT MÓN NÀY", font=("Segoe UI", 9, "bold"),
                                            bg=THEME["red"], fg="#ffffff", relief="flat", padx=12, pady=5,
                                            cursor="hand2", command=self.action_discard_current_slot_in_game)
        self.btn_discard_direct.pack(side="left")

        lbl_hint = tk.Label(self.editor_frame, text="💡 Mẹo: Nhập tên xong nhấn [Enter] để tự động lưu & chuyển ngay sang ô chưa đặt tên tiếp theo!",
                            bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 8, "italic"))
        lbl_hint.pack(anchor="w", pady=(4, 0))

        # CARD 2: KHUNG THEO DÕI & DỌN RÁC TRONG TÚI (CURRENT BAG TRASH MONITOR)
        trash_card = tk.Frame(right_panel, bg=THEME["bg_card"], padx=14, pady=10,
                              highlightbackground=THEME["border"], highlightthickness=1)
        trash_card.pack(fill="both", expand=True, pady=(0, 10))

        trash_header = tk.Frame(trash_card, bg=THEME["bg_card"])
        trash_header.pack(fill="x", pady=(0, 6))

        lbl_trash_title = tk.Label(trash_header, text="🧹 CÁC MÓN RÁC BLACKLIST TRONG TÚI HIỆN TẠI",
                                   bg=THEME["bg_card"], fg=THEME["red"], font=("Segoe UI", 10, "bold"))
        lbl_trash_title.pack(side="left")

        self.lbl_trash_summary = tk.Label(trash_header, text="Chưa quét túi đồ",
                                          bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 9))
        self.lbl_trash_summary.pack(side="right")

        # Bảng danh sách rác trong túi
        tree_trash_frame = tk.Frame(trash_card, bg=THEME["bg_dark"])
        tree_trash_frame.pack(fill="both", expand=True, pady=(0, 8))

        cols_trash = ("slot", "name", "qty", "hex")
        self.tree_trash_in_bag = ttk.Treeview(tree_trash_frame, columns=cols_trash, show="headings",
                                              selectmode="browse", height=6)
        self.tree_trash_in_bag.heading("slot", text="Vị Trí", anchor="center")
        self.tree_trash_in_bag.heading("name", text="Tên Món Rác", anchor="w")
        self.tree_trash_in_bag.heading("qty", text="SL", anchor="center")
        self.tree_trash_in_bag.heading("hex", text="Mã Hex", anchor="center")

        self.tree_trash_in_bag.column("slot", width=70, anchor="center")
        self.tree_trash_in_bag.column("name", width=220, anchor="w")
        self.tree_trash_in_bag.column("qty", width=60, anchor="center")
        self.tree_trash_in_bag.column("hex", width=90, anchor="center")

        sb_tr = ttk.Scrollbar(tree_trash_frame, orient="vertical", command=self.tree_trash_in_bag.yview)
        self.tree_trash_in_bag.configure(yscrollcommand=sb_tr.set)
        self.tree_trash_in_bag.pack(side="left", fill="both", expand=True)
        sb_tr.pack(side="right", fill="y")

        self.tree_trash_in_bag.bind("<Double-1>", self.on_trash_tree_double_click)

        self.btn_sweep_trash_panel = tk.Button(trash_card, text="🧹 VỨT SẠCH TẤT CẢ RÁC TRÊN RA KHỎI GAME (1-CLICK)",
                                               font=("Segoe UI", 10, "bold"), bg=THEME["red"], fg="#ffffff",
                                               activebackground="#f38ba8", relief="flat", padx=14, pady=6,
                                               cursor="hand2", command=self.action_sweep_all_blacklist_items)
        self.btn_sweep_trash_panel.pack(fill="x")

        # CARD 3: THỐNG KÊ NHANH TÚI ĐỒ (QUICK STATS CARD)
        stats_card = tk.Frame(right_panel, bg=THEME["bg_card"], padx=14, pady=8,
                              highlightbackground=THEME["border"], highlightthickness=1)
        stats_card.pack(fill="x")

        self.lbl_bag_stats = tk.Label(stats_card, text="Đang chứa: 0/50 ô  |  🟩 Đã có tên: 0  |  🟨 Chưa đặt tên: 0  |  🟥 Món rác: 0",
                                      bg=THEME["bg_card"], fg=THEME["text_main"], font=("Segoe UI", 9, "bold"))
        self.lbl_bag_stats.pack(anchor="w")

    # --------------------------------------------------------------------------
    # THAO TÁC QUÉT RAM & HIỂN THỊ TÚI ĐỒ
    # --------------------------------------------------------------------------
    def action_scan_bag_from_ram(self, silent=False):
        """Quét siêu tốc mảng túi đồ từ bộ nhớ RAM của game client"""
        if not self.script:
            if not silent:
                messagebox.showwarning("Cảnh Báo", "Chưa kết nối tới cửa sổ game nào! Vui lòng chọn tiến trình ở phía trên.")
            return

        try:
            res = self.script.exports_sync.readbag()
            if not res or not res.get("success"):
                if not silent:
                    messagebox.showwarning("Thông Báo", "Không thể đọc dữ liệu túi đồ từ RAM!\nHãy chắc chắn rằng nhân vật đã đăng nhập vào game và đang đứng trong bản đồ.")
                return

            items = res.get("items", {})
            self.current_bag_slots = {}
            for s_str, it in items.items():
                s = int(s_str)
                code_dec = it["code"]
                hex_c = normalize_code_hex(code_dec)
                qty = it["qty"]

                # Lấy tên từ database nếu có
                db_entry = self.database.get(hex_c, {})
                name = db_entry.get("name", "")

                # Nếu là mã mới hoàn toàn, tự thêm vào database
                if hex_c not in self.database:
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.database[hex_c] = {
                        "code_hex": hex_c,
                        "code_dec": code_dec,
                        "raw_bytes": f"{hex_c[4:6]} {hex_c[2:4]}",
                        "name": "",
                        "first_seen": now_str,
                        "last_seen": now_str,
                        "times_received": 1,
                        "last_qty": qty,
                        "landing_slot": s,
                        "note": ""
                    }

                self.current_bag_slots[s] = {
                    "code_hex": hex_c,
                    "code_dec": code_dec,
                    "qty": qty,
                    "name": name
                }

            self.save_database()
            self.refresh_bag_grid()
            self.refresh_table()
            self.refresh_blacklist_table()

            client_str = f"Đang xem: {self.active_proc_name} (PID: {self.active_pid}) | Đang có {len(self.current_bag_slots)}/50 ô đồ"
            self.lbl_client_info.configure(text=client_str)

            if not silent:
                # Tìm ô chưa đặt tên đầu tiên để trỏ tới
                first_unnamed = next((s for s, it in self.current_bag_slots.items() if not it["name"]), None)
                if first_unnamed:
                    self.on_slot_selected(first_unnamed)
                messagebox.showinfo("Thành Công", f"Đã quét xong túi đồ từ RAM ({len(self.current_bag_slots)} món đồ)!")
        except Exception as e:
            if not silent:
                messagebox.showerror("Lỗi", f"Lỗi quét túi đồ: {e}")

    def refresh_bag_grid(self):
        """Vẽ lại toàn bộ 50 ô trên lưới giao diện với màu sắc tương ứng"""
        for s in range(1, 51):
            w = self.slot_widgets[s]
            if s in self.current_bag_slots:
                it = self.current_bag_slots[s]
                hex_c = it["code_hex"]
                name = it["name"]
                qty = it["qty"]
                in_bl = self.is_in_blacklist(hex_c)

                # Xác định màu sắc
                if in_bl:
                    bg_col = THEME["slot_trash"]
                    border_col = THEME["red"]
                    name_display = f"⛔ {name or '(Chưa đặt tên)'}"
                    fg_name = THEME["red"]
                elif name and not name.startswith("0x"):
                    bg_col = THEME["slot_named"]
                    border_col = THEME["green"]
                    name_display = name
                    fg_name = THEME["green"]
                else:
                    bg_col = THEME["slot_unnamed"]
                    border_col = THEME["yellow"]
                    name_display = "(Chưa đặt tên)"
                    fg_name = THEME["yellow"]

                w["frame"].configure(bg=bg_col, highlightbackground=border_col)
                w["top"].configure(bg=bg_col)
                w["num"].configure(bg=bg_col, fg=THEME["text_muted"])
                w["qty"].configure(bg=bg_col, text=f"x{qty}", fg=THEME["text_main"])
                w["name"].configure(bg=bg_col, text=name_display, fg=fg_name)
                w["code"].configure(bg=bg_col, text=hex_c, fg=THEME["cyan"])
            else:
                w["frame"].configure(bg=THEME["slot_empty"], highlightbackground=THEME["border"])
                w["top"].configure(bg=THEME["slot_empty"])
                w["num"].configure(bg=THEME["slot_empty"], fg=THEME["text_muted"])
                w["qty"].configure(bg=THEME["slot_empty"], text="")
                w["name"].configure(bg=THEME["slot_empty"], text="(Trống)", fg=THEME["text_muted"])
                w["code"].configure(bg=THEME["slot_empty"], text="")

        self.update_trash_summary()
        self.update_bag_stats()

    def update_trash_summary(self):
        """Cập nhật danh sách các món rác Blacklist đang có trong túi ở cột phải"""
        if not hasattr(self, "tree_trash_in_bag"):
            return
        self.tree_trash_in_bag.delete(*self.tree_trash_in_bag.get_children())
        trash_count = 0
        total_qty = 0
        for s in range(1, 51):
            if s in self.current_bag_slots:
                it = self.current_bag_slots[s]
                hex_c = it["code_hex"]
                if self.is_in_blacklist(hex_c):
                    trash_count += 1
                    total_qty += it["qty"]
                    self.tree_trash_in_bag.insert("", "end", values=(f"Ô {s:02d}", it["name"] or "(Chưa đặt tên)", f"x{it['qty']}", hex_c))

        if trash_count > 0:
            self.lbl_trash_summary.configure(text=f"Phát hiện {trash_count} ô chứa rác (Tổng {total_qty} cái)", fg=THEME["red"])
            if hasattr(self, "btn_sweep_trash_panel"):
                self.btn_sweep_trash_panel.configure(state="normal", bg=THEME["red"])
        else:
            self.lbl_trash_summary.configure(text="Túi đồ sạch sẽ, không có món rác nào!", fg=THEME["green"])
            if hasattr(self, "btn_sweep_trash_panel"):
                self.btn_sweep_trash_panel.configure(state="disabled", bg=THEME["bg_input"])

    def update_bag_stats(self):
        """Cập nhật các số liệu thống kê nhanh ở cột phải"""
        if not hasattr(self, "lbl_bag_stats"):
            return
        total_items = len(self.current_bag_slots)
        named = sum(1 for it in self.current_bag_slots.values() if it.get("name") and not it["name"].startswith("0x"))
        unnamed = sum(1 for it in self.current_bag_slots.values() if not it.get("name") or it["name"].startswith("0x"))
        trash = sum(1 for it in self.current_bag_slots.values() if self.is_in_blacklist(it["code_hex"]))
        self.lbl_bag_stats.configure(
            text=f"Đang chứa: {total_items}/50 ô  |  🟩 Đã có tên: {named}  |  🟨 Chưa đặt tên: {unnamed}  |  🟥 Món rác: {trash}"
        )

    def on_trash_tree_double_click(self, event):
        """Nhấp đúp vào dòng món rác để tự động nhảy đến ô đó trên lưới túi đồ"""
        sel = self.tree_trash_in_bag.selection()
        if not sel:
            return
        item_vals = self.tree_trash_in_bag.item(sel[0], "values")
        if item_vals:
            slot_str = item_vals[0].replace("Ô", "").strip()
            try:
                slot_idx = int(slot_str)
                self.on_slot_selected(slot_idx)
            except ValueError:
                pass

    def on_slot_selected(self, slot_idx: int):
        self.selected_slot = slot_idx

        # Highlight ô được chọn
        for s in range(1, 51):
            if s in self.slot_widgets:
                w = self.slot_widgets[s]
                if s == slot_idx:
                    w["frame"].configure(highlightthickness=2, highlightbackground=THEME["primary"])
                else:
                    hex_c = self.current_bag_slots.get(s, {}).get("code_hex", "")
                    in_bl = self.is_in_blacklist(hex_c) if hex_c else False
                    col = THEME["red"] if in_bl else (THEME["green"] if self.current_bag_slots.get(s, {}).get("name") else THEME["yellow"])
                    w["frame"].configure(highlightthickness=1, highlightbackground=col if s in self.current_bag_slots else THEME["border"])

        if slot_idx in self.current_bag_slots:
            it = self.current_bag_slots[slot_idx]
            hex_c = it["code_hex"]
            dec_c = it["code_dec"]
            qty = it["qty"]
            name = it["name"]
            in_bl = self.is_in_blacklist(hex_c)

            self.lbl_ed_slot_title.configure(text=f"Đang chọn: Ô Slot {slot_idx:02d} (x{qty})")
            self.lbl_ed_codes.configure(text=f"Mã Hex: {hex_c}  |  Dec: {dec_c}")

            self.entry_item_name.delete(0, tk.END)
            self.entry_item_name.insert(0, name)
            self.entry_item_name.focus_set()
            self.entry_item_name.select_range(0, tk.END)

            if in_bl:
                self.lbl_ed_status.configure(text="⛔ MÓN TRONG BLACKLIST VỨT", fg=THEME["red"])
                self.btn_toggle_blacklist.configure(text="✔ Bỏ Khỏi Blacklist Vứt", bg=THEME["green"], fg="#11111b", state="normal")
            elif name:
                self.lbl_ed_status.configure(text="✔ Đã Đặt Tên", fg=THEME["green"])
                self.btn_toggle_blacklist.configure(text="⛔ Thêm Vào Blacklist Vứt", bg=THEME["orange"], fg="#11111b", state="normal")
            else:
                self.lbl_ed_status.configure(text="⚠️ CHƯA ĐẶT TÊN", fg=THEME["yellow"])
                self.btn_toggle_blacklist.configure(text="⛔ Thêm Vào Blacklist Vứt", bg=THEME["orange"], fg="#11111b", state="normal")

            if hasattr(self, "btn_discard_direct"):
                self.btn_discard_direct.configure(state="normal")
        else:
            self.lbl_ed_slot_title.configure(text=f"Đang chọn: Ô Slot {slot_idx:02d} (Ô TRỐNG)")
            self.lbl_ed_codes.configure(text="")
            self.lbl_ed_status.configure(text="Trống", fg=THEME["text_muted"])
            self.entry_item_name.delete(0, tk.END)
            if hasattr(self, "btn_discard_direct"):
                self.btn_discard_direct.configure(state="disabled")
            if hasattr(self, "btn_toggle_blacklist"):
                self.btn_toggle_blacklist.configure(state="disabled")

    def action_save_current_slot(self, next_slot=False):
        if not self.selected_slot or self.selected_slot not in self.current_bag_slots:
            return

        new_name = self.entry_item_name.get().strip()
        it = self.current_bag_slots[self.selected_slot]
        hex_c = it["code_hex"]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if hex_c in self.database:
            self.database[hex_c]["name"] = new_name
            self.database[hex_c]["last_seen"] = now_str
        else:
            self.database[hex_c] = {
                "code_hex": hex_c,
                "code_dec": it["code_dec"],
                "raw_bytes": f"{hex_c[4:6]} {hex_c[2:4]}",
                "name": new_name,
                "first_seen": now_str,
                "last_seen": now_str,
                "times_received": 1,
                "last_qty": it.get("qty", 1),
                "landing_slot": self.selected_slot,
                "note": ""
            }

        # Nếu món này đang trong blacklist, cập nhật tên luôn
        if hex_c in self.discard_config.get("blacklist", {}):
            self.discard_config["blacklist"][hex_c]["name"] = new_name
            self.save_discard_config()

        it["name"] = new_name
        self.save_database()
        self.refresh_bag_grid()
        self.refresh_table()

        if next_slot:
            # Tìm ô chưa đặt tên tiếp theo (bắt đầu từ ô hiện tại)
            cur = self.selected_slot
            found_next = None
            for s in range(cur + 1, 51):
                if s in self.current_bag_slots:
                    if not self.current_bag_slots[s]["name"]:
                        found_next = s
                        break
            if not found_next:
                for s in range(1, cur):
                    if s in self.current_bag_slots:
                        if not self.current_bag_slots[s]["name"]:
                            found_next = s
                            break

            if found_next:
                self.on_slot_selected(found_next)
            else:
                messagebox.showinfo("Hoàn Tất", "Tuyệt vời! Tất cả vật phẩm trong túi đồ đều đã được đặt tên!")

    def action_toggle_current_blacklist(self):
        if not self.selected_slot or self.selected_slot not in self.current_bag_slots:
            return

        it = self.current_bag_slots[self.selected_slot]
        hex_c = it["code_hex"]
        dec_c = it["code_dec"]
        name = it["name"] or f"Vật phẩm_{hex_c}"

        bl = self.discard_config.setdefault("blacklist", {})
        if hex_c in bl:
            del bl[hex_c]
            messagebox.showinfo("Thông Báo", f"Đã bỏ {hex_c} ({name}) khỏi Blacklist Vứt.")
        else:
            bl[hex_c] = {
                "name": name,
                "code_dec": dec_c,
                "enabled": True,
                "discard_count": 0
            }
            messagebox.showinfo("Thông Báo", f"Đã thêm {hex_c} ({name}) vào Blacklist Vứt thành công!")

        self.save_discard_config()
        self.refresh_bag_grid()
        self.refresh_blacklist_table()
        self.on_slot_selected(self.selected_slot)

    def action_discard_current_slot_in_game(self):
        """Gửi lệnh vứt trực tiếp món đồ đang chọn trong game"""
        if not self.selected_slot or self.selected_slot not in self.current_bag_slots:
            return

        if not self.script:
            messagebox.showwarning("Cảnh Báo", "Chưa kết nối tới cửa sổ game!")
            return

        it = self.current_bag_slots[self.selected_slot]
        slot = self.selected_slot
        qty = it["qty"]
        hex_c = it["code_hex"]
        name = it["name"] or hex_c

        if not messagebox.askyesno("Xác Nhận Vứt Đồ", f"Bạn có CHẮC CHẮN muốn vứt:\n\n• {name} (Mã: {hex_c})\n• Tại Ô Slot {slot:02d}\n• Số lượng: x{qty} cái\n\nThao tác này sẽ xóa vật phẩm ra khỏi game! Bạn có muốn tiếp tục?"):
            return

        # Gửi lệnh vứt 2 bước: 0x17 0x03 và 0x17 0x7C
        try:
            pkt_req = pack_wlo_packet(bytes([0x17, 0x03, slot, qty, 0x01]))
            self.script.exports_sync.sendraw(pkt_req.hex())
            time.sleep(0.15)
            pkt_cfm = pack_wlo_packet(bytes([0x17, 0x7C, slot, qty, 0x02]))
            self.script.exports_sync.sendraw(pkt_cfm.hex())
            time.sleep(0.3)

            messagebox.showinfo("Thành Công", f"Đã gửi lệnh vứt {name} tại Ô Slot {slot:02d} thành công!")
            # Quét lại túi đồ từ RAM để cập nhật
            self.action_scan_bag_from_ram(silent=True)
        except Exception as e:
            messagebox.showerror("Lỗi Vứt Đồ", f"Không thể gửi gói tin vứt: {e}")

    def action_sweep_all_blacklist_items(self):
        """Quét và vứt sạch toàn bộ các món trong túi đồ thuộc Blacklist"""
        if not self.script:
            messagebox.showwarning("Cảnh Báo", "Chưa kết nối tới cửa sổ game!")
            return

        trash_to_dump = []
        for s, it in self.current_bag_slots.items():
            if self.is_in_blacklist(it["code_hex"]):
                trash_to_dump.append((s, it))

        if not trash_to_dump:
            messagebox.showinfo("Thông Báo", "Trong túi đồ hiện tại KHÔNG CÓ món nào nằm trong Blacklist Vứt!")
            return

        msg = f"Tìm thấy {len(trash_to_dump)} ô chứa vật phẩm rác Blacklist:\n\n"
        for s, it in trash_to_dump:
            msg += f"• Ô {s:02d}: {it['name'] or it['code_hex']} (x{it['qty']})\n"
        msg += "\nBạn có muốn VỨT TOÀN BỘ các món này ngay bây giờ không?"

        if not messagebox.askyesno("Xác Nhận Dọn Sạch Túi", msg):
            return

        def _sweep_thread():
            count = 0
            for s, it in trash_to_dump:
                qty = it["qty"]
                try:
                    pkt_req = pack_wlo_packet(bytes([0x17, 0x03, s, qty, 0x01]))
                    self.script.exports_sync.sendraw(pkt_req.hex())
                    time.sleep(0.15)
                    pkt_cfm = pack_wlo_packet(bytes([0x17, 0x7C, s, qty, 0x02]))
                    self.script.exports_sync.sendraw(pkt_cfm.hex())
                    time.sleep(0.15)
                    count += 1
                except Exception:
                    pass

            time.sleep(0.4)
            self.root.after(0, lambda: self.action_scan_bag_from_ram(silent=True))
            self.root.after(0, lambda: messagebox.showinfo("Hoàn Tất", f"Đã dọn sạch {count} món rác ra khỏi túi đồ!"))

        threading.Thread(target=_sweep_thread, daemon=True).start()

    # --------------------------------------------------------------------------
    # TAB 2: QUẢN LÝ DATABASE VẬT PHẨM (TREEVIEW)
    # --------------------------------------------------------------------------
    def create_tab_database_table(self):
        tab = tk.Frame(self.notebook, bg=THEME["bg_main"], padx=14, pady=12)
        self.notebook.add(tab, text="  📋 Danh Sách Toàn Bộ Database  ")

        filter_bar = tk.Frame(tab, bg=THEME["bg_card"], padx=12, pady=8)
        filter_bar.pack(fill="x", pady=(0, 10))

        lbl_filter = tk.Label(filter_bar, text="Bộ lọc:", bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 9, "bold"))
        lbl_filter.pack(side="left", padx=(0, 6))

        self.cb_filter = ttk.Combobox(filter_bar, state="readonly", width=24,
                                      values=["Tất cả vật phẩm", "Chỉ món CHƯA ĐẶT TÊN", "Chỉ món ĐÃ CÓ TÊN", "Chỉ món trong BLACKLIST"])
        self.cb_filter.set("Tất cả vật phẩm")
        self.cb_filter.pack(side="left", padx=(0, 15))
        self.cb_filter.bind("<<ComboboxSelected>>", lambda e: self.refresh_table())

        lbl_search = tk.Label(filter_bar, text="🔍 Tìm kiếm:", bg=THEME["bg_card"], fg=THEME["text_muted"], font=("Segoe UI", 9, "bold"))
        lbl_search.pack(side="left", padx=(0, 6))

        self.entry_search = tk.Entry(filter_bar, bg=THEME["bg_input"], fg=THEME["text_main"],
                                     insertbackground=THEME["text_main"], font=("Segoe UI", 10), width=24)
        self.entry_search.pack(side="left", padx=(0, 8))
        self.entry_search.bind("<KeyRelease>", lambda e: self.refresh_table())

        btn_clear = ttk.Button(filter_bar, text="✕ Xóa lọc", command=self.clear_table_search)
        btn_clear.pack(side="left")

        # Bảng Treeview
        tree_frame = tk.Frame(tab, bg=THEME["bg_dark"])
        tree_frame.pack(fill="both", expand=True)

        cols = ("hex", "dec", "name", "blacklist", "times", "seen")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("hex", text="Mã Hex", anchor="center")
        self.tree.heading("dec", text="Mã Dec", anchor="center")
        self.tree.heading("name", text="Tên Vật Phẩm", anchor="w")
        self.tree.heading("blacklist", text="Blacklist Vứt?", anchor="center")
        self.tree.heading("times", text="Số Lần Gặp", anchor="center")
        self.tree.heading("seen", text="Lần Cuối Thấy", anchor="center")

        self.tree.column("hex", width=90, anchor="center")
        self.tree.column("dec", width=90, anchor="center")
        self.tree.column("name", width=340, anchor="w")
        self.tree.column("blacklist", width=120, anchor="center")
        self.tree.column("times", width=100, anchor="center")
        self.tree.column("seen", width=160, anchor="center")

        sb_v = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb_v.set)

        self.tree.pack(side="left", fill="both", expand=True)
        sb_v.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self.on_table_double_click)

    def refresh_table(self):
        query = self.entry_search.get().strip().lower()
        mode = self.cb_filter.get()

        self.tree.delete(*self.tree.get_children())
        for hex_c, v in sorted(self.database.items(), key=lambda x: x[0]):
            name = v.get("name", "")
            dec_c = v.get("code_dec", 0)
            times = v.get("times_received", 1)
            seen = v.get("last_seen", "")
            in_bl = self.is_in_blacklist(hex_c)

            # Lọc theo chế độ
            if mode == "Chỉ món CHƯA ĐẶT TÊN" and name:
                continue
            if mode == "Chỉ món ĐÃ CÓ TÊN" and not name:
                continue
            if mode == "Chỉ món trong BLACKLIST" and not in_bl:
                continue

            # Lọc theo tìm kiếm
            if query:
                if query not in hex_c.lower() and query not in str(dec_c) and query not in name.lower():
                    continue

            bl_str = "⛔ CÓ" if in_bl else ""
            name_str = name if name else "(Chưa đặt tên)"
            self.tree.insert("", "end", iid=hex_c, values=(hex_c, dec_c, name_str, bl_str, times, seen))

    def clear_table_search(self):
        self.entry_search.delete(0, tk.END)
        self.cb_filter.set("Tất cả vật phẩm")
        self.refresh_table()

    def on_table_double_click(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        hex_c = sel[0]
        it = self.database.get(hex_c, {})
        cur_name = it.get("name", "")

        new_name = simpledialog.askstring("Sửa Tên Vật Phẩm", f"Nhập tên mới cho mã {hex_c}:", initialvalue=cur_name, parent=self.root)
        if new_name is not None:
            self.database[hex_c]["name"] = new_name.strip()
            self.save_database()
            self.refresh_table()
            self.refresh_bag_grid()

    # --------------------------------------------------------------------------
    # TAB 3: QUẢN LÝ BLACKLIST VỨT ĐỒ
    # --------------------------------------------------------------------------
    def create_tab_blacklist_manager(self):
        tab = tk.Frame(self.notebook, bg=THEME["bg_main"], padx=14, pady=12)
        self.notebook.add(tab, text="  ⛔ Danh Sách Vứt (Auto-Discard Blacklist)  ")

        top_ctrl = tk.Frame(tab, bg=THEME["bg_card"], padx=12, pady=8)
        top_ctrl.pack(fill="x", pady=(0, 10))

        btn_add_bl = tk.Button(top_ctrl, text="➕ Thêm Mã Hex Vào Blacklist", font=("Segoe UI", 9, "bold"),
                               bg=THEME["primary"], fg="#11111b", relief="flat", padx=12, pady=5,
                               cursor="hand2", command=self.action_add_hex_manually_to_blacklist)
        btn_add_bl.pack(side="left", padx=(0, 10))

        btn_remove_bl = tk.Button(top_ctrl, text="🗑️ Bỏ Khỏi Blacklist", font=("Segoe UI", 9, "bold"),
                                  bg=THEME["red"], fg="#ffffff", relief="flat", padx=12, pady=5,
                                  cursor="hand2", command=self.action_remove_selected_from_blacklist)
        btn_remove_bl.pack(side="left")

        # Bảng danh sách blacklist
        tree_frame = tk.Frame(tab, bg=THEME["bg_dark"])
        tree_frame.pack(fill="both", expand=True)

        cols = ("hex", "dec", "name", "enabled")
        self.tree_bl = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")

        self.tree_bl.heading("hex", text="Mã Hex", anchor="center")
        self.tree_bl.heading("dec", text="Mã Dec", anchor="center")
        self.tree_bl.heading("name", text="Tên Vật Phẩm Rác", anchor="w")
        self.tree_bl.heading("enabled", text="Trạng Thái", anchor="center")

        self.tree_bl.column("hex", width=120, anchor="center")
        self.tree_bl.column("dec", width=120, anchor="center")
        self.tree_bl.column("name", width=380, anchor="w")
        self.tree_bl.column("enabled", width=150, anchor="center")

        sb_v = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_bl.yview)
        self.tree_bl.configure(yscrollcommand=sb_v.set)

        self.tree_bl.pack(side="left", fill="both", expand=True)
        sb_v.pack(side="right", fill="y")

        self.refresh_blacklist_table()

    def refresh_blacklist_table(self):
        self.tree_bl.delete(*self.tree_bl.get_children())
        bl = self.discard_config.get("blacklist", {})
        for hex_c, v in sorted(bl.items(), key=lambda x: x[0]):
            name = v.get("name", "")
            dec_c = v.get("code_dec", 0)
            en = "Đang kích hoạt vứt" if v.get("enabled", True) else "Đã tắt"
            self.tree_bl.insert("", "end", iid=hex_c, values=(hex_c, dec_c, name, en))

    def action_add_hex_manually_to_blacklist(self):
        val = simpledialog.askstring("Thêm Vào Blacklist", "Nhập mã Hex (VD: 0x85CF hoặc 85CF):", parent=self.root)
        if not val:
            return
        hex_c = normalize_code_hex(val)
        try:
            dec_c = int(hex_c, 16)
        except ValueError:
            messagebox.showerror("Lỗi", "Mã Hex không hợp lệ!")
            return

        db_name = self.database.get(hex_c, {}).get("name", "")
        name = db_name if db_name else f"Vật phẩm_{hex_c}"

        self.discard_config.setdefault("blacklist", {})[hex_c] = {
            "name": name,
            "code_dec": dec_c,
            "enabled": True,
            "discard_count": 0
        }
        self.save_discard_config()
        self.refresh_blacklist_table()
        self.refresh_bag_grid()
        messagebox.showinfo("Thành Công", f"Đã thêm {hex_c} ({name}) vào Blacklist Vứt!")

    def action_remove_selected_from_blacklist(self):
        sel = self.tree_bl.selection()
        if not sel:
            messagebox.showwarning("Cảnh Báo", "Vui lòng chọn một dòng trong bảng Blacklist để xóa!")
            return
        hex_c = sel[0]
        bl = self.discard_config.get("blacklist", {})
        if hex_c in bl:
            del bl[hex_c]
            self.save_discard_config()
            self.refresh_blacklist_table()
            self.refresh_bag_grid()
            messagebox.showinfo("Thành Công", f"Đã xóa {hex_c} khỏi Blacklist Vứt!")

    # --------------------------------------------------------------------------
    # STATUSBAR
    # --------------------------------------------------------------------------
    def create_statusbar(self):
        sb = tk.Frame(self.root, bg=THEME["bg_dark"], height=28, padx=16, pady=4)
        sb.pack(fill="x", side="bottom")

        self.lbl_sb_info = tk.Label(sb, text="", bg=THEME["bg_dark"], fg=THEME["text_muted"], font=("Segoe UI", 9))
        self.lbl_sb_info.pack(side="left")

        lbl_author = tk.Label(sb, text="WLO Tool Suite • Đồng bộ 100% WLOI, WLO & WLOI - Eng",
                              bg=THEME["bg_dark"], fg=THEME["primary"], font=("Segoe UI", 9, "bold"))
        lbl_author.pack(side="right")

    def update_status_counts(self):
        if not hasattr(self, "lbl_sb_info") or self.lbl_sb_info is None:
            return
        total = len(self.database)
        named = sum(1 for it in self.database.values() if it.get("name") and not it["name"].startswith("0x"))
        unnamed = total - named
        bl_count = len(self.discard_config.get("blacklist", {}))
        self.lbl_sb_info.configure(
            text=f"Database: {total} vật phẩm (Đã đặt tên: {named} | Chưa đặt tên: {unnamed}) • Blacklist vứt: {bl_count} món"
        )


def main():
    root = tk.Tk()
    app = WLOItemNamerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
