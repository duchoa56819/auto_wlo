#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO PACKET CAPTURE & LIVE ANALYZER CHO ALOGIN-F02 (INSTANCE / PHỤ BẢN)
======================================================================
Giám sát thời gian thực toàn bộ luồng gói tin gửi / nhận (C->S & S->C)
trên tiến trình alogin-F02 khi người chơi đánh Instance / Phụ bản.

Tính năng phân tích chuyên sâu:
1. CHIẾN ĐẤU (COMBAT):
   - Vào trận (Op: 0x0B Sub: 0xFA / 0x02) & Kết thúc trận (Op: 0x0B Sub: 0x00).
   - Hành động ra chiêu (Op: 0x32 Sub: 0x01): Nhận diện Char/Pet, Hàng, Slot, Chiêu thức (Skill ID & Tên skill), Mục tiêu.
   - Trạng thái Pet / HP / SP trong trận.
2. PHỤ BẢN & NPC (INSTANCE / LOBBY):
   - Vào phụ bản / Chọn ải / Tầng (Op: 0x55 Sub: 0x03).
   - Đối thoại NPC / Menu chọn (Op: 0x20, Op: 0x14, Op: 0x18).
   - Chuyển cảnh / Nạp Map mới (Op: 0x35, Op: 0x16 Sub: 0x04).
3. VẬT PHẨM & PHẦN THƯỞNG (INVENTORY & REWARDS):
   - Nhận thưởng sau ải (Op: 0x17 Sub: 0x06): Tự động tra cứu tên vật phẩm từ wlo_items_database.json.
   - Sử dụng vật phẩm / cắn bình thuốc (Op: 0x17 Sub: 0x0F / 0x4B).
   - Tiêu hao / trừ số lượng ô đồ (Op: 0x17 Sub: 0x09).
   - Di chuyển / vứt đồ (Op: 0x17 Sub: 0x0A, 0x03, 0xD4, 0x7C, 0x1A).
4. TỔ ĐỘI (PARTY):
   - Đồng bộ đội hình, mời vào nhóm, chuyển đội trưởng (Op: 0x0D).
"""

import os
import sys
import time
import json
import struct
from datetime import datetime

# UTF-8 Windows Console
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
LOG_FILE = os.path.join(SCRIPT_DIR, "f02_instance_capture.log")
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
    "d861": "Sát thương Thủy/Địa (Char W04/W03)",
    "a33a": "Sát thương Pet Thủy/Địa (Pet W04/W03)",
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
    0x35: "MAP_WARP_PORTAL",
    0x3F: "AUTH_LOGIN_SLOT",
    0x55: "DUNGEON_INSTANCE_LOBBY",
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

def decode_packet_details(direction, opcode, subcode, data):
    """Giải mã chi tiết ngữ nghĩa các gói tin game WLO."""
    details = []

    # =========================================================================
    # 1. CHIẾN ĐẤU (COMBAT)
    # =========================================================================
    # C->S Op: 0x32 Sub: 0x01: Lệnh hành động trong trận đánh
    if direction == "C->S" and opcode == 0x32 and subcode == 0x01:
        if len(data) >= 8:
            actor_slot, actor_row, target_slot, target_row = data[0], data[1], data[2], data[3]
            skill_raw = data[4:8]
            skill_hex = skill_raw[:2].hex()
            skill_name = KNOWN_SKILLS.get(skill_hex, f"Chiêu thức mã 0x{skill_hex}")
            actor_type = "Nhân vật (Char)" if actor_slot == 3 else ("Pet" if actor_slot == 4 else f"Slot {actor_slot}")
            target_pos = f"Hàng {target_row} (Cột {target_slot})"
            details.append(f"⚔️ [RA ĐÒN CHIẾN ĐẤU] {actor_type} (Hàng {actor_row}) -> Dùng chiêu [{skill_name} - Hex: {skill_hex}] -> Mục tiêu: {target_pos}")

    # S->C Op: 0x0B: Sự kiện trận đánh
    elif opcode == 0x0B:
        if subcode in (0xFA, 0x02):
            details.append("⚡ [VÀO TRẬN ĐÁNH] Quái vật xuất hiện! Trận chiến bắt đầu.")
        elif subcode == 0x00:
            details.append("🏁 [KẾT THÚC TRẬN ĐÁNH] Chiến thắng / Trận đánh đã hoàn tất thành công.")
        elif subcode == 0x01:
            details.append(f"⏳ [CẬP NHẬT LƯỢT ĐÁNH] Combat Turn tick / Round data: {data.hex()}")

    # =========================================================================
    # 2. PHỤ BẢN & ĐỐI THOẠI NPC (INSTANCE & NPC)
    # =========================================================================
    # C->S Op: 0x55 Sub: 0x03: Chọn Ải / Tầng / Phụ bản
    elif opcode == 0x55 and subcode == 0x03:
        if len(data) >= 2:
            dungeon_id = struct.unpack("<H", data[:2])[0]
            details.append(f"🏛️ [CHỌN PHỤ BẢN / ẢI] Dungeon / Stage ID: {dungeon_id} (0x{dungeon_id:04X}) | Data: {data.hex()}")
        else:
            details.append(f"🏛️ [CHỌN PHỤ BẢN] Data: {data.hex()}")

    # Op: 0x20: Đối thoại NPC
    elif opcode == 0x20:
        if subcode == 0x01:
            details.append(f"💬 [BƯỚC VÀO THOẠI NPC] Data: {data.hex()}")
        elif subcode == 0x02 and len(data) >= 1:
            details.append(f"👉 [CHỌN LỰA CHỌN MENU NPC] Lựa chọn số: {data[0]} (0x{data[0]:02X})")
        elif subcode == 0x03:
            details.append("❌ [ĐÓNG HỘP THOẠI NPC]")

    # Op: 0x14 Sub: 0x01: Tin nhắn / Đối thoại từ Server
    elif opcode == 0x14 and subcode == 0x01:
        details.append(f"💬 [HỘP THOẠI SERVER GỬI] Độ dài: {len(data)} bytes")

    # Op: 0x18 Sub: 0x05: Menu lựa chọn NPC trả về
    elif opcode == 0x18 and subcode == 0x05:
        details.append(f"📋 [DANH SÁCH LỰA CHỌN NPC TỪ SERVER] Độ dài: {len(data)} bytes")

    # =========================================================================
    # 3. CHUYỂN CẢNH / DI CHUYỂN (WARP & MOVEMENT)
    # =========================================================================
    # Op: 0x06 Sub: 0x01: Di chuyển bước đi
    elif opcode == 0x06 and subcode == 0x01 and len(data) >= 5:
        mode = data[0]
        x = struct.unpack("<H", data[1:3])[0]
        y = struct.unpack("<H", data[3:5])[0]
        details.append(f"🚶 [DI CHUYỂN] Tọa độ (X={x}, Y={y}) | Mode: 0x{mode:02X}")

    # Op: 0x06 Sub: 0x02: Click tương tác đối tượng trên bản đồ
    elif opcode == 0x06 and subcode == 0x02 and len(data) >= 5:
        target_id = data[0]
        x = struct.unpack("<H", data[1:3])[0]
        y = struct.unpack("<H", data[3:5])[0]
        details.append(f"🎯 [CLICK TƯƠNG TÁC ĐỐI TƯỢNG] ID: 0x{target_id:02X} tại tọa độ (X={x}, Y={y})")

    # Op: 0x35: Chuyển bản đồ / Cổng dịch chuyển
    elif opcode == 0x35 and subcode == 0x01:
        details.append("🌀 [BƯỚC QUA CỔNG DỊCH CHUYỂN / WARP MAP]")

    # Op: 0x16 Sub: 0x04: Nạp dữ liệu bản đồ mới
    elif opcode == 0x16 and subcode == 0x04:
        details.append(f"🗺️ [NẠP BẢN ĐỒ CẢNH MỚI] Map Data: {len(data)} bytes")

    # =========================================================================
    # 4. TÚI ĐỒ & VẬT PHẨM (INVENTORY & ITEMS)
    # =========================================================================
    elif opcode == 0x17:
        # S->C Sub: 0x06: Trao thưởng vật phẩm
        if direction == "S->C" and subcode == 0x06 and len(data) >= 2:
            item_code = struct.unpack("<H", data[:2])[0]
            qty = data[2] if len(data) >= 3 else 1
            name = get_item_name(item_code)
            details.append(f"🎁 [NHẬN PHẦN THƯỞNG] Mã 0x{item_code:04X} ({name}) x{qty}")

        # S->C Sub: 0x09: Cập nhật số lượng ô đồ
        elif subcode == 0x09 and len(data) >= 2:
            slot, remain = data[0], data[1]
            details.append(f"🎒 [CẬP NHẬT Ô ĐỒ] Ô #{slot:02d} -> Số lượng còn lại: {remain}")

        # C->S Sub: 0x0F: Sử dụng vật phẩm
        elif direction == "C->S" and subcode == 0x0F and len(data) >= 2:
            slot = data[0]
            details.append(f"💊 [SỬ DỤNG VẬT PHẨM] Người chơi dùng món đồ tại Ô #{slot:02d}")

        # C->S Sub: 0x0A: Di chuyển đồ trong túi
        elif direction == "C->S" and subcode == 0x0A and len(data) >= 3:
            s_from, s_qty, s_to = data[0], data[1], data[2]
            details.append(f"📦 [DỜI VẬT PHẨM] Ô #{s_from:02d} (x{s_qty}) -> Chuyển sang Ô #{s_to:02d}")

        # Sub: 0x03 / 0xD4 / 0x7C / 0x1A: Quy trình vứt đồ
        elif subcode == 0x03 and direction == "C->S" and len(data) >= 2:
            details.append(f"🗑️ [YÊU CẦU VỨT ĐỒ] Ô #{data[0]:02d} (SL: {data[1]})")
        elif subcode == 0xD4 and direction == "S->C" and len(data) >= 5:
            slot = data[1]
            code = struct.unpack("<H", data[2:4])[0]
            qty = data[4]
            name = get_item_name(code)
            details.append(f"⚠️ [POPUP XÁC NHẬN VỨT] Ô #{slot:02d} -> Mã 0x{code:04X} ({name}) x{qty}")
        elif subcode == 0x7C and direction == "C->S" and len(data) >= 2:
            details.append(f"✔ [XÁC NHẬN POPUP VỨT ĐỒ] Ô #{data[0]:02d} (SL: {data[1]})")
        elif subcode == 0x1A and direction == "S->C" and len(data) >= 2:
            code = struct.unpack("<H", data[:2])[0]
            name = get_item_name(code)
            details.append(f"✨ [ĐÃ VỨT XONG THÀNH CÔNG] Mã 0x{code:04X} ({name})")

    # =========================================================================
    # 5. TỔ ĐỘI (PARTY)
    # =========================================================================
    elif opcode == 0x0D:
        if subcode == 0x01 and len(data) >= 4:
            cid = struct.unpack("<I", data[:4])[0]
            details.append(f"🤝 [YÊU CẦU / MỜI TỔ ĐỘI] Đối tác ID: 0x{cid:08X}")
        elif subcode == 0x03 and len(data) >= 5:
            cid = struct.unpack("<I", data[1:5])[0]
            details.append(f"★ [VÀO TỔ ĐỘI THÀNH CÔNG] Thành viên ID: 0x{cid:08X}")
        elif subcode == 0x05 and len(data) >= 8:
            mem_id = struct.unpack("<I", data[:4])[0]
            lead_id = struct.unpack("<I", data[4:8])[0]
            details.append(f"👥 [ĐỒNG BỘ ĐỘI HÌNH] TV 0x{mem_id:08X} | Trưởng nhóm 0x{lead_id:08X}")
        elif subcode == 0x0A and len(data) >= 5:
            new_lead = struct.unpack("<I", data[1:5])[0]
            details.append(f"👑 [CHUYỂN ĐỘI TRƯỞNG] Đội trưởng mới: 0x{new_lead:08X}")

    return "\n       └── ".join(details) if details else ""

def find_f02_process():
    """Tìm PID của alogin-F02."""
    dev = frida.get_local_device()
    for p in dev.enumerate_processes():
        plow = p.name.lower()
        if "f02" in plow:
            return p
    return None

def main():
    print("=" * 85)
    print("      WLO LIVE PACKET CAPTURE & ANALYZER - ALOGIN-F02 (INSTANCE MONITOR)")
    print("=====================================================================================")
    proc = find_f02_process()
    if not proc:
        print("[!] Không tìm thấy tiến trình alogin-F02 nào đang chạy!")
        sys.exit(1)

    print(f"[+] Đã tìm thấy tiến trình: {proc.name} (PID: {proc.pid})")
    print(f"[*] File ghi nhận nhật ký: {LOG_FILE}")
    print("[*] Đang đính kèm Frida vào alogin-F02...")

    dev = frida.get_local_device()
    session = dev.attach(proc.pid)

    c2s_buf = bytearray()
    s2c_buf = bytearray()
    pkt_count = 0
    start_t = time.time()

    # Mở file log và ghi header
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"=== BẮT ĐẦU BẮT GÓI TIN ALOGIN-F02 (PID: {proc.pid}) LÚC {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")

    def on_message(message, raw_data):
        nonlocal pkt_count
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "recv")

        is_send = (dir_name == "send")
        buffer = c2s_buf if is_send else s2c_buf
        packets = parse_wlo_packet(raw_data, buffer)

        for opcode, subcode, data, raw_pkt in packets:
            # Bỏ qua ping heartbeat Op: 0x08 để tránh làm loãng dữ liệu
            if opcode == 0x08:
                continue

            pkt_count += 1
            direction = "C->S" if is_send else "S->C"
            now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            elapsed = time.time() - start_t

            op_name = OPCODE_NAMES.get(opcode, f"0x{opcode:02X}")
            sub_hex = f"0x{subcode:02X}" if subcode is not None else "--"
            hex_data = data.hex()
            details = decode_packet_details(direction, opcode, subcode, data)

            line = f"[{now_str}] [+ {elapsed:6.2f}s] [#{pkt_count:<4}] {direction} Op:0x{opcode:02X} ({op_name:<22}) Sub:{sub_hex} Len:{len(data):<3} | Hex: {hex_data}"
            if details:
                line += f"\n       └── {details}"

            print(line, flush=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()

    script = session.create_script(FRIDA_JS)
    script.on("message", on_message)
    script.load()

    print("[+] Hook thành công 100%! Đang lắng nghe mọi hành động từ alogin-F02...")
    print("=" * 85)
    print("  ★ BẠN CỨ THOẢI MÁI ĐÁNH INSTANCE TRÊN ALOGIN-F02!")
    print("    • Toàn bộ chiêu thức, lượt đánh, di chuyển, nhận thưởng, tương tác NPC đều được ghi lại.")
    print("    • File log thời gian thực: f02_instance_capture.log")
    print("=" * 85)

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[*] Đã dừng theo dõi.")
        session.detach()

if __name__ == "__main__":
    main()
