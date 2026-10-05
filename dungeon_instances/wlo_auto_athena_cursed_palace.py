#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO AUTO ATHENA TO CURSED PALACE
================================
Tự động hóa toàn bộ lộ trình:
1. Sử dụng item MiniDragonfly ở ô Slot 5 bay sang Thành phố Athena.
2. Đi bộ qua 14 điểm tọa độ xuyên qua Athena ra cổng dịch chuyển.
3. Bước qua cổng hành lang chuyển tiếp.
4. Di chuyển tới NPC Lính canh trước cổng Cursed Palace.
5. Đối thoại với NPC Lính canh, giao nộp 2 vé RegisVoucher (trừ tại ô Slot 9).
6. Bước qua cổng vào trong Cursed Palace và tiến vào vị trí chiến đấu.

Toàn bộ thời gian nghỉ và thứ tự gói tin được mô phỏng chính xác 100%
theo dữ liệu thực nghiệm vừa bắt được từ alogin-F02.
"""

import os
import sys
import time
import struct

# Đảm bảo UTF-8 trên Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    print("[!] Chưa cài đặt thư viện frida. Vui lòng chạy: pip install frida")
    sys.exit(1)

FRIDA_JS = """
var activeSocket = -1;
var isInjected = false;

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
    isInjected = true;
    try {
        var ret = sendFunc(activeSocket, buf, raw.length, 0);
        isInjected = false;
        return {success: true, ret: ret, sock: activeSocket};
    } catch(e) {
        isInjected = false;
        return {success: false, error: e.toString()};
    }
}

function readBagMemory() {
    var ranges = Process.enumerateRanges('rw-');
    var bestItems = {};
    var maxCount = 0;
    var sigs = [
        {sig: '01 1c 86', off: 0},
        {sig: '02 ac 75', off: 4},
        {sig: '05 1c 86', off: 16},
        {sig: '09 ac 75', off: 32}
    ];
    for (var i = 0; i < ranges.length; i++) {
        var r = ranges[i];
        if (r.size > 10 * 1024 * 1024) continue;
        try {
            var candidates = [];
            for (var si = 0; si < sigs.length; si++) {
                var sDef = sigs[si];
                var m = Memory.scanSync(r.base, r.size, sDef.sig);
                for (var j = 0; j < m.length; j++) {
                    candidates.push(m[j].address.sub(sDef.off));
                }
            }
            for (var k = 0; k < candidates.length; k++) {
                var base = candidates[k];
                var items = {};
                for (var s = 1; s <= 50; s++) {
                    var entry = base.add((s - 1) * 4);
                    var slot = entry.readU8();
                    var code = entry.add(1).readU16();
                    var qty = entry.add(3).readU8();
                    if (slot === s && code > 0 && qty > 0) items[s] = {code: code, qty: qty};
                }
                var cnt = Object.keys(items).length;
                if (cnt > maxCount) {
                    maxCount = cnt;
                    bestItems = items;
                }
            }
        } catch(e) {}
    }
    if (maxCount > 0) return {success: true, items: bestItems};
    return {success: false, items: {}};
}

rpc.exports = {
    getsocket: function() { return scanActiveSocket(); },
    sendraw: function(hex) { return doSendRaw(hex); },
    readbag: function() { return readBagMemory(); }
};
"""

def pack_wlo_packet(body_bytes):
    """Đóng gói Magic Header 0xF4 0x44, uint16 LE Length và XOR 0xAD."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain = header + body_bytes
    return bytes(b ^ 0xAD for b in plain)

# ==============================================================================
# DANH SÁCH BƯỚC THAO TÁC KHỚP CHÍNH XÁC VỚI THỰC NGHIỆM
# ==============================================================================
ROUTE_STEPS = [
    # GIAI ĐOẠN 1: DÙNG MINIDRAGONFLY TẠI SLOT 1 & BAY SANG ATHENA
    {
        "phase": "PHASE 1: DÙNG MINIDRAGONFLY BAY SANG ATHENA",
        "desc": "Kích hoạt MiniDragonfly tại Ô Slot 1 (Menu GPS)",
        "packet": bytes.fromhex("17591f0102"),
        "delay": 1.10
    },
    {
        "desc": "Chọn điểm đến Thành phố Athena (0x0A)",
        "packet": bytes.fromhex("20020a"),
        "delay": 1.26
    },
    {
        "desc": "Đóng hộp thoại bay / Xác nhận nạp cảnh Athena",
        "packet": bytes.fromhex("2003"),
        "delay": 2.50
    },

    # GIAI ĐOẠN 2: ĐI BỘ QUA 14 TỌA ĐỘ TRONG THÀNH PHỐ ATHENA
    {
        "phase": "PHASE 2: DI CHUYỂN QUA THÀNH PHỐ ATHENA (14 TỌA ĐỘ)",
        "desc": "Bước 1: Đi tới tọa độ (1082, 2355)",
        "packet": bytes.fromhex("0601003a043309affb"),
        "delay": 1.32
    },
    {
        "desc": "Bước 2: Đi tới tọa độ (1002, 2135)",
        "packet": bytes.fromhex("060100ea035708afe1"),
        "delay": 2.34
    },
    {
        "desc": "Bước 3: Đi tới tọa độ (642, 2035)",
        "packet": bytes.fromhex("0601018202f307afd6"),
        "delay": 1.35
    },
    {
        "desc": "Bước 4: Đi tới tọa độ (522, 1975)",
        "packet": bytes.fromhex("0601010a02b707aff1"),
        "delay": 1.20
    },
    {
        "desc": "Bước 5: Đi tới tọa độ (442, 1775)",
        "packet": bytes.fromhex("060107ba01ef06aff1"),
        "delay": 1.14
    },
    {
        "desc": "Bước 6: Đi tới tọa độ (482, 1695)",
        "packet": bytes.fromhex("060107e2019f06afcc"),
        "delay": 1.35
    },
    {
        "desc": "Bước 7: Đi tới tọa độ (662, 1575)",
        "packet": bytes.fromhex("06010796022706afd8"),
        "delay": 1.20
    },
    {
        "desc": "Bước 8: Đi tới tọa độ (562, 1415)",
        "packet": bytes.fromhex("06010032028705affa"),
        "delay": 1.11
    },
    {
        "desc": "Bước 9: Đi tới tọa độ (402, 1275)",
        "packet": bytes.fromhex("0601019201fb04afd3"),
        "delay": 0.81
    },
    {
        "desc": "Bước 10: Đi tới tọa độ (482, 1155)",
        "packet": bytes.fromhex("060100e2018304afd7"),
        "delay": 1.47
    },
    {
        "desc": "Bước 11: Đi tới tọa độ (422, 915)",
        "packet": bytes.fromhex("060100a6019303afff"),
        "delay": 1.20
    },
    {
        "desc": "Bước 12: Đi tới tọa độ (322, 735)",
        "packet": bytes.fromhex("0601004201df02afd4"),
        "delay": 1.23
    },
    {
        "desc": "Bước 13: Đi tới tọa độ (322, 575)",
        "packet": bytes.fromhex("06010042013f02afd0"),
        "delay": 2.31
    },
    {
        "desc": "Bước 14: Đi tới sát cổng ra Athena (282, 455)",
        "packet": bytes.fromhex("0601001a01c701aff0"),
        "delay": 0.72
    },

    # GIAI ĐOẠN 3: BƯỚC QUA CỔNG DỊCH CHUYỂN RA HÀNH LANG
    {
        "phase": "PHASE 3: BƯỚC QUA CỔNG DỊCH CHUYỂN RA HÀNH LANG",
        "desc": "Đồng bộ trạng thái trước cổng",
        "packet": bytes.fromhex("14080e00"),
        "delay": 0.24
    },
    {
        "desc": "Bước vào cổng dịch chuyển tại (282, 463)",
        "packet": bytes.fromhex("0602091a01cf01afcb"),
        "delay": 0.12
    },
    {
        "desc": "Xác nhận đối thoại chuyển map (0x09)",
        "packet": bytes.fromhex("200209"),
        "delay": 2.00
    },

    # GIAI ĐOẠN 4: VƯỢT QUA NPC CHẮN ĐƯỜNG HÀNH LANG (ĐÁNH & BỎ CHẠY)
    {
        "phase": "PHASE 4: VƯỢT QUA NPC CHẮN ĐƯỜNG HÀNH LANG (ĐÁNH & BỎ CHẠY)",
        "desc": "Khiêu chiến NPC lính gác chắn đường hành lang (0x0B Sub: 0x02)",
        "packet": bytes.fromhex("0b0203ff3b00000100"),
        "delay": 1.50
    },
    {
        "desc": "Lệnh Bỏ Chạy cho Pet trong trận đấu (Slot 4 Row 2)",
        "packet": bytes.fromhex("32010402040289ea44c000"),
        "delay": 0.80
    },
    {
        "desc": "Lệnh Bỏ Chạy cho Nhân vật trong trận đấu (Slot 3 Row 2)",
        "packet": bytes.fromhex("32010302030289ea689600"),
        "delay": 1.30
    },

    # GIAI ĐOẠN 5: DI CHUYỂN TỚI TRƯỚC CỔNG CURSED PALACE & ĐỐI THOẠI LÍNH CANH
    {
        "phase": "PHASE 5: DI CHUYỂN TỚI TRƯỚC CỔNG CURSED PALACE & ĐỐI THOẠI LÍNH CANH",
        "desc": "Đi bộ trong hành lang thẳng tới trước cổng Cursed Palace (302, 455)",
        "packet": bytes.fromhex("0601022e01c701aff8"),
        "delay": 2.50
    },
    {
        "desc": "Kích hoạt đối thoại Lính canh tại cổng (Lượt 1)",
        "packet": bytes.fromhex("14020100"),
        "delay": 0.40
    },
    {
        "desc": "Xác nhận xem nội dung đối thoại Lính canh",
        "packet": bytes.fromhex("1406"),
        "delay": 0.20
    },
    {
        "desc": "Chuyển sang trang thoại kế tiếp (0x0C)",
        "packet": bytes.fromhex("20020c"),
        "delay": 1.25
    },
    {
        "desc": "Đồng bộ dữ liệu thoại",
        "packet": bytes.fromhex("14091e"),
        "delay": 0.12
    },
    {
        "desc": "Tiếp tục xem thoại",
        "packet": bytes.fromhex("1406"),
        "delay": 0.20
    },
    {
        "desc": "Chọn Dòng 1 trong Menu: Đồng ý vào Cursed Palace (0x0D)",
        "packet": bytes.fromhex("20020d"),
        "delay": 0.70
    },
    {
        "desc": "Đồng bộ dữ liệu thoại",
        "packet": bytes.fromhex("14091e"),
        "delay": 0.12
    },
    {
        "desc": "Tiếp tục xem thoại",
        "packet": bytes.fromhex("1406"),
        "delay": 0.20
    },
    {
        "desc": "Xác nhận đồng ý điều kiện 2 vé RegisVoucher (0x0D)",
        "packet": bytes.fromhex("20020d"),
        "delay": 0.90
    },
    {
        "desc": "Tiếp tục xem thoại xác nhận",
        "packet": bytes.fromhex("1406"),
        "delay": 0.20
    },
    {
        "desc": "Xác nhận thanh toán trừ 2 vé RegisVoucher (0x0D)",
        "packet": bytes.fromhex("20020d"),
        "delay": 0.85
    },
    {
        "desc": "Đóng xác nhận thanh toán vé",
        "packet": bytes.fromhex("1406"),
        "delay": 0.35
    },

    # GIAI ĐOẠN 6: BƯỚC VÀO TRONG ĐIỆN CURSED PALACE (DỊCH CHUYỂN TOÀN ĐỘI)
    {
        "phase": "PHASE 6: BƯỚC VÀO TRONG ĐIỆN CURSED PALACE (DỊCH CHUYỂN TOÀN ĐỘI)",
        "desc": "Kích hoạt dịch chuyển vào Cursed Palace (Toàn đội theo Leader)",
        "packet": bytes.fromhex("14080e00"),
        "delay": 1.50
    },
    {
        "desc": "Hoàn tất nạp cảnh mới",
        "packet": bytes.fromhex("200200"),
        "delay": 0.20
    },
    {
        "desc": "Đóng giao diện đối thoại",
        "packet": bytes.fromhex("20020a"),
        "delay": 0.20
    },
    {
        "desc": "Cập nhật lại chỉ số & UI nhân vật trong điện - HOÀN TẤT!",
        "packet": bytes.fromhex("1736"),
        "delay": 0.50
    }
]

def find_target_process():
    dev = frida.get_local_device()
    for p in dev.enumerate_processes():
        plow = p.name.lower()
        if "w04" in plow or "w03" in plow or "f02" in plow:
            return p
    for p in dev.enumerate_processes():
        if "alogin" in p.name.lower():
            return p
    return None

def main():
    print("=" * 80)
    print("      WLO AUTO ATHENA -> CURSED PALACE (MINIDRAGONFLY & WAYPOINTS)")
    print("================================================================================")
    print("[*] Đang tìm kiếm tiến trình game alogin-F02...")

    proc = find_target_process()
    if not proc:
        print("[!] Không tìm thấy tiến trình alogin-F02 nào đang chạy!")
        sys.exit(1)

    print(f"[+] Tìm thấy tiến trình: {proc.name} (PID: {proc.pid})")
    print(f"[*] Đang đính kèm Frida & Quét Socket mạng kết nối port 6414...")

    dev = frida.get_local_device()
    session = dev.attach(proc.pid)

    voucher_deducted = 0
    in_cursed_palace = False
    npc_dialog_received = False

    def on_message(msg, data):
        nonlocal voucher_deducted, in_cursed_palace, npc_dialog_received
        if not data:
            return
        # Giải mã XOR 0xAD
        dec = bytes(b ^ 0xAD for b in data)

        # Bắt gói thoại NPC: Op: 0x14 Sub: 0x01 hoặc Op: 0x18 Sub: 0x05
        if b'\x14\x01' in dec or b'\x18\x05' in dec:
            npc_dialog_received = True
            print(f"\n  💬 [SERVER] ĐÃ NHẬN GÓI THOẠI NPC TỪ MÁY CHỦ! (Op: 0x14 Sub: 0x01 / 0x18 Sub: 0x05)\n", flush=True)

        # Bắt gói trừ item vé: Op: 0x17 Sub: 0x09 [slot, 02, ff, ff]
        idx = dec.find(b'\x17\x09')
        if idx != -1 and len(dec) >= idx + 4:
            slot_dec = dec[idx + 2]
            qty_dec = dec[idx + 3]
            if qty_dec == 2:
                voucher_deducted += 2
                print(f"\n  ★ [SERVER] ĐÃ XÁC NHẬN TRỪ 2 VÉ REGISVOUCHER TẠI Ô SLOT {slot_dec} THÀNH CÔNG! ★\n", flush=True)

        # Bắt thoát trận đánh thành công: Op: 0x0B Sub: 0x00
        if b'\x0b\x00' in dec:
            print(f"\n  ⚔️ [SERVER] ĐÃ BỎ CHẠY & THOÁT KHỎI TRẬN ĐÁNH THÀNH CÔNG! Vượt qua NPC chắn đường.\n", flush=True)

        # Bắt nạp map Cursed Palace
        if b'\x16\x04\x01\x00' in dec:
            in_cursed_palace = True

    script = session.create_script(FRIDA_JS)
    script.on("message", on_message)
    script.load()

    sock = script.exports_sync.getsocket()
    if sock <= 0:
        print("[!] Không tìm thấy socket active. Vui lòng đảm bảo nhân vật đã đăng nhập vào game!")
        session.detach()
        sys.exit(1)

    print(f"[+] Hook thành công! Socket active: #{sock} (Port 6414)")
    print("=" * 80)
    print("  ★ LỰA CHỌN CHẾ ĐỘ THỰC HIỆN:")
    print("    [1] Lộ trình đầy đủ: Dùng MiniDragonfly (Slot 1) bay Athena -> Đi Cursed Palace")
    print("    [2] Đã ở Athena: Bỏ qua dùng item bay, chỉ chạy bộ tới NPC Lính canh & vào điện")
    print("=" * 80)

    try:
        user_choice = input("\n>>> Nhập lựa chọn [1 hoặc 2, mặc định 1]: ").strip()
    except KeyboardInterrupt:
        print("\n[*] Đã hủy thao tác.")
        session.detach()
        sys.exit(0)

    already_at_athena = (user_choice == "2")
    if already_at_athena:
        steps_to_run = [s for s in ROUTE_STEPS if "PHASE 1" not in s.get("phase", "")]
        print("\n[+] ĐÃ CHỌN: ĐÃ Ở ATHENA -> Bỏ qua dùng item bay, bắt đầu đi bộ tới NPC!", flush=True)
    else:
        steps_to_run = ROUTE_STEPS
        print("\n[+] ĐÃ CHỌN: LỘ TRÌNH ĐẦY ĐỦ (Dùng MiniDragonfly bay Athena)!", flush=True)

    try:
        input("\n>>> Nhấn ENTER để BẮT ĐẦU chạy (hoặc Ctrl+C để hủy)... ")
    except KeyboardInterrupt:
        print("\n[*] Đã hủy thao tác.")
        session.detach()
        sys.exit(0)

    total_steps = len(steps_to_run)
    start_time = time.time()
    curr_phase = ""

    for idx, step in enumerate(steps_to_run, 1):
        if "phase" in step and step["phase"] != curr_phase:
            curr_phase = step["phase"]
            print(f"\n{'='*75}\n  {curr_phase}\n{'='*75}", flush=True)

        desc = step["desc"]
        raw_body = step["packet"]
        delay = step["delay"]

        if "Kích hoạt MiniDragonfly" in desc:
            try:
                bag_res = script.exports_sync.readbag()
                if bag_res and bag_res.get("success"):
                    inv = bag_res.get("items", {})
                    fly_slots = [int(s) for s, it in inv.items() if it.get("code") == 0x861C]
                    if fly_slots:
                        fly_slot = fly_slots[0]
                        raw_body = bytes([0x17, 0x59, 0x1F, fly_slot, 0x02])
                        print(f"  [RAM] Tự động phát hiện MiniDragonfly tại Ô Slot {fly_slot}. Packet: {raw_body.hex()}", flush=True)
            except Exception as e:
                pass

        if "Kích hoạt đối thoại Lính canh" in desc or "Tương tác với NPC Lính canh" in desc:
            npc_dialog_received = False

        enc_pkt = pack_wlo_packet(raw_body)
        res = script.exports_sync.sendraw(enc_pkt.hex())

        print(f"  [{idx:02d}/{total_steps:02d}] {desc:<58} (Nghỉ {delay:4.2f}s) | Res: {res.get('success', False)}", flush=True)

        if "Đóng hộp thoại bay" in desc:
            print("  [*] Đang đợi 2.5 giây cho bản đồ Athena nạp hoàn tất trước khi bước đi...", flush=True)

        # ĐIỀU KIỆN KIỂM TRA PHẢN HỒI TỪ SERVER KHI NÓI CHUYỆN NPC LÍNH CANH
        if "Lượt 1" in desc:
            print("  [*] Đang kiểm tra phản hồi từ Server để xác nhận đã đến đúng NPC Lính canh...", flush=True)
            wait_t = time.time()
            while time.time() - wait_t < 3.5:
                if npc_dialog_received:
                    break
                time.sleep(0.05)

            if not npc_dialog_received:
                print("\n" + "!" * 80)
                print("  ❌ LỖI: SERVER KHÔNG PHẢN HỒI ĐỐI THOẠI NPC LÍNH CANH!")
                print("  -> Nhân vật chưa di chuyển đến đúng vị trí (có thể bị kẹt hoặc trượt tọa độ).")
                print("  -> TỰ ĐỘNG DỪNG LỘ TRÌNH ĐỂ BẢO VỆ AN TOÀN!")
                print("!" * 80 + "\n")
                session.detach()
                sys.exit(1)
            else:
                print("  [+] ✔ XÁC NHẬN: Server ĐÃ PHẢN HỒI thoại NPC! Đã di chuyển chính xác đến trước cổng Cursed Palace.", flush=True)

        time.sleep(delay)

    total_elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"  ★ ĐÃ HOÀN TẤT TOÀN BỘ LỘ TRÌNH ĐẾN CURSED PALACE!")
    print(f"  • Tổng thời gian thực hiện : {total_elapsed:4.1f} giây")
    print(f"  • Vé RegisVoucher đã trừ    : {voucher_deducted} vé")
    print("=" * 80)

    session.detach()

if __name__ == "__main__":
    main()
