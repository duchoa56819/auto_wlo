#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO Skill & Combat Packet Sniffer (alogin-w01)
==============================================
Lắng nghe, bóc tách và phân tích toàn bộ gói tin khi nhân vật (Hệ Nước)
và Pet Niss thực hiện sử dụng kỹ năng trong Wonderland Online.
"""

import os
import sys
import time
import struct
import argparse
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    print("[!] Chua cai dat frida. Chay: pip install frida")
    sys.exit(1)

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skill_capture_w01.log")

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

# Các mã kỹ năng đã biết trong WLO
KNOWN_SKILLS = {
    "75ea": "Phòng thủ (Defend)",
    "1f3b": "Chiêu Hỏa Char (F04)",
    "043b": "Chiêu Hỏa Pet (F04)",
    "d861": "Chiêu Thủy/Địa Char (W04/W03)",
    "a33a": "Chiêu Thủy/Địa Pet (W04/W03)",
    "2b2b": "Chiêu Phong Char (Wi01)",
    "393b": "Chiêu Phong Pet (Wi01)",
    "212b": "Chiêu tấn công cơ bản",
    "0100": "Đánh thường (Normal Attack)",
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
hookSend('ws2_32.dll');
"""

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
    ascii_chars = [chr(b) if 32 <= b <= 126 else "" for b in raw_bytes]
    text_ascii = "".join(ascii_chars).strip()
    return text_ascii if len(text_ascii) >= 3 else ""

def interpret_skill_action(direction, opcode, subcode, data):
    details = []

    # 1. Combat Action / Move (Opcode 0x32)
    if opcode == 0x32:
        if subcode == 0x01 and len(data) >= 8:
            actor_slot = data[0]
            actor_row = data[1]
            target_slot = data[2]
            target_row = data[3]
            skill_code = data[4:6].hex()

            actor_str = "Char" if actor_slot == 3 else ("Pet" if actor_slot == 4 else f"Slot{actor_slot}")
            target_side = "Phe địch" if target_slot in [1, 2] else "Phe ta"
            skill_name = KNOWN_SKILLS.get(skill_code, f"Skill_0x{skill_code.upper()}")

            details.append(f"[XUẤT CHIÊU] {actor_str} (Hàng {actor_row}) -> Mục tiêu: {target_side} (Slot {target_slot} Hàng {target_row}) | Mã chiêu: 0x{skill_code.upper()} ({skill_name})")
        elif subcode == 0x06:
            details.append("[LƯỢT ĐÁNH] Đồng bộ trạng thái lượt chiến đấu")
        elif subcode == 0x01 and len(data) > 8:
            details.append(f"[BATTLE_SYNC] Đồng bộ hành động chiến đấu (Len {len(data)})")

    # 2. Combat Action (Opcode 0x06)
    elif opcode == 0x06:
        if subcode == 0x01:
            details.append("[CHIẾN ĐẤU] Bắt đầu lượt đánh mới")
        elif subcode == 0x02:
            details.append("[CHỌN MỤC TIÊU] Chọn mục tiêu ra đòn")

    # 3. Skill Effect / Sound (Opcode 0x04)
    elif opcode == 0x04:
        details.append(f"[HIỆU ỨNG KỸ NĂNG] Hiệu ứng hoạt họa / âm thanh chiêu thức (Sub 0x{subcode:02X} Len {len(data)})")

    # 4. Pet Action (Opcode 0x0E / 0x0F)
    elif opcode in [0x0E, 0x0F]:
        details.append(f"[PET_ACTION] Thao tác thú cưng / trạng thái Pet (Sub 0x{subcode:02X})")

    # 5. Out of combat skill / Shortcut bar (Opcode 0x18 / 0x17)
    elif opcode == 0x18:
        details.append(f"[SHORTCUT_BAR] Phím tắt kỹ năng / vật phẩm (Sub 0x{subcode:02X})")
    elif opcode == 0x17:
        if subcode == 0x4B:
            slot = data[0] if len(data) > 0 else 0
            details.append(f"[USE_ITEM/SKILL] Dùng ô {slot}")
        elif subcode == 0x4D:
            details.append("[CẬP NHẬT CHỈ SỐ] HP / SP / Exp thay đổi")

    # Text decode
    txt = decode_text(data)
    if txt:
        details.append(f'Text: "{txt}"')

    return " | ".join(details)

class SkillSniffer:
    def __init__(self, target_pid=10744):
        self.target_pid = target_pid
        self.c2s_dissector = WLOStreamDissector()
        self.s2c_dissector = WLOStreamDissector()
        self.packet_count = 0
        self.start_time = time.time()
        self.running = False
        self.log_file = open(LOG_FILE, "w", encoding="utf-8")
        self.session = None
        self.script = None

    def log(self, text):
        print(text, flush=True)
        if self.log_file:
            self.log_file.write(text + "\n")
            self.log_file.flush()

    def on_message(self, message, raw_data):
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "send")
        is_send = (dir_name == "send")
        dir_str = "C->S" if is_send else "S->C"
        dissector = self.c2s_dissector if is_send else self.s2c_dissector
        packets = dissector.feed(raw_data)
        for opcode, subcode, data, raw_pkt in packets:
            self.handle_packet(dir_str, opcode, subcode, data, raw_pkt)

    def handle_packet(self, direction, opcode, subcode, data, raw_pkt):
        # Ẩn Ping 0x08 để giữ log tập trung vào kỹ năng
        if opcode == 0x08:
            return

        self.packet_count += 1
        elapsed = time.time() - self.start_time
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        op_name = OPCODE_MAP.get(opcode, f"UNKNOWN_0x{opcode:02X}")
        sub_str = f"0x{subcode:02X}" if subcode is not None else "--"
        hex_data = data.hex()

        interp = interpret_skill_action(direction, opcode, subcode, data)
        interp_str = f" | {interp}" if interp else ""

        line = f"[{timestamp}] [+{elapsed:7.2f}s] [#{self.packet_count:<5}] {direction} Op:0x{opcode:02X} ({op_name:<18}) Sub:{sub_str:<4} Len:{len(data)+2:<4} | Hex: {hex_data}{interp_str}"
        self.log(line)

    def start(self):
        self.log("=" * 80)
        self.log("       WLO SKILL & COMBAT LIVE SNIFFER (alogin-w01)")
        self.log("=" * 80)
        self.log(f"[*] Dang dinh kem vao PID: {self.target_pid} (alogin-w01)...")
        self.session = frida.attach(self.target_pid)
        self.script = self.session.create_script(FRIDA_JS)
        self.script.on("message", self.on_message)
        self.script.load()
        self.running = True
        self.log(f"[+] Dinh kem thanh cong vao alogin-w01 (PID {self.target_pid})!")
        self.log(f"[*] File ghi log: {LOG_FILE}")
        self.log("[*] Bo loc: An Ping 0x08, tu dong phan tich ky nang Char & Pet Niss.")
        self.log("[*] SAN SANG! Nguoi choi co the thuc hien su dung ky nang ngay bay gio...\n")

        try:
            while self.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.log("\n[*] Dung lang nghe goi tin...")
        if self.session:
            try:
                self.session.detach()
            except Exception:
                pass
        if self.log_file:
            self.log_file.close()
        self.log("[+] Da ngat ket noi Hook an toan.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, default=10744, help="PID cua alogin-w01")
    args = parser.parse_args()
    sniffer = SkillSniffer(target_pid=args.pid)
    sniffer.start()
