#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO CURSED PALACE AUTO DISCARD TRASH REWARDS
=============================================
Tự động quét bộ nhớ RAM, tìm chính xác vị trí ô (Slot) và số lượng của các
vật phẩm phần thưởng rác rơi ra từ các ải Cursed Palace, sau đó gửi gói tin vứt bỏ:

Danh sách vật phẩm rác cần vứt:
- Ải 4 & 5  : Mã 0x7DB0 (32176) - FuguHotPot
- Ải 6 & 7  : Mã 0x7E1D (32285) - Turkey
- Ải 8 & 9  : Mã 0x7DB1 (32177) - SoyPorkboneNoodle
- Ải 10     : Mã 0x7E34 (32308) - CurryRice
- Ải 11     : Mã 0x8514 (34068) - LovePicnicLunch

Cơ chế an toàn:
- Quét trực tiếp mảng 50 ô túi đồ từ RAM để lấy chính xác số Slot và số lượng thực tế.
- Tuyệt đối không hardcode ô slot (tránh trường hợp quà rơi vào ô cộng dồn hoặc ô lệch).
- Gửi lệnh vứt chuẩn WLO: Gói 1 (0x17 Sub 0x03) + Gói 2 (0x17 Sub 0x7C) xác nhận popup.
- Đọc lại RAM sau khi vứt để xác nhận đã sạch 100%.
"""

import os
import sys
import time
import struct
import argparse
import threading
from datetime import datetime

# UTF-8 Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    print("[!] Chưa cài đặt thư viện frida. Vui lòng chạy: pip install frida")
    sys.exit(1)

# Danh sách vật phẩm rác cần vứt theo ải
PALACE_TRASH_ITEMS = {
    0x7DB0: {"name": "FuguHotPot",          "dec": 32176, "stages": "Ải 4, 5"},
    0x7E1D: {"name": "Turkey",              "dec": 32285, "stages": "Ải 6, 7"},
    0x7DB1: {"name": "SoyPorkboneNoodle",   "dec": 32177, "stages": "Ải 8, 9"},
    0x7E34: {"name": "CurryRice",           "dec": 32308, "stages": "Ải 10"},
    0x8514: {"name": "LovePicnicLunch",     "dec": 34068, "stages": "Ải 11"},
}

TARGET_CLIENTS = [
    "alogin-W04.exe",
    "alogin-W03.exe",
    "alogin-F04.exe",
    "alogin-Wi01.exe",
]

FRIDA_JS = """
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
    return activeSocket;
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
                this.buf = args[1];
                this.sock = sock;
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
    if (activeSocket <= 0) return {success: false, error: "Chưa có socket active"};
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

var cachedBagBase = null;

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
            if (Object.keys(items).length >= 1) {
                return {success: true, cached: true, items: items};
            }
        } catch(e) {
            cachedBagBase = null;
        }
    }

    // Bộ quét RAM phổ quát thông minh: Loại bỏ 100% Tủ Đồ Lều và Snapshot cũ
    var ranges = Process.enumerateRanges('rw-');
    var sigs = ['32 00 00 00 00 01', '32 00 00 00 00 00 00 00 00'];
    var candidates = [];

    for (var si = 0; si < sigs.length; si++) {
        var sPattern = sigs[si];
        for (var i = 0; i < ranges.length; i++) {
            var r = ranges[i];
            if (r.size > 2 * 1024 * 1024) continue;
            try {
                var m = Memory.scanSync(r.base, r.size, sPattern);
                for (var j = 0; j < m.length; j++) {
                    var base = m[j].address.add(5);
                    var items = {};
                    var count50 = 0;
                    for (var s = 1; s <= 50; s++) {
                        var entry = base.add((s - 1) * 4);
                        var slot = entry.readU8();
                        var code = entry.add(1).readU16();
                        var qty = entry.add(3).readU8();
                        if (slot === s && code > 0 && qty > 0) {
                            items[s] = {code: code, qty: qty};
                            if (qty === 50) count50++;
                        }
                    }
                    var cnt = Object.keys(items).length;
                    if (cnt >= 2) {
                        // Loại bỏ Tủ Đồ Lều (Cabinet Storage): Tủ đồ hầu như 100% đều là stack 50 món
                        var ratio50 = count50 / cnt;
                        if (ratio50 < 0.70) {
                            candidates.push({
                                base: base,
                                count: cnt,
                                items: items
                            });
                        }
                    }
                }
            } catch(e) {}
        }
        if (candidates.length > 0) break;
    }

    if (candidates.length === 0) return {success: false, items: {}};

    // Sắp xếp các candidates hợp lệ:
    // 1. Ưu tiên buffer có số lượng món nhiều nhất (Active Buffer chứa toàn bộ item mới nhận)
    // 2. Nếu bằng nhau, ưu tiên buffer có số vé RegisVoucher (Slot 2) nhỏ hơn (đã bị trừ vé khi vào điện)
    candidates.sort(function(a, b) {
        if (b.count !== a.count) {
            return b.count - a.count;
        }
        var vA = (a.items[2] && a.items[2].code === 0x75AC) ? a.items[2].qty : 999;
        var vB = (b.items[2] && b.items[2].code === 0x75AC) ? b.items[2].qty : 999;
        if (vA !== vB) {
            return vA - vB;
        }
        return b.base.compare(a.base);
    });

    var best = candidates[0];
    cachedBagBase = best.base;
    return {success: true, cached: false, items: best.items};
}

rpc.exports = {
    getsocket: function() { return scanActiveSocket(); },
    sendraw: function(hex) { return doSendRaw(hex); },
    readbag: function(forceRescan) { return readBagMemory(forceRescan); }
};
"""

def pack_wlo_packet(body_bytes):
    """Đóng gói Magic Header 0xF4 0x44, uint16 LE Length và XOR 0xAD."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain = header + body_bytes
    return bytes(b ^ 0xAD for b in plain)

def discard_specific_items(script, client_name, target_codes=None, delay=0.2):
    """
    Quét RAM túi đồ của client, tìm tất cả ô chứa mã target_codes và gửi lệnh vứt bỏ.
    - target_codes: Danh sách mã cần vứt (nếu None thì lấy toàn bộ PALACE_TRASH_ITEMS).
    """
    if target_codes is None:
        target_codes = list(PALACE_TRASH_ITEMS.keys())

    # BƯỚC 1: QUÉT RAM TÚI ĐỒ
    bag_res = script.exports_sync.readbag()
    if not bag_res or not bag_res.get("success"):
        print(f"  [-] [{client_name}] Không đọc được túi đồ từ RAM!", flush=True)
        return 0

    items = bag_res.get("items", {})
    if not items:
        print(f"  [*] [{client_name}] Túi đồ đang trống hoặc chưa đồng bộ.", flush=True)
        return 0

    # BƯỚC 2: TÌM CÁC Ô CHỨA VẬT PHẨM MỤC TIÊU
    matches = []
    for slot_str, it in items.items():
        slot = int(slot_str)
        code = it.get("code", 0)
        qty = it.get("qty", 0)
        if code in target_codes and qty > 0:
            info = PALACE_TRASH_ITEMS.get(code, {"name": f"Item_0x{code:04X}", "stages": "Tùy chỉnh"})
            matches.append({
                "slot": slot,
                "code": code,
                "qty": qty,
                "name": info["name"],
                "stages": info["stages"]
            })

    if not matches:
        print(f"  [✔] [{client_name}] Không có vật phẩm rác nào cần vứt. Túi đồ đã sạch!", flush=True)
        return 0

    print(f"  [!] [{client_name}] Phát hiện {len(matches)} ô chứa phần thưởng rác Cursed Palace:", flush=True)
    for m in matches:
        print(f"      • Ô {m['slot']:02d}: {m['name']} (Mã: 0x{m['code']:04X}) - SL: {m['qty']} [{m['stages']}]", flush=True)

    # BƯỚC 3: GỬI GÓI LỆNH VỨT BỎ CHÍNH XÁC THEO TỪNG Ô
    discarded_count = 0
    for m in matches:
        slot = m["slot"]
        qty = m["qty"]
        code = m["code"]
        name = m["name"]

        # Gói 1: Yêu cầu vứt đồ (Opcode 0x17 Sub 0x03)
        # Body: 17 03 [slot] [qty] 01
        pkt_req = pack_wlo_packet(bytes([0x17, 0x03, slot, qty, 0x01]))
        res1 = script.exports_sync.sendraw(pkt_req.hex())

        time.sleep(0.12)

        # Gói 2: Xác nhận popup vứt đồ (Opcode 0x17 Sub 0x7C)
        # Body: 17 7C [slot] [qty] 02
        pkt_cfm = pack_wlo_packet(bytes([0x17, 0x7C, slot, qty, 0x02]))
        res2 = script.exports_sync.sendraw(pkt_cfm.hex())

        if res1.get("success") or res2.get("success"):
            print(f"  🗑️ [{client_name}] ĐÃ VỨT: {name} tại Ô {slot:02d} (SL: {qty}) | Res: OK", flush=True)
            discarded_count += 1
        else:
            print(f"  ❌ [{client_name}] Lỗi vứt {name} tại Ô {slot:02d}: {res1.get('error', '')}", flush=True)

        time.sleep(delay)

    # BƯỚC 4: ĐỌC LẠI RAM ĐỂ XÁC NHẬN SẠCH 100%
    time.sleep(0.5)
    bag_after = script.exports_sync.readbag()
    if bag_after and bag_after.get("success"):
        items_after = bag_after.get("items", {})
        remaining = [s for s, it in items_after.items() if it.get("code") in target_codes]
        if not remaining:
            print(f"  ✨ [{client_name}] XÁC NHẬN RAM: Toàn bộ {discarded_count} món rác đã được XÓA HOÀN TOÀN khỏi túi đồ!", flush=True)
        else:
            print(f"  ⚠️ [{client_name}] Vẫn còn lại các ô chưa xóa hết: {remaining}", flush=True)

    return discarded_count

def clean_all_clients(target_codes=None):
    """Quét và vứt toàn bộ vật phẩm rác Cursed Palace trên cả 4 client."""
    print("=" * 80)
    print("      QUY TRÌNH QUÉT RAM & VỨT PHẦN THƯỞNG RÁC CURSED PALACE")
    print("=" * 80)
    if target_codes:
        code_strs = [f"0x{c:04X} ({PALACE_TRASH_ITEMS[c]['name']})" for c in target_codes if c in PALACE_TRASH_ITEMS]
        print(f"  • Các mã yêu cầu vứt: {', '.join(code_strs)}")
    else:
        print("  • Tự động quét toàn bộ 5 mã rác của Ải 4 -> 11:")
        for code, info in PALACE_TRASH_ITEMS.items():
            print(f"    - {info['stages']:<10}: {info['name']:<20} (Mã: 0x{code:04X} / {info['dec']})")
    print("=" * 80 + "\n")

    total_discarded = 0
    for proc in TARGET_CLIENTS:
        nick = proc.replace("alogin-", "").replace(".exe", "")
        print(f"▶ BẮT ĐẦU XỬ LÝ TIẾN TRÌNH [{nick}] ({proc}):")
        try:
            session = frida.attach(proc)
            script = session.create_script(FRIDA_JS)
            script.load()

            cnt = discard_specific_items(script, nick, target_codes=target_codes)
            total_discarded += cnt

            session.detach()
        except Exception as e:
            print(f"  [-] Lỗi kết nối {proc}: {e}", flush=True)
        print()

    print("=" * 80)
    print(f"  ★ HOÀN TẤT! Đã vứt thành công tổng cộng {total_discarded} ô vật phẩm rác trên cả 4 tài khoản.")
    print("=" * 80)
    return total_discarded

def main():
    parser = argparse.ArgumentParser(description="WLO Cursed Palace Auto Discard Trash Rewards")
    parser.add_argument("--stage", type=int, choices=[4, 5, 6, 7, 8, 9, 10, 11],
                        help="Chỉ vứt phần thưởng của một ải cụ thể (4, 5, 6, 7, 8, 9, 10, 11)")
    parser.add_argument("--code", type=str,
                        help="Chỉ vứt mã hex cụ thể, ví dụ: 0x7DB0 hoặc 7DB0")
    args = parser.parse_args()

    target_codes = None
    if args.stage:
        stage_to_codes = {
            4: [0x7DB0],
            5: [0x7DB0],
            6: [0x7E1D],
            7: [0x7E1D],
            8: [0x7DB1],
            9: [0x7DB1],
            10: [0x7E34],
            11: [0x8514],
        }
        target_codes = stage_to_codes.get(args.stage)
        print(f"[*] Chế độ: Chỉ xử lý phần thưởng rác của ẢI {args.stage}!")
    elif args.code:
        hex_c = args.code.lower().replace("0x", "")
        target_codes = [int(hex_c, 16)]
        print(f"[*] Chế độ: Chỉ xử lý mã 0x{target_codes[0]:04X}!")

    clean_all_clients(target_codes)

if __name__ == "__main__":
    main()
