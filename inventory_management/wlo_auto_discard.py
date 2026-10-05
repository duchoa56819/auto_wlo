#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO Smart Auto-Discard & Cleaner (Frida-based)
==============================================
Công cụ tự động phát hiện và vứt các vật phẩm rác trong Wonderland Online (WLO).
Tính năng chính:
1. CƠ CHẾ WPE PRO SIÊU TỐC & AN TOÀN TUYỆT ĐỐI (POPUP AUTO-CONFIRM):
   - Khi bạn kéo vứt bất kỳ vật phẩm rác nào trong game, Server hiện popup xác nhận (Sub: 0xD4).
   - Nếu món đồ đã có trong Blacklist, script lập tức gửi lệnh xác nhận (Sub: 0x7C) trong 0.04s!
   - Popup biến mất tức thì, không cần bấm chuột xác nhận.
   - Hoàn toàn chính xác vì ô đồ (slot) và mã vật phẩm do chính Server trả về.
2. HỌC BLACKLIST TRỰC TIẾP TỪ THAO TÁC NGƯỜI CHƠI:
   - Khi bạn vứt một món đồ mới trong game, console lập tức hỏi:
     "Có muốn thêm vật phẩm này vào Blacklist không? [1] Có  [0] Không"
   - Nhập [1] -> Đặt tên cho món đồ -> Lưu vĩnh viễn vào Blacklist!
3. TUYỆT ĐỐI KHÔNG DÙNG ITEM.DAT / KHÔNG DÙNG CÔNG THỨC LỆCH:
   - Không đọc file Item.Dat, không nạp bất kỳ tên hay ID ảo nào.
   - Nhận diện vật phẩm 100% bằng mã 2-byte nguyên bản từ Server (VD: 0x84D8, 0x8525).
   - Chỉ hiển thị tên do chính người chơi tự đặt. Nếu chưa đặt tên, hiển thị Mã_0xXXXX.
4. QUÉT TÚI ĐỒ BỘ NHỚ DELPHI THẬT:
   - Tự động nhận diện mảng túi đồ 50 ô thật của game trong bộ nhớ.
   - Xác định chính xác ô trống đầu tiên (First Empty Slot), không bao giờ vứt bừa vào ô có sẵn đồ!
5. AN TOÀN MỞ HỘP (CONTAINER SAFETY):
   - Mặc định chế độ tự vứt khi mở hộp (auto_discard_on_open) được TẮT để an toàn tuyệt đối.
   - Nếu bạn bật lên, script sẽ quét ô trống thực tế trước khi mở, tuyệt đối không đoán mò slot!
"""

import os
import sys
import time
import json
import queue
import struct
import signal
import argparse
import threading
from datetime import datetime

# Tránh lỗi bảng mã hiển thị trên console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    print("[!] Chưa cài đặt thư viện frida. Vui lòng chạy lệnh: pip install frida")
    sys.exit(1)

# ==============================================================================
# MÀU SẮC ANSI CHO CONSOLE
# ==============================================================================
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    CYAN = "\033[96m"      # Gửi C->S
    YELLOW = "\033[93m"    # Nhận S->C
    GREEN = "\033[92m"     # Thành công / Giữ đồ
    RED = "\033[91m"       # Cảnh báo / Vứt đồ
    MAGENTA = "\033[95m"   # Hành động / Mở đồ
    BLUE = "\033[94m"      # Tiêu đề
    GRAY = "\033[90m"      # Chi tiết phụ

# Bảng mã Opcode cơ bản để ghi log
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

# TUYỆT ĐỐI KHÔNG DÙNG ITEM.DAT - BẢNG ĐỂ TRỐNG HOÀN TOÀN
USER_KNOWN_ITEMS = {}

def format_item_code(code_int):
    """Định dạng mã vật phẩm 2-byte server thành chuỗi chuẩn 0xXXXX."""
    return f"0x{code_int:04X}"

def parse_code_input(user_str):
    """Chuyển đổi chuỗi nhập liệu (VD: 0x84D8, 84D8, hoặc 34008) thành số nguyên."""
    user_str = user_str.strip()
    if user_str.lower().startswith("0x"):
        return int(user_str, 16)
    if all(c in "0123456789abcdefABCDEF" for c in user_str) and len(user_str) == 4:
        return int(user_str, 16)
    if user_str.isdigit():
        return int(user_str)
    return None

def get_item_display_name(code_int, blacklist_dict=None, database_dict=None):
    """
    Tra cứu tên vật phẩm:
    - 1. Nếu người dùng đã đặt tên trong Blacklist: trả về tên đó.
    - 2. Nếu đã có tên trong cơ sở dữ liệu wlo_items_database.json: trả về tên đó.
    - 3. Tuyệt đối không đoán hay dùng Item.Dat: hiển thị Mã_0xXXXX.
    """
    if code_int is None or code_int == 0:
        return ""
    code_hex = format_item_code(code_int)
    str_int = str(code_int)

    if blacklist_dict:
        if code_hex in blacklist_dict:
            name = blacklist_dict[code_hex].get("name")
            if name:
                return f"{name} ({code_hex})"
        if str_int in blacklist_dict:
            name = blacklist_dict[str_int].get("name")
            if name:
                return f"{name} ({code_hex})"

    if database_dict:
        if code_hex in database_dict:
            name = database_dict[code_hex].get("name")
            if name:
                return f"{name} ({code_hex})"
        if str_int in database_dict:
            name = database_dict[str_int].get("name")
            if name:
                return f"{name} ({code_hex})"

    return f"Vật phẩm {code_hex}"


# ==============================================================================
# BỘ GIẢI MÃ DÒNG TCP (STREAM DISSECTOR)
# ==============================================================================
class WLOStreamDissector:
    """Tái ghép luồng TCP và giải mã gói tin WLO từ dữ liệu thô."""
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
# HÀM MÃ HÓA & ĐÓNG GÓI GIAO THỨC WLO
# ==============================================================================
def pack_wlo_packet(body_bytes):
    """Đóng gói Magic Header 0xF4 0x44, Length (uint16 LE) và XOR 0xAD toàn bộ."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain_packet = header + body_bytes
    return bytes(b ^ 0xAD for b in plain_packet)

def interpret_packet(direction, opcode, subcode, data, blacklist=None, database=None):
    """Dịch nhanh ý nghĩa gói tin túi đồ để ghi log rõ ràng."""
    details = []
    if opcode == 0x17:
        if subcode == 0x0A and len(data) >= 3:
            details.append(f"Kéo đồ: Ô {data[0]} (SL: {data[1]}) -> Ô {data[2]}")
        elif subcode == 0x4B and len(data) >= 1:
            details.append(f"Mở / Dùng vật phẩm tại Ô {data[0]}")
        elif subcode == 0x03 and len(data) >= 2:
            details.append(f"Yêu cầu vứt: Ô {data[0]} (SL: {data[1]})")
        elif subcode == 0x7C and len(data) >= 2:
            details.append(f"Xác nhận popup vứt: Ô {data[0]} (SL: {data[1]})")
        elif subcode == 0x06 and len(data) >= 3:
            raw_code = struct.unpack("<H", data[0:2])[0]
            qty = data[2]
            name = get_item_display_name(raw_code, blacklist, database)
            details.append(f"Server trả vật phẩm: {qty}x {name}")
        elif subcode == 0xD4 and len(data) >= 5:
            slot = data[1]
            raw_code = struct.unpack("<H", data[2:4])[0]
            qty = data[4]
            name = get_item_display_name(raw_code, blacklist, database)
            details.append(f"Server yêu cầu popup vứt: Ô {slot} ({qty}x {name})")
        elif subcode == 0x1A and len(data) >= 3:
            raw_code = struct.unpack("<H", data[0:2])[0]
            qty = data[2]
            name = get_item_display_name(raw_code, blacklist, database)
            details.append(f"Server xác nhận vứt xong: {qty}x {name}")
        elif subcode == 0x09 and len(data) >= 2:
            details.append(f"Cập nhật số lượng Ô {data[0]} (còn lại: {data[1]})")
    elif opcode == 0x08:
        details.append("Ping/Heartbeat" if subcode == 0x01 else "Pong/Heartbeat")
    return " | ".join(details)

# ==============================================================================
# FRIDA JAVASCRIPT CODE (HOOK SOCKET & REAL DELPHI BAG SCANNER)
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

// Quét và xác thực mảng túi đồ Delphi thực tế trong bộ nhớ game
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

function doGetFirstEmptySlot() {
    var base = findBagBase();
    if (!base) return -1;
    try {
        for (var s = 0; s < 50; s++) {
            var slotPtr = base.add(s * 0x48);
            var itemObjPtr = slotPtr.add(4).readU32();
            if (itemObjPtr === 0) {
                return s + 1; // Ô 1 đến 50
            }
        }
    } catch(e) {}
    return -1;
}

function doGetAllSlotStatuses() {
    var base = findBagBase();
    if (!base) return [];
    var res = [];
    try {
        for (var s = 0; s < 50; s++) {
            var slotPtr = base.add(s * 0x48);
            var itemObjPtr = slotPtr.add(4).readU32();
            res.push(itemObjPtr !== 0); // true = có đồ, false = trống
        }
    } catch(e) {}
    return res;
}

function doSendRaw(hexBytes) {
    if (activeSocket <= 0) {
        return {success: false, error: "Chưa có socket active (Hãy click di chuyển hoặc dùng 1 món để nhận socket)"};
    }
    var raw = [];
    for (var i = 0; i < hexBytes.length; i += 2) {
        raw.push(parseInt(hexBytes.substr(i, 2), 16));
    }
    var buf = Memory.alloc(raw.length);
    buf.writeByteArray(raw);
    isInjected = true;
    try {
        var res = sendFunc(activeSocket, buf, raw.length, 0);
        return {success: true, bytesSent: res};
    } catch(e) {
        return {success: false, error: e.toString()};
    } finally {
        isInjected = false;
    }
}

rpc.exports = {
    getsocket: function() { return activeSocket; },
    getSocket: function() { return activeSocket; },
    sendraw: function(h) { return doSendRaw(h); },
    sendRaw: function(h) { return doSendRaw(h); },
    getfirstemptyslot: function() { return doGetFirstEmptySlot(); },
    getFirstEmptySlot: function() { return doGetFirstEmptySlot(); },
    getallslotstatuses: function() { return doGetAllSlotStatuses(); },
    getAllSlotStatuses: function() { return doGetAllSlotStatuses(); }
};
"""

# ==============================================================================
# CLASS QUẢN LÝ AUTO-DISCARD
# ==============================================================================
class WLOAutoDiscarder:
    def __init__(self, target_process="alogin.exe", target_pid=None,
                 config_file="wlo_auto_discard_config.json", log_file="auto_discard_log.txt",
                 dry_run=False):
        self.target_process = target_process
        self.target_pid = target_pid
        self.config_file = config_file
        self.log_file = log_file
        self.dry_run = dry_run

        self.c2s_dissector = WLOStreamDissector()
        self.s2c_dissector = WLOStreamDissector()

        self.running = False
        self.session = None
        self.script = None
        self.active_socket = -1
        self.packet_count = 0
        self.start_time = time.time()

        # Quản lý hộp thoại hỏi Blacklist trên console
        self.pending_manual_discard = None
        self.pending_timer = None
        self.prompt_lock = threading.Lock()
        self.current_prompt = None

        # Hàng đợi gói tin mạng & hàng đợi vứt đồ
        self.packet_queue = queue.Queue()
        self.packet_worker_thread = None

        self.discard_queue = queue.Queue()
        self.discard_worker_thread = None

        # Tải cấu hình
        self.config = self.load_config()
        self.blacklist = self.config.get("blacklist", {})
        self.auto_discard_enabled = self.config.get("auto_discard_enabled", True)
        self.auto_discard_on_open = self.config.get("auto_discard_on_open", False)
        self.delay_ms = self.config.get("delay_between_steps_ms", 150)

        # Nạp cơ sở dữ liệu vật phẩm chung từ wlo_items_database.json (nếu có)
        self.db_file = os.path.join(os.path.dirname(os.path.abspath(self.config_file)), "wlo_items_database.json")
        self.items_database = self.load_items_database()

        # Mở file log
        self.log_handle = None
        try:
            self.log_handle = open(self.log_file, "a", encoding="utf-8")
            self.write_log_line(f"\n{'='*80}\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] KHỞI ĐỘNG WLO SMART AUTO-DISCARD (ZERO ITEM.DAT)\n{'='*80}")
        except Exception as e:
            print(f"[!] Không thể mở file log {self.log_file}: {e}")

        # Thống kê
        self.stats_discarded = 0
        self.stats_detected = 0

        # Trạng thái mở đồ gần nhất để bảo vệ an toàn
        self.last_open_slot = 0
        self.expected_landing_slot = 0
        self.last_user_discard_slot = 0

    def write_log_line(self, line):
        """Ghi ngay dòng nhật ký vào file log."""
        if self.log_handle:
            try:
                self.log_handle.write(line + "\n")
                self.log_handle.flush()
            except Exception:
                pass

    def load_config(self):
        """Tải file cấu hình JSON."""
        if os.path.isfile(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[!] Lỗi khi đọc {self.config_file}: {e}")
        return {
            "auto_discard_enabled": True,
            "auto_discard_on_open": False,
            "delay_between_steps_ms": 150,
            "blacklist": {}
        }

    def save_config(self):
        """Lưu cấu hình JSON."""
        self.config["auto_discard_enabled"] = self.auto_discard_enabled
        self.config["auto_discard_on_open"] = self.auto_discard_on_open
        self.config["blacklist"] = self.blacklist
        self.config["delay_between_steps_ms"] = self.delay_ms
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Lỗi khi lưu cấu hình: {e}")

    def load_items_database(self):
        """Đọc cơ sở dữ liệu vật phẩm đã thu thập từ wlo_items_database.json nếu có."""
        if hasattr(self, "db_file") and os.path.isfile(self.db_file):
            try:
                with open(self.db_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return {}

    def get_display_name(self, code_int):
        """Tra cứu tên hiển thị kết hợp giữa Blacklist và wlo_items_database.json."""
        return get_item_display_name(code_int, self.blacklist, self.items_database)

    def is_in_blacklist(self, code_int):
        """Kiểm tra mã vật phẩm có nằm trong Blacklist và đang bật hay không."""
        if code_int is None:
            return False
        code_hex = format_item_code(code_int)
        str_int = str(code_int)
        if code_hex in self.blacklist and self.blacklist[code_hex].get("enabled", True):
            return True
        if str_int in self.blacklist and self.blacklist[str_int].get("enabled", True):
            return True
        return False

    def get_blacklist_info(self, code_int):
        """Lấy thông tin Blacklist của một vật phẩm."""
        code_hex = format_item_code(code_int)
        str_int = str(code_int)
        return self.blacklist.get(code_hex) or self.blacklist.get(str_int) or {}

    def get_first_empty_slot(self):
        """Lấy ô trống đầu tiên (1-50) trong túi đồ từ bộ nhớ thực tế game."""
        try:
            if self.script:
                return self.script.exports_sync.getfirstemptyslot()
        except Exception:
            pass
        return -1

    def get_all_slot_statuses(self):
        """Lấy trạng thái của toàn bộ 50 ô trong túi (True = có đồ, False = trống)."""
        try:
            if self.script:
                return self.script.exports_sync.getallslotstatuses()
        except Exception:
            pass
        return []

    def on_frida_message(self, message, raw_data):
        """Nhận thông điệp từ Frida JS Hook đẩy vào queue chống nghẽn luồng."""
        if raw_data:
            self.packet_queue.put((message, raw_data))

    def packet_worker(self):
        """Luồng chuyên trách nhận và xử lý các gói tin mạng từ hàng đợi."""
        while self.running:
            try:
                message, raw_data = self.packet_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                payload = message.get("payload", {})
                dir_name = payload.get("dir", "send")
                sock = payload.get("sock", -1)
                if sock > 0:
                    self.active_socket = sock

                is_send = (dir_name == "send")
                direction_str = "C->S" if is_send else "S->C"
                dissector = self.c2s_dissector if is_send else self.s2c_dissector
                packets = dissector.feed(raw_data)

                for opcode, subcode, data, raw_pkt in packets:
                    self.handle_packet(direction_str, opcode, subcode, data)

            except Exception as e:
                self.write_log_line(f"[{datetime.now().strftime('%H:%M:%S')}] [PACKET_WORKER_ERROR] {e}")
            finally:
                self.packet_queue.task_done()

    def handle_packet(self, direction, opcode, subcode, data):
        """Ghi log và điều hướng xử lý các gói tin mạng WLO."""
        self.packet_count += 1
        elapsed = time.time() - self.start_time
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        op_name = OPCODE_MAP.get(opcode, f"UNKNOWN_0x{opcode:02X}" if opcode is not None else "NONE")
        sub_str = f"0x{subcode:02X}" if subcode is not None else "--"
        interp = interpret_packet(direction, opcode, subcode, data, self.blacklist, self.items_database)

        hex_preview = data.hex()
        log_line = f"[{timestamp}] [+{elapsed:7.2f}s] [#{self.packet_count:<5}] {direction} Op:0x{opcode:02X} ({op_name:<18}) Sub:{sub_str:<4} Len:{len(data)+2:<3}"
        if interp:
            log_line += f" | {interp}"
        log_line += f" | Hex: {hex_preview}"
        self.write_log_line(log_line)

        # In console (bỏ qua ping 0x08 và khi đang có prompt nhập liệu)
        if opcode != 0x08 and not self.current_prompt:
            dir_color = Colors.CYAN if direction == "C->S" else Colors.YELLOW
            console_line = (
                f"{Colors.GRAY}[{timestamp}]{Colors.RESET} "
                f"{Colors.BOLD}{dir_color}{direction}{Colors.RESET} "
                f"Op:0x{opcode:02X} ({op_name}) Sub:{sub_str}"
            )
            if interp:
                console_line += f" | {Colors.MAGENTA}{interp}{Colors.RESET}"
            print(console_line, flush=True)

        # ----------------------------------------------------------------------
        # 1. C->S Op 0x17 Sub 0x4B: Người chơi mở / dùng vật phẩm tại ô
        # ----------------------------------------------------------------------
        if direction == "C->S" and opcode == 0x17 and subcode == 0x4B:
            slot = data[0] if len(data) > 0 else 0
            self.last_open_slot = slot
            # Quét ô trống đầu tiên thực tế từ bộ nhớ game
            self.expected_landing_slot = self.get_first_empty_slot()
            msg = f">>> [MỞ ĐỒ] Ô {slot}. Ô trống đầu tiên phát hiện được trong túi: Ô {self.expected_landing_slot}"
            if not self.current_prompt:
                print(f"{Colors.MAGENTA}{msg}{Colors.RESET}")
            self.write_log_line(f"[{timestamp}] {msg}")

        # ----------------------------------------------------------------------
        # 2. S->C Op 0x17 Sub 0x06: Server trả vật phẩm khi mở đồ
        # ----------------------------------------------------------------------
        elif direction == "S->C" and opcode == 0x17 and subcode == 0x06:
            self.on_server_give_item(data, timestamp)

        # ----------------------------------------------------------------------
        # 3. S->C Op 0x17 Sub 0xD4: Server yêu cầu popup xác nhận vứt đồ (WPE PRO)
        # ----------------------------------------------------------------------
        elif direction == "S->C" and opcode == 0x17 and subcode == 0xD4:
            self.on_server_discard_confirm_request(data, timestamp)

        # ----------------------------------------------------------------------
        # 4. C->S Op 0x17 Sub 0x03 & 0x7C: Người chơi vứt đồ thủ công
        # ----------------------------------------------------------------------
        elif direction == "C->S" and opcode == 0x17:
            if subcode == 0x03 and len(data) >= 2:
                slot = data[0]
                qty = data[1]
                self.last_user_discard_slot = slot
            elif subcode == 0x7C and len(data) >= 2:
                # Người chơi tự tay bấm OK popup vứt trên màn hình
                pass

    def on_server_discard_confirm_request(self, data, timestamp):
        """
        Xử lý khi Server gửi S->C Op 0x17 Sub 0xD4 yêu cầu popup xác nhận vứt đồ.
        Cơ chế WPE Pro siêu tốc:
        - Server gửi: [0x07, slot, code_le (2 bytes), qty]
        - Nếu mã vật phẩm có trong Blacklist: lập tức tự gửi Sub 0x7C trong 0.04s.
        - Nếu chưa có trong Blacklist: KHÔNG gửi Sub 0x7C, hiện prompt hỏi thêm Blacklist.
        """
        if len(data) < 5:
            return

        slot = data[1]
        raw_code = struct.unpack("<H", data[2:4])[0]
        qty = data[4]
        code_hex = format_item_code(raw_code)
        display_name = self.get_display_name(raw_code)

        is_junk = self.is_in_blacklist(raw_code)

        if is_junk and self.auto_discard_enabled:
            # Gửi xác nhận popup ngay lập tức (WPE Pro)
            try:
                time.sleep(0.04)
                body = bytes([0x17, 0x7C, slot, qty, 0x02])
                enc = pack_wlo_packet(body)
                res = self.script.exports_sync.sendraw(enc.hex())
                now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                self.stats_discarded += 1
                confirm_msg = f"[WPE AUTO-CONFIRM] Đã tự động vứt: {display_name} tại Ô {slot} (SL: {qty}) | Result: {res}"
                if not self.current_prompt:
                    print(f"\n{Colors.BOLD}{Colors.GREEN}{confirm_msg}{Colors.RESET}\n")
                self.write_log_line(f"[{now}] {confirm_msg}")
            except Exception as e:
                self.write_log_line(f"[{timestamp}] [ERROR] Lỗi gửi xác nhận popup Sub 0x7C: {e}")
        else:
            # Vật phẩm chưa có trong Blacklist -> Kích hoạt hỏi người chơi có muốn thêm không
            self.trigger_learn_prompt(slot, qty, raw_code, code_hex, display_name, True)

    def on_server_give_item(self, data, timestamp):
        """Xử lý gói tin Server trả vật phẩm khi mở đồ (Op 0x17 Sub 0x06)."""
        if len(data) < 3:
            return

        raw_code = struct.unpack("<H", data[0:2])[0]
        qty = data[2]
        code_hex = format_item_code(raw_code)
        display_name = self.get_display_name(raw_code)

        target_slot = self.expected_landing_slot

        is_junk = self.is_in_blacklist(raw_code)

        if not is_junk:
            # Vật phẩm bình thường / vật phẩm quý -> Giữ nguyên, ghi log rõ ràng
            kept_msg = f"[GIỮ LẠI] Nhận vật phẩm: {display_name} (SL: {qty}) tại Ô {target_slot}"
            if not self.current_prompt:
                print(f"{Colors.BOLD}{Colors.GREEN}{kept_msg}{Colors.RESET}")
            self.write_log_line(f"[{timestamp}] [ITEM_KEPT] {kept_msg}")
            return

        # Vật phẩm nằm trong Blacklist
        self.stats_detected += 1
        det_msg = f"[PHÁT HIỆN RÁC MỞ ĐƯỢC] {display_name} (Mã: {code_hex}, SL: {qty}) rơi vào Ô {target_slot}"
        if not self.current_prompt:
            print(f"{Colors.BOLD}{Colors.RED}{det_msg}{Colors.RESET}")
        self.write_log_line(f"[{timestamp}] [JUNK_DETECTED] {det_msg}")

        # KIỂM TRA CHẾ ĐỘ TỰ VỨT KHI MỞ HỘP (AN TOÀN TUYỆT ĐỐI)
        if not self.auto_discard_on_open:
            notice = f"   [AN TOÀN] Chế độ tự vứt khi mở đang TẮT. Món rác nằm ở Ô {target_slot}. Bạn có thể kéo vứt để script tự xác nhận popup siêu tốc."
            if not self.current_prompt:
                print(f"{Colors.YELLOW}{notice}{Colors.RESET}")
            self.write_log_line(f"[{timestamp}] {notice}")
            return

        # Nếu bật chế độ tự vứt khi mở, kiểm tra các khiên an toàn trước khi vứt
        if target_slot <= 0 or target_slot > 50:
            warn = f"[CẢNH BÁO AN TOÀN] Không xác định được ô trống hợp lệ ({target_slot}). Hủy lệnh vứt tự động để bảo vệ đồ!"
            if not self.current_prompt:
                print(f"{Colors.BOLD}{Colors.RED}{warn}{Colors.RESET}")
            self.write_log_line(f"[{timestamp}] [SAFETY] {warn}")
            return

        if target_slot == self.last_open_slot:
            warn = f"[CẢNH BÁO AN TOÀN] Ô đích {target_slot} trùng với ô đang mở đồ ({self.last_open_slot}). Từ chối vứt!"
            if not self.current_prompt:
                print(f"{Colors.BOLD}{Colors.RED}{warn}{Colors.RESET}")
            self.write_log_line(f"[{timestamp}] [SAFETY] {warn}")
            return

        item_info = self.get_blacklist_info(raw_code)
        if self.dry_run:
            dry_msg = f"[DRY-RUN] Bỏ qua lệnh vứt thật đối với Ô {target_slot} ({display_name})"
            print(f"   {Colors.YELLOW}{dry_msg}{Colors.RESET}")
            self.write_log_line(f"[{timestamp}] {dry_msg}")
        else:
            self.discard_queue.put((target_slot, qty, raw_code, item_info))

    def trigger_learn_prompt(self, slot, qty, raw_code, code_hex, display_name, need_confirm):
        """Kích hoạt hộp thoại hỏi thêm Blacklist trên console."""
        with self.prompt_lock:
            if self.is_in_blacklist(raw_code):
                return

            if self.pending_timer:
                self.pending_timer.cancel()

            self.pending_manual_discard = {
                "slot": slot,
                "qty": qty,
                "raw_code": raw_code,
                "code_hex": code_hex,
                "display_name": display_name,
                "need_confirm": need_confirm
            }
            # Trì hoãn 0.8s để màn hình game ổn định rồi hiện câu hỏi
            self.pending_timer = threading.Timer(0.8, self.fire_learn_prompt)
            self.pending_timer.start()

    def fire_learn_prompt(self):
        """In hộp thoại tương tác trực tiếp lên console."""
        with self.prompt_lock:
            info = self.pending_manual_discard
            self.pending_manual_discard = None
            self.pending_timer = None

        if not info:
            return

        slot = info["slot"]
        qty = info["qty"]
        code_hex = info["code_hex"]
        popup_str = "Có Popup xác nhận" if info["need_confirm"] else "Vứt trực tiếp (không popup)"

        print("\n" + "=" * 80)
        print(f"{Colors.BOLD}{Colors.YELLOW}[?] PHÁT HIỆN BẠN VỪA VỨT VẬT PHẨM TẠI Ô {slot} (Số lượng: {qty})!{Colors.RESET}")
        print(f"    • Mã Server 2-byte : {Colors.CYAN}{code_hex}{Colors.RESET}")
        print(f"    • Kiểu vứt         : {Colors.MAGENTA}{popup_str}{Colors.RESET}")
        print(f"\n    {Colors.BOLD}Bạn có muốn THÊM vật phẩm này vào BLACKLIST để lần sau TỰ ĐỘNG VỨT không?{Colors.RESET}")
        print(f"    -> Nhập {Colors.GREEN}[1]{Colors.RESET} để ĐỒNG Ý thêm vào Blacklist")
        print(f"    -> Nhập {Colors.RED}[0]{Colors.RESET} hoặc nhấn Enter để BỎ QUA")
        print("=" * 80)
        print(f"{Colors.BOLD}Lựa chọn của bạn [1/0]: {Colors.RESET}", end="", flush=True)

        self.current_prompt = {
            "step": "ASK_CONFIRM",
            "data": info
        }

    def discard_worker(self):
        """Luồng chuyên trách thực hiện lệnh vứt đồ tuần tự, an toàn."""
        while self.running:
            try:
                task = self.discard_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            slot, qty, raw_code, item_info = task
            code_hex = format_item_code(raw_code)
            item_name = item_info.get("name") or code_hex

            try:
                now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                action_msg = f"[TIẾN HÀNH VỨT] Tự động vứt {qty}x {item_name} ({code_hex}) tại Ô {slot}..."
                if not self.current_prompt:
                    print(f"{Colors.GRAY}[{now}]{Colors.RESET} {Colors.BOLD}{Colors.RED}{action_msg}{Colors.RESET}")
                self.write_log_line(f"[{now}] [DISCARDING] {action_msg}")

                # Gửi lệnh vứt vật phẩm (Op 0x17 Sub 0x03)
                body1 = bytes([0x17, 0x03, slot, qty, 0x01])
                enc_packet1 = pack_wlo_packet(body1)
                res1 = self.script.exports_sync.sendraw(enc_packet1.hex())

                self.write_log_line(f"[{now}] [SENT] Op:0x17 Sub:0x03 Hex: {body1.hex()} | Result: {res1}")

                if not res1.get("success"):
                    err_msg = f"[!] Lỗi khi gửi lệnh vứt: {res1.get('error')}"
                    print(f"   {Colors.RED}{err_msg}{Colors.RESET}")
                    self.write_log_line(f"[{now}] [ERROR] {err_msg}")
                    continue

                self.stats_discarded += 1
                succ_msg = f"[✓ ĐÃ GỬI LỆNH VỨT] Ô {slot} ({qty}x {item_name} {code_hex}) (Tổng đã xử lý: {self.stats_discarded})"
                if not self.current_prompt:
                    print(f"{Colors.GRAY}[{now}]{Colors.RESET} {Colors.BOLD}{Colors.GREEN}{succ_msg}{Colors.RESET}\n")
                self.write_log_line(f"[{now}] [DISCARD_SENT] {succ_msg}")

                time.sleep(self.delay_ms / 1000.0)

            except Exception as e:
                err_exc = f"[!] Lỗi ngoại lệ trong luồng vứt: {e}"
                print(f"   {Colors.RED}{err_exc}{Colors.RESET}")
                self.write_log_line(f"[{datetime.now().strftime('%H:%M:%S')}] [EXCEPTION] {err_exc}")
            finally:
                self.discard_queue.task_done()

    def add_to_blacklist(self, code_int, item_name, need_confirm=True):
        """Thêm vật phẩm vào Blacklist bằng mã 2-byte thực tế và lưu file JSON."""
        code_hex = format_item_code(code_int)
        self.blacklist[code_hex] = {
            "name": item_name,
            "code": code_int,
            "need_confirm": need_confirm,
            "enabled": True
        }
        self.save_config()
        succ = f"[✓] ĐÃ THÊM THÀNH CÔNG VÀO BLACKLIST: {item_name} (Mã: {code_hex}, Popup: {need_confirm})"
        print(f"\n{Colors.BOLD}{Colors.GREEN}{succ}{Colors.RESET}\n")
        self.write_log_line(f"[{datetime.now().strftime('%H:%M:%S')}] [BLACKLIST_ADD] {succ}")

    def show_bag_status(self):
        """Hiển thị trạng thái các ô trong túi đồ từ bộ nhớ game thực tế."""
        statuses = self.get_all_slot_statuses()
        if not statuses:
            print("[!] Chưa quét được túi đồ trong bộ nhớ game (Hãy di chuyển hoặc mở 1 món trong game).")
            return

        occupied = [i + 1 for i, occ in enumerate(statuses) if occ]
        empty = [i + 1 for i, occ in enumerate(statuses) if not occ]
        first_empty = empty[0] if empty else "Không có (Túi đầy)"

        print("\n" + "=" * 70)
        print("          TRẠNG THÁI TÚI ĐỒ BỘ NHỚ THỰC TẾ (50 Ô)")
        print("=" * 70)
        print(f"[*] Số ô đang có đồ ({len(occupied)} ô): {occupied}")
        print(f"[*] Số ô đang trống ({len(empty)} ô): {empty}")
        print(f"[*] Ô trống đầu tiên (First Empty Slot): {Colors.GREEN}Ô {first_empty}{Colors.RESET}")
        print("=" * 70 + "\n")

    def start(self):
        print("=" * 80)
        print("     WLO SMART AUTO-DISCARD & CLEANER (ZERO ITEM.DAT - 100% AN TOÀN)")
        print("=" * 80)
        print(f"[*] File nhật ký log          : {Colors.CYAN}{self.log_file}{Colors.RESET}")
        print(f"[*] Chế độ tự động xác nhận   : {Colors.GREEN + 'BẬT' if self.auto_discard_enabled else Colors.RED + 'TẮT'}{Colors.RESET}")
        print(f"[*] Tự vứt khi mở hộp        : {Colors.GREEN + 'BẬT' if self.auto_discard_on_open else Colors.YELLOW + 'TẮT (An toàn)'}{Colors.RESET}")
        print(f"[*] Chế độ Dry-Run (thử)      : {Colors.YELLOW + 'BẬT (Không vứt thật)' if self.dry_run else Colors.GREEN + 'TẮT (Vứt thật)'}{Colors.RESET}")
        print(f"[*] Số vật phẩm Blacklist     : {Colors.CYAN}{len(self.blacklist)}{Colors.RESET} loại")

        print("\n" + "-" * 80)

        try:
            if self.target_pid:
                print(f"[*] Đang đính kèm vào PID: {self.target_pid} ...")
                self.session = frida.attach(self.target_pid)
            else:
                print(f"[*] Đang đính kèm vào tiến trình: {self.target_process} ...")
                self.session = frida.attach(self.target_process)

            self.script = self.session.create_script(FRIDA_JS)
            self.script.on("message", self.on_frida_message)
            self.script.load()

            print(f"{Colors.GREEN}[+] Đính kèm thành công vào game! Đang lắng nghe mạng và theo dõi túi đồ...{Colors.RESET}")
            print(f"[*] Hướng dẫn nhanh:")
            print(f"    - Để thêm đồ rác: Trong game bạn cứ kéo vứt món đó đi, console sẽ hỏi bạn có muốn thêm vào Blacklist không.")
            print(f"    - Sau khi thêm: Lần sau chỉ cần kéo vứt, script sẽ tự xác nhận popup trong 0.04s mà không cần bấm chuột.")
            print("-" * 80)

        except Exception as e:
            print(f"{Colors.RED}[!] Không thể đính kèm vào game: {e}{Colors.RESET}")
            return

        self.running = True

        # Khởi động luồng xử lý mạng và luồng vứt đồ
        self.packet_worker_thread = threading.Thread(target=self.packet_worker, daemon=True)
        self.packet_worker_thread.start()

        self.discard_worker_thread = threading.Thread(target=self.discard_worker, daemon=True)
        self.discard_worker_thread.start()

        self.console_loop()

    def console_loop(self):
        """Nhận lệnh điều khiển và phản hồi prompt từ người dùng."""
        print(f"{Colors.BOLD}Lệnh hỗ trợ: [list] xem Blacklist | [bag] xem túi đồ thực tế | [open_discard] bật/tắt tự vứt khi mở | [add <Mã> <Tên>] | [exit]{Colors.RESET}\n")
        while self.running:
            try:
                user_input = input().strip()
            except (EOFError, KeyboardInterrupt):
                break

            # ------------------------------------------------------------------
            # XỬ LÝ HỘP THOẠI HỎI THÊM BLACKLIST TRỰC TIẾP
            # ------------------------------------------------------------------
            if self.current_prompt:
                step = self.current_prompt.get("step")
                data = self.current_prompt.get("data", {})

                if step == "ASK_CONFIRM":
                    if user_input.lower() in ("1", "y", "yes"):
                        code_hex = data.get("code_hex")
                        default_name = self.items_database.get(code_hex, {}).get("name") or ""
                        self.current_prompt["step"] = "ASK_NAME"
                        self.current_prompt["default_name"] = default_name
                        if default_name:
                            prompt_name = f"Nhập tên gợi nhớ cho vật phẩm (Mã {code_hex}) [Enter để dùng '{default_name}']: "
                        else:
                            prompt_name = f"Nhập tên gợi nhớ cho vật phẩm (Mã {code_hex}): "
                        print(f"{Colors.BOLD}{prompt_name}{Colors.RESET}", end="", flush=True)
                    else:
                        print(f"[-] Đã bỏ qua, không thêm vào Blacklist.")
                        self.current_prompt = None

                elif step == "ASK_NAME":
                    raw_code = data.get("raw_code")
                    code_hex = data.get("code_hex")
                    def_name = self.current_prompt.get("default_name") or f"Vật phẩm_{code_hex}"
                    chosen_name = user_input if user_input else def_name
                    need_confirm = data.get("need_confirm", True)
                    self.add_to_blacklist(raw_code, chosen_name, need_confirm)
                    self.current_prompt = None
                continue

            # ------------------------------------------------------------------
            # XỬ LÝ LỆNH THÔNG THƯỜNG TRONG CONSOLE
            # ------------------------------------------------------------------
            if not user_input:
                continue

            parts = user_input.split()
            base = parts[0].lower()

            if base in ("exit", "quit", "q"):
                break
            elif base == "toggle":
                self.auto_discard_enabled = not self.auto_discard_enabled
                st = Colors.GREEN + "BẬT" if self.auto_discard_enabled else Colors.RED + "TẮT"
                print(f"[*] Chế độ Tự động vứt (Master Switch): {st}{Colors.RESET}")
                self.save_config()
            elif base == "open_discard":
                self.auto_discard_on_open = not self.auto_discard_on_open
                st = Colors.GREEN + "BẬT" if self.auto_discard_on_open else Colors.YELLOW + "TẮT (An toàn)"
                print(f"[*] Chế độ Tự động vứt khi MỞ HỘP: {st}{Colors.RESET}")
                self.save_config()
            elif base == "list":
                print("\n=== DANH SÁCH VẬT PHẨM TRONG BLACKLIST ===")
                if not self.blacklist:
                    print("  (Chưa có vật phẩm nào. Kéo vứt vật phẩm trong game để thêm vào Blacklist)")
                else:
                    for hex_id, info in self.blacklist.items():
                        cf = "Có popup" if info.get("need_confirm") else "Vứt ngay"
                        st = "Bật" if info.get("enabled", True) else "Tắt"
                        name = info.get("name", "Vật phẩm")
                        print(f"  Mã {hex_id:>8}: {name:<30} | {cf:<10} | Trạng thái: {st}")
                print()
            elif base == "bag":
                self.show_bag_status()
            elif base == "add":
                if len(parts) >= 2:
                    code_int = parse_code_input(parts[1])
                    if code_int is not None:
                        name = " ".join(parts[2:]).strip() if len(parts) >= 3 else f"Vật phẩm_{format_item_code(code_int)}"
                        self.add_to_blacklist(code_int, name, need_confirm=True)
                    else:
                        print("[!] Mã vật phẩm không hợp lệ! Vui lòng nhập dạng hex (VD: 0x84D8) hoặc số thập phân (VD: 34008).")
                else:
                    print("[!] Cú pháp: add <Mã 0xXXXX> [Tên gợi nhớ] (VD: add 0x84D8 Xu Giai Tri)")
            elif base == "remove":
                if len(parts) >= 2:
                    code_int = parse_code_input(parts[1])
                    code_hex = format_item_code(code_int) if code_int is not None else parts[1].upper()
                    removed = False
                    for k in [code_hex, parts[1], str(code_int)]:
                        if k and k in self.blacklist:
                            del self.blacklist[k]
                            removed = True
                    if removed:
                        self.save_config()
                        print(f"{Colors.GREEN}[✓] Đã xóa {code_hex} khỏi Blacklist.{Colors.RESET}")
                    else:
                        print(f"[!] Không tìm thấy mã {parts[1]} trong Blacklist.")
                else:
                    print("[!] Cú pháp: remove <Mã> (VD: remove 0x84D8)")
            elif base == "status":
                sock = self.script.exports_sync.getsocket() if self.script else -1
                empty_slot = self.get_first_empty_slot()
                print(f"[*] Active Socket: {sock} | Ô trống đầu tiên trong túi: Ô {empty_slot} | Đã vứt: {self.stats_discarded} lần")
            elif base == "help":
                print("\nDanh sách lệnh hỗ trợ:")
                print("  list               : Xem danh sách vật phẩm trong Blacklist")
                print("  bag                : Xem trạng thái thực tế 50 ô đồ trong túi (ô có đồ / ô trống)")
                print("  open_discard       : Bật/Tắt chế độ tự động vứt ngay khi mở hộp")
                print("  toggle             : Bật/Tắt toàn bộ hệ thống tự động vứt")
                print("  add <Mã> [Tên]     : Thêm thủ công một vật phẩm vào Blacklist (VD: add 0x84D8 Xu Giai Tri)")
                print("  remove <Mã>        : Xóa một vật phẩm khỏi Blacklist (VD: remove 0x84D8)")
                print("  status             : Xem trạng thái kết nối và ô trống đầu tiên")
                print("  exit               : Thoát chương trình an toàn\n")
            else:
                print("[?] Lệnh không hợp lệ. Gõ 'help' để xem hướng dẫn.")

    def stop(self):
        self.running = False
        print("\n[*] Đang dừng Auto-Discarder...")
        try:
            if self.script:
                self.script.unload()
            if self.session:
                self.session.detach()
        except Exception:
            pass
        if self.log_handle:
            try:
                self.write_log_line(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] DỪNG AUTO-DISCARD (Tổng đã vứt: {self.stats_discarded})\n")
                self.log_handle.close()
            except Exception:
                pass
        print(f"{Colors.GREEN}[+] Đã thoát an toàn.{Colors.RESET}")

# ==============================================================================
# HÀM TÌM TIẾN TRÌNH ALOGIN
# ==============================================================================
def find_alogin_processes():
    processes = []
    try:
        device = frida.get_local_device()
        for p in device.enumerate_processes():
            if "alogin" in p.name.lower():
                processes.append((p.pid, p.name))
    except Exception:
        pass
    return processes

# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="WLO Smart Auto-Discard & Cleaner (Zero Item.Dat)")
    parser.add_argument("-p", "--process", default=None, help="Tên tiến trình (VD: alogin-F03.exe, alogin.exe)")
    parser.add_argument("--pid", type=int, default=None, help="PID của tiến trình game cần kết nối")
    parser.add_argument("--config", default=None, help="Đường dẫn file cấu hình JSON")
    parser.add_argument("--log", default=None, help="Đường dẫn file log lưu gói tin")
    parser.add_argument("--dry-run", action="store_true", help="Chế độ chạy thử: chỉ phát hiện, không vứt thật")

    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = args.config or os.path.join(script_dir, "wlo_auto_discard_config.json")
    log_path = args.log or os.path.join(script_dir, "auto_discard_log.txt")

    target_process = args.process
    target_pid = args.pid

    if not target_process and not target_pid:
        running_procs = find_alogin_processes()
        if not running_procs:
            print("[!] Không tìm thấy tiến trình alogin*.exe nào đang chạy!")
            print("[*] Vui lòng mở game trước hoặc chỉ định PID: python wlo_auto_discard.py --pid <PID>")
            sys.exit(1)

        if len(running_procs) == 1:
            target_pid, target_process = running_procs[0]
            print(f"[*] Tự động phát hiện và chọn: {target_process} (PID: {target_pid})")
        else:
            print("[*] Tìm thấy nhiều cửa sổ game đang chạy:")
            for i, (p_pid, p_name) in enumerate(running_procs):
                print(f"    [{i+1}] {p_name} (PID: {p_pid})")
            try:
                choice = input(f"Chọn cửa sổ game [1-{len(running_procs)}] (Mặc định 1): ").strip()
                idx = int(choice) - 1 if choice else 0
                target_pid, target_process = running_procs[idx]
            except Exception:
                target_pid, target_process = running_procs[0]

    discarder = WLOAutoDiscarder(
        target_process=target_process,
        target_pid=target_pid,
        config_file=config_path,
        log_file=log_path,
        dry_run=args.dry_run
    )
    discarder.start()

if __name__ == "__main__":
    main()
