#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO Live Packet Sniffer & Translator (Frida-based)
=================================================
Công cụ lắng nghe, bóc tách và dịch trực tiếp các gói tin của Wonderland Online (WLO)
từ tiến trình alogin-F02.exe (hoặc bất kỳ tiến trình alogin*.exe nào) trong thời gian thực.

Đặc tả:
- Hook ws2_32.dll (send / recv) thông qua Frida Instrumentation.
- Giải mã XOR 0xAD theo luồng TCP.
- Ghép packet theo Magic Header 0xF4 0x44 và Payload Length (Little-Endian uint16).
- Tra cứu bảng mã Opcode, Subcode, giải mã chuỗi Big5/ASCII và hiển thị chi tiết theo thời gian thực.
"""

import os
import sys
import time
import struct
import argparse
import signal
import threading
from datetime import datetime

# Tránh lỗi Unicode trên Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    print("[!] Chua cai dat thu vien frida. Vui long chay: pip install frida")
    sys.exit(1)

# ==============================================================================
# BẢNG MÃ OPCODE & DỊCH THAO TÁC GAME
# ==============================================================================
OPCODE_MAP = {
    0x01: ("SYSTEM_HANDSHAKE", "Bat tay / Thong tin phien ban"),
    0x02: ("ACCOUNT_CHAR_LIST", "Danh sach nhan vat / Thong bao server"),
    0x03: ("CHANNEL_INFO", "Danh sach kenh / May chu"),
    0x04: ("SKILL_EFFECT", "Hieu ung ky nang / Am thanh"),
    0x05: ("LOGIN_AUTH", "Dang nhap / Vao the gioi game"),
    0x06: ("COMBAT_ACTION", "Thao tac chien dau (Danh/Skill/Bo chay)"),
    0x07: ("TEAM_FORMATION", "Doi hinh / Vi tri chien dau"),
    0x08: ("PING_HEARTBEAT", "Giu ket noi Ping/Pong"),
    0x0A: ("TRADE_STALL", "Giao dich / Mo sap ban hang"),
    0x0B: ("INVENTORY_ITEM", "Tui do / Trang bi / Vat pham"),
    0x0C: ("FRIEND_MAIL", "Ban be / Thu tin"),
    0x0D: ("PARTY_SYSTEM", "He thong To doi / Nhom"),
    0x0E: ("PET_ACTION", "Thao tac thu cung / Ban dong hanh"),
    0x0F: ("PET_STATUS", "Chi so & tinh trang Pet"),
    0x10: ("TENT_FURNITURE", "Leu bat / Do noi that"),
    0x13: ("SYNTHESIS_COMPOUND", "Che tao / Hop thanh vat pham"),
    0x14: ("CHAT_MESSAGE", "Kenh Chat / Thong bao he thong"),
    0x16: ("QUEST_MISSION", "Nhiem vu / Muc tieu"),
    0x17: ("CHAR_ATTRIBUTES", "Chi so nhan vat (HP/SP/Toa do/Exp)"),
    0x18: ("SHORTCUT_BAR", "Thanh phim tat"),
    0x19: ("PK_SYSTEM", "He thong PK / Ti thi"),
    0x1A: ("GUILD_SYSTEM", "Bang hoi"),
    0x20: ("NPC_DIALOG", "Doi thoai NPC / Lua chon nhiem vu"),
    0x23: ("MAP_OBJECT", "Vat the ban do / Ruong / Khoang san"),
    0x32: ("PLAYER_MOVE", "Nguoi choi di chuyen (Click chuot)"),
    0x33: ("ENTITY_MOVE_SYNC", "Dong bo di chuyen nguoi khac / NPC"),
    0x34: ("ENTITY_ACTION_SYNC", "Dong bo hanh dong (Ngoi/Dung/Huong)"),
    0x35: ("MAP_WARP_SCENE", "Chuyen canh / Doi ban do"),
    0x3E: ("WEATHER_EFFECT", "Hieu ung thoi tiet"),
    0x3F: ("SCENE_TRIGGER", "Kich hoat su kien map / Dang nhap"),
    0x4B: ("EXPRESSION_EMOTE", "Bieu cam Icon / Emote"),
    0x55: ("DUNGEON_LOBBY", "Giao dien & Phong cho Phu ban"),
    0x59: ("UI_INIT_FEATURE", "Khoi tao thong so giao dien"),
    0x5A: ("PET_COMMAND_SYNC", "Lenh thu cung / Dong bo dac biet"),
    0x5C: ("STATUS_SYNC", "Dong bo trang thai Client"),
    0xB7: ("SPECIAL_EXT", "Giao thuc mo rong / Proxy"),
}

# Màu sắc ANSI cho console
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    CYAN = "\033[96m"      # C->S (Client gửi)
    YELLOW = "\033[93m"    # S->C (Server trả lời)
    GREEN = "\033[92m"     # Thông tin giải mã
    RED = "\033[91m"       # Cảnh báo / Ping
    MAGENTA = "\033[95m"   # Action / Event
    BLUE = "\033[94m"      # Header
    GRAY = "\033[90m"      # Chi tiết phụ

# ==============================================================================
# HÀM GIẢI MÃ VÀ PHÂN TÍCH NỘI DUNG GÓI TIN (INTERPRETER)
# ==============================================================================
def decode_text(raw_bytes):
    """Cố gắng giải mã Big5 (chuẩn WLO) hoặc ASCII."""
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

def interpret_packet(direction, opcode, subcode, data):
    """
    Dịch chi tiết ý nghĩa gói tin dựa trên opcode, subcode và dữ liệu payload.
    """
    details = []

    # 0x08: Ping/Heartbeat
    if opcode == 0x08:
        if subcode == 0x01:
            details.append("Ping Heartbeat (C->S)")
        elif subcode == 0x02:
            details.append("Pong Heartbeat (S->C)")
        return " | ".join(details)

    # 0x32: Di chuyển (Player Move)
    if opcode == 0x32:
        details.append("Thao tac di chuyen")
        if len(data) >= 4:
            try:
                step_type = data[0] if len(data) > 0 else 0
                details.append(f"Kieu buoc: 0x{step_type:02X}")
            except Exception:
                pass
        return " | ".join(details)

    # 0x14: Chat / Tin nhắn / Thông báo
    if opcode == 0x14:
        chat_types = {
            0x01: "He thong / Thong bao chien thang",
            0x02: "Kenh The gioi (World)",
            0x03: "Kenh Doi (Team)",
            0x04: "Kenh Bang hoi (Guild)",
            0x05: "Chat mat (Whisper)",
            0x06: "Chat phu ban / Kieu dac biet",
            0x08: "Dong bo trang thai chat",
            0x09: "Dong bo tin nhan server",
        }
        ch_name = chat_types.get(subcode, f"Sub:0x{subcode:02X}" if subcode is not None else "")
        details.append(f"Chat: {ch_name}")
        txt = decode_text(data)
        if txt:
            details.append(f'Noi dung: "{txt}"')
        return " | ".join(details)

    # 0x20: NPC Dialog
    if opcode == 0x20:
        details.append("Doi thoai NPC")
        if subcode == 0x01:
            details.append("Mo hop thoai NPC")
        elif subcode == 0x02:
            opt = data[0] if len(data) > 0 else 0
            details.append(f"Chon lua chon thoai: 0x{opt:02X}")
        txt = decode_text(data)
        if txt:
            details.append(f'Thoai: "{txt}"')
        return " | ".join(details)

    # 0x06: Combat Action
    if opcode == 0x06:
        details.append("Hanh dong chien dau")
        if subcode == 0x01:
            details.append("Bat dau luot danh")
        elif subcode == 0x02:
            details.append("Chon muc tieu / Ra don")
        return " | ".join(details)

    # 0x17: Character Attributes
    if opcode == 0x17:
        attr_subcodes = {
            0x36: "Yeu cau cap nhat chi so",
            0x4D: "Dong bo thuoc tinh nhan vat",
            0x4E: "Dong bo vi tri / Toa do nhan vat",
        }
        details.append(attr_subcodes.get(subcode, f"Thuoc tinh (Sub 0x{subcode:02X})" if subcode is not None else "Thuoc tinh"))
        return " | ".join(details)

    # 0x05: Login / World
    if opcode == 0x05:
        if subcode == 0x07:
            details.append("Tin hieu vao the gioi game (Enter World)")
        elif subcode == 0x08:
            details.append("Xac nhan vao the gioi tu Server")
        else:
            details.append(f"Xac thuc dang nhap (Sub 0x{subcode:02X})" if subcode is not None else "Xac thuc")
        return " | ".join(details)

    # 0x35: Map Warp / Scene Change
    if opcode == 0x35:
        details.append("Chuyen map / Doi canh")
        if len(data) >= 2:
            map_id = struct.unpack("<H", data[:2])[0]
            details.append(f"Map ID: {map_id}")
        return " | ".join(details)

    # 0x0B: Inventory / Item
    if opcode == 0x0B:
        details.append("Vat pham / Tui do")
        return " | ".join(details)

    # 0x55: Dungeon Lobby / Instance
    if opcode == 0x55:
        lobby_actions = {
            0x01: "Mo danh sach Phu ban / San sang phong",
            0x02: "Xac nhan xuat phat vao Phu ban",
            0x05: "Dong bo thanh vien phong",
            0x07: "Server dem nguoc xuat phat",
            0x08: "Tao phong / Cap nhat phong phu ban",
            0x0B: "Thiet lap phong / Chu phong",
            0x0D: "Thong so phong phu ban",
        }
        act_name = lobby_actions.get(subcode, f"Sub:0x{subcode:02X}" if subcode is not None else "")
        if subcode == 0x03 and len(data) >= 2:
            dungeon_id = struct.unpack("<H", data[:2])[0]
            details.append(f"Chon Phu ban ID: {dungeon_id} (0x{dungeon_id:04X})")
        elif act_name:
            details.append(act_name)
        else:
            details.append("Phu ban / Phong cho")
        return " | ".join(details)

    # Mặc định: Trích xuất chuỗi chữ nếu có
    txt = decode_text(data)
    if txt:
        details.append(f'Text: "{txt}"')

    return " | ".join(details) if details else ""

# ==============================================================================
# STREAM DISSECTOR: GIẢI MÃ XOR VÀ GHÉP GÓI TCP
# ==============================================================================
class WLOStreamDissector:
    """Tái ghép luồng TCP và giải mã gói tin WLO từ dữ liệu thô."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, raw_bytes):
        # Giải mã XOR 0xAD trên từng byte
        decrypted = bytearray(b ^ 0xAD for b in raw_bytes)
        self.buffer.extend(decrypted)

        packets = []
        while len(self.buffer) >= 4:
            # Tìm header magic 0xF4 0x44
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
                # Chưa đủ dữ liệu cho toàn bộ gói
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
# JAVASCRIPT HOOK SCRIPT CHO FRIDA
# ==============================================================================
FRIDA_JS = """
function hookRecv(modName) {
    try {
        var mod = Process.getModuleByName(modName);
        if (!mod) return;
        var rPtr = mod.getExportByName('recv');
        if (!rPtr) return;
        Interceptor.attach(rPtr, {
            onEnter: function(args) {
                this.buf = args[1];
                this.sock = args[0].toInt32();
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
                var len = args[2].toInt32();
                if (len > 0) {
                    try {
                        var buf = args[1].readByteArray(len);
                        send({dir: 'send', len: len, sock: args[0].toInt32()}, buf);
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


# ==============================================================================
# QUẢN LÝ LẮNG NGHE & HIỂN THỊ
# ==============================================================================
class WLOLiveSniffer:
    def __init__(self, target_process="alogin-F02.exe", target_pid=None,
                 filter_opcode=None, filter_dir=None, no_ping=False,
                 save_file=None, show_hex=False):
        self.target_process = target_process
        self.target_pid = target_pid
        self.filter_opcode = filter_opcode
        self.filter_dir = filter_dir
        self.no_ping = no_ping
        self.save_file = save_file
        self.show_hex = show_hex

        self.c2s_dissector = WLOStreamDissector()
        self.s2c_dissector = WLOStreamDissector()
        self.packet_count = 0
        self.start_time = time.time()
        self.running = False
        self.log_handle = None

        if self.save_file:
            self.log_handle = open(self.save_file, "a", encoding="utf-8")

    def on_frida_message(self, message, raw_data):
        if not raw_data:
            return

        payload = message.get("payload", {})
        dir_name = payload.get("dir", "send")
        is_send = (dir_name == "send")

        direction_str = "C->S" if is_send else "S->C"
        dissector = self.c2s_dissector if is_send else self.s2c_dissector

        packets = dissector.feed(raw_data)

        for opcode, subcode, data, raw_pkt in packets:
            self.handle_packet(direction_str, opcode, subcode, data, raw_pkt)

    def handle_packet(self, direction, opcode, subcode, data, raw_pkt):
        if self.no_ping and opcode == 0x08:
            return

        if self.filter_dir and self.filter_dir != direction:
            return

        if self.filter_opcode is not None and opcode != self.filter_opcode:
            return

        self.packet_count += 1
        elapsed = time.time() - self.start_time
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        op_info = OPCODE_MAP.get(opcode, (f"UNKNOWN_0x{opcode:02X}" if opcode is not None else "NONE", "Chua ro"))
        op_name = op_info[0]

        sub_str = f"0x{subcode:02X}" if subcode is not None else "--"
        interp = interpret_packet(direction, opcode, subcode, data)

        hex_preview = data.hex()
        if len(hex_preview) > 32 and not self.show_hex:
            hex_preview = hex_preview[:32] + "..."

        # Định dạng dòng lưu file
        line_plain = f"[{timestamp}] [+{elapsed:7.2f}s] [#{self.packet_count:<5}] {direction} Op:0x{opcode:02X} ({op_name:<18}) Sub:{sub_str:<4} Len:{len(data)+2:<3}"
        if interp:
            line_plain += f" | {interp}"
        line_plain += f" | Hex: {hex_preview}"

        # In có màu trên console
        dir_color = Colors.CYAN if direction == "C->S" else Colors.YELLOW
        line_color = (
            f"{Colors.GRAY}[{timestamp}]{Colors.RESET} "
            f"{Colors.BOLD}{dir_color}{direction}{Colors.RESET} "
            f"Op:{Colors.BOLD}0x{opcode:02X}{Colors.RESET} ({Colors.GREEN}{op_name:<18}{Colors.RESET}) "
            f"Sub:{sub_str:<4} "
            f"Len:{len(data)+2:<3}"
        )
        if interp:
            line_color += f" | {Colors.MAGENTA}{interp}{Colors.RESET}"
        line_color += f" | {Colors.GRAY}Hex: {hex_preview}{Colors.RESET}"

        print(line_color, flush=True)

        if self.log_handle:
            self.log_handle.write(line_plain + "\n")
            self.log_handle.flush()

    def start(self):
        print("=" * 80)
        print("           WLO LIVE PACKET SNIFFER & TRANSLATOR (FRIDA)")
        print("=" * 80)

        session = None
        target_name = ""

        try:
            if self.target_pid:
                print(f"[*] Dang dinh kem vao PID: {self.target_pid} ...")
                session = frida.attach(self.target_pid)
                target_name = f"PID {self.target_pid}"
            else:
                print(f"[*] Dang dinh kem vao tien trinh: {self.target_process} ...")
                session = frida.attach(self.target_process)
                target_name = self.target_process

            print(f"[+] Dinh kem thanh cong vao {target_name}!")
        except Exception as e:
            print(f"[!] Khong the dinh kem vao tien trinh: {e}")
            print("[*] Goi y: Hay kiem tra xem game da duoc mo chua (tasklist /FI \"IMAGENAME eq alogin*\")")
            return

        print("[*] Dang nap ma Hook ws2_32.dll (send / recv) ...")
        script = session.create_script(FRIDA_JS)
        script.on("message", self.on_frida_message)
        script.load()

        print("[+] Hook thanh cong! Dang lang nghe goi tin trong thoi gian thuc...")
        print(f"    - Loc Ping/Heartbeat (0x08): {'BAT (An ping)' if self.no_ping else 'TAT (Hien ca ping)'}")
        if self.filter_opcode is not None:
            print(f"    - Chi hien thi Opcode: 0x{self.filter_opcode:02X}")
        if self.filter_dir:
            print(f"    - Chi hien thi Huong: {self.filter_dir}")
        if self.save_file:
            print(f"    - Ghi log vao file: {self.save_file}")
        print("=" * 80)
        print(">> Thuc hien cac thao tac trong game (di chuyen, danh NPC, chat, vao phu ban...)")
        print(">> Nhan [Ctrl + C] de dung lang nghe.\n")

        self.running = True
        try:
            while self.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n[*] Nhan tin hieu dung tu ban phim (Ctrl+C)...")
        finally:
            self.running = False
            try:
                session.detach()
                print("[+] Da ngat ket noi Hook an toan.")
            except Exception:
                pass

            if self.log_handle:
                self.log_handle.close()
                print(f"[+] Da dong file log: {self.save_file}")

            print(f"[*] Tong so goi tin da bat duoc: {self.packet_count}")

# ==============================================================================
# TỰ ĐỘNG TÌM KIẾM TIẾN TRÌNH ALOGIN ĐANG CHẠY
# ==============================================================================
def find_alogin_processes():
    """Tìm tất cả các tiến trình alogin*.exe đang chạy."""
    processes = []
    try:
        device = frida.get_local_device()
        for p in device.enumerate_processes():
            if "alogin" in p.name.lower():
                processes.append((p.pid, p.name))
    except Exception:
        pass
    return processes

def main():
    parser = argparse.ArgumentParser(description="WLO Live Packet Sniffer & Translator (Frida-based)")
    parser.add_argument("-p", "--process", default=None, help="Ten tien trinh game (VD: alogin-F02.exe, alogin.exe)")
    parser.add_argument("--pid", type=int, default=None, help="PID cua tien trinh game can lang nghe")
    parser.add_argument("-o", "--opcode", type=lambda x: int(x, 0), default=None, help="Loc theo ma Opcode (VD: 0x32, 0x14, 0x06)")
    parser.add_argument("-d", "--dir", choices=["C->S", "S->C"], default=None, help="Loc theo chieu goi (C->S hoac S->C)")
    parser.add_argument("--no-ping", action="store_true", help="An cac goi tin Ping/Heartbeat (0x08) de tranh roi mat")
    parser.add_argument("--save", default=None, help="Luu toan bo log goi tin da giai ma ra file txt")
    parser.add_argument("--hex", action="store_true", help="Hien thi toan bo du lieu Hex khong cat gon")

    args = parser.parse_args()

    target_process = args.process
    target_pid = args.pid

    # Nếu không chỉ định process hoặc pid, tìm các tiến trình alogin đang chạy
    if not target_process and not target_pid:
        running_procs = find_alogin_processes()
        if not running_procs:
            print("[!] Khong tim thay tien trinh alogin*.exe nao dang chay!")
            print("[*] Vui long mo game truoc hoac chi dinh PID: python wlo_live_sniffer.py --pid <PID>")
            sys.exit(1)

        # Ưu tiên alogin-F02.exe nếu có
        f02_proc = [p for p in running_procs if "f02" in p[1].lower()]
        if f02_proc:
            target_pid, target_process = f02_proc[0]
            print(f"[*] Phat hien {target_process} (PID: {target_pid}). Tu dong chon.")
        elif len(running_procs) == 1:
            target_pid, target_process = running_procs[0]
            print(f"[*] Phat hien {target_process} (PID: {target_pid}). Tu dong chon.")
        else:
            print("[*] Tim thay nhieu tien trinh alogin dang chay:")
            for i, (p_pid, p_name) in enumerate(running_procs):
                print(f"    [{i+1}] {p_name} (PID: {p_pid})")
            try:
                choice = input(f"Chon tien trinh [1-{len(running_procs)}] (Mac dinh 1): ").strip()
                idx = int(choice) - 1 if choice else 0
                target_pid, target_process = running_procs[idx]
            except Exception:
                target_pid, target_process = running_procs[0]

    sniffer = WLOLiveSniffer(
        target_process=target_process,
        target_pid=target_pid,
        filter_opcode=args.opcode,
        filter_dir=args.dir,
        no_ping=args.no_ping,
        save_file=args.save,
        show_hex=args.hex
    )
    sniffer.start()

if __name__ == "__main__":
    main()
