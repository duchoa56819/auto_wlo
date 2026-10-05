#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO Live Skill & Combat Monitor for alogin-F04
=============================================
Theo dõi, bóc tách và phân tích trực tiếp mọi kỹ năng (đặc biệt là Hệ Lửa)
của Char và Pet trên client alogin-F04.exe trong thời gian thực.
"""

import os
import sys
import time
import json
import struct
import argparse
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

try:
    import frida
except ImportError:
    print("[!] Chưa cài đặt frida. Chạy: pip install frida")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "skill_capture_f04.log")
SKILLS_DB_FILE = os.path.join(SCRIPT_DIR, "wlo_skills_database.json")
ITEMS_DB_FILE = os.path.join(SCRIPT_DIR, "wlo_items_database.json")

# Nạp CSDL Kỹ năng & Vật phẩm
SKILLS_DB = {}
if os.path.exists(SKILLS_DB_FILE):
    try:
        with open(SKILLS_DB_FILE, "r", encoding="utf-8") as f:
            SKILLS_DB = json.load(f)
    except Exception:
        pass

ITEMS_DB = {}
if os.path.exists(ITEMS_DB_FILE):
    try:
        with open(ITEMS_DB_FILE, "r", encoding="utf-8") as f:
            ITEMS_DB = json.load(f)
    except Exception:
        pass

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
    0x0D: "PARTY_SYSTEM",
    0x0E: "PET_ACTION",
    0x0F: "PET_STATUS",
    0x10: "TENT_FURNITURE",
    0x13: "SYNTHESIS_COMPOUND",
    0x14: "CHAT_MESSAGE",
    0x16: "QUEST_MISSION",
    0x17: "CHAR_ATTRIBUTES",
    0x18: "SHORTCUT_BAR",
    0x19: "PK_SYSTEM",
    0x1A: "GUILD_SYSTEM",
    0x20: "NPC_DIALOG",
    0x23: "MAP_OBJECT",
    0x32: "COMBAT_OR_MOVE",
    0x33: "ENTITY_MOVE_SYNC",
    0x34: "ENTITY_ACTION_SYNC",
    0x35: "MAP_WARP_SCENE",
    0x3E: "WEATHER_EFFECT",
    0x3F: "SCENE_TRIGGER",
    0x4B: "EXPRESSION_EMOTE",
    0x55: "DUNGEON_LOBBY",
    0x59: "UI_INIT_FEATURE",
    0x5C: "STATUS_SYNC",
}

FRIDA_HOOK_JS = """
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

hookRecv('ws2_32.dll');
hookSend('ws2_32.dll');
hookRecv('wsock32.dll');
hookSend('wsock32.dll');
"""

def decode_text(raw_bytes):
    if not raw_bytes:
        return ""
    try:
        text = raw_bytes.decode("big5")
        filtered = "".join(c for c in text if c.isprintable())
        if len(filtered) >= 2:
            return filtered
    except Exception:
        pass
    try:
        ascii_chars = [chr(b) if 32 <= b <= 126 else "" for b in raw_bytes]
        text_ascii = "".join(ascii_chars).strip()
        return text_ascii if len(text_ascii) >= 3 else ""
    except Exception:
        return ""

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

def interpret_packet(direction: str, opcode: int, subcode: int, data: bytes) -> str:
    details = []

    # 1. Combat Actions (Opcode 0x32)
    if opcode == 0x32:
        if subcode == 0x01:
            if direction == "C->S" and len(data) >= 8:
                a_slot, a_row = data[0], data[1]
                t_slot, t_row = data[2], data[3]
                skill_hex = data[4:6].hex().upper()
                actor_name = f"Slot{a_slot}Row{a_row}"
                target_desc = f"Phe địch(S{t_slot}R{t_row})" if t_slot in [1, 2] else f"Phe ta(S{t_slot}R{t_row})"
                skill_info = SKILLS_DB.get(f"0x{skill_hex}", {})
                s_name = skill_info.get("name_vi") or skill_info.get("name_en") or f"Chiêu 0x{skill_hex}"
                details.append(f"🔥 [XUẤT CHIÊU C->S] Actor(Slot {a_slot} Row {a_row}) -> Mục tiêu: {target_desc} | Mã Chiêu: [0x{skill_hex}] ({s_name})")
            elif direction == "S->C":
                if len(data) >= 6:
                    s_code = data[4:6].hex().upper()
                    details.append(f"💥 [HIỆU ỨNG CHIÊU S->C] Mã: 0x{s_code} | Len: {len(data)}")
                else:
                    details.append(f"💥 [HIỆU ỨNG ĐÒN ĐÁNH / SÁT THƯƠNG S->C] (Len {len(data)})")
        elif subcode == 0x06:
            details.append("🎬 [DIỄN HOẠT CHIẾN ĐẤU] Server phát hoạt ảnh lượt đánh")

    # 2. Combat Start / End / Monster defeated (Opcode 0x0B)
    elif opcode == 0x0B:
        if subcode in (0xFA, 0x02):
            details.append("⚔️ [BẮT ĐẦU TRẬN ĐẤU] Khởi tạo sàn đấu & danh sách quái")
        elif subcode == 0x00:
            details.append("🏆 [KẾT THÚC TRẬN ĐẤU] Hoàn tất trận đấu / Rời trận")
        elif subcode == 0x01:
            if len(data) >= 2:
                details.append(f"💀 [QUÁI TỬ TRẬN] Slot {data[0]} Row {data[1]} đã bị hạ gục")
        elif subcode == 0x0C:
            details.append("⭐ [KẾT QUẢ HIỆP] Tổng kết đợt đánh")

    # 3. HP/SP Sync (Opcode 0x33 Subcode 0x01)
    elif opcode == 0x33 and subcode == 0x01:
        if len(data) >= 7:
            slot, row, stat_type = data[0], data[1], data[2]
            val = struct.unpack("<I", data[3:7])[0]
            st_name = "HP" if stat_type == 0x19 else ("SP" if stat_type == 0x1A else f"Type_0x{stat_type:02X}")
            details.append(f"📊 [CHỈ SỐ] Slot {slot} Row {row} {st_name} = {val:,}")

    # 4. Item / Bag use (Opcode 0x17)
    elif opcode == 0x17:
        if subcode == 0x4B and len(data) >= 1:
            slot = data[0]
            details.append(f"🎒 [DÙNG VẬT PHẨM] Người chơi bấm dùng Ô Slot {slot}")
        elif subcode == 0x06:
            if len(data) >= 3:
                code = struct.unpack("<H", data[0:2])[0]
                qty = data[2]
                hex_c = f"0x{code:04X}"
                item_name = ITEMS_DB.get(hex_c, {}).get("name", "Vật phẩm")
                details.append(f"🎁 [NHẬN VẬT PHẨM / THƯỞNG] {item_name} ({hex_c}) x{qty}")
        elif subcode == 0x05:
            details.append(f"📦 [ĐỒNG BỘ TÚI ĐỒ] Server nạp danh sách {len(data)//31} món trang bị/vật phẩm")

    # 5. Map warp / Scene transition (Opcode 0x35)
    elif opcode == 0x35:
        if len(data) >= 2:
            map_id = struct.unpack("<H", data[:2])[0]
            details.append(f"🚪 [CHUYỂN CẢNH / MAP] Map ID: {map_id} (0x{map_id:04X})")

    # 6. NPC Dialog (Opcode 0x20)
    elif opcode == 0x20:
        if subcode == 0x01:
            details.append("💬 [ĐỐI THOẠI NPC] Mở hộp thoại đối thoại")
        elif subcode == 0x02 and len(data) >= 1:
            details.append(f"💬 [CHỌN TÙY CHỌN NPC] Chọn mục số {data[0]}")

    # 7. Chat (Opcode 0x14)
    elif opcode == 0x14:
        txt = decode_text(data)
        if txt:
            details.append(f"💬 [CHAT/THÔNG BÁO] \"{txt}\"")

    # Text generic
    if not details:
        txt = decode_text(data)
        if txt:
            details.append(f"Text: \"{txt}\"")

    return " | ".join(details)


class F04LiveSniffer:
    def __init__(self, target_pid=None):
        self.target_pid = target_pid
        self.c2s_dissector = WLOStreamDissector()
        self.s2c_dissector = WLOStreamDissector()
        self.packet_count = 0
        self.start_time = time.time()
        self.log_file = open(LOG_FILE, "a", encoding="utf-8")
        self.session = None
        self.script = None

    def find_f04_process(self):
        device = frida.get_local_device()
        for p in device.enumerate_processes():
            if "f04" in p.name.lower():
                return p.pid, p.name
        for p in device.enumerate_processes():
            if "alogin" in p.name.lower():
                return p.pid, p.name
        return None, None

    def on_frida_message(self, message, raw_data):
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "send")
        direction = "C->S" if dir_name == "send" else "S->C"

        dissector = self.c2s_dissector if dir_name == "send" else self.s2c_dissector
        packets = dissector.feed(raw_data)

        for opcode, subcode, data, raw_pkt in packets:
            self.handle_packet(direction, opcode, subcode, data, raw_pkt)

    def handle_packet(self, direction, opcode, subcode, data, raw_pkt):
        if opcode == 0x08:  # Ẩn Ping nhịp tim
            return

        self.packet_count += 1
        elapsed = time.time() - self.start_time
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        op_name = OPCODE_MAP.get(opcode, f"Op_0x{opcode:02X}")
        sub_str = f"Sub:0x{subcode:02X}" if subcode is not None else "Sub:--"
        interp = interpret_packet(direction, opcode, subcode, data)
        hex_data = data.hex()

        line = f"[{timestamp}] [+{elapsed:7.2f}s] [#{self.packet_count:<4}] {direction} Op:0x{opcode:02X} ({op_name:<18}) {sub_str:<8} Len:{len(raw_pkt):<3}"
        if interp:
            line += f" | {interp}"
        line += f" | Hex: {hex_data}"

        # Ghi log file
        self.log_file.write(line + "\n")
        self.log_file.flush()

        # In console
        print(line, flush=True)

    def start(self):
        print("=" * 80)
        print("     WLO LIVE SKILL & COMBAT MONITOR (alogin-F04 - Hệ Lửa)")
        print("=" * 80)

        if not self.target_pid:
            pid, name = self.find_f04_process()
            if not pid:
                print("[!] Không tìm thấy tiến trình alogin-F04.exe!")
                return
            self.target_pid = pid
            target_name = name
        else:
            target_name = f"PID {self.target_pid}"

        print(f"[*] Đang đính kèm vào {target_name} (PID: {self.target_pid})...")
        try:
            self.session = frida.attach(self.target_pid)
            print(f"[+] Đính kèm thành công vào {target_name}!")
        except Exception as e:
            print(f"[!] Lỗi đính kèm: {e}")
            return

        print(f"[*] File ghi log: {LOG_FILE}")
        print("[*] Đang nạp Frida Hook giám sát luồng mạng TCP ws2_32 / wsock32...")
        self.script = self.session.create_script(FRIDA_HOOK_JS)
        self.script.on("message", self.on_frida_message)
        self.script.load()

        print("[+] SẴN SÀNG! Đang lắng nghe mọi gói tin thời gian thực từ alogin-f04.")
        print("[*] Bộ lọc: Đã ẩn Ping 0x08. Bất kỳ chiêu thức hệ Lửa hoặc đòn đánh nào sẽ xuất hiện ngay lập tức...\n")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] Đang dừng lắng nghe...")
            if self.session:
                self.session.detach()
            self.log_file.close()
            print("[+] Đã ngắt kết nối an toàn.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WLO alogin-F04 Live Monitor")
    parser.add_argument("-p", "--pid", type=int, default=None, help="PID của alogin-f04")
    args = parser.parse_args()

    sniffer = F04LiveSniffer(target_pid=args.pid)
    sniffer.start()
