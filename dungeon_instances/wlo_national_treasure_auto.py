#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO NATIONAL TREASURE (QUỐC BẢO) AUTO CHEST OPENER & ROOM SOLVER
================================================================
Công cụ tự động hóa vượt phòng phụ bản Quốc Bảo (National Treasure):
1. Tự động mở từng rương trong phòng: Gửi C->S Op: 0x14 Sub: 0x01 [chest_idx 2B LE].
2. Lắng nghe phản hồi thời gian thực:
   - Nếu nhận vật phẩm ngẫu nhiên: Kiểm tra mã Item ID.
   - Nếu gặp quái vật: Tự động kích hoạt luồng chiến đấu giải quyết nhanh gọn trận đánh.
   - Nếu xuất hiện CHÌA KHÓA QUỐC BẢO (0x75AE - 0x75B2):
     ★ LẬP TỨC DỪNG MỞ RƯƠNG TRONG PHÒNG!
     ★ Thông báo đã có Chìa khóa và sẵn sàng sang phòng tiếp theo.
3. Tự động chăm sóc Pet: Tự động xuất chiến lại Pet (Op: 0x13 Sub: 0x01) nếu Pet bị hạ gục.
"""

import os
import sys
import time
import struct
import threading
from datetime import datetime

# UTF-8 Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

try:
    import frida
except ImportError:
    print("[!] Chưa cài đặt frida. Chạy lệnh: pip install frida")
    sys.exit(1)

# Danh sách 5 Chìa khóa / Dấu ấn Quốc Bảo
NATIONAL_TREASURE_KEYS = {
    0x75AE: "Chìa khóa Quốc Bảo 1 (Mã 30126)",
    0x75AF: "Chìa khóa Quốc Bảo 2 (Mã 30127)",
    0x75B0: "Chìa khóa Quốc Bảo 3 (Mã 30128)",
    0x75B1: "Chìa khóa Quốc Bảo 4 (Mã 30129)",
    0x75B2: "Chìa khóa Quốc Bảo 5 (Mã 30130)",
}

# Cấu hình Slot Pet mặc định
DEFAULT_COMBAT_PET_SLOTS = {
    "alogin-F04.exe": 2,
    "alogin-W03.exe": 4,
    "alogin-W04.exe": 4,
    "alogin-Wi01.exe": 2,
}

# Cấu hình Pet ID mặc định
DEFAULT_COMBAT_PETS = {
    "alogin-F04.exe": 14081,  # Slot 2 UI (0x3701)
    "alogin-W03.exe": 14242,  # Slot 4 (0x37A2)
    "alogin-W04.exe": 14242,  # Slot 4 (0x37A2)
    "alogin-Wi01.exe": 14609, # Slot 2 UI / pIdx 2 (0x3911)
}

TARGET_CLIENTS = [
    "alogin-W04.exe",
    "alogin-W03.exe",
    "alogin-F04.exe",
    "alogin-Wi01.exe",
]

# Kỹ năng chiến đấu mặc định
SKILL_DEFEND = bytes.fromhex("75ea0000")
SKILL_FIRE_1F3B = bytes.fromhex("1f3b0000")
SKILL_PET_043B = bytes.fromhex("043b0000")
SKILL_PET_2D2B = bytes.fromhex("2d2b0000")

FRIDA_HOOK_JS = """
var activeSocket = -1;

var ws2 = Process.getModuleByName('ws2_32.dll');
var sendPtr = ws2 ? ws2.getExportByName('send') : null;
var getpeernamePtr = ws2 ? ws2.getExportByName('getpeername') : null;

var sendFunc = sendPtr ? new NativeFunction(sendPtr, 'int', ['int', 'pointer', 'int', 'int']) : null;
var getpeernameFunc = getpeernamePtr ? new NativeFunction(getpeernamePtr, 'int', ['pointer', 'pointer', 'pointer']) : null;

function scanActiveSocket() {
    if (activeSocket > 0) return activeSocket;
    if (!getpeernameFunc) return -1;
    var sockaddr = Memory.alloc(32);
    var lenPtr = Memory.alloc(4);
    for (var h = 4; h < 65536; h += 4) {
        lenPtr.writeU32(32);
        var ret = getpeernameFunc(ptr(h), sockaddr, lenPtr);
        if (ret === 0) {
            var port = (sockaddr.add(2).readU8() << 8) | sockaddr.add(3).readU8();
            if (port === 6414 || port > 1024) {
                activeSocket = h;
                return h;
            }
        }
    }
    return -1;
}

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

hookRecv('ws2_32.dll');
hookRecv('wsock32.dll');
scanActiveSocket();

function doSendRaw(hexBytes) {
    if (activeSocket <= 0) scanActiveSocket();
    if (activeSocket <= 0) return {success: false, error: 'No active socket'};
    if (!sendFunc) return {success: false, error: 'No send function'};
    
    var raw = [];
    for (var i = 0; i < hexBytes.length; i += 2) {
        raw.push(parseInt(hexBytes.substr(i, 2), 16));
    }
    var buf = Memory.alloc(raw.length);
    buf.writeByteArray(raw);
    try {
        var ret = sendFunc(activeSocket, buf, raw.length, 0);
        return {success: true, ret: ret, sock: activeSocket};
    } catch(e) {
        return {success: false, error: e.toString()};
    }
}

function readPetInfo() {
    try {
        var playerPtr = ptr('0x8b76dc').readPointer().readPointer();
        if (playerPtr.isNull()) return {success: false};
        var activeSlot = playerPtr.add(0x2230).readU8();
        var pets = [];
        for (var i = 1; i <= 4; i++) {
            var pSlot = playerPtr.add(0x21e8 + i * 4).readPointer();
            if (!pSlot.isNull()) {
                var pId = pSlot.add(4).readU32();
                var pIdx = pSlot.add(0x21bc).readU8();
                var exists = pSlot.add(0xb0).readU8();
                var curHp = pSlot.add(0x158).readU32();
                var maxHp = pSlot.add(0x84).readU32();
                if (pId > 0 && exists > 0) {
                    pets.push({
                        slot: i,
                        id: pId,
                        idx: pIdx,
                        curHp: curHp,
                        maxHp: maxHp,
                        is_active: (activeSlot === i)
                    });
                }
            }
        }
        return {
            success: true,
            activeSlot: activeSlot,
            pets: pets
        };
    } catch(e) {
        return {success: false, error: e.toString()};
    }
}

rpc.exports = {
    getsocket: function() { return scanActiveSocket(); },
    sendraw: function(hex) { return doSendRaw(hex); },
    readpetinfo: function() { return readPetInfo(); }
};
"""

def pack_wlo_packet(body_bytes: bytes) -> bytes:
    """Đóng gói Magic Header 0xF4 0x44, uint16 LE Length và XOR 0xAD."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain = header + body_bytes
    return bytes(b ^ 0xAD for b in plain)


class WLOStreamDissector:
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


class NationalTreasureAutoRunner:
    def __init__(self):
        self.sessions = {}
        self.scripts = {}
        self.dissectors = {}
        self.locks = {p: threading.Lock() for p in TARGET_CLIENTS}
        self.running = True

        # Trạng thái phòng & rương
        self.current_map_id = 0
        self.in_battle = False
        self.key_found_in_room = False
        self.chests_unlocked_by_server = False
        self.keys_obtained = set()
        self.last_item_received = None
        self.last_item_time = 0

        # Điều khiển tự động mở rương
        self.auto_opening = False
        self.max_chests_per_room = 30
        self.current_chest_idx = 1
        self.opener_client = "alogin-F04.exe"  # Mặc định F04 mở rương

        # Điều khiển chiến đấu
        self.combat_turn = 0
        self.combat_enemies = []

    def log(self, tag: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] [{tag:<15}] {msg}", flush=True)

    def attach_all(self):
        print("=" * 85)
        print("   WLO NATIONAL TREASURE (QUỐC BẢO) AUTO CHEST & ROOM SOLVER")
        print("=" * 85)
        connected = 0
        for proc in TARGET_CLIENTS:
            nick = proc.replace("alogin-", "").replace(".exe", "")
            self.dissectors[proc] = WLOStreamDissector()
            try:
                session = frida.attach(proc)
                script = session.create_script(FRIDA_HOOK_JS)
                script.on("message", lambda msg, data, p=proc, n=nick: self.on_message(p, n, msg, data))
                script.load()

                self.sessions[proc] = session
                self.scripts[proc] = script
                self.log("INIT", f"✔ Đã kết nối thành công [{nick}] (PID: {session._impl.pid})")
                connected += 1
            except Exception as e:
                self.log("ERROR", f"❌ Lỗi kết nối [{nick}]: {e}")

        if connected == 0:
            print("[!] Không kết nối được client nào. Vui lòng mở game trước khi chạy.")
            return False

        print(f"\n[★] SẴN SÀNG! ĐÃ KẾT NỐI {connected}/4 TIẾN TRÌNH CLIENT.\n")
        return True

    def send_packet(self, proc: str, body_bytes: bytes):
        script = self.scripts.get(proc)
        if not script:
            return {"success": False, "error": "No script"}
        enc = pack_wlo_packet(body_bytes)
        try:
            return script.exports_sync.sendraw(enc.hex())
        except Exception as e:
            return {"success": False, "error": str(e)}

    def open_chest(self, chest_idx: int):
        """Gửi C->S Op: 0x14 Sub: 0x01 [chest_idx 2B LE] mở rương"""
        body = bytes([0x14, 0x01]) + struct.pack("<H", chest_idx)
        nick = self.opener_client.replace("alogin-", "").replace(".exe", "")
        self.log("OPEN CHEST", f"👉 [{nick}] Đang gửi lệnh mở Rương #{chest_idx:02d} (0x{chest_idx:04X})...")
        return self.send_packet(self.opener_client, body)

    def on_message(self, proc: str, nick: str, message: dict, raw_data: bytes):
        if not raw_data:
            return

        dissector = self.dissectors.get(proc)
        if not dissector:
            return

        packets = dissector.feed(raw_data)
        for opcode, subcode, data, _ in packets:
            # 1. NHẬN VẬT PHẨM: S->C Op: 0x17 Sub: 0x06
            if opcode == 0x17 and subcode == 0x06 and len(data) >= 2:
                item_id = struct.unpack("<H", data[:2])[0]
                qty = data[2] if len(data) >= 3 else 1
                self.last_item_received = item_id
                self.last_item_time = time.time()

                if item_id in NATIONAL_TREASURE_KEYS:
                    key_name = NATIONAL_TREASURE_KEYS[item_id]
                    self.key_found_in_room = True
                    self.keys_obtained.add(item_id)
                    self.log("👑 KEY FOUND!", f"★ [{nick}] NHẬN ĐƯỢC CHÌA KHÓA: {key_name} x{qty}!")
                    self.log("ROOM CLEAR", f"✨ ĐÃ CÓ CHÌA KHÓA! DỪNG MỞ RƯƠNG TRONG PHÒNG NÀY NGAY LẬP TỨC!")
                else:
                    self.log("REWARD", f"🎁 [{nick}] Nhận vật phẩm: Mã 0x{item_id:04X} ({item_id}) x{qty}")

            # 2. VÀO TRẬN ĐÁNH: S->C Op: 0x0B Sub: 0xFA hoặc 0x02
            elif opcode == 0x0B and subcode in (0xFA, 0x02):
                if not self.in_battle:
                    self.in_battle = True
                    self.combat_turn = 0
                    self.log("BATTLE START", f"⚔️ Quái vật xuất hiện từ rương! Bắt đầu trận đánh...")
                    # Kích hoạt luồng tự động combat
                    threading.Thread(target=self.auto_combat_loop, daemon=True).start()

            # 3. KẾT THÚC TRẬN ĐÁNH: S->C Op: 0x0B Sub: 0x00
            elif opcode == 0x0B and subcode == 0x00:
                if self.in_battle:
                    self.in_battle = False
                    self.log("BATTLE END", f"🏆 Trận đánh kết thúc! Dọn dẹp và kiểm tra trạng thái...")
                    # Kiểm tra và gọi lại Pet nếu bị hạ gục
                    threading.Thread(target=self.resummon_all_pets, daemon=True).start()

            # 4. CHUYỂN MAP MỚI: S->C Op: 0x35 Sub: 0x05
            elif opcode == 0x35:
                map_id = struct.unpack("<H", data[:2])[0] if len(data) >= 2 else 0
                if map_id != self.current_map_id:
                    self.current_map_id = map_id
                    self.key_found_in_room = False
                    self.chests_unlocked_by_server = False
                    self.current_chest_idx = 1
                    self.log("MAP WARP", f"🚪 Đã chuyển sang Phòng / Map mới: ID {map_id} (0x{map_id:04X})")

            # 5. TẤT CẢ RƯƠNG MỞ KHÓA: S->C Op: 0x16 Sub: 0x01
            elif opcode == 0x16 and subcode == 0x01:
                self.chests_unlocked_by_server = True

    def auto_combat_loop(self):
        """Xử lý chiến đấu tự động khi mở trúng rương có quái"""
        time.sleep(1.2)
        while self.in_battle and self.running:
            self.combat_turn += 1
            self.log("COMBAT TURN", f"⚡ Đang thực hiện Hiệp {self.combat_turn}...")

            # 1. F04 và Pet F04 tấn công
            # Lượt 1: F04 dùng 1f3b vào Hàng 2 (Slot 1 Row 2), Pet F04 dùng 043b vào Hàng 3 (Slot 1 Row 3)
            # Lượt sau: Dồn sát thương vào mục tiêu ưu tiên
            target_slot, target_row = 1, 2
            pkt_f04_pet = bytes([0x32, 0x01, 0x04, 0x02, target_slot, 3]) + SKILL_PET_043B + bytes([0x00])
            self.send_packet("alogin-F04.exe", pkt_f04_pet)

            pkt_f04_char = bytes([0x32, 0x01, 0x03, 0x02, target_slot, target_row]) + SKILL_FIRE_1F3B + bytes([0x00])
            self.send_packet("alogin-F04.exe", pkt_f04_char)

            # 2. W04, W03, Wi01: Hiệp 1 thủ (75ea), Hiệp sau pet tấn công (2d2b)
            for proc, p_slot, p_row in [("alogin-W04.exe", 4, 4), ("alogin-W03.exe", 4, 3), ("alogin-Wi01.exe", 4, 1)]:
                c_slot = 3
                if self.combat_turn == 1:
                    # Thủ toàn diện
                    pkt_p = bytes([0x32, 0x01, p_slot, p_row, p_slot, p_row]) + SKILL_DEFEND + bytes([0x00])
                    pkt_c = bytes([0x32, 0x01, c_slot, p_row, c_slot, p_row]) + SKILL_DEFEND + bytes([0x00])
                else:
                    # Pet tấn công 2d2b
                    pkt_p = bytes([0x32, 0x01, p_slot, p_row, 1, 2]) + SKILL_PET_2D2B + bytes([0x00])
                    pkt_c = bytes([0x32, 0x01, c_slot, p_row, c_slot, p_row]) + SKILL_DEFEND + bytes([0x00])

                self.send_packet(proc, pkt_p)
                self.send_packet(proc, pkt_c)

            time.sleep(3.5)

    def resummon_all_pets(self):
        """Kiểm tra và tự động gọi lại Pet nếu bị hạ gục trong trận"""
        time.sleep(0.8)
        for proc in TARGET_CLIENTS:
            nick = proc.replace("alogin-", "").replace(".exe", "")
            script = self.scripts.get(proc)
            if not script:
                continue
            try:
                info = script.exports_sync.readpetinfo()
                if not info or not info.get("success"):
                    continue
                active_slot = info.get("activeSlot", 0)
                if active_slot == 0:
                    # Cần gọi lại pet
                    target_id = DEFAULT_COMBAT_PETS.get(proc)
                    if target_id:
                        self.log("PET SUMMON", f"🐾 [{nick}] Gọi lại Pet (ID: 0x{target_id:04X})...")
                        pkt = bytes([0x13, 0x01]) + struct.pack("<I", target_id)
                        self.send_packet(proc, pkt)
            except Exception as e:
                pass

    def run_room_auto_open(self, start_idx: int = 1, max_chests: int = 30):
        """Vòng lặp tự động mở từng rương cho đến khi ra Chìa khóa Quốc Bảo"""
        self.auto_opening = True
        self.key_found_in_room = False
        self.current_chest_idx = start_idx

        self.log("START ROOM", f"🚀 Bắt đầu tự động mở rương từ Rương #{start_idx} đến #{max_chests}...")
        self.log("RULE", f"📌 Quy tắc: Mở từng rương -> Nếu gặp quái sẽ tự đánh -> Khi có CHÌA KHÓA sẽ DỪNG NGAY!")

        while self.auto_opening and self.current_chest_idx <= max_chests:
            # 1. Nếu đã tìm thấy chìa khóa -> Dừng ngay lập tức!
            if self.key_found_in_room:
                self.log("SUCCESS", f"🎉 [HOÀN TẤT PHÒNG] Đã có Chìa khóa Quốc Bảo! Vui lòng bước qua cổng sang phòng tiếp theo.")
                self.auto_opening = False
                return True

            # 2. Nếu đang trong trận đánh -> Đợi trận kết thúc
            if self.in_battle:
                time.sleep(1.0)
                continue

            # 3. Mở rương hiện tại
            self.last_item_received = None
            self.open_chest(self.current_chest_idx)

            # 4. Đợi phản hồi từ server (vật phẩm, trận đấu hoặc rương rỗng)
            wait_time = 0
            while wait_time < 2.0:
                time.sleep(0.2)
                wait_time += 0.2
                if self.in_battle or self.key_found_in_room or self.last_item_received is not None:
                    break

            # 5. Nếu trận chiến nổ ra -> Đợi kết thúc trận
            if self.in_battle:
                self.log("WAIT BATTLE", f"Đang chiến đấu quái vật từ Rương #{self.current_chest_idx:02d}...")
                while self.in_battle and self.running:
                    time.sleep(1.0)
                time.sleep(1.0)  # Chờ đồng bộ sau trận

            # 6. Kiểm tra lại sau trận nếu có rơi chìa khóa
            if self.key_found_in_room:
                self.log("SUCCESS", f"🎉 [HOÀN TẤT PHÒNG] Đã có Chìa khóa Quốc Bảo sau trận đánh! Dừng mở rương.")
                self.auto_opening = False
                return True

            # Chuyển sang rương tiếp theo
            self.current_chest_idx += 1
            time.sleep(0.6)

        if not self.key_found_in_room:
            self.log("INFO", f"Đã mở hết {max_chests} rương trong phòng hiện tại.")
        self.auto_opening = False
        return self.key_found_in_room


def main():
    runner = NationalTreasureAutoRunner()
    if not runner.attach_all():
        return

    print("=" * 80)
    print("                BẢNG ĐIỀU KHIỂN AUTO QUỐC BẢO")
    print("=" * 80)
    print("  Các lệnh có sẵn trên console:")
    print("    [Enter] hoặc [start] : Bắt đầu tự động mở rương trong phòng hiện tại")
    print("    [stop]              : Dừng mở rương")
    print("    [open <số>]         : Mở thủ công 1 rương chỉ định (VD: open 5)")
    print("    [pet]               : Xuất chiến lại toàn bộ Pet của cả 4 acc")
    print("    [status]            : Xem trạng thái phòng, chìa khóa đã có")
    print("    [exit]              : Thoát chương trình")
    print("=" * 80 + "\n")

    while runner.running:
        try:
            cmd = input("AutoQuocBao > ").strip().lower()
            if not cmd or cmd == "start":
                threading.Thread(target=runner.run_room_auto_open, daemon=True).start()
            elif cmd == "stop":
                runner.auto_opening = False
                runner.log("STOP", "Đã gửi lệnh dừng tự động mở rương.")
            elif cmd.startswith("open "):
                try:
                    c_idx = int(cmd.split()[1])
                    runner.open_chest(c_idx)
                except ValueError:
                    print("Cú pháp: open <số_thứ_tự_rương> (VD: open 1)")
            elif cmd == "pet":
                runner.resummon_all_pets()
            elif cmd == "status":
                keys_str = ", ".join(f"0x{k:04X}" for k in runner.keys_obtained) or "Chưa có"
                print(f"Map hiện tại: {runner.current_map_id} | Chìa khóa đã gom: [{keys_str}] | Đang mở rương: {runner.auto_opening}")
            elif cmd in ("exit", "quit"):
                runner.running = False
                print("Đang thoát...")
                break
        except (KeyboardInterrupt, EOFError):
            break

if __name__ == "__main__":
    main()
