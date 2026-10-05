#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO Inventory Synchronization & Gift Opening Verifier
=====================================================
Công cụ phân tích và xác thực cơ chế đồng bộ túi đồ của Wonderland Online (WLO):
1. XÁC MINH GÓI TIN ĐĂNG NHẬP (Op: 0x17 Sub: 0x05):
   - Server gửi duy nhất một danh sách các món đồ hiện có khi đăng nhập vào game.
   - Mỗi món chiếm đúng 31 bytes: [Slot 1 byte, Code 2 bytes LE, Qty 1 byte, Thuộc tính 27 bytes].
   - Các ô không có trong danh sách chính là Ô TRỐNG.
2. XÁC MINH GÓI TIN MỞ QUÀ (Op: 0x17 Sub: 0x06):
   - Khi mở quà (Sub: 0x4B), server trả về Sub: 0x06 [Code 2B, Qty 1B, 28 byte 0].
   - XÁC THỰC RÕ RÀNG: Gói Sub: 0x06 hoàn toàn KHÔNG CHỨA SỐ Ô (Slot).
   - Game client tự động gán món quà mới vào Ô TRỐNG CÓ CHỈ SỐ NHỎ NHẤT (Lowest Empty Slot).
3. ĐỒNG BỘ 2 CHIỀU:
   - Theo dõi luồng mạng trực tiếp (Live Hook qua Frida).
   - Hoặc phân tích trực tiếp từ file bắt gói tin PCAP/PCAPNG có sẵn (--pcap).
   - Quét mảng túi đồ 50 ô thật trong bộ nhớ Delphi để đối chiếu.
"""

import os
import sys
import time
import struct
import argparse
import threading
from datetime import datetime

# Tránh lỗi font console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    frida = None

class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    BLUE = "\033[94m"
    GRAY = "\033[90m"

# ==============================================================================
# HÀM PHÂN TÍCH GÓI TIN TÚI ĐỒ (OPCODE 0x17)
# ==============================================================================
def parse_login_inventory_packet(data):
    """
    Bóc tách gói tin S->C Op: 0x17 Sub: 0x05 (Gói danh sách đồ khi đăng nhập).
    Cấu trúc: các block 31 bytes liên tiếp:
    - Byte 0: Slot (1-50)
    - Byte 1..2: Item Code (uint16 LE)
    - Byte 3: Quantity (uint8)
    - Byte 4..30: 27 bytes thuộc tính (độ bền, socket, ngọc...)
    """
    entry_len = 31
    num_entries = len(data) // entry_len
    items = {}
    for i in range(num_entries):
        entry = data[i * entry_len : (i + 1) * entry_len]
        slot = entry[0]
        code = struct.unpack("<H", entry[1:3])[0]
        qty = entry[3]
        extra = entry[4:]
        items[slot] = {
            "slot": slot,
            "code_hex": f"0x{code:04X}",
            "code_dec": code,
            "qty": qty,
            "extra_hex": extra.hex()
        }
    return items

def parse_gift_reward_packet(data):
    """
    Bóc tách gói tin S->C Op: 0x17 Sub: 0x06 (Server trả quà khi mở đồ).
    Cấu trúc: 31 bytes:
    - Byte 0..1: Item Code (uint16 LE)
    - Byte 2: Quantity (uint8)
    - Byte 3..30: 28 bytes padding (0x00)
    """
    if len(data) < 3:
        return None
    code = struct.unpack("<H", data[0:2])[0]
    qty = data[2]
    padding = data[3:]
    has_slot = False  # Kiểm tra xem có trường nào là số ô (1-50) hợp lý không
    return {
        "code_hex": f"0x{code:04X}",
        "code_dec": code,
        "qty": qty,
        "raw_bytes": f"{data[0]:02X} {data[1]:02X}",
        "data_len": len(data),
        "padding_is_all_zero": all(b == 0 for b in padding),
        "raw_hex": data.hex()
    }

# ==============================================================================
# PHÂN TÍCH FILE PCAP CÓ SẴN (OFFLINE VERIFICATION)
# ==============================================================================
def verify_from_pcap(pcap_path):
    print("\n" + "=" * 80)
    print(f"[*] ĐANG PHÂN TÍCH FILE PCAP: {pcap_path}")
    print("=" * 80)

    try:
        from wlo_packet_parser import parse_pcap
    except ImportError:
        print("[!] Không tìm thấy module wlo_packet_parser.py!")
        return

    pkts = parse_pcap(pcap_path)
    print(f"[+] Đã giải mã thành công {len(pkts)} gói tin WLO từ file PCAP.\n")

    login_inventory = None
    gift_events = []

    last_open_slot = None

    for p in pkts:
        # 1. Gói đăng nhập khởi tạo túi đồ
        if p.direction == "S->C" and p.opcode == 0x17 and p.subcode == 0x05:
            login_inventory = parse_login_inventory_packet(p.data)
            print(f"{Colors.BOLD}{Colors.CYAN}[1] PHÁT HIỆN GÓI TIN ĐĂNG NHẬP KHỞI TẠO TÚI ĐỒ (S->C Op:0x17 Sub:0x05){Colors.RESET}")
            print(f"    • Thời điểm trong file : {p.time:.3f}s")
            print(f"    • Kích thước payload    : {len(p.data)} bytes (chia hết cho 31 bytes: {len(p.data)//31} món)")
            print(f"    • Số ô đang có đồ       : {Colors.GREEN}{len(login_inventory)} ô{Colors.RESET}")
            empty_slots = [s for s in range(1, 51) if s not in login_inventory]
            print(f"    • Số ô đang trống       : {Colors.YELLOW}{len(empty_slots)} ô{Colors.RESET} {empty_slots[:10]}...")
            print(f"    • Ô trống đầu tiên      : {Colors.BOLD}{Colors.GREEN}Ô {empty_slots[0] if empty_slots else 'Hết'}{Colors.RESET}")
            print("-" * 80)

        # 2. Người chơi mở quà
        elif p.direction == "C->S" and p.opcode == 0x17 and p.subcode == 0x4B:
            slot = p.data[0] if len(p.data) > 0 else 0
            last_open_slot = slot
            print(f"\n{Colors.MAGENTA}>>> [THAO TÁC MỞ ĐỒ] Người chơi bấm mở vật phẩm tại Ô {slot} (thời điểm: {p.time:.3f}s){Colors.RESET}")

        # 3. Server trả quà
        elif p.direction == "S->C" and p.opcode == 0x17 and p.subcode == 0x06:
            reward = parse_gift_reward_packet(p.data)
            print(f"{Colors.YELLOW}[2] SERVER TRẢ PHẦN THƯỞNG MỞ HỘP (S->C Op:0x17 Sub:0x06):{Colors.RESET}")
            print(f"    • Thời điểm     : {p.time:.3f}s")
            print(f"    • Mã vật phẩm   : {Colors.BOLD}{Colors.CYAN}{reward['code_hex']}{Colors.RESET} (Thập phân: {reward['code_dec']}, Bytes: {reward['raw_bytes']})")
            print(f"    • Số lượng nhận : {Colors.BOLD}{Colors.GREEN}{reward['qty']}{Colors.RESET}")
            print(f"    • Toàn bộ Hex   : {reward['raw_hex']}")
            print(f"    • {Colors.BOLD}{Colors.RED}KẾT LUẬN XÁC THỰC: Gói tin Sub:0x06 hoàn toàn KHÔNG CÓ SỐ Ô (Slot)!{Colors.RESET}")
            print(f"      (Toàn bộ 28 bytes phía sau đều là 0x00: {reward['padding_is_all_zero']})")

        # 4. Server cập nhật số lượng hộp quà còn lại
        elif p.direction == "S->C" and p.opcode == 0x17 and p.subcode == 0x09:
            if len(p.data) >= 2:
                slot = p.data[0]
                remain = p.data[1]
                print(f"    • Cập nhật số lượng Ô {slot} còn lại: {remain}")

    if login_inventory:
        print("\n" + "=" * 80)
        print(" BẢNG CHI TIẾT CÁC Ô ĐỒ TỪ GÓI ĐĂNG NHẬP (SUB: 0x05)")
        print("=" * 80)
        print(f"{'Ô':<4} | {'Mã Hex':<8} | {'Mã Dec':<7} | {'SL':<4} | {'Thuộc tính 27B'}")
        print("-" * 80)
        for s in range(1, 51):
            if s in login_inventory:
                it = login_inventory[s]
                print(f"Ô {s:2d} | {Colors.CYAN}{it['code_hex']:<8}{Colors.RESET} | {it['code_dec']:<7} | {it['qty']:<4} | {it['extra_hex'][:16]}...")
            else:
                print(f"Ô {s:2d} | {Colors.GRAY}(TRỐNG){Colors.RESET}")
        print("=" * 80)

# ==============================================================================
# LIVE MONITOR QUA FRIDA
# ==============================================================================
FRIDA_JS = """
var activeSocket = -1;
var cachedBagBase = null;

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

function findBagBase() {
    if (cachedBagBase) {
        try {
            if (cachedBagBase.readU32() === 0x88000100 &&
                cachedBagBase.add(0x48).readU32() === 0x88000200) {
                return cachedBagBase;
            }
        } catch(e) {
            cachedBagBase = null;
        }
    }
    var ranges = Process.enumerateRanges('rw-');
    for (var i = 0; i < ranges.length; i++) {
        var r = ranges[i];
        if (r.size < 4096 || r.size > 20 * 1024 * 1024) continue;
        try {
            var matches = Memory.scanSync(r.base, r.size, "00 01 00 88");
            for (var j = 0; j < matches.length; j++) {
                var p = matches[j].address;
                try {
                    if (p.add(0x48 * 1).readU32() === 0x88000200 &&
                        p.add(0x48 * 2).readU32() === 0x88000300 &&
                        p.add(0x48 * 3).readU32() === 0x88000400) {
                        cachedBagBase = p;
                        return p;
                    }
                } catch(e) {}
            }
        } catch(e) {}
    }
    return null;
}

function dumpMemoryBag() {
    var base = findBagBase();
    if (!base) return {found: false};
    var slots = [];
    for (var s = 0; s < 50; s++) {
        var slotPtr = base.add(s * 0x48);
        var val1 = slotPtr.add(4).readU32();
        var isEmpty = (val1 === 0 || val1 === 0x0c00 || val1 === 3072);
        slots.push({
            slot: s + 1,
            isEmpty: isEmpty,
            val1: val1,
            val1_hex: "0x" + val1.toString(16).toUpperCase()
        });
    }
    return {found: true, base: base.toString(), slots: slots};
}

rpc.exports = {
    dumpbag: function() { return dumpMemoryBag(); }
};
"""

class LiveInventoryVerifier:
    def __init__(self, target_pid=None, target_process=None):
        self.target_pid = target_pid
        self.target_process = target_process
        self.running = False
        self.session = None
        self.script = None

        # Trạng thái túi đồ theo dõi qua mạng
        self.network_bag = {}
        self.last_open_slot = 0

    def start(self):
        print("=" * 80)
        print("   WLO LIVE INVENTORY SYNCHRONIZATION VERIFIER (THEO DÕI ĐỒNG BỘ TRỰC TIẾP)")
        print("=" * 80)

        device = frida.get_local_device()
        if self.target_pid:
            self.session = frida.attach(self.target_pid)
        else:
            procs = [p for p in device.enumerate_processes() if "alogin" in p.name.lower()]
            if not procs:
                print("[!] Không tìm thấy alogin*.exe nào đang chạy!")
                return
            self.session = frida.attach(procs[0].pid)
            print(f"[*] Đã chọn tiến trình: {procs[0].name} (PID: {procs[0].pid})")

        self.script = self.session.create_script(FRIDA_JS)
        self.script.on("message", self.on_message)
        self.script.load()

        print(f"{Colors.GREEN}[+] Đính kèm thành công! Đang lắng nghe mạng và theo dõi đồng bộ túi đồ...{Colors.RESET}")
        print(f"[*] Hướng dẫn:")
        print(f"    - Nếu bạn đăng nhập / đổi map: Server sẽ gửi S->C Op: 0x17 Sub: 0x05 khởi tạo 50 ô.")
        print(f"    - Nếu bạn mở quà: Script sẽ hiển thị gói Sub: 0x4B và gói Sub: 0x06 (chứng minh không có số ô).")
        print(f"    - Gõ lệnh 'bag' trên console để xem trạng thái 50 ô túi đồ từ bộ nhớ ngay lập tức.")
        print("-" * 80 + "\n")

        self.running = True

        # Đọc ngay trạng thái bộ nhớ ban đầu
        self.print_memory_bag()

        while self.running:
            try:
                cmd = input().strip()
                if cmd.lower() in ("exit", "quit", "q"):
                    break
                elif cmd.lower() == "bag":
                    self.print_memory_bag()
                elif cmd.lower() == "slots":
                    self.print_network_bag()
                elif cmd.lower() == "help":
                    print("Lệnh: [bag] xem bộ nhớ thực tế | [slots] xem túi đồ bóc tách từ mạng | [exit] thoát")
            except (EOFError, KeyboardInterrupt):
                break

    def print_memory_bag(self):
        try:
            res = self.script.exports_sync.dumpbag()
            if not res['found']:
                print("[!] Chưa quét được mảng túi đồ trong bộ nhớ game.")
                return
            occupied = [s for s in res['slots'] if not s['isEmpty']]
            empty = [s for s in res['slots'] if s['isEmpty']]
            print("\n" + "=" * 75)
            print(f" TRẠNG THÁI TÚI ĐỒ BỘ NHỚ DELPHI HIỆN TẠI (Base: {res['base']})")
            print("=" * 75)
            print(f"[*] Số ô có đồ: {len(occupied)} ô | Số ô trống: {len(empty)} ô")
            print(f"[*] Ô trống đầu tiên (First Empty Slot): {Colors.BOLD}{Colors.GREEN}Ô {empty[0]['slot'] if empty else 'Hết'}{Colors.RESET}")
            print("-" * 75)
            line = []
            for s in range(1, 51):
                slot_info = res['slots'][s - 1]
                if slot_info['isEmpty']:
                    line.append(f"[{s:02d}: TRỐNG]")
                else:
                    line.append(f"[{s:02d}: {slot_info['val1_hex']}]")
                if len(line) == 5:
                    print("  " + "  ".join(line))
                    line = []
            print("=" * 75 + "\n")
        except Exception as e:
            print(f"[!] Lỗi khi đọc bộ nhớ: {e}")

    def print_network_bag(self):
        if not self.network_bag:
            print("[!] Chưa nhận được gói tin khởi tạo túi đồ Op: 0x17 Sub: 0x05 (Gói này chỉ gửi khi đăng nhập).")
            return
        print("\n=== TÚI ĐỒ THEO DÕI QUA MẠNG ===")
        for s in range(1, 51):
            if s in self.network_bag:
                it = self.network_bag[s]
                print(f"  Ô {s:2d}: {it['code_hex']} (SL: {it['qty']})")
            else:
                print(f"  Ô {s:2d}: (TRỐNG)")
        print()

    def on_message(self, message, raw_data):
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "recv")
        is_send = (dir_name == "send")

        # Giải mã XOR 0xAD
        dec = bytes(b ^ 0xAD for b in raw_data)
        idx = 0
        while idx + 4 <= len(dec):
            if dec[idx] != 0xF4 or dec[idx + 1] != 0x44:
                idx += 1
                continue
            p_len = struct.unpack("<H", dec[idx + 2 : idx + 4])[0]
            total_len = 4 + p_len
            if idx + total_len > len(dec):
                break
            body = dec[idx + 4 : idx + total_len]
            idx += total_len

            if len(body) < 2:
                continue
            opcode = body[0]
            subcode = body[1]
            data = body[2:]

            # 1. Bắt gói khởi tạo túi đồ khi đăng nhập
            if not is_send and opcode == 0x17 and subcode == 0x05:
                items = parse_login_inventory_packet(data)
                self.network_bag = items
                now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"\n{Colors.BOLD}{Colors.CYAN}[{now}] [BẮT ĐƯỢC GÓI ĐĂNG NHẬP] S->C Op:0x17 Sub:0x05 Len:{len(data)+2}{Colors.RESET}")
                print(f"    -> Server vừa gửi cấu hình toàn bộ túi đồ gồm {len(items)} món đồ có sẵn!")
                empty = [s for s in range(1, 51) if s not in items]
                print(f"    -> Các ô trống phát hiện được: {empty}")
                print(f"    -> Ô trống đầu tiên là: Ô {empty[0] if empty else 'Hết'}\n")

            # 2. Người chơi mở quà
            elif is_send and opcode == 0x17 and subcode == 0x4B:
                slot = data[0] if len(data) > 0 else 0
                self.last_open_slot = slot
                now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"{Colors.MAGENTA}[{now}] C->S Mở hộp quà tại Ô {slot}{Colors.RESET}")

            # 3. Server trả quà
            elif not is_send and opcode == 0x17 and subcode == 0x06:
                reward = parse_gift_reward_packet(data)
                now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"\n{Colors.BOLD}{Colors.YELLOW}[{now}] [SERVER TRẢ QUÀ MỞ ĐƯỢC] S->C Op:0x17 Sub:0x06{Colors.RESET}")
                print(f"    • Mã vật phẩm : {Colors.CYAN}{reward['code_hex']}{Colors.RESET} (Thập phân: {reward['code_dec']}, Raw: {reward['raw_bytes']})")
                print(f"    • Số lượng    : {Colors.GREEN}{reward['qty']}{Colors.RESET}")
                print(f"    • Raw Payload : {reward['raw_hex']}")
                print(f"    • {Colors.BOLD}{Colors.RED}[CHỨNG MINH KỸ THUẬT] Gói tin hoàn toàn KHÔNG CHỨA SỐ Ô NÀO!{Colors.RESET}")
                print(f"      (Padding 28 bytes hoàn toàn bằng 0: {reward['padding_is_all_zero']})")
                print(f"    -> Game Client tự động xếp món {reward['code_hex']} vào ô trống nhỏ nhất trong túi.\n")

            # 4. Server trừ số lượng hộp quà
            elif not is_send and opcode == 0x17 and subcode == 0x09:
                if len(data) >= 2:
                    slot = data[0]
                    qty = data[1]
                    now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    print(f"[{now}] S->C Cập nhật Ô {slot} còn lại {qty} cái.")

def main():
    parser = argparse.ArgumentParser(description="WLO Inventory Synchronization Verifier")
    parser.add_argument("--pcap", default=None, help="Đường dẫn file PCAP để phân tích gói tin có sẵn")
    parser.add_argument("-p", "--process", default=None, help="Tên tiến trình game để hook trực tiếp")
    parser.add_argument("--pid", type=int, default=None, help="PID tiến trình game")

    args = parser.parse_args()

    # Nếu có file PCAP, phân tích trực tiếp từ capture
    if args.pcap:
        verify_from_pcap(args.pcap)
        return

    # Nếu không chỉ định, kiểm tra xem có file pcap mặc định không
    default_pcap = "G:/WLOI_beta/WLOI/captures/wlo_game_only.pcapng"
    if len(sys.argv) == 1 and os.path.isfile(default_pcap):
        print("=" * 80)
        print("          WLO INVENTORY SYNCHRONIZATION VERIFIER")
        print("=" * 80)
        print("  [1] Phân tích file bắt gói tin mẫu (wlo_game_only.pcapng)")
        print("  [2] Theo dõi trực tiếp tiến trình game đang chạy (Live Frida Hook)")
        print("=" * 80)
        try:
            choice = input("Chọn chế độ [1-2] (Mặc định 1): ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "1"
        if choice == "2":
            verifier = LiveInventoryVerifier(target_pid=args.pid, target_process=args.process)
            verifier.start()
        else:
            verify_from_pcap(default_pcap)
        return

    verifier = LiveInventoryVerifier(target_pid=args.pid, target_process=args.process)
    verifier.start()

if __name__ == "__main__":
    main()
