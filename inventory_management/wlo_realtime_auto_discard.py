#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO REAL-TIME AUTO DISCARD DAEMON (THÁP 29 TẦNG & CURSED PALACE)
================================================================
Dịch vụ tự động chạy ngầm, giám sát thời gian thực gói tin Server trao thưởng
(Opcode 0x17 Subcode 0x06) và sự kiện kết thúc trận đánh (Opcode 0x0B Subcode 0x00).

NGAY KHI VỪA VƯỢT ẢI / TẦNG VÀ NHẬN ĐƯỢC PHẦN THƯỞNG RÁC:
1. Phát hiện ngay lập tức mã vật phẩm rác trong luồng gói tin Server -> Client.
2. Đợi 0.3s để game nạp vật phẩm vào ô RAM.
3. Quét trực tiếp bộ nhớ RAM túi đồ (Zero Hardcode) để tìm chính xác số ô Slot và số lượng.
4. Gửi chuỗi gói tin vứt bỏ 2 bước chuẩn:
   - Gói 1: Yêu cầu vứt đồ (Op: 0x17 Sub: 0x03)
   - Gói 2: Xác nhận popup vứt đồ (Op: 0x17 Sub: 0x7C)
5. Quét lại RAM xác nhận 100% túi đồ đã sạch và in thông báo tức thì.

DANH MỤC PHẦN THƯỞNG RÁC ĐƯỢC TỰ ĐỘNG VỨT TỨC THÌ:
- Tháp 29 Tầng (Sky Tower):
  * r5 (Tầng 05): Mã 0x7D4A (32074) - BubbleGum (Kẹo cao su)
  * r6 (Tầng 06): Mã 0x7D4B (32075) - Chocolate (Sô-cô-la)
  * r7 (Tầng 07): Mã 0x7D49 (32073) - InstantNoodle (Mì gói)
  * r8 (Tầng 08): Mã 0x7D48 (32072) - ChocolateIceCream (Kem)
- Cursed Palace (Cung Điện Bị Nguyền Rủa):
  * Ải 4 & 5  : Mã 0x7DB0 (32176) - FuguHotPot
  * Ải 6 & 7  : Mã 0x7E1D (32285) - Turkey
  * Ải 8 & 9  : Mã 0x7DB1 (32177) - SoyPorkboneNoodle
  * Ải 10     : Mã 0x7E34 (32308) - CurryRice
  * Ải 11     : Mã 0x8514 (34068) - LovePicnicLunch
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
    print("[!] Chưa cài đặt thư viện frida. Vui lòng cài: pip install frida")
    sys.exit(1)

# Danh sách đầy đủ 9 mã phần thưởng rác cần vứt tức thì
ALL_TRASH_REWARDS = {
    # --- THÁP 29 TẦNG (SKY TOWER) ---
    0x7D4A: {"name": "BubbleGum (Kẹo cao su)", "round": "Tháp r5 (Tầng 5)", "dec": 32074},
    0x7D4B: {"name": "Chocolate (Sô-cô-la)",   "round": "Tháp r6 (Tầng 6)", "dec": 32075},
    0x7D49: {"name": "InstantNoodle (Mì gói)", "round": "Tháp r7 (Tầng 7)", "dec": 32073},
    0x7D48: {"name": "ChocolateIceCream (Kem)","round": "Tháp r8 (Tầng 8)", "dec": 32072},

    # --- CURSED PALACE (CUNG ĐIỆN BỊ NGUYỀN RỦA) ---
    0x7DB0: {"name": "FuguHotPot",          "round": "Cursed Palace Ải 4, 5", "dec": 32176},
    0x7E1D: {"name": "Turkey",              "round": "Cursed Palace Ải 6, 7", "dec": 32285},
    0x7DB1: {"name": "SoyPorkboneNoodle",   "round": "Cursed Palace Ải 8, 9", "dec": 32177},
    0x7E34: {"name": "CurryRice",           "round": "Cursed Palace Ải 10",    "dec": 32308},
    0x8514: {"name": "LovePicnicLunch",     "round": "Cursed Palace Ải 11",    "dec": 34068},
}

# Cấu hình Slot Pet mặc định cho từng nhân vật (Wi01: slot 2, W04: slot 4, W03: slot 4, F04: slot 2)
DEFAULT_COMBAT_PET_SLOTS = {
    "alogin-F04.exe": 2,
    "alogin-W03.exe": 4,
    "alogin-W04.exe": 4,
    "alogin-Wi01.exe": 2,
}

# Cấu hình Pet xuất chiến chủ lực mặc định cho từng nhân vật (Op: 0x13 Sub: 0x01)
DEFAULT_COMBAT_PETS = {
    "alogin-F04.exe": 14081,   # Pet slot 2 (0x3701)
    "alogin-W03.exe": 14242,   # Pet slot 4 (0x37A2)
    "alogin-W04.exe": 14242,   # Pet slot 4 (0x37A2)
    "alogin-Wi01.exe": 14609,  # Pet slot 2 trong UI / pIdx 2 (0x3911)
}

TARGET_CLIENTS = [
    "alogin-W04.exe",
    "alogin-W03.exe",
    "alogin-F04.exe",
    "alogin-Wi01.exe",
]

FRIDA_HOOK_JS = """
var activeSocket = -1;
var cachedBagBase = null;

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
            if (port === 6414) {
                activeSocket = h;
                return h;
            }
        }
    }
    // Fallback: any port > 1024
    for (var h = 4; h < 65536; h += 4) {
        lenPtr.writeU32(32);
        var ret = getpeernameFunc(ptr(h), sockaddr, lenPtr);
        if (ret === 0) {
            var port = (sockaddr.add(2).readU8() << 8) | sockaddr.add(3).readU8();
            if (port > 1024) {
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

hookRecv('wsock32.dll');
hookRecv('ws2_32.dll');
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

function readBagMemory() {
    // 1. Dùng bộ nhớ đệm cachedBagBase siêu tốc (0.001s)
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

    // 2. Quét nhanh các dải Heap
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
    readbag: function() { return readBagMemory(); },
    readpetinfo: function() { return readPetInfo(); }
};
"""

def pack_wlo_packet(body_bytes: bytes) -> bytes:
    """Đóng gói Magic Header 0xF4 0x44, uint16 LE Length và XOR 0xAD."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain = header + body_bytes
    return bytes(b ^ 0xAD for b in plain)


class WLOStreamDissector:
    """Bộ giải mã stream packet WLO (XOR 0xAD, Magic 0xF4 0x44)."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, chunk: bytes):
        decrypted = bytes(b ^ 0xAD for b in chunk)
        self.buffer.extend(decrypted)
        packets = []

        while len(self.buffer) >= 4:
            magic, length = struct.unpack("<HH", self.buffer[:4])
            if magic != 0x44F4:
                idx = -1
                for i in range(1, len(self.buffer) - 1):
                    if self.buffer[i] == 0xF4 and self.buffer[i+1] == 0x44:
                        idx = i
                        break
                if idx != -1:
                    del self.buffer[:idx]
                    continue
                else:
                    self.buffer.clear()
                    break

            total_pkt_len = 4 + length
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


class RealtimeTrashCleaner:
    """Quản lý kết nối Frida, tự động vứt rác tức thì và tự động xuất chiến Pet sau trận"""

    def __init__(self):
        self.sessions = {}
        self.scripts = {}
        self.dissectors = {}
        self.locks = {}
        self.running = True
        self.designated_pets = dict(DEFAULT_COMBAT_PETS)
        self.pet_needs_resummon = {proc: False for proc in TARGET_CLIENTS}

    def log(self, tag: str, nick: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] [{nick:<4}] [{tag:<12}] {msg}", flush=True)

    def attach_all(self):
        print("=" * 85)
        print("   WLO REAL-TIME AUTO DISCARD & PET RE-SUMMON SERVICE")
        print("=" * 85)
        print("  1. Tự động vứt tức thì ngay khi nhận thưởng rác:")
        print("     • Tháp 29 tầng : r5 (0x7D4A), r6 (0x7D4B), r7 (0x7D49), r8 (0x7D48)")
        print("     • Cursed Palace: Ải 4,5 (0x7DB0), Ải 6,7 (0x7E1D), Ải 8,9 (0x7DB1), Ải 10 (0x7E34), Ải 11 (0x8514)")
        print("  2. Tự động xuất chiến lại Pet (C->S Op: 0x13 Sub: 0x01) ngay khi kết thúc trận đánh:")
        print("     • Phát hiện Pet hết máu / bị rút về trạng thái Nghỉ ngơi (val2230 = 0)")
        print("     • Tự động gọi Pet xuất chiến trở lại ngay sau trận để sẵn sàng vượt ải tiếp theo!")
        print("=" * 85 + "\n")

        connected = 0
        for proc in TARGET_CLIENTS:
            nick = proc.replace("alogin-", "").replace(".exe", "")
            self.locks[proc] = threading.Lock()
            self.dissectors[proc] = WLOStreamDissector()
            try:
                session = frida.attach(proc)
                script = session.create_script(FRIDA_HOOK_JS)
                script.on("message", lambda msg, data, p=proc, n=nick: self.on_message(p, n, msg, data))
                script.load()

                self.sessions[proc] = session
                self.scripts[proc] = script
                self.log("INIT", nick, f"✔ Đã kết nối và hook thành công vào tiến trình {proc} (PID: {session._impl.pid})")
                connected += 1

                # Quét dọn ban đầu nếu đã có sẵn rác trong túi & kiểm tra gọi Pet
                threading.Thread(target=self.initial_sweep, args=(proc, nick), daemon=True).start()

            except Exception as e:
                self.log("ERROR", nick, f"❌ Không thể attach vào {proc}: {e}")

        if connected == 0:
            print("[!] Không kết nối được client nào. Vui lòng mở game trước khi chạy service.")
            return False

        print(f"\n[★] ĐANG GIÁM SÁT THỜI GIAN THỰC TRÊN {connected} CỬA SỔ CLIENT... SẴN SÀNG!\n")
        return True

    def on_message(self, proc: str, nick: str, message: dict, raw_data: bytes):
        if not raw_data:
            return

        dissector = self.dissectors.get(proc)
        if not dissector:
            return

        packets = dissector.feed(raw_data)
        for opcode, subcode, data, _ in packets:
            # 1. PHÁT HIỆN GÓI TRAO THƯỞNG: S->C Op: 0x17 Sub: 0x06
            if opcode == 0x17 and subcode == 0x06 and len(data) >= 2:
                item_id = struct.unpack("<H", data[:2])[0]
                qty = data[2] if len(data) >= 3 else 1
                if item_id in ALL_TRASH_REWARDS:
                    trash_info = ALL_TRASH_REWARDS[item_id]
                    self.log("🎁 REWARD", nick, f"★ VỪA NHẬN THƯỞNG RÁC: {trash_info['name']} (Mã: 0x{item_id:04X}) x{qty} [{trash_info['round']}]")
                    # Kích hoạt luồng vứt ngay lập tức
                    threading.Thread(
                        target=self.discard_item_by_code,
                        args=(proc, nick, item_id, trash_info),
                        daemon=True
                    ).start()

            # 2. PHÁT HIỆN PET BỊ HẠ GỤC / RÚT VỀ NGHỈ NGƠI: S->C Op: 0x0E Sub: 0x09 hoặc Op: 0x05 Sub: 0x08
            elif (opcode == 0x0E and subcode == 0x09) or (opcode == 0x05 and subcode == 0x08):
                if len(data) >= 5:
                    pet_id, status = struct.unpack("<IB", data[:5])
                    if status == 0x03:  # 0x03: Nghỉ ngơi / Hết máu
                        self.pet_needs_resummon[proc] = True
                        self.log("🐾 PET ALERT", nick, f"⚠️ Server thông báo: Pet (ID: 0x{pet_id:04X}) đã bị hạ gục / rút về Nghỉ ngơi -> Sẽ tự động gọi lại ngay khi hết trận!")
                    elif status == 0x00:  # 0x00: Đang xuất chiến
                        self.pet_needs_resummon[proc] = False

            # 3. PHÁT HIỆN KẾT THÚC TRẬN ĐÁNH: S->C Op: 0x0B Sub: 0x00
            elif opcode == 0x0B and subcode == 0x00:
                # Quét an toàn sau trận đấu đề phòng trễ packet & tự động gọi lại Pet nếu chết
                threading.Thread(
                    target=self.post_battle_sweep,
                    args=(proc, nick),
                    daemon=True
                ).start()

    def discard_item_by_code(self, proc: str, nick: str, item_id: int, trash_info: dict):
        """Quét RAM và vứt ngay lập tức một mã vật phẩm cụ thể khi vừa nhận"""
        with self.locks[proc]:
            script = self.scripts.get(proc)
            if not script:
                return

            # Đợi 0.3s để game nạp dữ liệu vật phẩm mới vào RAM
            time.sleep(0.3)

            try:
                bag_res = script.exports_sync.readbag()
                if not bag_res or not bag_res.get("success"):
                    time.sleep(0.2)
                    bag_res = script.exports_sync.readbag()

                if not bag_res or not bag_res.get("success"):
                    self.log("WARN", nick, f"Không đọc được RAM túi đồ khi xử lý {trash_info['name']}")
                    return

                items = bag_res.get("items", {})
                target_slots = []
                for s_str, it in items.items():
                    if it.get("code") == item_id:
                        target_slots.append((int(s_str), it.get("qty", 1)))

                if not target_slots:
                    # Có thể vật phẩm chưa kịp nạp, thử lại lần 2 sau 0.3s
                    time.sleep(0.3)
                    bag_res2 = script.exports_sync.readbag()
                    if bag_res2 and bag_res2.get("success"):
                        for s_str, it in bag_res2.get("items", {}).items():
                            if it.get("code") == item_id:
                                target_slots.append((int(s_str), it.get("qty", 1)))

                if not target_slots:
                    self.log("INFO", nick, f"Không tìm thấy ô chứa {trash_info['name']} trong RAM (có thể đã bị dọn)")
                    return

                # Tiến hành vứt từng ô phát hiện được
                for slot_num, qty in target_slots:
                    self.log("TRASH", nick, f"Đang gửi lệnh vứt: Ô {slot_num:02d} -> {trash_info['name']} x{qty}...")
                    
                    # Gói 1: Yêu cầu vứt đồ
                    pkt_req = pack_wlo_packet(bytes([0x17, 0x03, slot_num, qty, 0x01]))
                    script.exports_sync.sendraw(pkt_req.hex())
                    time.sleep(0.12)

                    # Gói 2: Xác nhận Popup
                    pkt_cfm = pack_wlo_packet(bytes([0x17, 0x7C, slot_num, qty, 0x02]))
                    script.exports_sync.sendraw(pkt_cfm.hex())
                    time.sleep(0.15)

                # Quét lại RAM xác thực 100%
                time.sleep(0.3)
                bag_after = script.exports_sync.readbag()
                if bag_after and bag_after.get("success"):
                    items_after = bag_after.get("items", {})
                    still_has = any(it.get("code") == item_id for it in items_after.values())
                    if not still_has:
                        self.log("SUCCESS", nick, f"✨ [HOÀN TẤT VỨT RÁC] Đã xóa sạch 100% {trash_info['name']} khỏi túi đồ!")
                    else:
                        self.log("WARN", nick, f"Vẫn còn sót vật phẩm {trash_info['name']} trong túi!")

            except Exception as e:
                self.log("ERROR", nick, f"Lỗi trong quá trình vứt rác tức thì: {e}")

    def post_battle_sweep(self, proc: str, nick: str):
        """Quét dọn an toàn và tự động gọi lại Pet ngay sau khi kết thúc trận đấu"""
        time.sleep(0.8)
        self.sweep_client(proc, nick, reason="SAU TRẬN ĐẤU")
        self.check_and_resummon_pet(proc, nick)

    def initial_sweep(self, proc: str, nick: str):
        """Quét dọn toàn diện và đồng bộ trạng thái Pet ngay khi khởi động service"""
        time.sleep(0.5)
        self.sweep_client(proc, nick, reason="KHỞI ĐỘNG")
        self.check_and_resummon_pet(proc, nick)

    def check_and_resummon_pet(self, proc: str, nick: str, force: bool = False):
        """Kiểm tra nếu Pet đang nghỉ ngơi / bị hạ gục thì tự động gửi lệnh xuất chiến (Op: 0x13 Sub: 0x01)"""
        with self.locks[proc]:
            script = self.scripts.get(proc)
            if not script:
                return

            try:
                info = script.exports_sync.readpetinfo()
                if not info or not info.get("success"):
                    return

                active_slot = info.get("activeSlot", 0)
                pets = info.get("pets", [])

                target_pet_id = DEFAULT_COMBAT_PETS.get(proc)
                target_slot = DEFAULT_COMBAT_PET_SLOTS.get(proc)

                # Tìm pet tương ứng trong RAM: ưu tiên theo target_pet_id, hoặc theo UI idx (pIdx), hoặc theo RAM slot
                matched_pet = None
                if pets:
                    if target_pet_id:
                        matched_pet = next((p for p in pets if p.get("id") == target_pet_id), None)
                    if not matched_pet and target_slot:
                        matched_pet = next((p for p in pets if p.get("idx") == target_slot), None)
                    if not matched_pet and target_slot:
                        matched_pet = next((p for p in pets if p.get("slot") == target_slot), None)

                if matched_pet:
                    target_pet_id = matched_pet.get("id")
                    target_slot_num = matched_pet.get("slot")
                elif not target_pet_id and pets:
                    target_pet_id = pets[0].get("id")
                    target_slot_num = pets[0].get("slot")
                else:
                    target_slot_num = target_slot

                if not target_pet_id:
                    self.log("WARN", nick, "Không tìm thấy Pet nào trong danh sách để xuất chiến lại!")
                    return

                cur_active_pet = next((p for p in pets if p.get("slot") == active_slot), None) if active_slot > 0 else None

                # Nếu không force và pet đang xuất chiến bình thường
                if not force and active_slot > 0 and cur_active_pet:
                    self.designated_pets[proc] = cur_active_pet.get("id")
                    self.pet_needs_resummon[proc] = False
                    self.log("🐾 PET OK", nick, f"Pet đang xuất chiến bình thường: Slot {active_slot} (ID: 0x{cur_active_pet['id']:04X}) | HP: {cur_active_pet['curHp']}/{cur_active_pet['maxHp']}")
                    return

                # Nếu force và đã đúng pet
                if force and cur_active_pet and cur_active_pet.get("id") == target_pet_id:
                    hp_str = f" | HP: {cur_active_pet['curHp']}/{cur_active_pet['maxHp']}"
                    self.log("🐾 PET OK", nick, f"Pet đang ở đúng vị trí (ID: 0x{target_pet_id:04X}{hp_str})")
                    return

                slot_desc = f"Slot {target_slot} (RAM Slot {target_slot_num})" if target_slot else "chỉ định"
                self.log("🐾 CALL PET", nick, f"Phát hiện Pet đang ở trạng thái NGHỈ NGƠI hoặc khác Pet mục tiêu (activeSlot={active_slot}) -> Gửi lệnh Xuất chiến Pet {slot_desc} (ID: 0x{target_pet_id:04X})...")

                # Gói tin C->S Op: 0x13 Sub: 0x01 [Pet ID 4 bytes LE]
                pkt = pack_wlo_packet(bytes([0x13, 0x01]) + struct.pack("<I", target_pet_id))
                script.exports_sync.sendraw(pkt.hex())
                time.sleep(0.4)

                # Quét lại RAM xác thực xuất chiến thành công
                info_after = script.exports_sync.readpetinfo()
                if info_after and info_after.get("success"):
                    active_after = info_after.get("activeSlot", 0)
                    if active_after > 0:
                        self.pet_needs_resummon[proc] = False
                        self.designated_pets[proc] = target_pet_id
                        p_found = next((p for p in info_after.get("pets", []) if p.get("slot") == active_after), None)
                        hp_str = f" | HP: {p_found['curHp']}/{p_found['maxHp']}" if p_found else ""
                        self.log("SUCCESS", nick, f"✨ [XUẤT CHIẾN THÀNH CÔNG] Đã gọi Pet trở lại đội hình chiến đấu (Slot {active_after}{hp_str})! Sẵn sàng cho tầng tiếp theo.")
                    else:
                        self.log("WARN", nick, "Chưa thấy Pet xuất chiến lại (activeSlot vẫn = 0), có thể cần kiểm tra trạng thái pet trong game.")

            except Exception as e:
                self.log("ERROR", nick, f"Lỗi khi tự động xuất chiến Pet: {e}")

    def sweep_client(self, proc: str, nick: str, reason: str = ""):
        """Quét RAM và dọn sạch toàn bộ 9 loại rác nếu còn sót trong túi đồ"""
        with self.locks[proc]:
            script = self.scripts.get(proc)
            if not script:
                return

            try:
                bag_res = script.exports_sync.readbag()
                if not bag_res or not bag_res.get("success"):
                    return

                items = bag_res.get("items", {})
                trash_found = []
                for s_str, it in items.items():
                    code = it.get("code")
                    if code in ALL_TRASH_REWARDS:
                        trash_found.append((int(s_str), code, it.get("qty", 1), ALL_TRASH_REWARDS[code]))

                if not trash_found:
                    return

                self.log("SWEEP", nick, f"[{reason}] Phát hiện {len(trash_found)} ô rác tồn dư -> Bắt đầu dọn sạch:")
                for slot_num, code, qty, info in trash_found:
                    self.log("SWEEP", nick, f"  • Vứt Ô {slot_num:02d}: {info['name']} (x{qty}) [{info['round']}]")
                    pkt_req = pack_wlo_packet(bytes([0x17, 0x03, slot_num, qty, 0x01]))
                    script.exports_sync.sendraw(pkt_req.hex())
                    time.sleep(0.12)
                    pkt_cfm = pack_wlo_packet(bytes([0x17, 0x7C, slot_num, qty, 0x02]))
                    script.exports_sync.sendraw(pkt_cfm.hex())
                    time.sleep(0.15)

                self.log("SUCCESS", nick, f"✨ [{reason}] Đã giải phóng toàn bộ {len(trash_found)} ô rác thành công!")

            except Exception as e:
                self.log("ERROR", nick, f"Lỗi khi quét dọn túi đồ: {e}")

    def run_forever(self):
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] Đang dừng service tự động vứt rác...")
            for s in self.sessions.values():
                try:
                    s.detach()
                except Exception:
                    pass
            print("[✔] Đã đóng an toàn toàn bộ kết nối.")


def main():
    cleaner = RealtimeTrashCleaner()
    if cleaner.attach_all():
        cleaner.run_forever()


if __name__ == "__main__":
    main()
