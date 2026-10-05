#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO MULTI-CLIENT PARTY INSTANCE PACKET CAPTURE & ANALYZER
=========================================================
Giám sát thời gian thực toàn bộ luồng gói tin gửi / nhận (C->S & S->C)
trên cả 3 tiến trình alogin-W01, alogin-F02, alogin-F04 khi đi Instance tổ đội.

Tính năng phân tích:
1. TỔ ĐỘI & ĐỘI HÌNH (PARTY SYSTEM):
   - Mời nhóm, chấp thuận, chuyển đội trưởng, đồng bộ thành viên (Op: 0x0D, Op: 0x07).
2. PHỤ BẢN & SẢNH LOBBY (INSTANCE & LOBBY):
   - Mở sảnh, chọn mã Phụ bản ID (Op: 0x55 Sub: 0x03).
   - Chat 'go' sẵn sàng (Op: 0x02 Sub: 0x02) & bắt đầu phụ bản (Op: 0x55 Sub: 0x02).
   - Nạp map bản đồ cảnh mới (Op: 0x16 Sub: 0x04, Op: 0x35).
3. DI CHUYỂN & TƯƠNG TÁC NPC:
   - Tọa độ di chuyển (Op: 0x06 Sub: 0x01).
   - Đối thoại NPC và chọn Menu Option (Op: 0x14, Op: 0x20 Sub: 0x02).
   - Tương tác đối tượng trên bản đồ: Chiếc Lu, rương, cửa (Op: 0x14 Sub: 0x01, Op: 0x06 Sub: 0x02).
4. CHIẾN ĐẤU ĐA THÀNH VIÊN (MULTI-COMBAT):
   - Vào trận (Op: 0x0B Sub: 0xFA / 0x02) & Kết thúc trận (Op: 0x0B Sub: 0x00).
   - Lượt đánh / cập nhật hiệp (Op: 0x0B Sub: 0x01).
   - Hành động ra chiêu của từng thành viên (Char & Pet) (Op: 0x32 Sub: 0x01):
     Slot, Row, Mục tiêu, Mã Skill & Tên chiêu thức.
5. VẬT PHẨM & PHẦN THƯỞNG (REWARDS & ITEMS):
   - Nhận thưởng từng thành viên sau ải/sau boss (Op: 0x17 Sub: 0x06).
   - Tự động tra cứu tên vật phẩm từ wlo_items_database.json.
   - Sử dụng dược phẩm / cắn thuốc hồi phục (Op: 0x17 Sub: 0x0F).
"""

import os
import sys
import time
import json
import struct
import threading
from datetime import datetime

# Thiết lập encoding UTF-8 console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

try:
    import frida
except ImportError:
    print("[!] Chưa cài đặt thư viện frida. Vui lòng chạy: pip install frida")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "party_instance_capture.log")
DB_FILE = os.path.join(SCRIPT_DIR, "wlo_items_database.json")

# Nạp cơ sở dữ liệu vật phẩm
ITEM_DB = {}
if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            ITEM_DB = json.load(f)
    except Exception:
        pass

# Bảng mã tên chiêu thức đã biết
KNOWN_SKILLS = {
    "75ea": "Phòng thủ (Defend)",
    "1f3b": "Hỏa Long Kích / Liệt Hỏa (Char F04/F02)",
    "043b": "Sát thương Pet Hỏa (Pet F04/F02)",
    "d861": "Sát thương Thủy/Địa (Char W04/W03/W01)",
    "a33a": "Sát thương Pet Thủy/Địa (Pet W04/W03/W01)",
    "2b2b": "Phong Kích (Char Wi01)",
    "393b": "Sát thương Pet Phong (Pet Wi01)",
    "212b": "Kỹ năng Quét Pet (Pet AoE)",
    "2d2b": "Đòn đánh Pet Thường",
    "0000": "Đánh thường / Không dùng skill",
}

# Tên Opcode
OPCODE_NAMES = {
    0x01: "SYSTEM_HANDSHAKE",
    0x02: "ACCOUNT_CHAR_LIST",
    0x03: "CHANNEL_INFO",
    0x04: "SKILL_EFFECT",
    0x05: "LOGIN_AUTH",
    0x06: "MOVEMENT_OR_CLICK",
    0x07: "TEAM_FORMATION",
    0x08: "PING_HEARTBEAT",
    0x0A: "TRADE_STALL",
    0x0B: "COMBAT_STATUS",
    0x0C: "FRIEND_MAIL",
    0x0D: "PARTY_SYSTEM",
    0x0E: "PET_ACTION",
    0x0F: "PET_STATUS",
    0x10: "TENT_FURNITURE",
    0x13: "SYNTHESIS_PET",
    0x14: "CHAT_DIALOG_TEXT",
    0x16: "MAP_SCENE_QUEST",
    0x17: "INVENTORY_ITEMS",
    0x18: "SHORTCUT_POPUP_MENU",
    0x20: "NPC_DIALOG_CHOICE",
    0x32: "COMBAT_ACTION_MOVE",
    0x33: "COMBAT_TURN_STATUS",
    0x34: "COMBAT_ROUND_START",
    0x35: "MAP_WARP_PORTAL",
    0x55: "DUNGEON_INSTANCE_LOBBY",
    0x59: "UI_SYSTEM_PARAM",
    0x5C: "CLIENT_SYNC",
}

FRIDA_JS = """
var activeSocket = -1;

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
hookSend('wsock32.dll');
hookSend('ws2_32.dll');
"""

def parse_wlo_packet(raw_bytes, buffer):
    """Bóc tách packet WLO (Magic 0xF4 0x44, 2B LE length, XOR 0xAD)."""
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

def get_item_name(code_int):
    code_hex = f"0x{code_int:04X}"
    if code_hex in ITEM_DB:
        return ITEM_DB[code_hex].get("name", code_hex)
    return code_hex

def decode_packet_details(direction, opcode, subcode, data, client_label=""):
    """Giải mã chi tiết ngữ nghĩa các gói tin game WLO."""
    details = []

    # 1. CHIẾN ĐẤU (COMBAT)
    if direction == "C->S" and opcode == 0x32 and subcode == 0x01:
        if len(data) >= 8:
            actor_slot, actor_row, target_slot, target_row = data[0], data[1], data[2], data[3]
            skill_raw = data[4:8]
            skill_hex = skill_raw[:2].hex()
            skill_name = KNOWN_SKILLS.get(skill_hex, f"Chiêu thức mã 0x{skill_hex}")
            actor_type = "Nhân vật (Char)" if actor_slot == 3 else ("Pet" if actor_slot == 4 else f"Slot {actor_slot}")
            target_pos = f"Hàng {target_row} (Cột {target_slot})"
            details.append(f"⚔️ [{client_label} RA ĐÒN] {actor_type} (Hàng {actor_row}) -> [{skill_name} - Hex: {skill_hex}] -> Mục tiêu: {target_pos}")

    elif opcode == 0x0B:
        if subcode in (0xFA, 0x02):
            details.append(f"⚡ [{client_label}] [VÀO TRẬN ĐÁNH] Quái vật xuất hiện! Bắt đầu chiến đấu.")
        elif subcode == 0x00:
            details.append(f"🏁 [{client_label}] [KẾT THÚC TRẬN ĐÁNH] Chiến thắng hoàn tất!")
        elif subcode == 0x01:
            details.append(f"⏳ [{client_label}] [LƯỢT ĐÁNH] Round tick data: {data.hex()[:12]}")

    # 2. PHỤ BẢN & ĐỐI THOẠI NPC (INSTANCE & NPC)
    elif opcode == 0x55 and subcode == 0x03:
        if len(data) >= 2:
            dungeon_id = struct.unpack("<H", data[:2])[0]
            details.append(f"🏛️ [{client_label}] [CHỌN PHỤ BẢN] ID: {dungeon_id} (0x{dungeon_id:04X}) | Data: {data.hex()}")
        else:
            details.append(f"🏛️ [{client_label}] [CHỌN PHỤ BẢN] Data: {data.hex()}")

    elif opcode == 0x02 and subcode == 0x02 and data == b'go':
        details.append(f"💬 [{client_label}] [SẴN SÀNG LOBBY] Gửi lệnh chat 'go'")

    elif opcode == 0x55 and subcode == 0x02:
        details.append(f"🚀 [{client_label}] [BẮT ĐẦU PHỤ BẢN] Gửi lệnh Start Instance")

    elif opcode == 0x20:
        if subcode == 0x01:
            details.append(f"💬 [{client_label}] [BƯỚC VÀO THOẠI NPC] Data: {data.hex()}")
        elif subcode == 0x02 and len(data) >= 1:
            details.append(f"👉 [{client_label}] [CHỌN MENU NPC] Lựa chọn số: {data[0]} (0x{data[0]:02X})")
        elif subcode == 0x03:
            details.append(f"❌ [{client_label}] [ĐÓNG HỘP THOẠI NPC]")

    elif opcode == 0x14 and subcode == 0x01:
        if data == bytes.fromhex("1300"):
            details.append(f"🏺 [{client_label}] [CLICK CHIẾC LU / RƯƠNG THƯỞNG] Tương tác nhận quà phụ bản (14011300)")
        else:
            details.append(f"💬 [{client_label}] [HỘP THOẠI SERVER GỬI] Độ dài: {len(data)} bytes | Hex: {data.hex()[:16]}")

    elif opcode == 0x18 and subcode == 0x05:
        details.append(f"📋 [{client_label}] [DANH SÁCH LỰA CHỌN NPC] Độ dài: {len(data)} bytes")

    # 3. CHUYỂN CẢNH / DI CHUYỂN (WARP & MOVEMENT)
    elif opcode == 0x06 and subcode == 0x01 and len(data) >= 5:
        mode = data[0]
        x = struct.unpack("<H", data[1:3])[0]
        y = struct.unpack("<H", data[3:5])[0]
        details.append(f"🚶 [{client_label}] [DI CHUYỂN] Tọa độ (X={x}, Y={y}) | Mode: 0x{mode:02X}")

    elif opcode == 0x06 and subcode == 0x02 and len(data) >= 5:
        target_id = data[0]
        x = struct.unpack("<H", data[1:3])[0]
        y = struct.unpack("<H", data[3:5])[0]
        details.append(f"🎯 [{client_label}] [CLICK TƯƠNG TÁC VẬT THỂ] ID: 0x{target_id:02X} tại (X={x}, Y={y})")

    elif opcode == 0x35 and subcode == 0x01:
        details.append(f"🌀 [{client_label}] [CỔNG DỊCH CHUYỂN / WARP PORTAL]")

    elif opcode == 0x16 and subcode == 0x04:
        details.append(f"🗺️ [{client_label}] [NẠP BẢN ĐỒ CẢNH MỚI] Map Data: {len(data)} bytes")

    # 4. TÚI ĐỒ & VẬT PHẨM (INVENTORY & ITEMS)
    elif opcode == 0x17:
        if direction == "S->C" and subcode == 0x06 and len(data) >= 2:
            i = 0
            rewards_str = []
            while i + 2 <= len(data):
                item_code = struct.unpack("<H", data[i:i+2])[0]
                qty = struct.unpack("<H", data[i+2:i+4])[0] if i + 4 <= len(data) else 1
                if item_code > 0:
                    name = get_item_name(item_code)
                    rewards_str.append(f"Mã 0x{item_code:04X} ({name}) x{qty}")
                i += 4
            if rewards_str:
                details.append(f"🎁 [{client_label}] [NHẬN PHẦN THƯỞNG] " + ", ".join(rewards_str))

        elif subcode == 0x09 and len(data) >= 2:
            slot, remain = data[0], data[1]
            details.append(f"🎒 [{client_label}] [CẬP NHẬT Ô ĐỒ] Ô #{slot:02d} -> Còn: {remain}")

        elif direction == "C->S" and subcode == 0x0F and len(data) >= 2:
            slot = data[0]
            details.append(f"💊 [{client_label}] [CẮN THUỐC / DÙNG ĐỒ] Dùng món đồ tại Ô #{slot:02d}")

        elif direction == "C->S" and subcode == 0x0A and len(data) >= 3:
            s_from, s_qty, s_to = data[0], data[1], data[2]
            details.append(f"📦 [{client_label}] [DỜI VẬT PHẨM] Ô #{s_from:02d} (x{s_qty}) -> Ô #{s_to:02d}")

    # 5. TỔ ĐỘI (PARTY)
    elif opcode == 0x0D:
        if subcode == 0x01 and len(data) >= 4:
            cid = struct.unpack("<I", data[:4])[0]
            details.append(f"🤝 [{client_label}] [YÊU CẦU / MỜI TỔ ĐỘI] Đối tác ID: 0x{cid:08X}")
        elif subcode == 0x03 and len(data) >= 5:
            cid = struct.unpack("<I", data[1:5])[0]
            details.append(f"★ [{client_label}] [VÀO TỔ ĐỘI THÀNH CÔNG] Thành viên ID: 0x{cid:08X}")
        elif subcode == 0x05 and len(data) >= 8:
            mem_id = struct.unpack("<I", data[:4])[0]
            lead_id = struct.unpack("<I", data[4:8])[0]
            details.append(f"👥 [{client_label}] [ĐỒNG BỘ ĐỘI HÌNH] TV 0x{mem_id:08X} | Leader 0x{lead_id:08X}")
        elif subcode == 0x0A and len(data) >= 5:
            new_lead = struct.unpack("<I", data[1:5])[0]
            details.append(f"👑 [{client_label}] [CHUYỂN ĐỘI TRƯỞNG] Leader mới: 0x{new_lead:08X}")

    return "\n       └── ".join(details) if details else ""

class ClientCaptureWorker:
    def __init__(self, label, proc, logger):
        self.label = label
        self.proc = proc
        self.logger = logger
        self.session = None
        self.script = None
        self.c2s_buf = bytearray()
        self.s2c_buf = bytearray()
        self.last_packet_sig = None
        self.last_packet_time = 0

    def start(self, dev):
        self.session = dev.attach(self.proc.pid)
        self.script = self.session.create_script(FRIDA_JS)
        self.script.on("message", self.on_message)
        self.script.load()

    def on_message(self, message, raw_data):
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "recv")
        is_send = (dir_name == "send")
        buffer = self.c2s_buf if is_send else self.s2c_buf
        packets = parse_wlo_packet(raw_data, buffer)

        now = time.time()
        for opcode, subcode, data, raw_pkt in packets:
            if opcode == 0x08:  # Bỏ qua ping
                continue

            # Deduplication
            sig = (dir_name, opcode, subcode, data[:8])
            if sig == self.last_packet_sig and (now - self.last_packet_time) < 0.05:
                continue
            self.last_packet_sig = sig
            self.last_packet_time = now

            direction = "C->S" if is_send else "S->C"
            self.logger.log_packet(self.label, direction, opcode, subcode, data)

    def stop(self):
        try:
            if self.script:
                self.script.unload()
            if self.session:
                self.session.detach()
        except Exception:
            pass

class UnifiedPartyLogger:
    def __init__(self, log_path):
        self.log_path = log_path
        self.lock = threading.Lock()
        self.pkt_count = 0
        self.start_t = time.time()
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write(f"=== BẮT ĐẦU BẮT GÓI TIN TỔ ĐỘI (W01, F02, F04) LÚC {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")

    def log_packet(self, label, direction, opcode, subcode, data):
        with self.lock:
            self.pkt_count += 1
            now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            elapsed = time.time() - self.start_t

            op_name = OPCODE_NAMES.get(opcode, f"0x{opcode:02X}")
            sub_hex = f"0x{subcode:02X}" if subcode is not None else "--"
            hex_data = data.hex()
            details = decode_packet_details(direction, opcode, subcode, data, label)

            line = f"[{now_str}] [+ {elapsed:6.2f}s] [#{self.pkt_count:<5}] [{label:<3}] {direction} Op:0x{opcode:02X} ({op_name:<22}) Sub:{sub_hex} Len:{len(data):<3} | Hex: {hex_data}"
            if details:
                line += f"\n       └── {details}"

            print(line, flush=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()

def main():
    print("=" * 90)
    print("      WLO LIVE PARTY INSTANCE CAPTURE & ANALYZER (W01, F02, F04)")
    print("==========================================================================================")
    
    dev = frida.get_local_device()
    procs = dev.enumerate_processes()

    target_keys = ["w01", "f02", "f04"]
    found_targets = {}

    for p in procs:
        plow = p.name.lower()
        for k in target_keys:
            if k in plow:
                found_targets[k.upper()] = p

    if not found_targets:
        print("[!] Không tìm thấy bất kỳ tiến trình nào trong số (W01, F02, F04) đang chạy!")
        sys.exit(1)

    print("[+] Đã nhận diện các thành viên tổ đội tham gia:")
    for label, p in found_targets.items():
        print(f"    • [{label}] PID: {p.pid} | Tên: {p.name}")

    print(f"[*] File ghi nhận nhật ký: {LOG_FILE}")
    print("[*] Đang đính kèm Frida Hook đồng thời vào toàn bộ thành viên...")

    logger = UnifiedPartyLogger(LOG_FILE)
    workers = []

    for label, proc in found_targets.items():
        worker = ClientCaptureWorker(label, proc, logger)
        worker.start(dev)
        workers.append(worker)
        print(f"    ✓ Đã hook thành công client [{label}] (PID: {proc.pid})")

    print("\n" + "=" * 90)
    print("  ★ HỆ THỐNG ĐANG LẮNG NGHE ĐỒNG BỘ 100% CẢ 3 TIẾN TRÌNH!")
    print("    • Bạn cứ thoải mái lập nhóm và đi Instance tổ đội (W01, F02, F04).")
    print("    • Mọi gói tin di chuyển, đối thoại NPC, chiêu thức từng hiệp của mỗi người và phần thưởng đều được ghi nhận.")
    print("    • Nhấn Ctrl+C để kết thúc phiên ghi và xem kết quả.")
    print("=" * 90 + "\n", flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Đang dừng các bộ lắng nghe Frida...")
        for w in workers:
            w.stop()
        print(f"[+] Hoàn tất! File nhật ký đã được lưu tại: {LOG_FILE}")

if __name__ == "__main__":
    main()
