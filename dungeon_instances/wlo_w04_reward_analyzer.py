#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO W04 REWARD & GIFT OPENING LIVE ANALYZER
===========================================
Công cụ chuyên biệt theo dõi, bóc tách và phân tích thời gian thực:
- Tiến trình mục tiêu: alogin-W04.exe / alogin-w04
- Tự động bắt gói tin Đăng nhập (Login), nhận diện Char ID và đồng bộ túi đồ ban đầu.
- Khi người dùng nhấp MỞ CÁC PHẦN QUÀ / HỘP THƯỞNG:
  1. Ghi nhận vị trí Ô Slot và tên loại Hộp quà đang mở (C->S Op: 0x17 Sub: 0x4B / 0x01).
  2. Bắt gói tin Server trả thưởng (S->C Op: 0x17 Sub: 0x06): Phân tích mã Item ID (Hex & Dec), số lượng.
  3. Tra cứu ngay tên vật phẩm từ wlo_items_database.json và từ điển WLO.
  4. Ghi nhận tiêu hao hộp quà (S->C Op: 0x17 Sub: 0x09 / 0x07).
  5. Thống kê tỷ lệ rơi đồ (Drop Rate & Drop List) theo từng loại hộp quà.
  6. Tự động lưu các vật phẩm mới vào wlo_items_database.json.
  7. Tự động kết nối lại (Auto-reconnect) nếu tài khoản relog hoặc đổi tiến trình.
"""

import os
import sys
import time
import json
import struct
import threading
from datetime import datetime

# Cấu hình encoding console UTF-8 trên Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

try:
    import frida
except ImportError:
    print("[!] Chưa cài đặt frida. Chạy lệnh: pip install frida")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "w04_reward_opening_analysis.log")
SUMMARY_FILE = os.path.join(SCRIPT_DIR, "w04_reward_drop_summary.txt")
DB_FILE = os.path.join(SCRIPT_DIR, "wlo_items_database.json")

# Danh sách tên các hộp quà và vật phẩm quen thuộc
KNOWN_BOXES = {
    0x8544: "Hộp Quà Thần Bí (Mysterious Gift Box)",
    0x8545: "Hộp Quà May Mắn (Lucky Gift Box)",
    0x8546: "Túi Phúc Hoàng Kim (Golden Fortune Bag)",
    0x8547: "Túi Phúc Bạch Ngân (Silver Fortune Bag)",
    0x8548: "Hộp Quà Lễ Hội (Festival Gift Box)",
    0x8549: "Túi Quà Tân Thủ (Newbie Gift Bag)",
    0x854A: "Hộp Thưởng Hoạt Động (Event Reward Box)",
    0x84D8: "Hộp Quà Bất Ngờ (Surprise Box)",
    0x7DA0: "Hộp Thức Ăn Thượng Hạng (Deluxe Food Box)",
    0x7DA1: "Hộp Thức Ăn Đặc Biệt (Special Food Box)",
    0x7D30: "Hộp Kho Báu Tháp (Tower Treasure Box)",
    0x7D31: "Hộp Thưởng Ải Tháp (Tower Stage Box)",
}

FRIDA_HOOK_JS = """
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
            if (Object.keys(items).length > 0) {
                return {success: true, cached: true, items: items};
            }
        } catch(e) {
            cachedBagBase = null;
        }
    }

    var ranges = Process.enumerateRanges('rw-');
    var sigs = [
        {sig: '01 1c 86', off: 0},
        {sig: '02 ac 75', off: 4},
        {sig: '05 1c 86', off: 16},
        {sig: '09 ac 75', off: 32}
    ];

    for (var si = 0; si < sigs.length; si++) {
        var sDef = sigs[si];
        for (var i = 0; i < ranges.length; i++) {
            var r = ranges[i];
            if (r.size > 2 * 1024 * 1024) continue;
            try {
                var m = Memory.scanSync(r.base, r.size, sDef.sig);
                for (var j = 0; j < m.length; j++) {
                    var base = m[j].address.sub(sDef.off);
                    var items = {};
                    for (var s = 1; s <= 50; s++) {
                        var entry = base.add((s - 1) * 4);
                        var slot = entry.readU8();
                        var code = entry.add(1).readU16();
                        var qty = entry.add(3).readU8();
                        if (slot === s && code > 0 && qty > 0) {
                            items[s] = {code: code, qty: qty};
                        }
                    }
                    if (Object.keys(items).length >= 2) {
                        cachedBagBase = base;
                        return {success: true, cached: false, items: items};
                    }
                }
            } catch(e) {}
        }
    }
    return {success: false, items: {}};
}

rpc.exports = {
    getsocket: function() { return activeSocket; },
    readbag: function() { return readBagMemory(); }
};
"""


class WLOStreamDissector:
    """Tái ghép luồng TCP và giải mã gói tin WLO (Magic 0xF444, XOR 0xAD)"""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, raw_bytes):
        decrypted = bytearray(b ^ 0xAD for b in raw_bytes)
        self.buffer.extend(decrypted)
        packets = []

        while len(self.buffer) >= 4:
            magic = struct.unpack("<H", self.buffer[:2])[0]
            if magic != 0x44F4:
                idx = -1
                for i in range(len(self.buffer) - 1):
                    if self.buffer[i] == 0xF4 and self.buffer[i + 1] == 0x44:
                        idx = i
                        break
                if idx != -1:
                    del self.buffer[:idx]
                    if len(self.buffer) < 4:
                        break
                else:
                    self.buffer.clear()
                    break

            payload_len = struct.unpack("<H", self.buffer[2:4])[0]
            total_pkt_len = 4 + payload_len

            if len(self.buffer) < total_pkt_len:
                break

            full_pkt = bytes(self.buffer[:total_pkt_len])
            payload = bytes(self.buffer[4:total_pkt_len])
            del self.buffer[:total_pkt_len]

            if len(payload) > 0:
                opcode = payload[0]
                subcode = payload[1] if len(payload) > 1 else None
                data = payload[2:] if len(payload) > 1 else b""
                packets.append((opcode, subcode, data, full_pkt))

        return packets


class W04RewardAnalyzer:
    def __init__(self):
        self.target_name = "alogin-w04"
        self.session = None
        self.script = None
        self.current_pid = None
        self.running = True
        self.dissector_c2s = WLOStreamDissector()
        self.dissector_s2c = WLOStreamDissector()

        # Database vật phẩm
        self.items_db = self.load_database()

        # Trạng thái nhân vật & túi đồ
        self.char_id = None
        self.char_name = "W04"
        self.inventory = {}  # slot (1..50) -> {"code": int, "qty": int, "name": str}
        self.last_opened_slot = None
        self.last_opened_box_code = None
        self.last_opened_box_name = None
        self.last_open_time = 0

        # Thống kê mở quà
        # box_code -> {"name": str, "total_opened": int, "drops": {item_code: {"name": str, "qty": int, "times": int}}}
        self.drop_statistics = {}

        # Mở file log
        self.log_file_handle = open(LOG_FILE, "a", encoding="utf-8")
        self.write_log_header()

    def load_database(self) -> dict:
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_database(self):
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(self.items_db, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_item_name(self, code: int) -> str:
        code_hex = f"0x{code:04X}"
        if code in KNOWN_BOXES:
            return KNOWN_BOXES[code]
        if code_hex in self.items_db:
            name = self.items_db[code_hex].get("name", "")
            if name:
                return name
        return f"Vật phẩm_{code_hex}"

    def write_log_header(self):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hdr = f"\n{'=' * 85}\n   WLO W04 REWARD OPENING MONITOR SESSION - {ts}\n{'=' * 85}\n"
        self.log_file_handle.write(hdr)
        self.log_file_handle.flush()

    def log(self, tag: str, msg: str, console_color: str = ""):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{ts}] [{tag:<16}] {msg}"
        print(f"{console_color}{line}\033[0m" if console_color else line, flush=True)
        self.log_file_handle.write(line + "\n")
        self.log_file_handle.flush()

    def find_target_pid(self):
        try:
            import psutil
            for proc in psutil.process_iter(["pid", "name"]):
                name = (proc.info.get("name") or "").lower()
                if "alogin-w04" in name or "alogin_w04" in name or "aloginw04" in name:
                    return proc.info["pid"]
        except ImportError:
            # Dùng tasklist trên Windows
            import subprocess
            res = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True)
            for row in res.stdout.strip().splitlines():
                parts = row.replace('"', '').split(',')
                if len(parts) >= 2:
                    pname = parts[0].lower()
                    if "alogin-w04" in pname or "aloginw04" in pname:
                        try:
                            return int(parts[1])
                        except ValueError:
                            pass
        return None

    def attach_client(self) -> bool:
        pid = self.find_target_pid()
        if not pid:
            return False

        if self.current_pid == pid and self.session:
            return True

        self.log("INIT", f"🔍 Phát hiện tiến trình alogin-W04 (PID: {pid}). Đang kết nối...", "\033[96m")
        try:
            session = frida.attach(pid)
            script = session.create_script(FRIDA_HOOK_JS)
            script.on("message", self.on_frida_message)
            script.load()

            self.session = session
            self.script = script
            self.current_pid = pid
            self.dissector_c2s = WLOStreamDissector()
            self.dissector_s2c = WLOStreamDissector()

            self.log("ATTACH_SUCCESS", f"✔ ĐÃ KẾT NỐI THÀNH CÔNG VÀO ALOGIN-W04 (PID: {pid})!", "\033[92m")
            self.log("READY", "★ SẴN SÀNG! Hãy thực hiện Đăng nhập và Mở các hộp quà thưởng trên game.", "\033[93m")
            return True
        except Exception as e:
            self.log("ATTACH_ERROR", f"❌ Lỗi khi đính kèm PID {pid}: {e}", "\033[91m")
            self.session = None
            self.script = None
            self.current_pid = None
            return False

    def on_frida_message(self, message: dict, raw_data: bytes):
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "recv")
        is_send = (dir_name == "send")

        dissector = self.dissector_c2s if is_send else self.dissector_s2c
        packets = dissector.feed(raw_data)

        for opcode, subcode, data, full_pkt in packets:
            self.handle_packet(is_send, opcode, subcode, data, full_pkt)

    def handle_packet(self, is_send: bool, opcode: int, subcode: int, data: bytes, full_pkt: bytes):
        # ----------------------------------------------------------------------
        # GỬI LÊN (CLIENT -> SERVER)
        # ----------------------------------------------------------------------
        if is_send:
            # 1. Đăng nhập: C->S Op: 0x05 Sub: 0x01
            if opcode == 0x05 and subcode == 0x01:
                self.log("C2S_LOGIN", "🔑 Gửi gói tin thông tin Đăng nhập (Account Auth)...", "\033[96m")

            # 2. Dùng/Mở vật phẩm tại Ô Slot: C->S Op: 0x17 Sub: 0x4B [slot 1B, count 1B]
            elif opcode == 0x17 and subcode == 0x4B and len(data) >= 1:
                slot = data[0]
                cnt = data[1] if len(data) >= 2 else 1
                self.last_opened_slot = slot
                self.last_open_time = time.time()

                box_info = self.inventory.get(slot, {})
                box_code = box_info.get("code")
                box_name = box_info.get("name") or self.get_item_name(box_code) if box_code else f"Ô Slot #{slot:02d}"
                self.last_opened_box_code = box_code
                self.last_opened_box_name = box_name

                code_str = f" [Mã 0x{box_code:04X}]" if box_code else ""
                self.log("ACTION_USE_ITEM", f"👉 [MỞ HỘP QUÀ] Nhấp mở tại Ô Slot {slot:02d}: {box_name}{code_str} x{cnt}", "\033[95m")

            # 3. Dùng vật phẩm thông thường: C->S Op: 0x17 Sub: 0x01 [slot 1B, ...]
            elif opcode == 0x17 and subcode == 0x01 and len(data) >= 1:
                slot = data[0]
                box_info = self.inventory.get(slot, {})
                box_code = box_info.get("code")
                box_name = box_info.get("name") or self.get_item_name(box_code) if box_code else f"Ô Slot #{slot:02d}"
                self.last_opened_slot = slot
                self.last_open_time = time.time()
                self.last_opened_box_code = box_code
                self.last_opened_box_name = box_name
                self.log("ACTION_USE_ITEM", f"👉 [DÙNG VẬT PHẨM] Ô Slot {slot:02d}: {box_name}", "\033[95m")

            # 4. Di chuyển / xếp đồ: C->S Op: 0x17 Sub: 0x0A [src_slot, qty, dest_slot]
            elif opcode == 0x17 and subcode == 0x0A and len(data) >= 3:
                src, qty, dest = data[0], data[1], data[2]
                self.log("C2S_MOVE", f"🔄 [DI CHUYỂN ĐỒ] Yêu cầu chuyển từ Ô {src:02d} -> Ô {dest:02d} (x{qty})")

            # 5. Vứt đồ: C->S Op: 0x17 Sub: 0x03 [slot, qty, ...]
            elif opcode == 0x17 and subcode == 0x03 and len(data) >= 2:
                slot, qty = data[0], data[1]
                it = self.inventory.get(slot, {})
                name = it.get("name") or self.get_item_name(it.get("code", 0))
                self.log("C2S_DISCARD", f"🗑️ [YÊU CẦU VỨT ĐỒ] Ô {slot:02d}: {name} x{qty}", "\033[91m")

            return

        # ----------------------------------------------------------------------
        # SERVER TRẢ VỀ (SERVER -> CLIENT)
        # ----------------------------------------------------------------------
        # 1. Nhận diện Char ID khi đăng nhập: S->C Op: 0x05 Sub: 0x08 hoặc 0x1E
        if opcode == 0x05 and subcode in (0x08, 0x1E) and len(data) >= 4:
            cid = struct.unpack("<I", data[:4])[0] if subcode == 0x08 else struct.unpack("<I", data[6:10])[0] if len(data) >= 10 else 0
            if cid > 1000:
                self.char_id = cid
                self.log("LOGIN_CHAR_ID", f"★ ĐÃ NHẬN DIỆN CHAR ID: 0x{cid:08X} (Dec: {cid})", "\033[92m")

        # 2. Khởi tạo túi đồ ban đầu khi login/đổi map: S->C Op: 0x17 Sub: 0x05
        elif opcode == 0x17 and subcode == 0x05:
            entry_len = 31
            num_entries = len(data) // entry_len
            self.inventory = {}
            for i in range(num_entries):
                entry = data[i * entry_len : (i + 1) * entry_len]
                slot = entry[0]
                code = struct.unpack("<H", entry[1:3])[0]
                qty = entry[3]
                name = self.get_item_name(code)
                self.inventory[slot] = {"code": code, "qty": qty, "name": name}

            self.log("INVENTORY_SYNC", f"🎒 [SERVER] Đã đồng bộ túi đồ ban đầu: {len(self.inventory)} món đồ trong túi.", "\033[92m")
            self.print_current_inventory_boxes()

        # 3. NHẬN VẬT PHẨM MỚI / THƯỞNG RƠI RA: S->C Op: 0x17 Sub: 0x06
        elif opcode == 0x17 and subcode == 0x06 and len(data) >= 2:
            item_id = struct.unpack("<H", data[:2])[0]
            qty = data[2] if len(data) >= 3 else 1
            code_hex = f"0x{item_id:04X}"
            item_name = self.get_item_name(item_id)

            # Phân tích nguồn gốc rơi (từ hộp quà vừa mở)
            source_desc = ""
            if self.last_opened_box_name and (time.time() - self.last_open_time < 3.0):
                source_desc = f" (Từ hộp: {self.last_opened_box_name})"
                self.record_drop_stat(self.last_opened_box_code, self.last_opened_box_name, item_id, item_name, qty)

            self.log("🎁 REWARD_DROP", 
                     f"★ [NHẬN ĐƯỢC PHẦN THƯỞNG] Mã: {code_hex} ({item_id}) | Tên: {item_name} x{qty}{source_desc}", 
                     "\033[92m")

            # Cập nhật vào wlo_items_database.json nếu là đồ mới hoặc cập nhật thời gian
            is_new = code_hex not in self.items_db
            if is_new:
                self.items_db[code_hex] = {
                    "code_hex": code_hex,
                    "code_dec": item_id,
                    "name": item_name,
                    "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "times_received": 1,
                    "last_qty": qty,
                    "opened_from_box": self.last_opened_box_name or "",
                    "note": "Thu thập từ phiên mở quà W04"
                }
                self.log("NEW_ITEM_DB", f"✨ [VẬT PHẨM MỚI KHÁM PHÁ] Đã tự động lưu mã {code_hex} ({item_name}) vào database!", "\033[93m")
                self.save_database()
            else:
                self.items_db[code_hex]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.items_db[code_hex]["times_received"] = self.items_db[code_hex].get("times_received", 0) + 1
                self.items_db[code_hex]["last_qty"] = qty
                self.save_database()

            self.export_drop_summary()

        # 4. TIÊU THỤ / GIẢM SỐ LƯỢNG HỘP QUÀ TẠI Ô SLOT: S->C Op: 0x17 Sub: 0x09
        elif opcode == 0x17 and subcode == 0x09 and len(data) >= 2:
            slot, remain = data[0], data[1]
            old_info = self.inventory.get(slot, {})
            name = old_info.get("name") or self.get_item_name(old_info.get("code", 0))

            if remain == 0:
                self.inventory.pop(slot, None)
                self.log("BOX_CONSUMED", f"📦 [HẾT HỘP QUÀ] Ô Slot {slot:02d} ({name}) đã dùng hết!", "\033[94m")
            else:
                if slot in self.inventory:
                    self.inventory[slot]["qty"] = remain
                self.log("BOX_DECREMENT", f"📦 [TIÊU THỤ HỘP QUÀ] Ô Slot {slot:02d} ({name}) giảm còn: {remain} cái", "\033[94m")

        # 5. CẬP NHẬT Ô ĐỒ: S->C Op: 0x17 Sub: 0x07
        elif opcode == 0x17 and subcode == 0x07 and len(data) >= 4:
            slot = data[0]
            code = struct.unpack("<H", data[1:3])[0]
            qty = data[3]
            name = self.get_item_name(code)
            self.inventory[slot] = {"code": code, "qty": qty, "name": name}
            self.log("INVENTORY_UPDATE", f"🎒 [CẬP NHẬT Ô {slot:02d}] Mã 0x{code:04X} ({name}) x{qty}")

        # 6. DI CHUYỂN VẬT PHẨM: S->C Op: 0x17 Sub: 0x0A
        elif opcode == 0x17 and subcode == 0x0A and len(data) >= 3:
            src, qty, dest = data[0], data[1], data[2]
            src_it = self.inventory.get(src, {})
            name = src_it.get("name") or "Vật phẩm"
            self.log("ITEM_MOVED", f"🔄 [DI CHUYỂN ĐỒ THÀNH CÔNG] {name} x{qty} từ Ô {src:02d} -> Ô {dest:02d}")

        # 7. HỘP THOẠI / THÔNG BÁO TỪ HỆ THỐNG: S->C Op: 0x14 Sub: 0x01 / 0x02
        elif opcode == 0x14:
            text = ""
            for enc in ("utf-8", "cp950", "big5", "latin1"):
                try:
                    text = data.decode(enc).strip()
                    break
                except Exception:
                    pass
            if text:
                self.log("SYS_MESSAGE", f"💬 [THÔNG BÁO] {text}", "\033[93m")

    def record_drop_stat(self, box_code, box_name, item_code, item_name, qty):
        bkey = f"0x{box_code:04X}" if box_code else box_name
        if bkey not in self.drop_statistics:
            self.drop_statistics[bkey] = {
                "box_name": box_name,
                "total_opened": 0,
                "drops": {}
            }
        self.drop_statistics[bkey]["total_opened"] += 1

        dkey = f"0x{item_code:04X}"
        drops = self.drop_statistics[bkey]["drops"]
        if dkey not in drops:
            drops[dkey] = {
                "name": item_name,
                "total_qty": 0,
                "times": 0
            }
        drops[dkey]["total_qty"] += qty
        drops[dkey]["times"] += 1

    def print_current_inventory_boxes(self):
        """Liệt kê các hộp quà hoặc vật phẩm đang có trong túi đồ của W04"""
        print("\n" + "=" * 70)
        print("        DANH SÁCH VẬT PHẨM & HỘP QUÀ HIỆN CÓ TRONG TÚI ĐỒ (W04)")
        print("=" * 70)
        if not self.inventory:
            print("  (Túi đồ hiện đang trống hoặc chưa đồng bộ)")
        else:
            for slot in sorted(self.inventory.keys()):
                it = self.inventory[slot]
                code_hex = f"0x{it['code']:04X}"
                is_box = ("hộp" in it['name'].lower() or "túi" in it['name'].lower() or "box" in it['name'].lower() or "bag" in it['name'].lower())
                marker = " 🎁 [HỘP QUÀ]" if is_box else ""
                print(f"  Ô Slot {slot:02d} | Mã: {code_hex} ({it['code']:<5d}) | x{it['qty']:<3d} | {it['name']}{marker}")
        print("=" * 70 + "\n")

    def export_drop_summary(self):
        """Xuất bảng tổng hợp kết quả mở quà ra file text"""
        try:
            with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
                f.write("=====================================================================\n")
                f.write("         BẢNG THỐNG KÊ KẾT QUẢ MỞ HỘP QUÀ W04 (NATIONAL TREASURE / EVENT)\n")
                f.write(f"         Thời gian cập nhật: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=====================================================================\n\n")

                if not self.drop_statistics:
                    f.write("Chưa ghi nhận lần mở quà nào trong phiên hiện tại.\n")
                    return

                for bkey, binfo in self.drop_statistics.items():
                    f.write(f"📦 LOẠI HỘP: {binfo['box_name']} (Mã: {bkey})\n")
                    f.write(f"   Tổng số lần mở ghi nhận: {binfo['total_opened']} lần\n")
                    f.write("   -----------------------------------------------------------------\n")
                    f.write("   Mã Hex   | Mã Dec | Tên Phần Thưởng Nhận Được       | Số Lượng | Tỉ Lệ\n")
                    f.write("   -----------------------------------------------------------------\n")
                    for dkey, dval in binfo["drops"].items():
                        rate = (dval["times"] / binfo["total_opened"]) * 100 if binfo["total_opened"] > 0 else 0
                        f.write(f"   {dkey:<8} | {int(dkey, 16):<6} | {dval['name']:<32} | x{dval['total_qty']:<7} | {rate:5.1f}%\n")
                    f.write("\n")
        except Exception:
            pass

    def run(self):
        print("\n" + "=" * 80)
        print("      WLO W04 REWARD & GIFT OPENING LIVE ANALYZER & MONITOR")
        print("=" * 80)
        print("  [*] Mục tiêu theo dõi: Tiến trình alogin-W04.exe")
        print("  [*] Nhiệm vụ:")
        print("      - Bắt gói tin Đăng nhập (Login Auth, Char ID, Túi đồ ban đầu).")
        print("      - Phân tích chi tiết mỗi lần nhấp mở Hộp quà / Túi thưởng.")
        print("      - Nhận diện tức thì mã phần thưởng nhận được (Hex & Dec).")
        print("      - Tự động tra cứu tên và lưu vật phẩm mới vào database.")
        print("      - Thống kê tỷ lệ rơi đồ ra file: w04_reward_drop_summary.txt")
        print("=" * 80 + "\n")

        print("[*] Đang chờ tiến trình alogin-W04.exe hoạt động...\n")
        while self.running:
            try:
                if not self.session:
                    self.attach_client()
                time.sleep(1.0)
            except KeyboardInterrupt:
                print("\n[!] Đang dừng giám sát...")
                self.running = False
                break
            except Exception as e:
                time.sleep(1.0)

        if self.log_file_handle:
            self.log_file_handle.close()
        print("[✔] Đã đóng giám sát an toàn.")


if __name__ == "__main__":
    analyzer = W04RewardAnalyzer()
    analyzer.run()
