#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO CAPTURE & ANALYZE CURSED PALACE ON ALOGIN-W04
=================================================
Lắng nghe và phân tích toàn bộ gói tin gửi/nhận (C->S & S->C)
trên tiến trình alogin-W04 khi người dùng thực hiện các bước
di chuyển và bước vào Cursed Palace.
"""

import os
import sys
import time
import struct
from datetime import datetime

# UTF-8 Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    print("[!] Chưa cài đặt thư viện frida.")
    sys.exit(1)

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "w04_cursed_palace_capture.txt")

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

OPCODE_NAMES = {
    0x01: "SYSTEM_HANDSHAKE",
    0x05: "LOGIN_AUTH",
    0x06: "MOVEMENT_OR_COMBAT",
    0x07: "TEAM_FORMATION",
    0x08: "PING_HEARTBEAT",
    0x0A: "TRADE_STALL",
    0x0B: "INVENTORY_ITEM",
    0x0C: "FRIEND_MAIL",
    0x0D: "PARTY_SYSTEM",
    0x0E: "CHANNEL_LIST",
    0x0F: "PET_STATUS",
    0x14: "CHAT_DIALOG_TEXT",
    0x16: "MAP_SCENE_QUEST",
    0x17: "CHAR_ATTRIBUTES_ITEM",
    0x18: "SHORTCUT_BAR_DIALOG",
    0x20: "NPC_DIALOG_CHOICE",
    0x3E: "WEATHER_EFFECT",
    0x3F: "AUTH_LOGIN_SLOT",
}

def parse_wlo_packet(raw_bytes, buffer):
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

def decode_details(direction, opcode, subcode, data):
    details = ""
    # Tọa độ di chuyển
    if opcode == 0x06 and subcode == 0x01 and len(data) >= 5:
        mode = data[0]
        x = struct.unpack("<H", data[1:3])[0]
        y = struct.unpack("<H", data[3:5])[0]
        checksum = data[5:].hex() if len(data) > 5 else ""
        details = f"[BƯỚC ĐI BỘ] Tọa độ (X={x}, Y={y}) | Mode: 0x{mode:02X} | Checksum: {checksum}"
    # Tương tác NPC / Cổng
    elif opcode == 0x06 and subcode == 0x02 and len(data) >= 5:
        target_id = data[0]
        x = struct.unpack("<H", data[1:3])[0]
        y = struct.unpack("<H", data[3:5])[0]
        details = f"[TƯƠNG TÁC NPC/CỔNG] Mục tiêu: 0x{target_id:02X} tại (X={x}, Y={y})"
    # Lựa chọn đối thoại
    elif opcode == 0x20 and subcode == 0x02 and len(data) >= 1:
        details = f"[CHỌN THOẠI NPC] Option: 0x{data[0]:02X} ({data[0]})"
    elif opcode == 0x20 and subcode == 0x03:
        details = "[ĐÓNG HỘP THOẠI NPC]"
    # Dùng item MiniDragonfly
    elif opcode == 0x17 and subcode == 0x59:
        details = f"[DÙNG ITEM BAY GPS] Data: {data.hex()}"
    # Trừ item / vé
    elif opcode == 0x17 and subcode == 0x09 and len(data) >= 2:
        slot = data[0]
        qty = data[1]
        details = f"★ [TRỪ ITEM / VÉ REGISVOUCHER] Ô Slot: {slot} | Số lượng thay đổi: {qty}"
    # Nạp map cảnh
    elif opcode == 0x16 and subcode == 0x04:
        details = f"★ [NẠP BẢN ĐỒ CẢNH MỚI] Map/Spawn data length: {len(data)} bytes"
    # Thoại Server
    elif opcode == 0x14 and subcode == 0x01:
        details = f"[THOẠI SERVER TRẢ VỀ] Length: {len(data)}"
    elif opcode == 0x18 and subcode == 0x05:
        details = f"[MENU THOẠI SERVER TRẢ VỀ] Length: {len(data)}"

    return details

def find_w04_process():
    dev = frida.get_local_device()
    for p in dev.enumerate_processes():
        plow = p.name.lower()
        if "w04" in plow:
            return p
    return None

def main():
    print("=" * 80)
    print("       WLO PACKET CAPTURE & ANALYZER CHO ALOGIN-W04")
    print("================================================================================")
    proc = find_w04_process()
    if not proc:
        print("[!] Không tìm thấy tiến trình alogin-W04 nào đang chạy!")
        sys.exit(1)

    print(f"[+] Đã tìm thấy tiến trình: {proc.name} (PID: {proc.pid})")
    print(f"[*] File ghi nhận nhật ký: {LOG_FILE}")
    print("[*] Đang đính kèm Frida...")

    dev = frida.get_local_device()
    session = dev.attach(proc.pid)

    c2s_buf = bytearray()
    s2c_buf = bytearray()
    pkt_count = 0
    start_t = time.time()

    # Làm sạch file log cũ
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"=== BẮT ĐẦU BẮT GÓI TIN ALOGIN-W04 (PID: {proc.pid}) LÚC {datetime.now()} ===\n\n")

    def on_message(message, raw_data):
        nonlocal pkt_count
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "recv")
        sock = payload.get("sock", -1)

        is_send = (dir_name == "send")
        buffer = c2s_buf if is_send else s2c_buf
        packets = parse_wlo_packet(raw_data, buffer)

        for opcode, subcode, data, raw_pkt in packets:
            # Bỏ qua ping heartbeat Op: 0x08 để đỡ loãng log
            if opcode == 0x08:
                continue

            pkt_count += 1
            direction = "C->S" if is_send else "S->C"
            now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            elapsed = time.time() - start_t

            op_name = OPCODE_NAMES.get(opcode, f"0x{opcode:02X}")
            sub_hex = f"0x{subcode:02X}" if subcode is not None else "--"
            hex_data = data.hex()
            details = decode_details(direction, opcode, subcode, data)

            line = f"[{now_str}] [+ {elapsed:6.2f}s] [#{pkt_count:<4}] {direction} Op:0x{opcode:02X} ({op_name:<18}) Sub:{sub_hex} Len:{len(data):<3} | Hex: {hex_data}"
            if details:
                line += f"\n       └── {details}"

            print(line, flush=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    script = session.create_script(FRIDA_JS)
    script.on("message", on_message)
    script.load()

    print("[+] Hook thành công! Đang theo dõi mọi thao tác trên alogin-W04...")
    print("=" * 80)
    print("  ★ BÂY GIỜ BẠN HÃY THỰC HIỆN THAO TÁC BƯỚC VÀO CURSED PALACE TRÊN ALOGIN-W04!")
    print("    • Toàn bộ bước click chuột, đi bộ, tương tác NPC, nộp vé, vào điện sẽ được ghi lại.")
    print("    • Nhấn Ctrl+C để kết thúc khi đã hoàn tất.")
    print("=" * 80)

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[*] Đã dừng theo dõi.")
        session.detach()

if __name__ == "__main__":
    main()
