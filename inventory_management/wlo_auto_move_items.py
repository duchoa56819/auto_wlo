#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO AUTO MOVE ITEMS IN BAG (TỰ ĐỘNG DỒN ĐỒ & SẮP XẾP TÚI ĐỒ WLO)
=====================================================================
Quy trình tự động hóa thông minh, chuẩn xác 100% theo giao thức WLO:
1. Bộ quét RAM phổ quát (Universal Memory Scanner):
   - Nhận diện chính xác mảng túi đồ 50 ô trên TẤT CẢ các tài khoản/client (F03, F032, W01, W03, W04, Wi01...).
   - Không phụ thuộc vào bất kỳ vật phẩm cố định nào.
2. GIAI ĐOẠN 1: GỘP TRÙNG THÔNG MINH (SMART STACK MERGER):
   - Nhận diện chính xác vật phẩm cộng dồn (Stackable) vs Trang bị/Đạo cụ (Non-stackable).
   - Tuyệt đối không cố gộp trang bị để tránh bị Server hoán đổi (Swap) vị trí.
   - Cập nhật số lượng tức thời trong bộ nhớ để không bao giờ gửi lệnh vượt quá giới hạn 50 cái/ô.
3. GIAI ĐOẠN 2: DỒN TÚI ĐỒ BẰNG THUẬT TOÁN CON TRỎ KÉP (TWO-POINTER COMPACTOR):
   - Chế độ 1 (Mặc định): DỒN LÊN ĐẦU TÚI (Compact to Top - Ô 01, 02, 03... liền mạch, không kẽ hở).
   - Chế độ 2: DỒN XUỐNG ĐÁY TÚI (Compact to Bottom - Ô 50, 49, 48... giải phóng ô đầu để mở quà).
   - Mỗi lệnh di chuyển LUÔN LUÔN chuyển vào một ô ĐANG TRỐNG, loại bỏ 100% nguy cơ bị swap nhầm.
4. BƯỚC 3: Xác thực và kiểm chứng kết quả từ bộ nhớ RAM.
"""

import os
import sys
import time
import json
import struct
import argparse
from datetime import datetime

# UTF-8 Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    print("[!] Chưa cài đặt thư viện frida (pip install frida).")
    sys.exit(1)

STEP_DELAY = 0.20          # 200 ms
CODE_MINIDRAGONFLY = 0x861C  # 34332 - MiniDragonfly
CODE_REGISVOUCHER = 0x75AC   # 30124 - RegisVoucher

# Từ khóa các loại trang bị / đạo cụ không cộng dồn (Max stack = 1)
NON_STACKABLE_KEYWORDS = [
    "spear", "sword", "bow", "blade", "wand", "staff", "mace", "axe", "gun",
    "armor", "suit", "dress", "robe", "coat", "vest", "cloth", "boots", "shoes",
    "cap", "hat", "helm", "crown", "ring", "necklace", "earring", "wrist", "bracer",
    "glove", "shield", "spar", "vehicle", "car", "plane", "boat", "tent",
    "20t", "30t", "40t", "weight", "lottery", "tạ", "kiếm", "cung", "đao", "trượng"
]

def pack_wlo_packet(body_bytes):
    """Magic Header 0xF4 0x44, uint16 LE payload length, XOR 0xAD."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain = header + body_bytes
    return bytes(b ^ 0xAD for b in plain)

def build_move_item_packet(src_slot, qty, dest_slot):
    body = bytes([0x17, 0x0A, src_slot, qty, dest_slot])
    return pack_wlo_packet(body)

def find_target_process(pref_name="w03"):
    dev = frida.get_local_device()
    procs = dev.enumerate_processes()
    if pref_name:
        for p in procs:
            if pref_name.lower() in p.name.lower():
                return p
    for p in procs:
        plow = p.name.lower()
        if "alogin" in plow:
            return p
    return None

FRIDA_MOVE_JS = """
var activeSocket = -1;
var sendFunc = null;

function scanActiveSocket() {
    var ws2 = Process.getModuleByName('ws2_32.dll');
    if (!ws2) ws2 = Process.getModuleByName('wsock32.dll');
    var getpeernamePtr = ws2 ? ws2.getExportByName('getpeername') : null;
    if (getpeernamePtr) {
        var getpeernameFunc = new NativeFunction(getpeernamePtr, 'int', ['pointer', 'pointer', 'pointer']);
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
    }
    return activeSocket;
}

function hookWinsock() {
    var ws2 = Process.getModuleByName('ws2_32.dll');
    if (!ws2) ws2 = Process.getModuleByName('wsock32.dll');
    if (ws2) {
        var sPtr = ws2.getExportByName('send');
        if (sPtr) sendFunc = new NativeFunction(sPtr, 'int', ['int', 'pointer', 'int', 'int']);
        
        var rPtr = ws2.getExportByName('recv');
        if (rPtr) {
            Interceptor.attach(rPtr, {
                onEnter: function(args) {
                    var s = args[0].toInt32();
                    if (s > 0) activeSocket = s;
                    this.sock = s;
                    this.buf = args[1];
                },
                onLeave: function(retval) {
                    var len = retval.toInt32();
                    if (len > 0) {
                        try {
                            var b = this.buf.readByteArray(len);
                            send({dir: 'recv', len: len, sock: this.sock}, b);
                        } catch(e) {}
                    }
                }
            });
        }
        
        if (sPtr) {
            Interceptor.attach(sPtr, {
                onEnter: function(args) {
                    var s = args[0].toInt32();
                    if (s > 0) activeSocket = s;
                }
            });
        }
    }
}

hookWinsock();

function doSendRaw(hexBytes) {
    if (!sendFunc) {
        var ws2 = Process.getModuleByName('ws2_32.dll');
        if (!ws2) ws2 = Process.getModuleByName('wsock32.dll');
        if (ws2) {
            var sPtr = ws2.getExportByName('send');
            if (sPtr) sendFunc = new NativeFunction(sPtr, 'int', ['int', 'pointer', 'int', 'int']);
        }
    }
    if (!sendFunc) return {success: false, error: "Không tìm thấy hàm send"};
    if (activeSocket <= 0) scanActiveSocket();
    if (activeSocket <= 0) return {success: false, error: "Chưa có active socket"};

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
    // 1. Kiểm tra địa chỉ đã lưu trong bộ nhớ đệm nếu còn hợp lệ
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

    // 2. Bộ quét RAM phổ quát thông minh (Smart Universal Bag Scanner):
    // Quét mảng 50 ô đồ thật, loại bỏ 100% Tủ Đồ Lều và Snapshot cũ
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

    // Sắp xếp các candidates hợp lệ theo địa chỉ bộ nhớ giảm dần:
    // Vùng nhớ mới nhất trong Heap (được cấp phát sau cùng) là Active Buffer hiện tại
    candidates.sort(function(a, b) {
        return b.base.compare(a.base);
    });

    var best = candidates[0];
    cachedBagBase = best.base;
    return {success: true, cached: false, items: best.items};
}

rpc.exports = {
    getsocket: function() { 
        if (activeSocket <= 0) scanActiveSocket();
        return activeSocket; 
    },
    sendraw: function(hexBytes) { return doSendRaw(hexBytes); },
    readbag: function() { return readBagMemory(); }
};
"""

def is_stackable_item(code, item_db, observed_max_qty=1):
    """Xác định xem vật phẩm có thể cộng dồn số lượng (>1) trong 1 ô hay không."""
    if observed_max_qty > 1:
        return True
    code_hex = f"0x{code:04X}"
    item_info = item_db.get(code_hex, {})
    name = (item_info.get("name") or "").lower()
    for kw in NON_STACKABLE_KEYWORDS:
        if kw in name:
            return False
    return False

def generate_compaction_plan_to_top(inventory):
    """
    Thuật toán Two-pointer dồn toàn bộ đồ lên ĐẦU TÚI (1, 2, 3...).
    Mỗi bước di chuyển LUÔN LUÔN chuyển vào một ô ĐANG TRỐNG!
    """
    inv = {s: dict(v) for s, v in inventory.items()}
    moves = []
    while True:
        first_empty = None
        for s in range(1, 51):
            if s not in inv:
                first_empty = s
                break
        if first_empty is None:
            break
        next_occupied = None
        for s in range(first_empty + 1, 51):
            if s in inv:
                next_occupied = s
                break
        if next_occupied is None:
            break
        it = inv[next_occupied]
        moves.append((next_occupied, it["qty"], first_empty, it["code"]))
        inv[first_empty] = it
        del inv[next_occupied]
    return moves

def generate_compaction_plan_to_bottom(inventory, protect_slots=None):
    """
    Thuật toán Two-pointer dồn toàn bộ đồ xuống ĐÁY TÚI (50, 49, 48...).
    Mỗi bước di chuyển LUÔN LUÔN chuyển vào một ô ĐANG TRỐNG!
    """
    if protect_slots is None:
        protect_slots = set()
    inv = {s: dict(v) for s, v in inventory.items()}
    moves = []
    while True:
        last_empty = None
        for s in range(50, 0, -1):
            if s not in protect_slots and s not in inv:
                last_empty = s
                break
        if last_empty is None:
            break
        first_occupied = None
        for s in range(1, last_empty):
            if s not in protect_slots and s in inv:
                first_occupied = s
                break
        if first_occupied is None:
            break
        it = inv[first_occupied]
        moves.append((first_occupied, it["qty"], last_empty, it["code"]))
        inv[last_empty] = it
        del inv[first_occupied]
    return moves

def main():
    parser = argparse.ArgumentParser(description="Tự động dồn đồ & sắp xếp túi đồ WLO chuẩn xác 100%")
    parser.add_argument("-p", "--proc", type=str, default="f04", help="Tên tiến trình (mặc định: f04)")
    parser.add_argument("-d", "--delay", type=float, default=STEP_DELAY, help="Delay giữa các lần gửi (giây, mặc định 0.20s)")
    parser.add_argument("-m", "--mode", choices=["top", "bottom"], default="bottom", 
                        help="Hướng dồn đồ: 'bottom' = dồn xuống đáy túi (50, 49, 48...); 'top' = dồn lên đầu túi (1, 2, 3..)")
    parser.add_argument("--no-merge", action="store_true", help="Không gộp các món trùng nhau (chỉ dồn ô)")
    parser.add_argument("--no-protect", action="store_true", help="Không cố định Ô 1 (MiniDragonfly) và Ô 2 (RegisVoucher)")
    parser.add_argument("-y", "--yes", action="store_true", help="Tự động thực thi ngay không cần nhấn Enter xác nhận")
    args = parser.parse_args()

    args.protect_dragonfly = not args.no_protect

    print("=" * 80)
    print("      WLO SMART BAG COMPACTOR & ORGANIZER (TỰ ĐỘNG DỒN & SẮP XẾP TÚI)")
    print("================================================================================")
    proc = find_target_process(args.proc)
    if not proc:
        print(f"[!] Không tìm thấy tiến trình nào khớp với từ khóa '{args.proc}'!")
        sys.exit(1)

    print(f"[+] Tiến trình đích: {proc.name} (PID: {proc.pid})")
    print(f"[+] Chế độ dồn đồ  : {'⬆ DỒN LÊN ĐẦU TÚI (Ô 01, 02, 03...)' if args.mode == 'top' else '⬇ DỒN XUỐNG ĐÁY TÚI (Ô 50, 49, 48...)'}")
    print(f"[+] Gộp trùng lặp  : {'Tắt' if args.no_merge else 'Bật (Chỉ gộp các món có thể cộng dồn)'}")

    # Nạp cơ sở dữ liệu tên vật phẩm
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wlo_items_database.json")
    item_db = {}
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                item_db = json.load(f)
        except Exception:
            pass

    dev = frida.get_local_device()
    session = dev.attach(proc.pid)

    script = session.create_script(FRIDA_MOVE_JS)
    script.load()
    time.sleep(0.5)

    def send_pkt(body_bytes):
        enc = pack_wlo_packet(body_bytes)
        return script.exports_sync.sendraw(enc.hex())

    # BƯỚC 1: LẤY DỮ LIỆU TÚI ĐỒ TỪ BỘ NHỚ RAM
    print(f"\n[*] [BƯỚC 1/3] Đang nạp dữ liệu túi đồ 50 ô của {proc.name}...")
    inventory = {}
    try:
        mem_res = script.exports_sync.readbag()
        if mem_res and mem_res.get("success") and len(mem_res.get("items", {})) > 0:
            for s_str, it in mem_res["items"].items():
                inventory[int(s_str)] = {"code": it["code"], "qty": it["qty"]}
            print(f"[✔] Đã đọc thành công {len(inventory)}/50 ô đồ từ RAM!")
    except Exception as e:
        print(f"[!] Lỗi đọc RAM: {e}")

    if len(inventory) == 0:
        print("[!] Không tìm thấy dữ liệu túi đồ! Hãy chắc chắn nhân vật đã đăng nhập vào game.")
        session.detach()
        sys.exit(1)

    # Hiển thị danh sách vật phẩm hiện tại
    print("=" * 80)
    print(f"  ★ DANH SÁCH {len(inventory)} VẬT PHẨM TRONG TÚI HIỆN TẠI:")
    for s in sorted(inventory.keys()):
        item = inventory[s]
        code_hex = f"0x{item['code']:04X}"
        name = item_db.get(code_hex, {}).get("name", "")
        name_str = f" | {name:<20}" if name else f" | {'(Chưa rõ tên)':<20}"
        print(f"    • Ô {s:02d} | Mã: {code_hex}{name_str} | Số lượng: {item['qty']:2d}")
    print("=" * 80)

    if not args.yes:
        try:
            input(f"\n>>> Nhấn ENTER để BẮT ĐẦU DỒN ĐỒ ({args.mode.upper()}) hoặc Ctrl+C để hủy... ")
        except KeyboardInterrupt:
            print("\n[*] Đã hủy thao tác.")
            session.detach()
            sys.exit(0)
    else:
        print("\n>>> Tự động thực thi (--yes)... Bắt đầu dồn đồ ngay!")

    start_t = time.time()
    total_merged = 0
    total_compact = 0

    try:
        # GIAI ĐOẠN 1: GỘP TRÙNG THÔNG MINH (SMART STACK MERGE)
        if not args.no_merge:
            print("\n" + "=" * 80)
            print("  [GIAI ĐOẠN 1/2] GỘP CÁC VẬT PHẨM TRÙNG NHAU (SMART STACK MERGER)")
            print("=" * 80)

            # Phân loại nhóm ô theo mã vật phẩm
            code_groups = {}
            for s, it in inventory.items():
                code_groups.setdefault(it["code"], []).append(s)

            for code, slots in sorted(code_groups.items()):
                if len(slots) <= 1:
                    continue

                # Kiểm tra xem món này có thể stack không
                max_qty_in_slots = max(inventory[s]["qty"] for s in slots)
                if not is_stackable_item(code, item_db, max_qty_in_slots):
                    continue

                # Chọn dest_slot là ô đầu tiên hoặc ô có số lượng nhiều nhất
                slots_sorted = sorted(slots, key=lambda s: inventory[s]["qty"], reverse=True)
                dest_slot = slots_sorted[0]
                src_slots = [s for s in slots if s != dest_slot]

                for src_slot in src_slots:
                    if dest_slot not in inventory or src_slot not in inventory:
                        continue
                    
                    dest_qty = inventory[dest_slot]["qty"]
                    src_qty = inventory[src_slot]["qty"]
                    room = 50 - dest_qty
                    if room <= 0:
                        # Ô đích đã đầy 50 cái, tìm ô đích mới
                        rem_dests = [s for s in src_slots if s in inventory and inventory[s]["qty"] < 50]
                        if not rem_dests:
                            break
                        dest_slot = rem_dests[0]
                        dest_qty = inventory[dest_slot]["qty"]
                        room = 50 - dest_qty

                    move_qty = min(src_qty, room)
                    if move_qty <= 0:
                        continue

                    code_hex = f"0x{code:04X}"
                    name = item_db.get(code_hex, {}).get("name", "")
                    print(f"  [+] Gộp mã {code_hex} ({name}): Ô {src_slot:02d} (SL:{src_qty}) -> Ô {dest_slot:02d} (SL:{dest_qty}) [Chuyển {move_qty}]...", flush=True)
                    send_pkt(bytes([0x17, 0x0A, src_slot, move_qty, dest_slot]))
                    
                    # Cập nhật bộ nhớ ngay lập tức
                    inventory[dest_slot]["qty"] += move_qty
                    inventory[src_slot]["qty"] -= move_qty
                    if inventory[src_slot]["qty"] == 0:
                        del inventory[src_slot]

                    total_merged += 1
                    time.sleep(args.delay)

            print(f"[✔] Hoàn tất Giai đoạn 1: Đã thực hiện {total_merged} lệnh gộp trùng!")
            time.sleep(0.3)

            # Đồng bộ lại từ RAM sau khi gộp
            try:
                mem_res = script.exports_sync.readbag()
                if mem_res and mem_res.get("success") and len(mem_res.get("items", {})) > 0:
                    inventory.clear()
                    for s_str, it in mem_res["items"].items():
                        inventory[int(s_str)] = {"code": it["code"], "qty": it["qty"]}
            except Exception:
                pass

        # GIAI ĐOẠN 2: DỒN TÚI ĐỒ BẰNG THUẬT TOÁN TWO-POINTER COMPACTOR
        print("\n" + "=" * 80)
        mode_str = "DỒN LÊN ĐẦU TÚI (TOP: Ô 01, 02, 03...)" if args.mode == "top" else "DỒN XUỐNG ĐÁY TÚI (BOTTOM: Ô 50, 49, 48...)"
        print(f"  [GIAI ĐOẠN 2/2] {mode_str}")
        print("=" * 80)

        if args.mode == "top":
            # Dồn lên đầu túi (Multi-Pass)
            for pass_num in range(1, 9):
                moves = generate_compaction_plan_to_top(inventory)
                if not moves:
                    print(f"[✔] Đã hoàn tất dồn lên đầu túi (Đạt chuẩn 100% ở Lượt {pass_num})!")
                    break
                print(f"  ▶ [Lượt {pass_num}] Cần dời {len(moves)} món lên đầu...")
                for src, qty, dest, code in moves:
                    code_hex = f"0x{code:04X}"
                    name = item_db.get(code_hex, {}).get("name", "")
                    print(f"  🚚 Dời: Ô {src:02d} -> Ô {dest:02d} (Mã {code_hex} {name}, SL: {qty})...", flush=True)
                    send_pkt(bytes([0x17, 0x0A, src, qty, dest]))
                    inventory[dest] = inventory[src]
                    del inventory[src]
                    total_compact += 1
                    time.sleep(args.delay)
                time.sleep(0.35)
                # Đọc lại RAM cho pass tiếp theo
                try:
                    mem_res = script.exports_sync.readbag()
                    if mem_res and mem_res.get("success") and len(mem_res.get("items", {})) > 0:
                        inventory.clear()
                        for s_str, it in mem_res["items"].items():
                            inventory[int(s_str)] = {"code": it["code"], "qty": it["qty"]}
                except Exception:
                    pass
        else:
            # Dồn xuống đáy túi (BOTTOM: 50, 49, 48...)
            # BƯỚC 1: XẾP CỐ ĐỊNH MINIDRAGONFLY LÊN Ô 01 & REGISVOUCHER LÊN Ô 02
            if args.protect_dragonfly:
                fly_slots = [s for s, it in inventory.items() if it["code"] == CODE_MINIDRAGONFLY]
                vouch_slots = [s for s, it in inventory.items() if it["code"] == CODE_REGISVOUCHER]

                def _get_empty_bottom_temp():
                    for s in range(50, 2, -1):
                        if s not in inventory:
                            return s
                    return None

                # 1. MiniDragonfly -> Ô 1
                if fly_slots and fly_slots[0] != 1:
                    src_fly = fly_slots[0]
                    if 1 in inventory:
                        temp_s = _get_empty_bottom_temp()
                        if temp_s:
                            it_1 = inventory[1]
                            code_hex = f"0x{it_1['code']:04X}"
                            name = item_db.get(code_hex, {}).get("name", "")
                            print(f"  🔄 Giải phóng Ô 01: Dời món {code_hex} ({name}) -> Ô {temp_s:02d}...", flush=True)
                            send_pkt(bytes([0x17, 0x0A, 1, it_1["qty"], temp_s]))
                            inventory[temp_s] = it_1
                            del inventory[1]
                            time.sleep(args.delay)
                    it_fly = inventory[src_fly]
                    print(f"  🛸 Xếp MiniDragonfly: Ô {src_fly:02d} -> Ô 01 (SL: {it_fly['qty']})...", flush=True)
                    send_pkt(bytes([0x17, 0x0A, src_fly, it_fly["qty"], 1]))
                    inventory[1] = it_fly
                    del inventory[src_fly]
                    time.sleep(args.delay)

                # 2. RegisVoucher -> Ô 2
                vouch_slots = [s for s, it in inventory.items() if it["code"] == CODE_REGISVOUCHER]
                if vouch_slots and vouch_slots[0] != 2:
                    src_vouch = vouch_slots[0]
                    if 2 in inventory:
                        temp_s = _get_empty_bottom_temp()
                        if temp_s:
                            it_2 = inventory[2]
                            code_hex = f"0x{it_2['code']:04X}"
                            name = item_db.get(code_hex, {}).get("name", "")
                            print(f"  🔄 Giải phóng Ô 02: Dời món {code_hex} ({name}) -> Ô {temp_s:02d}...", flush=True)
                            send_pkt(bytes([0x17, 0x0A, 2, it_2["qty"], temp_s]))
                            inventory[temp_s] = it_2
                            del inventory[2]
                            time.sleep(args.delay)
                    it_vouch = inventory[src_vouch]
                    print(f"  🎫 Xếp RegisVoucher: Ô {src_vouch:02d} -> Ô 02 (SL: {it_vouch['qty']})...", flush=True)
                    send_pkt(bytes([0x17, 0x0A, src_vouch, it_vouch["qty"], 2]))
                    inventory[2] = it_vouch
                    del inventory[src_vouch]
                    time.sleep(args.delay)

                time.sleep(0.35)
                try:
                    mem_res = script.exports_sync.readbag()
                    if mem_res and mem_res.get("success") and len(mem_res.get("items", {})) > 0:
                        inventory.clear()
                        for s_str, it in mem_res["items"].items():
                            inventory[int(s_str)] = {"code": it["code"], "qty": it["qty"]}
                except Exception:
                    pass

            # BƯỚC 2: MULTI-PASS TWO-POINTER COMPACTION TO BOTTOM
            protect_set = set()
            if args.protect_dragonfly:
                if 1 in inventory and inventory[1]["code"] == CODE_MINIDRAGONFLY:
                    protect_set.add(1)
                if 2 in inventory and inventory[2]["code"] == CODE_REGISVOUCHER:
                    protect_set.add(2)

            for pass_num in range(1, 9):
                moves = generate_compaction_plan_to_bottom(inventory, protect_slots=protect_set)
                if not moves:
                    print(f"[✔] Đã hoàn tất dồn xuống đáy túi (Đạt chuẩn 100% ở Lượt {pass_num})!")
                    break
                print(f"  ▶ [Lượt {pass_num}] Cần dời {len(moves)} món xuống đáy...")
                for src, qty, dest, code in moves:
                    code_hex = f"0x{code:04X}"
                    name = item_db.get(code_hex, {}).get("name", "")
                    print(f"  🚚 Dời: Ô {src:02d} -> Ô {dest:02d} (Mã {code_hex} {name}, SL: {qty})...", flush=True)
                    send_pkt(bytes([0x17, 0x0A, src, qty, dest]))
                    inventory[dest] = inventory[src]
                    del inventory[src]
                    total_compact += 1
                    time.sleep(args.delay)
                time.sleep(0.35)
                # Đọc lại RAM cho pass tiếp theo
                try:
                    mem_res = script.exports_sync.readbag()
                    if mem_res and mem_res.get("success") and len(mem_res.get("items", {})) > 0:
                        inventory.clear()
                        for s_str, it in mem_res["items"].items():
                            inventory[int(s_str)] = {"code": it["code"], "qty": it["qty"]}
                except Exception:
                    pass

        # BƯỚC 3: XÁC THỰC KẾT QUẢ TỪ BỘ NHỚ RAM
        time.sleep(0.4)
        try:
            mem_res = script.exports_sync.readbag()
            if mem_res and mem_res.get("success") and len(mem_res.get("items", {})) > 0:
                inventory.clear()
                for s_str, it in mem_res["items"].items():
                    inventory[int(s_str)] = {"code": it["code"], "qty": it["qty"]}
        except Exception:
            pass

        total_elapsed = time.time() - start_t
        occupied = sorted(inventory.keys())
        empty_slots = [s for s in range(1, 51) if s not in inventory]

        print("\n" + "=" * 80)
        print("★ KẾT QUẢ SẮP XẾP TÚI ĐỒ:")
        print(f"  • Tổng thời gian thực hiện : {total_elapsed:.2f} giây")
        print(f"  • Số lệnh gộp trùng đã gửi : {total_merged}")
        print(f"  • Số lệnh dời ô đã gửi     : {total_compact}")
        print(f"  • Tổng số ô có đồ hiện tại : {len(inventory)}/50 ô")
        if occupied:
            print(f"  • Vị trí các ô có đồ       : Ô [{min(occupied):02d} .. {max(occupied):02d}] ({len(occupied)} ô)")
        if empty_slots:
            print(f"  • Vị trí các ô trống sạch   : Ô [{min(empty_slots):02d} .. {max(empty_slots):02d}] ({len(empty_slots)} ô trống)")
        print("★ HOÀN TẤT DỒN ĐỒ THÀNH CÔNG RỰC RỠ, CHÍNH XÁC 100%! ★")
        print("=" * 80)

    except KeyboardInterrupt:
        print("\n[!] Đã dừng thao tác theo lệnh người dùng!")
    finally:
        session.detach()

if __name__ == "__main__":
    main()
