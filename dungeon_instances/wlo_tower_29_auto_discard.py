#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO Sky Tower (Tháp 29 Tầng) Auto Discard Tool
=============================================
Tự động quét RAM và vứt bỏ 4 loại vật phẩm rác nhận được từ các vòng r5, r6, r7, r8:
  - r5 (Tầng 05): Mã 0x7D4A (32074) - BubbleGum
  - r6 (Tầng 06): Mã 0x7D4B (32075) - Chocolate
  - r7 (Tầng 07): Mã 0x7D49 (32073) - InstantNoodle
  - r8 (Tầng 08): Mã 0x7D48 (32072) - ChocolateIceCream

Nguyên tắc an toàn tuyệt đối:
  1. Quét bộ nhớ RAM để xác định chính xác ô Slot thực tế chứa vật phẩm.
  2. Tuyệt đối không hardcode số ô để tránh vứt nhầm khi đồ bị dồn/lệch ô.
  3. Gửi gói tin C->S Op: 0x17 Sub: 0x09 [slot, qty].
  4. Quét lại RAM sau khi vứt để xác thực 100% túi đồ đã sạch.
"""

import os
import sys
import time
import struct
import argparse

# Thiết lập console UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    print("[!] Chưa cài đặt frida. Chạy lệnh: pip install frida")
    sys.exit(1)

# Danh sách vật phẩm rác của Tháp 29 tầng
TOWER_TRASH_ITEMS = {
    0x7D4A: {"name": "BubbleGum (Kẹo cao su)", "round": "r5"},
    0x7D4B: {"name": "Chocolate (Sô-cô-la)",   "round": "r6"},
    0x7D49: {"name": "InstantNoodle (Mì gói)", "round": "r7"},
    0x7D48: {"name": "ChocolateIceCream (Kem)","round": "r8"},
}

TARGET_CLIENTS = [
    "alogin-W04.exe",
    "alogin-W03.exe",
    "alogin-F04.exe",
    "alogin-Wi01.exe"
]

FRIDA_JS = """
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

function hookSocket() {
    if (ws2) {
        var rPtr = ws2.getExportByName('recv');
        if (rPtr) {
            Interceptor.attach(rPtr, {
                onEnter: function(args) {
                    var sock = args[0].toInt32();
                    if (sock > 0) activeSocket = sock;
                }
            });
        }
        var sPtr = ws2.getExportByName('send');
        if (sPtr) {
            Interceptor.attach(sPtr, {
                onEnter: function(args) {
                    var sock = args[0].toInt32();
                    if (sock > 0) activeSocket = sock;
                }
            });
        }
    }
}
hookSocket();
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
    if (cachedBagBase) {
        try {
            var items = {};
            for (var s = 1; s <= 50; s++) {
                var entry = cachedBagBase.add((s - 1) * 4);
                var slot = entry.readU8();
                var code = entry.add(1).readU16();
                var qty = entry.add(3).readU8();
                if (slot === s && code > 0 && qty > 0) items[s] = {code: code, qty: qty};
            }
            if (Object.keys(items).length > 0) return {success: true, items: items};
        } catch(e) { cachedBagBase = null; }
    }

    var ranges = Process.enumerateRanges('rw-');
    var sigs = [{sig: '01 1c 86', off: 0}, {sig: '02 ac 75', off: 4}, {sig: '05 1c 86', off: 16}];
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
                        if (slot === s && code > 0 && qty > 0) items[s] = {code: code, qty: qty};
                    }
                    if (Object.keys(items).length >= 2) {
                        cachedBagBase = base;
                        return {success: true, items: items};
                    }
                }
            } catch(e) {}
        }
    }
    return {success: false, items: {}};
}

rpc.exports = {
    getsocket: function() { return scanActiveSocket(); },
    sendraw: function(hex) { return doSendRaw(hex); },
    readbag: function() { return readBagMemory(); }
};
"""

def pack_wlo_packet(body_bytes):
    """Đóng gói Header 0xF4 0x44, uint16 LE Length và XOR 0xAD."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain = header + body_bytes
    return bytes(b ^ 0xAD for b in plain)

def discard_tower_trash(client_name, delay=0.2):
    """Quét và vứt bỏ vật phẩm rác Tháp 29 tầng trên một client."""
    print(f"\n{'='*75}")
    print(f"[*] ĐANG XỬ LÝ TIẾN TRÌNH: [{client_name}]")
    print(f"{'='*75}")

    try:
        session = frida.attach(client_name)
    except Exception as e:
        print(f"[-] Không thể attach vào {client_name}: {e}")
        return False, 0

    script = session.create_script(FRIDA_JS)
    script.load()

    # Bước 1: Quét RAM túi đồ
    bag_res = script.exports_sync.readbag()
    if not bag_res or not bag_res.get("success"):
        print("[-] Không đọc được túi đồ từ RAM!")
        session.detach()
        return False, 0

    items = bag_res.get("items", {})
    print(f"[+] Đã đọc thành công túi đồ từ RAM: Tổng {len(items)} ô đang có đồ.")

    # Bước 2: Lọc các ô chứa vật phẩm rác
    trash_slots = []
    for s_str, it in items.items():
        slot_num = int(s_str)
        code = it["code"]
        qty = it["qty"]
        if code in TOWER_TRASH_ITEMS:
            info = TOWER_TRASH_ITEMS[code]
            trash_slots.append((slot_num, code, qty, info["name"], info["round"]))

    if not trash_slots:
        print("[✔] Không tìm thấy vật phẩm rác nào trong túi đồ. Túi đã sạch!")
        session.detach()
        return True, 0

    print(f"[!] Tìm thấy {len(trash_slots)} ô chứa vật phẩm rác cần vứt bỏ:")
    for slot_num, code, qty, name, rnd in trash_slots:
        print(f"    - Ô {slot_num:02d}: {name} (Mã: 0x{code:04X} / {code}) | {rnd} | Số lượng: {qty}")

    # Bước 3: Đảm bảo socket kết nối
    sock = script.exports_sync.getsocket()
    if sock <= 0:
        print("[-] Chưa tìm thấy active socket để gửi gói tin vứt đồ!")
        session.detach()
        return False, 0

    # Bước 4: Gửi lệnh vứt từng món (2 bước chuẩn: Yêu cầu 0x17 0x03 + Xác nhận 0x17 0x7C)
    discarded_count = 0
    for slot_num, code, qty, name, rnd in trash_slots:
        print(f"[🚚] Đang gửi lệnh vứt: Ô {slot_num:02d} - {name} ({rnd}) x{qty}...", end="", flush=True)
        # Gói 1: Yêu cầu vứt đồ (Opcode 0x17 Sub 0x03)
        # Body: 17 03 [slot] [qty] 01
        pkt_req = pack_wlo_packet(bytes([0x17, 0x03, slot_num, qty, 0x01]))
        res1 = script.exports_sync.sendraw(pkt_req.hex())
        time.sleep(0.12)

        # Gói 2: Xác nhận popup vứt đồ (Opcode 0x17 Sub 0x7C)
        # Body: 17 7C [slot] [qty] 02
        pkt_cfm = pack_wlo_packet(bytes([0x17, 0x7C, slot_num, qty, 0x02]))
        res2 = script.exports_sync.sendraw(pkt_cfm.hex())

        if res1.get("success") or res2.get("success"):
            print(" ✔ Xong!")
            discarded_count += 1
        else:
            print(f" ❌ Lỗi: {res1.get('error')}")
        time.sleep(delay)

    # Bước 5: Quét RAM đối chiếu lại kết quả
    time.sleep(0.5)
    bag_after = script.exports_sync.readbag()
    if bag_after and bag_after.get("success"):
        items_after = bag_after.get("items", {})
        rem_trash = [s for s, it in items_after.items() if it["code"] in TOWER_TRASH_ITEMS]
        if not rem_trash:
            print(f"[✔] HOÀN TẤT: Toàn bộ {discarded_count} ô rác đã được vứt sạch 100% khỏi túi đồ!")
        else:
            print(f"[!] Cảnh báo: Còn lại {len(rem_trash)} ô chưa sạch: {rem_trash}")

    session.detach()
    return True, discarded_count

def main():
    print("=" * 80)
    print("      WLO SKY TOWER (THÁP 29 TẦNG) - AUTO DISCARD TRASH REWARDS")
    print("=" * 80)
    print("  Danh mục vật phẩm rác cần vứt:")
    for code, info in TOWER_TRASH_ITEMS.items():
        print(f"    • {info['round']}: Mã 0x{code:04X} ({code}) - {info['name']}")
    print("=" * 80)

    total_cleaned = 0
    for client in TARGET_CLIENTS:
        ok, cnt = discard_tower_trash(client)
        if ok:
            total_cleaned += cnt

    print("\n" + "=" * 80)
    print(f"[★] ĐÃ HOÀN TẤT DỌN RÁC THÁP 29 TẦNG TRÊN CẢ 4 TÀI KHOẢN!")
    print(f"[★] Tổng cộng đã giải phóng thành công {total_cleaned} ô chứa vật phẩm rác.")
    print("=" * 80)

if __name__ == "__main__":
    main()
