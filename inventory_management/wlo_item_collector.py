#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO Smart Item Collector & Database Builder
============================================
Công cụ tự động theo dõi và lưu trữ thông tin vật phẩm khi MỞ QUÀ hoặc VỨT ĐỒ trong Wonderland Online (WLO).

Tính năng chính:
1. TỰ ĐỘNG THU THẬP KHI MỞ QUÀ:
   - Lắng nghe gói tin mở đồ: C->S Op:0x17 Sub:0x4B (ghi nhận ô mở quà).
   - Lắng nghe gói tin server trả quà: S->C Op:0x17 Sub:0x06 (nhận diện mã vật phẩm và số lượng).
   - Quét mảng túi đồ Delphi thật để xác định chính xác ô quà rơi vào (Landing Slot).
2. TỰ ĐỘNG THU THẬP KHI VỨT ĐỒ (DISCARD):
   - Lắng nghe gói tin popup vứt đồ: S->C Op:0x17 Sub:0xD4 (chứa chính xác 100% ô và mã 2-byte server).
   - Lắng nghe gói tin xác nhận vứt: S->C Op:0x17 Sub:0x1A (mã vật phẩm và số lượng vứt).
   - Đồng bộ danh sách 50 ô túi đồ từ server khi đăng nhập / đổi map (Op:0x17 Sub:0x05).
3. TỰ ĐỘNG LƯU VÀO DATABASE (NẾU CHƯA CÓ):
   - Nếu mã 2-byte server chưa có trong database -> Tự động thêm mới vào wlo_items_database.json!
   - Bật thông báo nổi bật trên console và cho phép người chơi đặt tên ngay lập tức.
   - Nếu đã có trong database -> Cập nhật số lần mở/vứt và thời gian gần nhất (last_seen).
4. AN TOÀN TUYỆT ĐỐI (READ-ONLY):
   - Script chỉ đọc và ghi nhận dữ liệu, TUYỆT ĐỐI KHÔNG gửi lệnh vứt hay can thiệp phá hủy đồ.
5. 100% KHÔNG DÙNG ITEM.DAT:
   - Định danh vật phẩm thuần túy bằng mã 2-byte server nguyên bản (Hex 0xXXXX, Dec YYYYY).
   - Tên vật phẩm hoàn toàn do chính người chơi đặt hoặc để trống, không tự bịa tên ảo.
6. CÔNG CỤ QUẢN LÝ DATABASE TRÊN CONSOLE:
   - [list]: Xem bảng danh sách toàn bộ vật phẩm đã khám phá.
   - [inv]: Xem đồ trong 50 ô túi đồ (đồng bộ mạng).
   - [name <Mã> <Tên>]: Đặt/sửa tên gợi nhớ cho vật phẩm.
   - [find <từ khóa>]: Tìm kiếm theo mã hoặc tên.
   - [export]: Xuất file báo cáo wlo_items_database.txt dễ đọc.
   - [bag]: Xem trạng thái 50 ô túi đồ thực tế.
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

# Tránh lỗi font tiếng Việt trên console Windows
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
    GREEN = "\033[92m"     # Thành công / Đồ mới
    RED = "\033[91m"       # Cảnh báo
    MAGENTA = "\033[95m"   # Hành động mở đồ
    BLUE = "\033[94m"      # Tiêu đề
    GRAY = "\033[90m"      # Chi tiết phụ

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
    """Phân tích chuỗi người dùng nhập (VD: 0x84D8, 84D8 hoặc 34008) thành số nguyên."""
    user_str = user_str.strip()
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
# FRIDA JAVASCRIPT CODE (HOOK SOCKET & DELPHI BAG SCANNER)
# ==============================================================================
FRIDA_JS = """
var activeSocket = -1;
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

// Quét mảng túi đồ Delphi thực tế trong bộ nhớ
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

rpc.exports = {
    getsocket: function() { return activeSocket; },
    getSocket: function() { return activeSocket; },
    getfirstemptyslot: function() { return doGetFirstEmptySlot(); },
    getFirstEmptySlot: function() { return doGetFirstEmptySlot(); },
    getallslotstatuses: function() { return doGetAllSlotStatuses(); },
    getAllSlotStatuses: function() { return doGetAllSlotStatuses(); }
};
"""

# ==============================================================================
# CLASS QUẢN LÝ THU THẬP VẬT PHẨM & DATABASE
# ==============================================================================
class WLOItemCollector:
    def __init__(self, target_process="alogin.exe", target_pid=None,
                 db_file="wlo_items_database.json", txt_file="wlo_items_database.txt",
                 log_file="item_collector_log.txt"):
        self.target_process = target_process
        self.target_pid = target_pid
        self.db_file = db_file
        self.txt_file = txt_file
        self.log_file = log_file

        self.c2s_dissector = WLOStreamDissector()
        self.s2c_dissector = WLOStreamDissector()

        self.running = False
        self.session = None
        self.script = None
        self.active_socket = -1
        self.packet_count = 0
        self.start_time = time.time()

        # Quản lý hàng đợi gói tin mạng
        self.packet_queue = queue.Queue()
        self.packet_worker_thread = None

        # Trạng thái mở quà gần nhất
        self.last_open_slot = 0
        self.expected_landing_slot = 0

        # Trạng thái vứt đồ gần nhất
        self.last_discard_req = None
        self.last_discard_event = None

        # Bộ nhớ đệm danh sách đồ trong túi (đồng bộ từ Op:0x17 Sub:0x05)
        self.inventory_cache = {}

        # Tải cơ sở dữ liệu
        self.database = self.load_database()

        # Quản lý nhập liệu console cho item mới
        self.current_prompt = None
        self.prompt_lock = threading.Lock()

        # Mở file log
        self.log_handle = None
        try:
            self.log_handle = open(self.log_file, "a", encoding="utf-8")
            self.write_log_line(f"\n{'='*80}\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] KHỞI ĐỘNG WLO ITEM COLLECTOR & DATABASE\n{'='*80}")
        except Exception as e:
            print(f"[!] Không thể mở file log {self.log_file}: {e}")

    def write_log_line(self, line):
        """Ghi ngay dòng log vào file."""
        if self.log_handle:
            try:
                self.log_handle.write(line + "\n")
                self.log_handle.flush()
            except Exception:
                pass

    def load_database(self):
        """Đọc cơ sở dữ liệu từ file JSON."""
        if os.path.isfile(self.db_file):
            try:
                with open(self.db_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                print(f"[!] Lỗi khi đọc database {self.db_file}: {e}")
        return {}

    def save_database(self):
        """Lưu cơ sở dữ liệu vào JSON và xuất bản xem trước dạng text."""
        try:
            with open(self.db_file, "w", encoding="utf-8") as f:
                json.dump(self.database, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Lỗi khi lưu database {self.db_file}: {e}")

        # Tự động cập nhật file text báo cáo
        self.export_text_report()

    def export_text_report(self):
        """Xuất danh sách vật phẩm ra file text có bảng biểu đẹp mắt."""
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
                    if source == "discard" or times_disc > 0 and times_rec == 0:
                        note = f"Vứt Ô {item.get('last_discarded_from_slot', '?')}"
                    else:
                        note = f"Rơi Ô {item.get('landing_slot', '?')}"
                    first = item.get("first_seen", "")
                    f.write(f"{hex_id:<10} | {dec:<8} | {name:<30} | {stats:<16} | {note:<12} | {first}\n")
                f.write("=" * 105 + "\n")
        except Exception:
            pass

    def get_first_empty_slot(self):
        """Lấy ô trống đầu tiên trong túi từ bộ nhớ game."""
        try:
            if self.script:
                return self.script.exports_sync.getfirstemptyslot()
        except Exception:
            pass
        return -1

    def get_all_slot_statuses(self):
        """Lấy trạng thái 50 ô đồ trong túi."""
        try:
            if self.script:
                return self.script.exports_sync.getallslotstatuses()
        except Exception:
            pass
        return []

    def on_frida_message(self, message, raw_data):
        """Nhận gói tin mạng từ Frida JS Hook."""
        if raw_data:
            self.packet_queue.put((message, raw_data))

    def packet_worker(self):
        """Luồng chuyên trách bóc tách gói tin mạng."""
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
        """Xử lý các gói tin mở quà, vứt đồ và đồng bộ túi đồ."""
        self.packet_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # ----------------------------------------------------------------------
        # 1. C->S Op:0x17 Sub:0x4B: Người chơi mở / dùng vật phẩm tại ô
        # ----------------------------------------------------------------------
        if direction == "C->S" and opcode == 0x17 and subcode == 0x4B:
            slot = data[0] if len(data) > 0 else 0
            self.last_open_slot = slot
            self.expected_landing_slot = self.get_first_empty_slot()
            log_msg = f"[MỞ QUÀ] Người chơi mở vật phẩm tại Ô {slot}. Ô trống đầu tiên trong túi: Ô {self.expected_landing_slot}"
            self.write_log_line(f"[{timestamp}] {log_msg}")
            if not self.current_prompt:
                print(f"{Colors.MAGENTA}>>> [MỞ QUÀ] Tại Ô {slot} (Ô trống dự kiến nhận quà: Ô {self.expected_landing_slot}){Colors.RESET}")

        # ----------------------------------------------------------------------
        # 2. S->C Op:0x17 Sub:0x06: Server trả phần thưởng mở hộp
        # ----------------------------------------------------------------------
        elif direction == "S->C" and opcode == 0x17 and subcode == 0x06:
            self.on_server_reward_item(data, timestamp)

        # ----------------------------------------------------------------------
        # 3. C->S Op:0x17 Sub:0x03: Người chơi yêu cầu vứt vật phẩm
        # ----------------------------------------------------------------------
        elif direction == "C->S" and opcode == 0x17 and subcode == 0x03:
            slot = data[0] if len(data) > 0 else 0
            qty = data[1] if len(data) > 1 else 1
            self.last_discard_req = {"slot": slot, "qty": qty, "time": time.time()}
            self.write_log_line(f"[{timestamp}] [USER_DISCARD_REQ] Người chơi yêu cầu vứt vật phẩm tại Ô {slot} (SL: {qty})")

        # ----------------------------------------------------------------------
        # 4. S->C Op:0x17 Sub:0xD4: Server gửi popup xác nhận vứt đồ (có Mã & Ô)
        # ----------------------------------------------------------------------
        elif direction == "S->C" and opcode == 0x17 and subcode == 0xD4:
            if len(data) >= 5:
                # data[0] = 0x07 (dialog id), data[1] = slot, data[2:4] = code_le, data[4] = qty
                slot = data[1]
                raw_code = struct.unpack("<H", data[2:4])[0]
                qty = data[4]
                self.on_item_discarded(raw_code, qty, slot, timestamp, source="popup_discard")

        # ----------------------------------------------------------------------
        # 5. C->S Op:0x17 Sub:0x7C: Người chơi xác nhận vứt đồ trên popup
        # ----------------------------------------------------------------------
        elif direction == "C->S" and opcode == 0x17 and subcode == 0x7C:
            slot = data[0] if len(data) > 0 else 0
            qty = data[1] if len(data) > 1 else 1
            self.write_log_line(f"[{timestamp}] [USER_DISCARD_CONFIRM] Người chơi xác nhận popup vứt Ô {slot} (SL: {qty})")

        # ----------------------------------------------------------------------
        # 6. S->C Op:0x17 Sub:0x1A: Server xác nhận hoàn tất vứt đồ (có Mã & SL)
        # ----------------------------------------------------------------------
        elif direction == "S->C" and opcode == 0x17 and subcode == 0x1A:
            if len(data) >= 3:
                raw_code = struct.unpack("<H", data[0:2])[0]
                qty = data[2]
                slot = self.last_discard_req.get("slot", -1) if self.last_discard_req else -1
                self.on_item_discarded(raw_code, qty, slot, timestamp, source="direct_discard")

        # ----------------------------------------------------------------------
        # 7. S->C Op:0x17 Sub:0x05: Server đồng bộ túi đồ khi Đăng nhập / Đổi map
        # ----------------------------------------------------------------------
        elif direction == "S->C" and opcode == 0x17 and subcode == 0x05:
            entry_len = 31
            num_entries = len(data) // entry_len
            self.inventory_cache = {}
            for i in range(num_entries):
                entry = data[i * entry_len : (i + 1) * entry_len]
                slot = entry[0]
                code = struct.unpack("<H", entry[1:3])[0]
                qty = entry[3]
                self.inventory_cache[slot] = {"code": code, "qty": qty}
            self.write_log_line(f"[{timestamp}] [SYNC_INVENTORY] Nhận {len(self.inventory_cache)} món đồ trong túi từ Server")
            if not self.current_prompt:
                print(f"{Colors.CYAN}[i] Đã đồng bộ danh sách 50 ô túi đồ từ Server ({len(self.inventory_cache)} món đồ). Gõ 'inv' để xem.{Colors.RESET}")

        # ----------------------------------------------------------------------
        # 8. S->C Op:0x17 Sub:0x09: Server cập nhật số lượng vật phẩm trong ô
        # ----------------------------------------------------------------------
        elif direction == "S->C" and opcode == 0x17 and subcode == 0x09:
            if len(data) >= 2:
                slot = data[0]
                remain = data[1]
                if slot in self.inventory_cache:
                    if remain == 0:
                        del self.inventory_cache[slot]
                    else:
                        self.inventory_cache[slot]["qty"] = remain
                self.write_log_line(f"[{timestamp}] [UPDATE_SLOT] Ô {slot} cập nhật số lượng còn lại: {remain}")

    def on_server_reward_item(self, data, timestamp):
        """Xử lý vật phẩm nhận được từ Server khi mở hộp và lưu vào database nếu chưa có."""
        if len(data) < 3:
            return

        raw_code = struct.unpack("<H", data[0:2])[0]
        qty = data[2]
        code_hex = format_item_code(raw_code)
        raw_bytes_str = f"{data[0]:02X} {data[1]:02X}"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # KIỂM TRA ĐÃ CÓ TRONG DATABASE CHƯA
        if code_hex in self.database:
            item_entry = self.database[code_hex]
            item_entry["times_received"] = item_entry.get("times_received", 0) + 1
            item_entry["last_seen"] = now_str
            item_entry["last_qty"] = qty
            item_entry["opened_from_slot"] = self.last_open_slot
            item_entry["landing_slot"] = self.expected_landing_slot
            self.save_database()

            name_display = item_entry.get("name") or "(Chưa đặt tên)"
            log_line = f"[ITEM_EXISTED] Mã: {code_hex} ({name_display}) | SL: {qty} | Lần nhận thứ: {item_entry['times_received']}"
            self.write_log_line(f"[{timestamp}] {log_line}")

            if not self.current_prompt:
                print(f"{Colors.GREEN}[✓ VẬT PHẨM ĐÃ CÓ]{Colors.RESET} {Colors.BOLD}{name_display}{Colors.RESET} "
                      f"(Mã: {Colors.CYAN}{code_hex}{Colors.RESET}, SL: {qty}) | "
                      f"Rơi vào: Ô {self.expected_landing_slot} | "
                      f"Đã mở được: {item_entry['times_received']} lần")
        else:
            # VẬT PHẨM MỚI HOÀN TOÀN TỪ MỞ QUÀ!
            new_entry = {
                "code_hex": code_hex,
                "code_dec": raw_code,
                "raw_bytes": raw_bytes_str,
                "name": "",
                "first_seen": now_str,
                "last_seen": now_str,
                "times_received": 1,
                "times_discarded": 0,
                "last_qty": qty,
                "opened_from_slot": self.last_open_slot,
                "landing_slot": self.expected_landing_slot,
                "source": "gift_open",
                "note": ""
            }
            self.database[code_hex] = new_entry
            self.save_database()

            log_line = f"[NEW_ITEM_DISCOVERED] Mã: {code_hex} (Dec: {raw_code}, Bytes: {raw_bytes_str}) | SL: {qty} | Rơi vào Ô {self.expected_landing_slot}"
            self.write_log_line(f"[{timestamp}] {log_line}")

            # In thông báo nổi bật lên màn hình
            print("\n" + "=" * 80)
            print(f"{Colors.BOLD}{Colors.YELLOW}★ PHÁT HIỆN VẬT PHẨM MỚI KHI MỞ QUÀ (CHƯA CÓ TRONG DATABASE)! ★{Colors.RESET}")
            print(f"  • Mã Server 2-byte : {Colors.CYAN}{code_hex}{Colors.RESET} (Thập phân: {raw_code}, Bytes: {raw_bytes_str})")
            print(f"  • Số lượng nhận    : {Colors.GREEN}{qty}{Colors.RESET}")
            print(f"  • Vị trí rơi trong túi : {Colors.MAGENTA}Ô {self.expected_landing_slot}{Colors.RESET} (Mở từ Ô {self.last_open_slot})")
            print(f"  • Đã tự động lưu vào : {Colors.CYAN}{self.db_file}{Colors.RESET}")
            print("=" * 80)
            print(f"{Colors.BOLD}Nhập tên gợi nhớ cho vật phẩm {code_hex} [Hoặc nhấn Enter để bỏ qua]: {Colors.RESET}", end="", flush=True)

            self.current_prompt = {
                "step": "NAME_NEW_ITEM",
                "code_hex": code_hex
            }

    def on_item_discarded(self, raw_code, qty, slot, timestamp, source="discard"):
        """Xử lý vật phẩm khi người chơi vứt và lưu vào database nếu chưa có."""
        if not raw_code:
            return

        now = time.time()
        # Chống trùng lặp (debounce) giữa gói Sub: 0xD4 (popup) và Sub: 0x1A (xác nhận) trong vòng 2.0 giây
        if self.last_discard_event:
            last_code = self.last_discard_event.get("code")
            last_time = self.last_discard_event.get("time", 0)
            if last_code == raw_code and (now - last_time) < 2.0:
                self.write_log_line(f"[{timestamp}] [DISCARD_CONFIRMED] Xác nhận vứt xong mã 0x{raw_code:04X} (SL: {qty})")
                return

        self.last_discard_event = {
            "code": raw_code,
            "qty": qty,
            "slot": slot,
            "time": now
        }

        code_hex = format_item_code(raw_code)
        raw_bytes_str = f"{raw_code & 0xFF:02X} {(raw_code >> 8) & 0xFF:02X}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Cập nhật cache túi đồ nếu biết slot
        if slot and slot > 0 and slot in self.inventory_cache:
            if self.inventory_cache[slot].get("qty", 0) <= qty:
                del self.inventory_cache[slot]
            else:
                self.inventory_cache[slot]["qty"] -= qty

        # KIỂM TRA ĐÃ CÓ TRONG DATABASE CHƯA
        if code_hex in self.database:
            item_entry = self.database[code_hex]
            item_entry["times_discarded"] = item_entry.get("times_discarded", 0) + 1
            item_entry["last_seen"] = now_str
            item_entry["last_discarded_from_slot"] = slot
            item_entry["last_discarded_qty"] = qty
            self.save_database()

            name_display = item_entry.get("name") or "(Chưa đặt tên)"
            log_line = f"[ITEM_DISCARDED_EXISTED] Mã: {code_hex} ({name_display}) | SL: {qty} | Ô: {slot} | Số lần vứt: {item_entry['times_discarded']}"
            self.write_log_line(f"[{timestamp}] {log_line}")

            if not self.current_prompt:
                slot_str = f"Ô {slot}" if slot > 0 else "Túi đồ"
                print(f"{Colors.YELLOW}[🗑 VỨT VẬT PHẨM]{Colors.RESET} {Colors.BOLD}{name_display}{Colors.RESET} "
                      f"(Mã: {Colors.CYAN}{code_hex}{Colors.RESET}, SL: {qty}) | "
                      f"Tại {slot_str} | "
                      f"Đã vứt: {item_entry['times_discarded']} lần | Đã có trong database")
        else:
            # VẬT PHẨM MỚI HOÀN TOÀN TỪ THAO TÁC VỨT ĐỒ!
            new_entry = {
                "code_hex": code_hex,
                "code_dec": raw_code,
                "raw_bytes": raw_bytes_str,
                "name": "",
                "first_seen": now_str,
                "last_seen": now_str,
                "times_received": 0,
                "times_discarded": 1,
                "last_qty": qty,
                "opened_from_slot": -1,
                "landing_slot": -1,
                "last_discarded_from_slot": slot,
                "last_discarded_qty": qty,
                "source": "discard",
                "note": "Thu thập từ thao tác vứt đồ"
            }
            self.database[code_hex] = new_entry
            self.save_database()

            log_line = f"[NEW_ITEM_DISCARDED] Mã: {code_hex} (Dec: {raw_code}, Bytes: {raw_bytes_str}) | SL: {qty} | Tại Ô {slot}"
            self.write_log_line(f"[{timestamp}] {log_line}")

            slot_str = f"Ô {slot}" if slot > 0 else "Túi đồ"
            # In thông báo nổi bật lên màn hình console
            print("\n" + "=" * 80)
            print(f"{Colors.BOLD}{Colors.YELLOW}★ PHÁT HIỆN VẬT PHẨM MỚI KHI VỨT ĐỒ (CHƯA CÓ TRONG DATABASE)! ★{Colors.RESET}")
            print(f"  • Mã Server 2-byte : {Colors.CYAN}{code_hex}{Colors.RESET} (Thập phân: {raw_code}, Bytes: {raw_bytes_str})")
            print(f"  • Số lượng vứt     : {Colors.GREEN}{qty}{Colors.RESET}")
            print(f"  • Vị trí ô trong túi: {Colors.MAGENTA}{slot_str}{Colors.RESET}")
            print(f"  • Đã tự động lưu vào: {Colors.CYAN}{self.db_file}{Colors.RESET}")
            print("=" * 80)
            print(f"{Colors.BOLD}Nhập tên gợi nhớ cho vật phẩm {code_hex} [Hoặc nhấn Enter để bỏ qua]: {Colors.RESET}", end="", flush=True)

            self.current_prompt = {
                "step": "NAME_NEW_ITEM",
                "code_hex": code_hex
            }

    def show_items_list(self):
        """Hiển thị danh sách vật phẩm trong database dạng bảng."""
        if not self.database:
            print("\n[i] Cơ sở dữ liệu hiện đang trống. Hãy mở quà hoặc vứt một món đồ trong game để bắt đầu thu thập!\n")
            return

        print("\n" + "=" * 105)
        print(f"         DANH SÁCH VẬT PHẨM ĐÃ THU THẬP ĐƯỢC ({len(self.database)} VẬT PHẨM)")
        print("=" * 105)
        print(f"{'STT':<4} | {'Mã Hex':<8} | {'Mã Dec':<7} | {'Tên Vật Phẩm':<28} | {'Thống Kê':<16} | {'Ghi Chú':<12} | {'Lần Đầu Thấy'}")
        print("-" * 105)
        for idx, (hex_id, item) in enumerate(sorted(self.database.items()), 1):
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
            print(f"{idx:<4} | {Colors.CYAN}{hex_id:<8}{Colors.RESET} | {dec:<7} | {Colors.BOLD}{name:<28}{Colors.RESET} | {stats:<16} | {note:<12} | {first}")
        print("=" * 105)
        print(f"[*] Để đặt tên cho vật phẩm, gõ: name <Mã Hex> <Tên vật phẩm> (VD: name 0x8525 Đào Tiên)\n")

    def show_bag_inventory(self):
        """Hiển thị danh sách 50 ô túi đồ từ cache đồng bộ mạng (Op:0x17 Sub:0x05)."""
        if not self.inventory_cache:
            print("[!] Chưa có dữ liệu túi đồ (Server chỉ gửi danh sách này khi bạn Đăng nhập hoặc Chuyển map).")
            print("[*] Mẹo: Bạn có thể đi qua cổng chuyển map trong game để đồng bộ ngay danh sách 50 ô.")
            return

        print("\n" + "=" * 85)
        print(f"        TÚI ĐỒ ĐỒNG BỘ QUA MẠNG (ĐANG CÓ: {len(self.inventory_cache)} MÓN / 50 Ô)")
        print("=" * 85)
        print(f"{'Ô':<4} | {'Mã Hex':<8} | {'Mã Dec':<7} | {'SL':<4} | {'Tên Đã Lưu Trong Database'}")
        print("-" * 85)
        for s in range(1, 51):
            if s in self.inventory_cache:
                info = self.inventory_cache[s]
                code = info["code"]
                qty = info["qty"]
                hex_id = format_item_code(code)
                db_name = self.database.get(hex_id, {}).get("name") or "(Chưa có tên trong database)"
                print(f"Ô {s:2d} | {Colors.CYAN}{hex_id:<8}{Colors.RESET} | {code:<7} | {qty:<4} | {Colors.BOLD}{db_name}{Colors.RESET}")
            else:
                print(f"Ô {s:2d} | {Colors.GRAY}(TRỐNG){Colors.RESET}")
        print("=" * 85 + "\n")

    def find_items(self, query):
        """Tìm kiếm vật phẩm theo từ khóa."""
        query = query.strip().lower()
        matches = []
        for hex_id, item in self.database.items():
            name = item.get("name", "").lower()
            dec_str = str(item.get("code_dec", ""))
            hex_str = hex_id.lower()
            if query in hex_str or query in dec_str or query in name:
                matches.append((hex_id, item))

        if not matches:
            print(f"[!] Không tìm thấy vật phẩm nào khớp với từ khóa '{query}'.")
            return

        print(f"\n[*] Tìm thấy {len(matches)} vật phẩm phù hợp:")
        for hex_id, item in matches:
            name = item.get("name") or "(Chưa đặt tên)"
            dec = item.get("code_dec", 0)
            times = item.get("times_received", 1)
            print(f"  • {Colors.CYAN}{hex_id}{Colors.RESET} (Dec: {dec}): {Colors.BOLD}{name}{Colors.RESET} - Đã mở: {times} lần")
        print()

    def set_item_name(self, code_int_or_hex, name):
        """Đặt hoặc cập nhật tên cho vật phẩm."""
        code_hex = None
        if isinstance(code_int_or_hex, int):
            code_hex = format_item_code(code_int_or_hex)
        else:
            code_int = parse_code_input(code_int_or_hex)
            if code_int is not None:
                code_hex = format_item_code(code_int)
            elif code_int_or_hex.upper() in self.database:
                code_hex = code_int_or_hex.upper()

        if not code_hex or code_hex not in self.database:
            print(f"[!] Không tìm thấy mã '{code_int_or_hex}' trong database.")
            return

        self.database[code_hex]["name"] = name
        self.save_database()
        print(f"{Colors.GREEN}[✓] Đã cập nhật tên cho {code_hex}: '{name}'!{Colors.RESET}")
        self.write_log_line(f"[{datetime.now().strftime('%H:%M:%S')}] Đổi tên {code_hex} thành '{name}'")

    def show_bag_status(self):
        """Hiển thị trạng thái các ô túi đồ thực tế từ bộ nhớ game."""
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
        print("     WLO SMART ITEM COLLECTOR & DATABASE BUILDER (READ-ONLY)")
        print("=" * 80)
        print(f"[*] File cơ sở dữ liệu JSON   : {Colors.CYAN}{self.db_file}{Colors.RESET}")
        print(f"[*] File báo cáo danh sách TXT: {Colors.CYAN}{self.txt_file}{Colors.RESET}")
        print(f"[*] File nhật ký log          : {Colors.CYAN}{self.log_file}{Colors.RESET}")
        print(f"[*] Số vật phẩm hiện có       : {Colors.GREEN}{len(self.database)}{Colors.RESET} loại")
        print(f"[*] Chế độ hoạt động          : {Colors.GREEN}Giám sát thuần túy (Mở quà & Vứt đồ, không can thiệp game){Colors.RESET}")
        print("-" * 80)

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

            print(f"{Colors.GREEN}[+] Đính kèm thành công! Đang theo dõi gói tin Mở quà & Vứt đồ...{Colors.RESET}")
            print(f"[*] Mẹo:")
            print(f"    - Mở hộp quà / túi quà: Tự động lưu phần thưởng nhận được.")
            print(f"    - Vứt đồ ra ngoài: Tự động lưu thông tin vật phẩm bị vứt vào database.")
            print("-" * 80)

        except Exception as e:
            print(f"{Colors.RED}[!] Không thể đính kèm vào game: {e}{Colors.RESET}")
            return

        self.running = True

        self.packet_worker_thread = threading.Thread(target=self.packet_worker, daemon=True)
        self.packet_worker_thread.start()

        self.console_loop()

    def console_loop(self):
        """Vòng lặp nhận lệnh điều khiển từ người dùng."""
        print(f"{Colors.BOLD}Lệnh hỗ trợ: [list] xem database | [inv] xem đồ trong túi | [name <Mã> <Tên>] đặt tên | [find <từ khóa>] | [bag] xem ô trống | [exit]{Colors.RESET}\n")
        while self.running:
            try:
                user_input = input().strip()
            except (EOFError, KeyboardInterrupt):
                break

            # Xử lý khi đang chờ người dùng nhập tên cho item mới vừa mở hoặc vừa vứt
            if self.current_prompt:
                step = self.current_prompt.get("step")
                if step == "NAME_NEW_ITEM":
                    code_hex = self.current_prompt.get("code_hex")
                    chosen_name = user_input if user_input else f"Vật phẩm_{code_hex}"
                    self.database[code_hex]["name"] = chosen_name
                    self.save_database()
                    print(f"{Colors.GREEN}[✓] Đã lưu tên: '{chosen_name}' cho mã {code_hex}!{Colors.RESET}\n")
                    self.current_prompt = None
                    continue

            if not user_input:
                continue

            parts = user_input.split()
            base = parts[0].lower()

            if base in ("exit", "quit", "q"):
                break
            elif base == "list":
                self.show_items_list()
            elif base == "inv":
                self.show_bag_inventory()
            elif base == "name":
                if len(parts) >= 3:
                    code_str = parts[1]
                    item_name = " ".join(parts[2:]).strip()
                    self.set_item_name(code_str, item_name)
                else:
                    print("[!] Cú pháp: name <Mã 0xXXXX> <Tên gợi nhớ> (VD: name 0x8525 Đào Tiên)")
            elif base == "find":
                if len(parts) >= 2:
                    query = " ".join(parts[1:]).strip()
                    self.find_items(query)
                else:
                    print("[!] Cú pháp: find <từ khóa> (VD: find 8525 hoặc find Đào)")
            elif base == "bag":
                self.show_bag_status()
            elif base == "export":
                self.export_text_report()
                print(f"{Colors.GREEN}[✓] Đã xuất báo cáo ra file: {self.txt_file}{Colors.RESET}")
            elif base == "status":
                sock = self.script.exports_sync.getsocket() if self.script else -1
                empty_slot = self.get_first_empty_slot()
                print(f"[*] Active Socket: {sock} | Ô trống đầu tiên trong túi: Ô {empty_slot} | Tổng vật phẩm đã lưu: {len(self.database)} | Đang trong túi: {len(self.inventory_cache)} món")
            elif base == "clear":
                os.system("cls" if os.name == "nt" else "clear")
            elif base == "help":
                print("\nDanh sách lệnh hỗ trợ:")
                print("  list               : Xem toàn bộ vật phẩm đã thu thập trong database")
                print("  inv                : Xem danh sách vật phẩm trong 50 ô túi đồ (đồng bộ qua mạng)")
                print("  name <Mã> <Tên>    : Đặt hoặc đổi tên cho vật phẩm (VD: name 0x8525 Đào Tiên)")
                print("  find <từ khóa>     : Tìm kiếm vật phẩm theo mã Hex, Dec hoặc tên")
                print("  bag                : Xem trạng thái thực tế 50 ô đồ trong túi (quét bộ nhớ Delphi)")
                print("  export             : Xuất cơ sở dữ liệu ra file text bảng biểu")
                print("  status             : Xem trạng thái socket và tổng số lượng vật phẩm")
                print("  clear              : Xóa sạch màn hình console")
                print("  exit               : Dừng script an toàn\n")
            else:
                print("[?] Lệnh không hợp lệ. Gõ 'help' để xem hướng dẫn.")

    def stop(self):
        self.running = False
        print("\n[*] Đang dừng Item Collector...")
        try:
            if self.script:
                self.script.unload()
            if self.session:
                self.session.detach()
        except Exception:
            pass
        if self.log_handle:
            try:
                self.write_log_line(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] DỪNG COLLECTOR (Tổng vật phẩm: {len(self.database)})\n")
                self.log_handle.close()
            except Exception:
                pass
        print(f"{Colors.GREEN}[+] Đã thoát an toàn.{Colors.RESET}")

# ==============================================================================
# TÌM TIẾN TRÌNH ALOGIN
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
    parser = argparse.ArgumentParser(description="WLO Smart Item Collector & Database Builder")
    parser.add_argument("-p", "--process", default=None, help="Tên tiến trình (VD: alogin-W01.exe, alogin.exe)")
    parser.add_argument("--pid", type=int, default=None, help="PID của tiến trình game")
    parser.add_argument("--db", default=None, help="Đường dẫn file database JSON")
    parser.add_argument("--log", default=None, help="Đường dẫn file log")

    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = args.db or os.path.join(script_dir, "wlo_items_database.json")
    txt_path = os.path.join(script_dir, "wlo_items_database.txt")
    log_path = args.log or os.path.join(script_dir, "item_collector_log.txt")

    target_process = args.process
    target_pid = args.pid

    if not target_process and not target_pid:
        running_procs = find_alogin_processes()
        if not running_procs:
            print("[!] Không tìm thấy tiến trình alogin*.exe nào đang chạy!")
            print("[*] Vui lòng mở game trước hoặc chỉ định PID: python wlo_item_collector.py --pid <PID>")
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

    collector = WLOItemCollector(
        target_process=target_process,
        target_pid=target_pid,
        db_file=db_path,
        txt_file=txt_path,
        log_file=log_path
    )
    collector.start()

if __name__ == "__main__":
    main()
