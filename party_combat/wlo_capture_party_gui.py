#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO PACKET STUDIO & MULTI-CLIENT SNIFFER (GUI v2.0)
===================================================
Giao diện đồ họa chuyên nghiệp phân tích gói tin mạng Wonderland Online (WLO) thời gian thực:
- Bắt gói đa tiến trình (Multi-client alogin*.exe không giới hạn).
- Bóc tách chuyên sâu giao thức WLO (XOR 0xAD, Magic 0xF444, Opcode/Subcode, Party, Chat, Move, v.v.).
- Bộ lọc thông minh (Hướng C->S / S->C, lọc Opcode, tìm kiếm thời gian thực, preset ẩn Ping/Di chuyển).
- Khung xem chi tiết kiểu Wireshark (Cây phân tích trường dữ liệu + Hex Dump 16-byte + ASCII/Big5).
- Xuất dữ liệu (JSON, CSV, TXT) và công cụ Replay/Inject gói tin.
"""

import os
import sys
import time
import json
import csv
import struct
import queue
import threading
from datetime import datetime

# GUI Tkinter
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from tkinter.scrolledtext import ScrolledText

# Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    frida = None

# ==============================================================================
# BẢNG MÀU GIAO DIỆN (CATPPUCCIN MOCHA THEME)
# ==============================================================================
THEME = {
    "bg_dark": "#11111b",       # Nền sâu nhất (Header, Statusbar, Log)
    "bg_main": "#181825",       # Nền chính cửa sổ
    "bg_card": "#1e1e2e",       # Nền khung Card, Container
    "bg_input": "#313244",      # Nền ô nhập liệu / Treeview
    "bg_hover": "#45475a",      # Khi hover
    "bg_selected": "#585b70",   # Khi chọn dòng
    "text_main": "#cdd6f4",     # Chữ sáng chính
    "text_muted": "#a6adc8",    # Chữ mờ, phụ đề
    "primary": "#89b4fa",       # Xanh dương điểm nhấn
    "primary_hover": "#b4befe",
    "green": "#a6e3a1",         # Party / Thành công
    "yellow": "#f9e2af",        # Chat / Cảnh báo
    "gold": "#fab387",          # Đội trưởng / Highlight
    "orange": "#fab387",
    "red": "#f38ba8",           # Ngắt kết nối / Lỗi / Từ chối
    "cyan": "#89dceb",          # Socket / Di chuyển
    "magenta": "#f5c2e7",       # Sự kiện đặc biệt
    "purple": "#cba6f7",        # Combat
    "border": "#45475a",        # Màu viền
}

# ==============================================================================
# TỪ ĐIỂN MÃ LỆNH OPCODE CHUẨN WLO
# ==============================================================================
OPCODE_NAMES = {
    0x01: "SYSTEM_HANDSHAKE",    # Kết nối ban đầu, phiên bản server
    0x02: "ACCOUNT_CHAR_LIST",   # Danh sách nhân vật, thông báo server
    0x03: "CHANNEL_INFO",        # Thông tin kênh / danh sách máy chủ
    0x04: "SKILL_EFFECT",        # Hiệu ứng kỹ năng, âm thanh
    0x05: "LOGIN_AUTH",          # Đăng nhập, khởi tạo nhân vật vào game
    0x06: "COMBAT_ACTION",       # Thao tác chiến đấu (đánh, đỡ, bỏ chạy, kỹ năng)
    0x07: "TEAM_FORMATION",      # Đội hình chiến đấu
    0x08: "PING_HEARTBEAT",      # Giữ kết nối Ping/Pong
    0x0A: "TRADE_STALL",         # Giao dịch, mở sạp bán hàng
    0x0B: "INVENTORY_ITEM",      # Túi đồ, trang bị, vật phẩm
    0x0C: "FRIEND_MAIL",         # Bạn bè, thư tín
    0x0D: "PARTY_SYSTEM",        # Hệ thống tổ đội (mời, vào, rời, giải tán, chuyển trưởng)
    0x0E: "PET_ACTION",          # Thao tác thú cưng / bạn đồng hành
    0x0F: "PET_STATUS",          # Chỉ số pet / tình trạng pet
    0x10: "TENT_FURNITURE",      # Lều bạt, đồ nội thất
    0x13: "SYNTHESIS_COMPOUND",  # Chế tạo, hợp thành vật phẩm
    0x14: "CHAT_MESSAGE",        # Kênh chat (Thế giới, Đội, Bang, Mật, Hệ thống)
    0x16: "QUEST_MISSION",       # Nhiệm vụ
    0x17: "CHAR_ATTRIBUTES",     # Chỉ số nhân vật (HP, SP, EXP, Level, Tọa độ)
    0x18: "SHORTCUT_BAR",        # Thanh phím tắt
    0x19: "PK_SYSTEM",           # Hệ thống PK / tỉ thí
    0x1A: "GUILD_SYSTEM",        # Bang hội
    0x20: "NPC_DIALOG",          # Đối thoại NPC, lựa chọn nhiệm vụ
    0x23: "MAP_OBJECT",          # Vật thể trên bản đồ (rương, tài nguyên)
    0x32: "PLAYER_MOVE",         # Di chuyển nhân vật (tọa độ click chuột)
    0x33: "ENTITY_MOVE_SYNC",    # Đồng bộ di chuyển người chơi khác / NPC
    0x34: "ENTITY_ACTION_SYNC",  # Đồng bộ hành động (ngồi, đứng, xoay hướng)
    0x35: "MAP_WARP_SCENE",      # Chuyển cảnh, đổi map, nạp vị trí
    0x3E: "WEATHER_EFFECT",      # Hiệu ứng thời tiết / ngày đêm
    0x3F: "SCENE_TRIGGER",       # Kích hoạt sự kiện trên map
    0x4B: "EXPRESSION_EMOTE",    # Biểu cảm emote
    0x55: "DUNGEON_LOBBY",       # Phòng chờ phó bản, phụ bản
    0xB7: "SPECIAL_EXT",         # Giao thức mở rộng proxy / anti-cheat
}

# ==============================================================================
# FRIDA INJECTION SCRIPT
# ==============================================================================
FRIDA_JS = """
var activeSocket = -1;
var sendFunc = null;
var isInjected = false;

function initSendFunc() {
    try {
        var mod = Process.getModuleByName('ws2_32.dll') || Process.getModuleByName('wsock32.dll');
        if (mod) {
            var sPtr = mod.getExportByName('send');
            if (sPtr) {
                sendFunc = new NativeFunction(sPtr, 'int', ['int', 'pointer', 'int', 'int']);
            }
        }
    } catch(e) {}
}
initSendFunc();

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
                if (isInjected) return;
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
hookSend('wsock32.dll');
hookSend('ws2_32.dll');

rpc.exports = {
    getsocket: function() {
        return activeSocket;
    },
    sendraw: function(hexBytes) {
        if (!sendFunc) initSendFunc();
        if (activeSocket <= 0) return {success: false, error: "Chưa tìm thấy active socket"};
        if (!sendFunc) return {success: false, error: "Không tìm thấy hàm send trong ws2_32.dll"};
        try {
            var raw = [];
            for (var i = 0; i < hexBytes.length; i += 2) {
                raw.push(parseInt(hexBytes.substr(i, 2), 16));
            }
            var buf = Memory.alloc(raw.length);
            buf.writeByteArray(raw);
            isInjected = true;
            var ret = sendFunc(activeSocket, buf, raw.length, 0);
            isInjected = false;
            return {success: true, ret: ret, sock: activeSocket};
        } catch(e) {
            isInjected = false;
            return {success: false, error: e.toString()};
        }
    }
};
"""

# ==============================================================================
# HÀM BÓC TÁCH & PHÂN TÍCH GÓI TIN WLO (DISSECTOR ENGINE)
# ==============================================================================
def dissect_wlo_packet(opcode, subcode, data, direction):
    """
    Bóc tách sâu gói tin WLO.
    Trả về: (summary, fields_list, category)
    """
    op_name = OPCODE_NAMES.get(opcode, f"0x{opcode:02X}" if opcode is not None else "--")
    fields = []
    category = "misc"

    # Thử giải mã text Big5 / ASCII
    text_preview = ""
    if data:
        try:
            txt = data.decode("big5", errors="ignore")
            clean = "".join(c for c in txt if c.isprintable()).strip()
            if len(clean) >= 2:
                text_preview = clean
        except Exception:
            pass

    # 1. Hệ thống tổ đội (Opcode 0x0D & 0x07)
    if opcode == 0x0D:
        category = "party"
        if subcode == 0x01:
            if len(data) >= 4:
                target_id = struct.unpack("<I", data[:4])[0]
                summary = f"Mời / Xin vào nhóm -> Target ID: 0x{target_id:08X} ({target_id})"
                fields.append(("Hành động", "Xin gia nhập hoặc Mời tổ đội (Sub 0x01)"))
                fields.append(("Mục tiêu (Target ID)", f"0x{target_id:08X} ({target_id})"))
            else:
                summary = "Yêu cầu tổ đội (Dữ liệu ngắn)"
        elif subcode == 0x02:
            summary = "Rời khỏi tổ đội (Leave Party)"
            fields.append(("Hành động", "Tự rời khỏi tổ đội (Sub 0x02)"))
        elif subcode == 0x03:
            if len(data) >= 5:
                flag = data[0]
                partner_id = struct.unpack("<I", data[1:5])[0]
                summary = f"Chấp thuận vào nhóm (Flag={flag}) -> Partner ID: 0x{partner_id:08X} ({partner_id})"
                fields.append(("Hành động", "Chấp thuận vào tổ đội (Sub 0x03)"))
                fields.append(("Cờ chấp thuận (Flag)", str(flag)))
                fields.append(("ID đối tác (Partner ID)", f"0x{partner_id:08X} ({partner_id})"))
            elif len(data) >= 4:
                partner_id = struct.unpack("<I", data[:4])[0]
                summary = f"Chấp thuận vào nhóm -> Partner ID: 0x{partner_id:08X} ({partner_id})"
                fields.append(("ID đối tác", f"0x{partner_id:08X} ({partner_id})"))
            else:
                summary = "Chấp thuận tổ đội (Sub 0x03)"
        elif subcode == 0x04:
            summary = "Giải tán tổ đội (Disband Party)"
            fields.append(("Hành động", "Đội trưởng giải tán tổ đội (Sub 0x04)"))
            if len(data) >= 4:
                leader_id = struct.unpack("<I", data[:4])[0]
                fields.append(("Leader ID", f"0x{leader_id:08X} ({leader_id})"))
        elif subcode == 0x0A:
            if len(data) >= 5:
                flag = data[0]
                leader_id = struct.unpack("<I", data[1:5])[0]
                summary = f"Chuyển Đội trưởng (Flag={flag}) -> New Leader: 0x{leader_id:08X} ({leader_id})"
                fields.append(("Hành động", "Trao quyền Đội trưởng (Sub 0x0A)"))
                fields.append(("Flag", str(flag)))
                fields.append(("Tân Đội trưởng ID", f"0x{leader_id:08X} ({leader_id})"))
            elif len(data) >= 4:
                leader_id = struct.unpack("<I", data[:4])[0]
                summary = f"Chuyển Đội trưởng -> New Leader: 0x{leader_id:08X} ({leader_id})"
                fields.append(("Tân Đội trưởng ID", f"0x{leader_id:08X} ({leader_id})"))
            else:
                summary = "Chuyển quyền Đội trưởng (Sub 0x0A)"
        elif subcode in (0x05, 0x06):
            summary = f"Đồng bộ danh sách thành viên nhóm (Len: {len(data)})"
            fields.append(("Hành động", "Server cập nhật danh sách tổ đội"))
        else:
            summary = f"Lệnh tổ đội (Sub 0x{subcode:02X})"
            if text_preview:
                summary += f" | '{text_preview}'"

    elif opcode == 0x07:
        category = "party"
        summary = f"Đội hình chiến đấu TEAM_FORMATION (Sub 0x{subcode:02X}, Len {len(data)})"
        if text_preview:
            summary += f" | '{text_preview}'"

    # 2. Kênh chat (Opcode 0x14)
    elif opcode == 0x14:
        category = "chat"
        channel_id = subcode
        fields.append(("Kênh chat (Channel)", f"0x{channel_id:02X}"))
        if text_preview:
            summary = f"Chat: '{text_preview}'"
            fields.append(("Nội dung văn bản (Big5)", text_preview))
        else:
            summary = f"Tin nhắn chat (Sub 0x{subcode:02X}, Len {len(data)})"

    # 3. Di chuyển nhân vật (Opcode 0x32, 0x33, 0x34)
    elif opcode in (0x32, 0x33, 0x34):
        category = "move"
        if opcode == 0x32 and len(data) >= 4:
            x, y = struct.unpack("<HH", data[:4])
            summary = f"Di chuyển người chơi -> Tọa độ ({x}, {y})"
            fields.append(("Tọa độ X", str(x)))
            fields.append(("Tọa độ Y", str(y)))
        elif opcode == 0x33:
            summary = f"Đồng bộ vị trí thực thể/NPC (Len {len(data)})"
        else:
            summary = f"Đồng bộ hành động thực thể (Sub 0x{subcode:02X})"

    # 4. Nhịp tim giữ kết nối (Opcode 0x08)
    elif opcode == 0x08:
        category = "ping"
        summary = f"Heartbeat PING/PONG (Sub 0x{subcode:02X})"
        fields.append(("Loại nhịp tim", "Ping" if subcode == 0x01 else "Pong"))

    # 5. Hệ thống đăng nhập / Xác thực (Opcode 0x01, 0x02, 0x05)
    elif opcode in (0x01, 0x02, 0x05):
        category = "login"
        summary = f"{op_name} (Sub 0x{subcode:02X})"
        if text_preview:
            summary += f" | '{text_preview}'"
            fields.append(("Thông điệp", text_preview))

    # 6. Chiến đấu (Opcode 0x06)
    elif opcode == 0x06:
        category = "combat"
        summary = f"Thao tác chiến đấu (Sub 0x{subcode:02X}, Len {len(data)})"
        fields.append(("Mã hành động chiến đấu", f"0x{subcode:02X}"))

    # 7. Túi đồ & Trang bị (Opcode 0x0B)
    elif opcode == 0x0B:
        category = "inventory"
        summary = f"Cập nhật vật phẩm / Túi đồ (Sub 0x{subcode:02X})"
        if text_preview:
            summary += f" | '{text_preview}'"

    # Mặc định
    else:
        summary = f"{op_name} (Sub 0x{subcode:02X if subcode is not None else '--'})"
        if text_preview:
            summary += f" | '{text_preview}'"

    return summary, fields, category

# ==============================================================================
# QUẢN LÝ TIẾN TRÌNH SNIFFER TỪNG CLIENT
# ==============================================================================
class ClientSnifferNode:
    def __init__(self, proc_name, pid, event_queue):
        self.proc_name = proc_name
        self.pid = pid
        self.event_queue = event_queue
        self.c2s_buf = bytearray()
        self.s2c_buf = bytearray()
        self.session = None
        self.script = None
        self.is_hooked = False
        self.packet_count = 0
        self.error_message = None

    def feed_dissector(self, raw_bytes, buffer):
        """Giải mã XOR 0xAD và cắt khung gói tin WLO 0xF444."""
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

    def on_message(self, message, raw_data):
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "recv")
        is_send = (dir_name == "send")
        direction = "C->S" if is_send else "S->C"
        buffer = self.c2s_buf if is_send else self.s2c_buf

        try:
            packets = self.feed_dissector(raw_data, buffer)
            for opcode, subcode, data, raw_pkt in packets:
                self.packet_count += 1
                now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                summary, fields, category = dissect_wlo_packet(opcode, subcode, data, direction)

                pkt_obj = {
                    "time": now_str,
                    "proc_name": self.proc_name,
                    "pid": self.pid,
                    "dir": direction,
                    "opcode": opcode,
                    "subcode": subcode,
                    "length": len(data),
                    "summary": summary,
                    "fields": fields,
                    "category": category,
                    "raw_decrypted": raw_pkt,
                    "data": data,
                }
                self.event_queue.put(("PACKET", pkt_obj))
        except Exception as e:
            self.event_queue.put(("ERROR", {"pid": self.pid, "error": str(e)}))

    def start(self):
        if not frida:
            self.error_message = "Chưa cài đặt thư viện Frida"
            return False
        try:
            dev = frida.get_local_device()
            self.session = dev.attach(self.pid)
            self.script = self.session.create_script(FRIDA_JS)
            self.script.on("message", self.on_message)
            self.script.load()
            self.is_hooked = True
            self.error_message = None
            return True
        except Exception as e:
            self.is_hooked = False
            self.error_message = str(e)
            return False

    def stop(self):
        try:
            if self.script:
                self.script.unload()
            if self.session:
                self.session.detach()
        except Exception:
            pass
        finally:
            self.script = None
            self.session = None
            self.is_hooked = False

    def send_packet(self, body_bytes):
        """Đóng gói và gửi raw packet vào socket của client này."""
        if not self.is_hooked or not self.script:
            return {"success": False, "error": "Client chưa được hook"}
        header = struct.pack("<HH", 0x44F4, len(body_bytes))
        plain = header + body_bytes
        enc = bytes(b ^ 0xAD for b in plain)
        try:
            res = self.script.exports_sync.sendraw(enc.hex())
            return res
        except Exception as e:
            return {"success": False, "error": str(e)}

# ==============================================================================
# GIAO DIỆN CHÍNH: WLO PACKET STUDIO
# ==============================================================================
class WLOPacketStudioGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("WLO Packet Studio & Multi-Client Sniffer v2.0")
        self.root.geometry("1280x820")
        self.root.minsize(1050, 700)
        self.root.configure(bg=THEME["bg_main"])

        # Luồng dữ liệu và lưu trữ
        self.event_queue = queue.Queue()
        self.nodes = {}  # pid -> ClientSnifferNode
        self.packets = []  # Toàn bộ danh sách gói tin
        self.packet_seq = 0
        self.is_auto_scroll = True
        self.log_file_fp = None
        self.selected_packet = None

        # Thống kê
        self.total_captured = 0
        self.displayed_count = 0
        self.last_stat_time = time.time()
        self.last_stat_count = 0
        self.packet_rate = 0.0

        # Biến lọc (Filters)
        self.dir_filter_var = tk.StringVar(value="ALL")          # ALL, C2S, S2C
        self.hide_ping_var = tk.BooleanVar(value=True)           # Bỏ qua 0x08
        self.hide_move_var = tk.BooleanVar(value=True)           # Bỏ qua 0x32, 0x33, 0x34
        self.only_party_var = tk.BooleanVar(value=False)         # Chỉ hiện 0x07, 0x0D
        self.only_chat_var = tk.BooleanVar(value=False)          # Chỉ hiện 0x14
        self.search_var = tk.StringVar(value="")                 # Tìm kiếm
        self.opcode_filter_var = tk.StringVar(value="")          # Lọc opcode tùy chọn

        self.setup_styles()
        self.create_header()
        self.create_client_dock()
        self.create_filter_toolbar()
        self.create_main_content()
        self.create_status_bar()

        # Quét tiến trình ngay khi mở
        self.scan_processes()

        # Bắt đầu vòng lặp xử lý sự kiện
        self.root.after(40, self.process_event_queue)
        self.root.after(1000, self.update_statistics)

        # Xử lý đóng cửa sổ an toàn
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=THEME["bg_main"], foreground=THEME["text_main"], font=("Segoe UI", 10))
        style.configure("Card.TFrame", background=THEME["bg_card"], relief="flat")
        style.configure("Dark.TFrame", background=THEME["bg_dark"], relief="flat")

        # Treeview Bảng gói tin
        style.configure("Packet.Treeview",
                        background=THEME["bg_input"],
                        foreground=THEME["text_main"],
                        fieldbackground=THEME["bg_input"],
                        font=("Segoe UI", 9),
                        rowheight=24)
        style.map("Packet.Treeview",
                  background=[("selected", THEME["bg_selected"])],
                  foreground=[("selected", "#ffffff")])

        style.configure("Treeview.Heading",
                        background=THEME["bg_dark"],
                        foreground=THEME["text_main"],
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview.Heading", background=[("active", THEME["bg_hover"])])

        # Scrollbar
        style.configure("Vertical.TScrollbar", background=THEME["bg_card"], troughcolor=THEME["bg_dark"])

    def create_header(self):
        header = tk.Frame(self.root, bg=THEME["bg_dark"], height=50)
        header.pack(fill=tk.X, side=tk.TOP)

        title_lbl = tk.Label(header, text="⚡ WLO PACKET STUDIO", font=("Segoe UI", 14, "bold"),
                             fg=THEME["primary"], bg=THEME["bg_dark"])
        title_lbl.pack(side=tk.LEFT, padx=15, pady=8)

        subtitle_lbl = tk.Label(header, text="Multi-Client Real-Time Packet Sniffer & Deep Dissector",
                                font=("Segoe UI", 9, "italic"), fg=THEME["text_muted"], bg=THEME["bg_dark"])
        subtitle_lbl.pack(side=tk.LEFT, pady=10)

        # Huy hiệu trạng thái bên phải
        self.badge_rate = tk.Label(header, text="Tốc độ: 0 pkt/s", font=("Consolas", 9, "bold"),
                                   fg=THEME["yellow"], bg=THEME["bg_card"], padx=10, pady=3)
        self.badge_rate.pack(side=tk.RIGHT, padx=(5, 15), pady=10)

        self.badge_count = tk.Label(header, text="Đã bắt: 0 gói", font=("Consolas", 9, "bold"),
                                    fg=THEME["green"], bg=THEME["bg_card"], padx=10, pady=3)
        self.badge_count.pack(side=tk.RIGHT, padx=5, pady=10)

    def create_client_dock(self):
        dock_frame = tk.LabelFrame(self.root, text=" 🎮 Quản Lý Tiến Trình Game (Client Dock) ",
                                   font=("Segoe UI", 10, "bold"), fg=THEME["gold"],
                                   bg=THEME["bg_card"], padx=10, pady=8)
        dock_frame.pack(fill=tk.X, padx=10, pady=(6, 4))

        # Toolbar điều khiển dock
        btn_bar = tk.Frame(dock_frame, bg=THEME["bg_card"])
        btn_bar.pack(fill=tk.X, side=tk.TOP, pady=(0, 6))

        tk.Button(btn_bar, text="🔄 Quét lại Client", font=("Segoe UI", 9, "bold"),
                  bg=THEME["primary"], fg=THEME["bg_dark"], activebackground=THEME["primary_hover"],
                  command=self.scan_processes, relief="flat", padx=10, pady=3, cursor="hand2").pack(side=tk.LEFT, padx=4)

        tk.Button(btn_bar, text="▶ Bắt đầu Hook Đã Chọn", font=("Segoe UI", 9, "bold"),
                  bg=THEME["green"], fg=THEME["bg_dark"], activebackground="#c6f4be",
                  command=self.hook_selected_clients, relief="flat", padx=10, pady=3, cursor="hand2").pack(side=tk.LEFT, padx=4)

        tk.Button(btn_bar, text="⏹ Ngắt Hook Tất Cả", font=("Segoe UI", 9, "bold"),
                  bg=THEME["red"], fg="#ffffff", activebackground="#f5a0b7",
                  command=self.unhook_all_clients, relief="flat", padx=10, pady=3, cursor="hand2").pack(side=tk.LEFT, padx=4)

        tk.Button(btn_bar, text="➕ Thêm PID Thủ Công", font=("Segoe UI", 9),
                  bg=THEME["bg_input"], fg=THEME["text_main"],
                  command=self.add_manual_pid, relief="flat", padx=10, pady=3, cursor="hand2").pack(side=tk.LEFT, padx=4)

        self.lbl_dock_info = tk.Label(btn_bar, text="Đang quét...", font=("Segoe UI", 9),
                                      fg=THEME["text_muted"], bg=THEME["bg_card"])
        self.lbl_dock_info.pack(side=tk.RIGHT, padx=5)

        # Khung chứa danh sách client (Cards container)
        self.clients_container = tk.Frame(dock_frame, bg=THEME["bg_card"])
        self.clients_container.pack(fill=tk.X, side=tk.TOP)
        self.client_widgets = {}  # pid -> {chk_var, lbl_status, lbl_count, ...}

    def create_filter_toolbar(self):
        fbar = tk.LabelFrame(self.root, text=" 🔍 Bộ Lọc & Tìm Kiếm Thông Minh ",
                             font=("Segoe UI", 10, "bold"), fg=THEME["cyan"],
                             bg=THEME["bg_card"], padx=10, pady=6)
        fbar.pack(fill=tk.X, padx=10, pady=4)

        # Hàng 1: Hướng và Checkbox Presets
        r1 = tk.Frame(fbar, bg=THEME["bg_card"])
        r1.pack(fill=tk.X, side=tk.TOP, pady=2)

        tk.Label(r1, text="Chiều:", font=("Segoe UI", 9, "bold"), fg=THEME["text_main"], bg=THEME["bg_card"]).pack(side=tk.LEFT, padx=(0, 4))
        for text, val in [("Tất cả", "ALL"), ("C->S (Gửi)", "C2S"), ("S->C (Nhận)", "S2C")]:
            rb = tk.Radiobutton(r1, text=text, variable=self.dir_filter_var, value=val,
                                bg=THEME["bg_card"], fg=THEME["text_main"], selectcolor=THEME["bg_input"],
                                activebackground=THEME["bg_card"], activeforeground=THEME["primary"],
                                command=self.apply_filters)
            rb.pack(side=tk.LEFT, padx=4)

        # Phân cách dọc
        tk.Label(r1, text="|", fg=THEME["border"], bg=THEME["bg_card"]).pack(side=tk.LEFT, padx=8)

        # Presets nhanh
        chk_ping = tk.Checkbutton(r1, text="Ẩn Ping 0x08", variable=self.hide_ping_var,
                                  bg=THEME["bg_card"], fg=THEME["text_main"], selectcolor=THEME["bg_input"],
                                  activebackground=THEME["bg_card"], activeforeground=THEME["green"],
                                  command=self.apply_filters)
        chk_ping.pack(side=tk.LEFT, padx=4)

        chk_move = tk.Checkbutton(r1, text="Ẩn Di chuyển (0x32/33)", variable=self.hide_move_var,
                                  bg=THEME["bg_card"], fg=THEME["text_main"], selectcolor=THEME["bg_input"],
                                  activebackground=THEME["bg_card"], activeforeground=THEME["cyan"],
                                  command=self.apply_filters)
        chk_move.pack(side=tk.LEFT, padx=4)

        chk_party = tk.Checkbutton(r1, text="★ Chỉ Tổ Đội (0x07, 0x0D)", variable=self.only_party_var,
                                   bg=THEME["bg_card"], fg=THEME["green"], selectcolor=THEME["bg_input"],
                                   activebackground=THEME["bg_card"], activeforeground=THEME["green"],
                                   command=self.apply_filters)
        chk_party.pack(side=tk.LEFT, padx=4)

        chk_chat = tk.Checkbutton(r1, text="💬 Chỉ Chat (0x14)", variable=self.only_chat_var,
                                  bg=THEME["bg_card"], fg=THEME["yellow"], selectcolor=THEME["bg_input"],
                                  activebackground=THEME["bg_card"], activeforeground=THEME["yellow"],
                                  command=self.apply_filters)
        chk_chat.pack(side=tk.LEFT, padx=4)

        # Các nút tác vụ nhanh bên phải hàng 1
        self.btn_autoscroll = tk.Button(r1, text="⏸ Cuộn: BẬT", font=("Segoe UI", 9, "bold"),
                                        bg=THEME["bg_input"], fg=THEME["green"],
                                        command=self.toggle_autoscroll, relief="flat", padx=8, pady=2, cursor="hand2")
        self.btn_autoscroll.pack(side=tk.RIGHT, padx=4)

        tk.Button(r1, text="🗑 Xóa Danh Sách", font=("Segoe UI", 9),
                  bg=THEME["bg_input"], fg=THEME["text_main"],
                  command=self.clear_packets, relief="flat", padx=8, pady=2, cursor="hand2").pack(side=tk.RIGHT, padx=4)

        tk.Button(r1, text="💾 Xuất File...", font=("Segoe UI", 9),
                  bg=THEME["bg_input"], fg=THEME["primary"],
                  command=self.export_packets_dialog, relief="flat", padx=8, pady=2, cursor="hand2").pack(side=tk.RIGHT, padx=4)

        # Hàng 2: Tìm kiếm & Lọc Opcode
        r2 = tk.Frame(fbar, bg=THEME["bg_card"])
        r2.pack(fill=tk.X, side=tk.TOP, pady=(4, 0))

        tk.Label(r2, text="Lọc Opcode:", font=("Segoe UI", 9), fg=THEME["text_main"], bg=THEME["bg_card"]).pack(side=tk.LEFT, padx=(0, 4))
        self.ent_opcode = tk.Entry(r2, textvariable=self.opcode_filter_var, font=("Consolas", 9),
                                   bg=THEME["bg_input"], fg=THEME["text_main"], insertbackground="#ffffff",
                                   relief="flat", width=18)
        self.ent_opcode.pack(side=tk.LEFT, padx=4)
        self.ent_opcode.bind("<KeyRelease>", lambda e: self.apply_filters())

        tk.Label(r2, text="(VD: 0x07, 0x0D)", font=("Segoe UI", 8, "italic"), fg=THEME["text_muted"], bg=THEME["bg_card"]).pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(r2, text="Tìm kiếm (Text/Hex):", font=("Segoe UI", 9), fg=THEME["text_main"], bg=THEME["bg_card"]).pack(side=tk.LEFT, padx=(0, 4))
        self.ent_search = tk.Entry(r2, textvariable=self.search_var, font=("Segoe UI", 9),
                                   bg=THEME["bg_input"], fg=THEME["text_main"], insertbackground="#ffffff",
                                   relief="flat", width=28)
        self.ent_search.pack(side=tk.LEFT, padx=4)
        self.ent_search.bind("<KeyRelease>", lambda e: self.apply_filters())

        tk.Button(r2, text="✕", font=("Segoe UI", 8, "bold"), bg=THEME["bg_input"], fg=THEME["text_muted"],
                  command=self.clear_search, relief="flat", padx=6, pady=1, cursor="hand2").pack(side=tk.LEFT, padx=2)

    def create_main_content(self):
        # PanedWindow chia đôi trên/dưới
        self.paned = tk.PanedWindow(self.root, orient=tk.VERTICAL, bg=THEME["border"], sashwidth=4, sashrelief="flat")
        self.paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 2))

        # Khung trên: Bảng danh sách gói tin (Packet Table)
        top_frame = tk.Frame(self.paned, bg=THEME["bg_card"])
        self.paned.add(top_frame, height=360)

        cols = ("seq", "time", "proc", "dir", "opcode", "name", "sub", "len", "summary")
        self.tree_packets = ttk.Treeview(top_frame, columns=cols, show="headings",
                                         style="Packet.Treeview", selectmode="browse")

        self.tree_packets.heading("seq", text="#")
        self.tree_packets.heading("time", text="Thời gian")
        self.tree_packets.heading("proc", text="Tiến trình")
        self.tree_packets.heading("dir", text="Hướng")
        self.tree_packets.heading("opcode", text="Opcode")
        self.tree_packets.heading("name", text="Tên Gói Tin")
        self.tree_packets.heading("sub", text="Sub")
        self.tree_packets.heading("len", text="Len")
        self.tree_packets.heading("summary", text="Tóm tắt & Nội dung bóc tách")

        self.tree_packets.column("seq", width=50, anchor=tk.CENTER)
        self.tree_packets.column("time", width=95, anchor=tk.CENTER)
        self.tree_packets.column("proc", width=115, anchor=tk.W)
        self.tree_packets.column("dir", width=55, anchor=tk.CENTER)
        self.tree_packets.column("opcode", width=65, anchor=tk.CENTER)
        self.tree_packets.column("name", width=150, anchor=tk.W)
        self.tree_packets.column("sub", width=55, anchor=tk.CENTER)
        self.tree_packets.column("len", width=45, anchor=tk.CENTER)
        self.tree_packets.column("summary", width=600, anchor=tk.W)

        # Cấu hình màu cho từng loại gói (Category Tags)
        self.tree_packets.tag_configure("party", background="#1b2e24", foreground="#a6e3a1")     # Xanh lá đậm
        self.tree_packets.tag_configure("chat", background="#2a271b", foreground="#f9e2af")      # Vàng đậm
        self.tree_packets.tag_configure("move", background="#182333", foreground="#89dceb")      # Cyan đậm
        self.tree_packets.tag_configure("combat", background="#251b30", foreground="#cba6f7")    # Tím đậm
        self.tree_packets.tag_configure("login", background="#2b2318", foreground="#fab387")     # Cam đậm
        self.tree_packets.tag_configure("ping", background="#1e1e2e", foreground="#6c7086")      # Xám
        self.tree_packets.tag_configure("misc", background="#1e1e2e", foreground="#cdd6f4")      # Bình thường

        sb_y = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.tree_packets.yview)
        sb_x = ttk.Scrollbar(top_frame, orient=tk.HORIZONTAL, command=self.tree_packets.xview)
        self.tree_packets.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)

        sb_y.pack(side=tk.RIGHT, fill=tk.Y)
        sb_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_packets.pack(fill=tk.BOTH, expand=True)

        self.tree_packets.bind("<<TreeviewSelect>>", self.on_packet_selected)

        # Khung dưới: Deep Packet Inspector (Chia làm 2 cột: Trái là Cây bóc tách, Phải là Hex Dump)
        bottom_frame = tk.Frame(self.paned, bg=THEME["bg_card"])
        self.paned.add(bottom_frame, height=220)

        paned_bottom = tk.PanedWindow(bottom_frame, orient=tk.HORIZONTAL, bg=THEME["border"], sashwidth=4)
        paned_bottom.pack(fill=tk.BOTH, expand=True)

        # Cột Trái: Cây phân tích bóc tách (Dissection Tree)
        frame_tree = tk.LabelFrame(paned_bottom, text=" 🌲 Cây Phân Tích Cấu Trúc (Dissection Tree) ",
                                   font=("Segoe UI", 9, "bold"), fg=THEME["primary"],
                                   bg=THEME["bg_card"], padx=6, pady=4)
        paned_bottom.add(frame_tree, width=540)

        self.tree_inspect = ttk.Treeview(frame_tree, columns=("val",), show="tree headings",
                                         style="Packet.Treeview")
        self.tree_inspect.heading("#0", text="Trường / Cấu trúc")
        self.tree_inspect.heading("val", text="Giá trị")
        self.tree_inspect.column("#0", width=220, anchor=tk.W)
        self.tree_inspect.column("val", width=280, anchor=tk.W)

        sb_it_y = ttk.Scrollbar(frame_tree, orient=tk.VERTICAL, command=self.tree_inspect.yview)
        self.tree_inspect.configure(yscrollcommand=sb_it_y.set)
        sb_it_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_inspect.pack(fill=tk.BOTH, expand=True)

        # Cột Phải: Hex Dump & Action Buttons
        frame_hex = tk.LabelFrame(paned_bottom, text=" 💾 Bảng Hex View (16-Bytes Offset & ASCII) ",
                                  font=("Segoe UI", 9, "bold"), fg=THEME["gold"],
                                  bg=THEME["bg_card"], padx=6, pady=4)
        paned_bottom.add(frame_hex, width=680)

        # Toolbar Hex
        hex_btn_bar = tk.Frame(frame_hex, bg=THEME["bg_card"])
        hex_btn_bar.pack(fill=tk.X, side=tk.TOP, pady=(0, 4))

        tk.Button(hex_btn_bar, text="📋 Copy Raw Hex", font=("Segoe UI", 8),
                  bg=THEME["bg_input"], fg=THEME["text_main"],
                  command=self.copy_raw_hex, relief="flat", padx=6, pady=1, cursor="hand2").pack(side=tk.LEFT, padx=3)

        tk.Button(hex_btn_bar, text="📋 Copy Python bytes", font=("Segoe UI", 8),
                  bg=THEME["bg_input"], fg=THEME["text_main"],
                  command=self.copy_python_bytes, relief="flat", padx=6, pady=1, cursor="hand2").pack(side=tk.LEFT, padx=3)

        tk.Button(hex_btn_bar, text="⚡ Gửi Lại Gói Tin (Replay)", font=("Segoe UI", 8, "bold"),
                  bg=THEME["primary"], fg=THEME["bg_dark"],
                  command=self.replay_packet_dialog, relief="flat", padx=8, pady=1, cursor="hand2").pack(side=tk.RIGHT, padx=3)

        self.txt_hex = ScrolledText(frame_hex, font=("Consolas", 9),
                                    bg=THEME["bg_dark"], fg="#a6e3a1", insertbackground="#ffffff",
                                    relief="flat", wrap=tk.NONE)
        self.txt_hex.pack(fill=tk.BOTH, expand=True)

    def create_status_bar(self):
        sbar = tk.Frame(self.root, bg=THEME["bg_dark"], height=26)
        sbar.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_status = tk.Label(sbar, text="Sẵn sàng.", font=("Segoe UI", 9),
                                   fg=THEME["text_muted"], bg=THEME["bg_dark"])
        self.lbl_status.pack(side=tk.LEFT, padx=12, pady=3)

        self.lbl_filter_stat = tk.Label(sbar, text="Hiển thị: 0 / 0 gói tin", font=("Segoe UI", 9),
                                        fg=THEME["text_muted"], bg=THEME["bg_dark"])
        self.lbl_filter_stat.pack(side=tk.RIGHT, padx=15, pady=3)

    # ==========================================================================
    # QUẢN LÝ TIẾN TRÌNH CLIENT
    # ==========================================================================
    def scan_processes(self):
        """Quét toàn bộ tiến trình alogin*.exe đang chạy trên Windows."""
        for w in self.clients_container.winfo_children():
            w.destroy()
        self.client_widgets.clear()

        if not frida:
            self.lbl_dock_info.config(text="[!] Lỗi: Chưa cài đặt thư viện Frida", fg=THEME["red"])
            return

        try:
            dev = frida.get_local_device()
            procs = dev.enumerate_processes()
        except Exception as e:
            self.lbl_dock_info.config(text=f"[!] Lỗi Frida: {e}", fg=THEME["red"])
            return

        found_clients = []
        for p in procs:
            name_lower = p.name.lower()
            if "alogin" in name_lower or name_lower.startswith("wlo"):
                found_clients.append(p)

        # Sắp xếp theo tên
        found_clients.sort(key=lambda x: x.name.lower())

        if not found_clients:
            self.lbl_dock_info.config(text="Không tìm thấy client alogin*.exe nào đang mở.", fg=THEME["yellow"])
            empty_lbl = tk.Label(self.clients_container, text="(Không có client alogin nào. Hãy mở game hoặc bấm 'Thêm PID Thủ Công')",
                                 font=("Segoe UI", 9, "italic"), fg=THEME["text_muted"], bg=THEME["bg_card"])
            empty_lbl.pack(pady=4)
            return

        self.lbl_dock_info.config(text=f"Tìm thấy {len(found_clients)} client WLO:", fg=THEME["green"])

        # Tạo thẻ Card cho từng client
        for p in found_clients:
            self.add_client_card(p.pid, p.name)

    def add_client_card(self, pid, name):
        if pid in self.client_widgets:
            return

        card = tk.Frame(self.clients_container, bg=THEME["bg_input"], padx=8, pady=4, relief="ridge")
        card.pack(side=tk.LEFT, padx=5, pady=3)

        chk_var = tk.BooleanVar(value=True)
        chk = tk.Checkbutton(card, text=f"{name}", variable=chk_var,
                             font=("Segoe UI", 9, "bold"), fg=THEME["text_main"],
                             bg=THEME["bg_input"], selectcolor=THEME["bg_dark"],
                             activebackground=THEME["bg_input"], activeforeground=THEME["primary"])
        chk.pack(side=tk.LEFT, padx=(0, 4))

        lbl_pid = tk.Label(card, text=f"(PID: {pid})", font=("Consolas", 8),
                           fg=THEME["text_muted"], bg=THEME["bg_input"])
        lbl_pid.pack(side=tk.LEFT, padx=(0, 6))

        # Node sniffer
        if pid not in self.nodes:
            self.nodes[pid] = ClientSnifferNode(name, pid, self.event_queue)
        node = self.nodes[pid]

        status_text = "Đã Hook" if node.is_hooked else "Chưa Hook"
        status_fg = THEME["green"] if node.is_hooked else THEME["yellow"]
        lbl_status = tk.Label(card, text=status_text, font=("Segoe UI", 8, "bold"),
                              fg=status_fg, bg=THEME["bg_dark"], padx=6, pady=1)
        lbl_status.pack(side=tk.LEFT, padx=(0, 4))

        lbl_count = tk.Label(card, text=f"0 pkt", font=("Consolas", 8),
                             fg=THEME["cyan"], bg=THEME["bg_input"])
        lbl_count.pack(side=tk.LEFT)

        self.client_widgets[pid] = {
            "chk_var": chk_var,
            "lbl_status": lbl_status,
            "lbl_count": lbl_count,
            "proc_name": name,
            "card": card
        }

    def add_manual_pid(self):
        val = simpledialog.askstring("Thêm PID Thủ Công", "Nhập PID hoặc Tên tiến trình cần hook:")
        if not val:
            return
        val = val.strip()
        try:
            pid = int(val)
            name = f"Process_{pid}"
            self.add_client_card(pid, name)
            self.lbl_dock_info.config(text=f"Đã thêm PID {pid} thủ công", fg=THEME["green"])
        except ValueError:
            messagebox.showerror("Lỗi", "Vui lòng nhập số PID hợp lệ!")

    def hook_selected_clients(self):
        """Bắt đầu tiêm Frida vào các client được chọn."""
        if not frida:
            messagebox.showerror("Lỗi", "Thư viện Frida chưa được cài đặt!")
            return

        success_count = 0
        for pid, widgets in self.client_widgets.items():
            if widgets["chk_var"].get():
                node = self.nodes[pid]
                if not node.is_hooked:
                    if node.start():
                        widgets["lbl_status"].config(text="Đang Bắt", fg=THEME["green"])
                        success_count += 1
                    else:
                        widgets["lbl_status"].config(text="Lỗi", fg=THEME["red"])
                        messagebox.showwarning("Lỗi Hook", f"Không thể hook PID {pid} ({node.proc_name}):\n{node.error_message}")
                else:
                    success_count += 1

        self.lbl_status.config(text=f"Đã kích hoạt hook trên {success_count} client.")

    def unhook_all_clients(self):
        """Dừng tất cả các hook."""
        for pid, node in self.nodes.items():
            node.stop()
            if pid in self.client_widgets:
                self.client_widgets[pid]["lbl_status"].config(text="Chưa Hook", fg=THEME["yellow"])
        self.lbl_status.config(text="Đã ngắt kết nối hook trên tất cả client.")

    # ==========================================================================
    # XỬ LÝ SỰ KIỆN GÓI TIN & GIAO DIỆN
    # ==========================================================================
    def process_event_queue(self):
        """Rút các gói tin từ hàng đợi đa luồng và cập nhật Treeview theo batch."""
        max_batch = 50
        count = 0

        while not self.event_queue.empty() and count < max_batch:
            try:
                ev_type, ev_data = self.event_queue.get_nowait()
            except queue.Empty:
                break

            if ev_type == "PACKET":
                self.packet_seq += 1
                self.total_captured += 1
                ev_data["seq"] = self.packet_seq
                self.packets.append(ev_data)

                # Cập nhật số gói của widget client
                pid = ev_data["pid"]
                if pid in self.client_widgets:
                    count_pkt = self.nodes[pid].packet_count
                    self.client_widgets[pid]["lbl_count"].config(text=f"{count_pkt} pkt")

                # Kiểm tra bộ lọc
                if self.packet_matches_filter(ev_data):
                    self.insert_packet_row(ev_data)
                    self.displayed_count += 1

                count += 1

            elif ev_type == "ERROR":
                pass

        # Giới hạn số lượng hiển thị trong Treeview nếu quá lớn (> 5000)
        children = self.tree_packets.get_children()
        if len(children) > 5000:
            for item in children[:500]:
                self.tree_packets.delete(item)

        # Lập lịch chu kỳ tiếp theo
        self.root.after(35, self.process_event_queue)

    def packet_matches_filter(self, pkt):
        """Kiểm tra một gói tin có thỏa mãn toàn bộ bộ lọc hay không."""
        # 1. Hướng
        dir_filter = self.dir_filter_var.get()
        if dir_filter == "C2S" and pkt["dir"] != "C->S":
            return False
        if dir_filter == "S2C" and pkt["dir"] != "S->C":
            return False

        # 2. Ẩn Ping 0x08
        if self.hide_ping_var.get() and pkt["opcode"] == 0x08:
            return False

        # 3. Ẩn Di chuyển 0x32, 0x33, 0x34
        if self.hide_move_var.get() and pkt["opcode"] in (0x32, 0x33, 0x34):
            return False

        # 4. Chỉ Tổ Đội (0x07, 0x0D, 0x1A)
        if self.only_party_var.get() and pkt["opcode"] not in (0x07, 0x0D, 0x1A):
            return False

        # 5. Chỉ Chat (0x14)
        if self.only_chat_var.get() and pkt["opcode"] != 0x14:
            return False

        # 6. Lọc Opcode tùy chọn (VD: 0x07, 0x0D)
        op_str = self.opcode_filter_var.get().strip()
        if op_str:
            targets = []
            for part in op_str.split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    targets.append(int(part, 16) if part.lower().startswith("0x") else int(part))
                except ValueError:
                    pass
            if targets and pkt["opcode"] not in targets:
                return False

        # 7. Tìm kiếm chuỗi văn bản hoặc Hex
        query = self.search_var.get().strip().lower()
        if query:
            match_found = False
            # Tìm trong summary
            if query in pkt["summary"].lower():
                match_found = True
            # Tìm trong tên client
            elif query in pkt["proc_name"].lower():
                match_found = True
            # Tìm trong tên opcode
            elif query in OPCODE_NAMES.get(pkt["opcode"], "").lower():
                match_found = True
            # Tìm trong chuỗi Hex
            elif query in pkt["data"].hex().lower():
                match_found = True
            if not match_found:
                return False

        return True

    def insert_packet_row(self, pkt):
        op_hex = f"0x{pkt['opcode']:02X}" if pkt["opcode"] is not None else "--"
        sub_hex = f"0x{pkt['subcode']:02X}" if pkt["subcode"] is not None else "--"
        op_name = OPCODE_NAMES.get(pkt["opcode"], op_hex)

        item_id = self.tree_packets.insert("", tk.END, values=(
            pkt["seq"],
            pkt["time"],
            pkt["proc_name"],
            pkt["dir"],
            op_hex,
            op_name,
            sub_hex,
            pkt["length"],
            pkt["summary"]
        ), tags=(pkt["category"],))

        if self.is_auto_scroll:
            self.tree_packets.see(item_id)

    def apply_filters(self):
        """Lọc lại toàn bộ danh sách gói tin đã lưu trong bộ nhớ."""
        self.tree_packets.delete(*self.tree_packets.get_children())
        self.displayed_count = 0
        for pkt in self.packets:
            if self.packet_matches_filter(pkt):
                self.insert_packet_row(pkt)
                self.displayed_count += 1
        self.lbl_filter_stat.config(text=f"Hiển thị: {self.displayed_count} / {self.total_captured} gói tin")

    def clear_search(self):
        self.search_var.set("")
        self.apply_filters()

    def toggle_autoscroll(self):
        self.is_auto_scroll = not self.is_auto_scroll
        if self.is_auto_scroll:
            self.btn_autoscroll.config(text="⏸ Cuộn: BẬT", fg=THEME["green"])
        else:
            self.btn_autoscroll.config(text="▶ Cuộn: TẮT", fg=THEME["yellow"])

    def clear_packets(self):
        self.tree_packets.delete(*self.tree_packets.get_children())
        self.packets.clear()
        self.packet_seq = 0
        self.total_captured = 0
        self.displayed_count = 0
        self.tree_inspect.delete(*self.tree_inspect.get_children())
        self.txt_hex.delete("1.0", tk.END)
        self.selected_packet = None
        self.lbl_filter_stat.config(text="Hiển thị: 0 / 0 gói tin")
        self.badge_count.config(text="Đã bắt: 0 gói")

    # ==========================================================================
    # CHI TIẾT GÓI TIN & HEX VIEW (INSPECTOR PANE)
    # ==========================================================================
    def on_packet_selected(self, event):
        sel = self.tree_packets.selection()
        if not sel:
            return
        item = self.tree_packets.item(sel[0])
        seq = item["values"][0]

        # Tìm gói tin theo seq
        pkt = next((p for p in self.packets if p["seq"] == seq), None)
        if not pkt:
            return
        self.selected_packet = pkt

        # Cập nhật Cây bóc tách (Tree Inspector)
        self.tree_inspect.delete(*self.tree_inspect.get_children())

        # 1. Header Frame
        raw_bytes = pkt["raw_decrypted"]
        r_header = self.tree_inspect.insert("", tk.END, text="▼ Tiêu đề gói tin (WLO Header)", open=True)
        self.tree_inspect.insert(r_header, tk.END, text="Magic Header", values=("0xF444 (Little-Endian: 44 F4)",))
        self.tree_inspect.insert(r_header, tk.END, text="Tổng độ dài gói", values=(f"{len(raw_bytes)} bytes",))
        self.tree_inspect.insert(r_header, tk.END, text="Độ dài Payload", values=(f"{len(raw_bytes) - 4} bytes",))

        # 2. Protocol Body
        r_proto = self.tree_inspect.insert("", tk.END, text="▼ Giao thức WLO (Protocol Body)", open=True)
        op_hex = f"0x{pkt['opcode']:02X}" if pkt["opcode"] is not None else "--"
        op_name = OPCODE_NAMES.get(pkt["opcode"], "UNKNOWN")
        self.tree_inspect.insert(r_proto, tk.END, text="Mã lệnh chính (Opcode)", values=(f"{op_hex} ({op_name})",))

        sub_hex = f"0x{pkt['subcode']:02X}" if pkt["subcode"] is not None else "--"
        self.tree_inspect.insert(r_proto, tk.END, text="Mã lệnh phụ (Subcode)", values=(sub_hex,))
        self.tree_inspect.insert(r_proto, tk.END, text="Hướng truyền", values=(f"{pkt['dir']} ({'Client gửi' if pkt['dir']=='C->S' else 'Server trả về'})",))
        self.tree_inspect.insert(r_proto, tk.END, text="Client / Tiến trình", values=(f"{pkt['proc_name']} (PID {pkt['pid']})",))

        # 3. Dissected Fields
        if pkt["fields"]:
            r_fields = self.tree_inspect.insert("", tk.END, text="▼ Các trường dữ liệu bóc tách (Dissected Fields)", open=True)
            for fname, fval in pkt["fields"]:
                self.tree_inspect.insert(r_fields, tk.END, text=fname, values=(fval,))

        # Cập nhật Hex View (16 bytes offset kiểu Wireshark)
        self.update_hex_view(raw_bytes)

    def update_hex_view(self, raw_bytes):
        self.txt_hex.delete("1.0", tk.END)
        lines = []
        for i in range(0, len(raw_bytes), 16):
            chunk = raw_bytes[i:i+16]
            hex_part1 = " ".join(f"{b:02X}" for b in chunk[:8])
            hex_part2 = " ".join(f"{b:02X}" for b in chunk[8:])
            hex_str = f"{hex_part1:<23}  {hex_part2:<23}".rstrip()

            # ASCII / Big5 representation
            ascii_chars = []
            for b in chunk:
                if 32 <= b <= 126:
                    ascii_chars.append(chr(b))
                else:
                    ascii_chars.append(".")
            ascii_str = "".join(ascii_chars)

            lines.append(f"{i:04X}   {hex_str:<50}  |{ascii_str}|")

        self.txt_hex.insert(tk.END, "\n".join(lines))

    def copy_raw_hex(self):
        if not self.selected_packet:
            return
        hex_str = self.selected_packet["raw_decrypted"].hex().upper()
        self.root.clipboard_clear()
        self.root.clipboard_append(hex_str)
        self.lbl_status.config(text="Đã sao chép Raw Hex vào clipboard!")

    def copy_python_bytes(self):
        if not self.selected_packet:
            return
        raw = self.selected_packet["raw_decrypted"]
        py_str = f"bytes.fromhex('{raw.hex()}')"
        self.root.clipboard_clear()
        self.root.clipboard_append(py_str)
        self.lbl_status.config(text="Đã sao chép Python bytes vào clipboard!")

    # ==========================================================================
    # GỬI LẠI GÓI TIN (PACKET REPLAY / INJECTOR)
    # ==========================================================================
    def replay_packet_dialog(self):
        if not self.selected_packet:
            messagebox.showinfo("Thông báo", "Vui lòng chọn một gói tin trên danh sách để Replay!")
            return

        pkt = self.selected_packet
        dlg = tk.Toplevel(self.root)
        dlg.title("Gửi Lại Gói Tin (Packet Replay / Injector)")
        dlg.geometry("550x380")
        dlg.configure(bg=THEME["bg_card"])
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="⚡ CÔNG CỤ REPLAY & INJECT GÓI TIN", font=("Segoe UI", 11, "bold"),
                 fg=THEME["primary"], bg=THEME["bg_card"]).pack(pady=(12, 4))

        # Chọn Client đích
        f_target = tk.Frame(dlg, bg=THEME["bg_card"])
        f_target.pack(fill=tk.X, padx=20, pady=6)
        tk.Label(f_target, text="Gửi vào Client:", font=("Segoe UI", 9, "bold"),
                 fg=THEME["text_main"], bg=THEME["bg_card"]).pack(side=tk.LEFT)

        hooked_clients = [f"{n.proc_name} (PID {pid})" for pid, n in self.nodes.items() if n.is_hooked]
        if not hooked_clients:
            hooked_clients = ["(Chưa có client nào được hook)"]

        cb_client = ttk.Combobox(f_target, values=hooked_clients, state="readonly", width=35)
        cb_client.current(0)
        cb_client.pack(side=tk.LEFT, padx=10)

        # Body bytes thô (không kèm 0xF444 vì hàm send_packet tự thêm)
        body = pkt["raw_decrypted"][4:]  # Cắt bỏ 4 byte header 0xF444 + Len

        tk.Label(dlg, text="Dữ liệu Body (Hex) [Opcode + Subcode + Data]:", font=("Segoe UI", 9),
                 fg=THEME["text_muted"], bg=THEME["bg_card"], anchor=tk.W).pack(fill=tk.X, padx=20, pady=(6, 2))

        txt_body = tk.Text(dlg, font=("Consolas", 10), bg=THEME["bg_dark"], fg=THEME["yellow"],
                           insertbackground="#ffffff", height=6, relief="flat")
        txt_body.pack(fill=tk.X, padx=20)
        txt_body.insert(tk.END, body.hex())

        lbl_res = tk.Label(dlg, text="", font=("Segoe UI", 9), fg=THEME["green"], bg=THEME["bg_card"])
        lbl_res.pack(pady=6)

        def do_inject():
            raw_hex = txt_body.get("1.0", tk.END).strip().replace(" ", "")
            try:
                b_bytes = bytes.fromhex(raw_hex)
            except ValueError:
                lbl_res.config(text="[!] Lỗi: Chuỗi Hex không hợp lệ!", fg=THEME["red"])
                return

            sel_text = cb_client.get()
            target_node = None
            for pid, node in self.nodes.items():
                if f"PID {pid}" in sel_text:
                    target_node = node
                    break

            if not target_node or not target_node.is_hooked:
                lbl_res.config(text="[!] Client mục tiêu chưa được hook!", fg=THEME["red"])
                return

            res = target_node.send_packet(b_bytes)
            if res.get("success"):
                lbl_res.config(text=f"[+] Đã gửi thành công vào Socket {res.get('sock')}!", fg=THEME["green"])
            else:
                lbl_res.config(text=f"[!] Lỗi khi gửi: {res.get('error')}", fg=THEME["red"])

        btn_box = tk.Frame(dlg, bg=THEME["bg_card"])
        btn_box.pack(pady=10)

        tk.Button(btn_box, text="⚡ GỬI GÓI TIN NGAY", font=("Segoe UI", 10, "bold"),
                  bg=THEME["green"], fg=THEME["bg_dark"], activebackground="#c6f4be",
                  command=do_inject, relief="flat", padx=15, pady=5, cursor="hand2").pack(side=tk.LEFT, padx=6)

        tk.Button(btn_box, text="Đóng", font=("Segoe UI", 9),
                  bg=THEME["bg_input"], fg=THEME["text_main"],
                  command=dlg.destroy, relief="flat", padx=12, pady=5, cursor="hand2").pack(side=tk.LEFT, padx=6)

    # ==========================================================================
    # XUẤT FILE BÁO CÁO (EXPORT)
    # ==========================================================================
    def export_packets_dialog(self):
        if not self.packets:
            messagebox.showinfo("Thông báo", "Không có gói tin nào để xuất!")
            return

        fpath = filedialog.asksaveasfilename(
            title="Lưu Dữ Liệu Bắt Gói",
            defaultextension=".json",
            filetypes=[("JSON File", "*.json"), ("CSV File", "*.csv"), ("Text Log", "*.txt")]
        )
        if not fpath:
            return

        try:
            if fpath.endswith(".json"):
                out_data = []
                for p in self.packets:
                    out_data.append({
                        "seq": p["seq"],
                        "time": p["time"],
                        "proc": p["proc_name"],
                        "pid": p["pid"],
                        "dir": p["dir"],
                        "opcode": f"0x{p['opcode']:02X}" if p["opcode"] is not None else None,
                        "op_name": OPCODE_NAMES.get(p["opcode"], "UNKNOWN"),
                        "subcode": f"0x{p['subcode']:02X}" if p["subcode"] is not None else None,
                        "length": p["length"],
                        "summary": p["summary"],
                        "fields": dict(p["fields"]) if p["fields"] else {},
                        "raw_hex": p["raw_decrypted"].hex()
                    })
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(out_data, f, indent=4, ensure_ascii=False)

            elif fpath.endswith(".csv"):
                with open(fpath, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Seq", "Time", "Client", "PID", "Direction", "Opcode", "OpName", "Subcode", "Length", "Summary", "RawHex"])
                    for p in self.packets:
                        writer.writerow([
                            p["seq"], p["time"], p["proc_name"], p["pid"], p["dir"],
                            f"0x{p['opcode']:02X}" if p["opcode"] is not None else "",
                            OPCODE_NAMES.get(p["opcode"], ""),
                            f"0x{p['subcode']:02X}" if p["subcode"] is not None else "",
                            p["length"], p["summary"], p["raw_decrypted"].hex()
                        ])

            else:  # TXT
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(f"=== WLO PACKET CAPTURE EXPORT: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
                    for p in self.packets:
                        op_hex = f"0x{p['opcode']:02X}" if p["opcode"] is not None else "--"
                        sub_hex = f"0x{p['subcode']:02X}" if p["subcode"] is not None else "--"
                        line = (f"[{p['time']}] [{p['proc_name']:<12} | {p['dir']}] "
                                f"Op:{op_hex:<4} Sub:{sub_hex:<4} Len:{p['length']:<3} | {p['summary']} | Hex: {p['raw_decrypted'].hex()}\n")
                        f.write(line)

            messagebox.showinfo("Thành công", f"Đã xuất {len(self.packets)} gói tin ra tệp:\n{fpath}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể lưu tệp: {e}")

    # ==========================================================================
    # CẬP NHẬT THỐNG KÊ (PPS & COUNTERS)
    # ==========================================================================
    def update_statistics(self):
        now = time.time()
        dt = now - self.last_stat_time
        if dt >= 1.0:
            count_diff = self.total_captured - self.last_stat_count
            self.packet_rate = count_diff / dt
            self.last_stat_time = now
            self.last_stat_count = self.total_captured

            self.badge_rate.config(text=f"Tốc độ: {self.packet_rate:.1f} pkt/s")
            self.badge_count.config(text=f"Đã bắt: {self.total_captured} gói")
            self.lbl_filter_stat.config(text=f"Hiển thị: {self.displayed_count} / {self.total_captured} gói tin")

        self.root.after(1000, self.update_statistics)

    def on_close(self):
        self.unhook_all_clients()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = WLOPacketStudioGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
