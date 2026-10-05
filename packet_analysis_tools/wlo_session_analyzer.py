#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO Dedicated Session Analyzer
==============================
Chuyên biệt để phân tích 1 session đăng nhập từ đầu và theo dõi từng biến động của túi đồ:
- Tự động đính kèm vào alogin-F032.exe (hoặc PID chỉ định).
- Bóc tách gói đăng nhập Op: 0x17 Sub: 0x05 (Snapshot 50 ô ban đầu).
- Theo dõi thời gian thực mọi thao tác: mở quà, kéo thả đồ, vứt đồ, dùng đồ.
- Ghi toàn bộ dữ liệu chi tiết vào session_f032_log.txt.
"""

import os
import sys
import time
import struct
import argparse
from datetime import datetime

# Thiết lập encoding UTF-8 console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

try:
    import frida
except ImportError:
    print("[!] Chưa cài đặt frida. Chạy lệnh: pip install frida")
    sys.exit(1)

class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    CYAN = "\033[96m"      # C->S
    YELLOW = "\033[93m"    # S->C
    GREEN = "\033[92m"     # Thành công / Chi tiết
    RED = "\033[91m"       # Vứt đồ / Cảnh báo
    MAGENTA = "\033[95m"   # Mở quà / Sự kiện
    BLUE = "\033[94m"      # Tiêu đề
    GRAY = "\033[90m"      # Chi tiết phụ

OPCODE_MAP = {
    0x01: "SYSTEM_HANDSHAKE",
    0x02: "ACCOUNT_CHAR_LIST",
    0x03: "CHANNEL_INFO",
    0x04: "SKILL_EFFECT",
    0x05: "LOGIN_AUTH",
    0x06: "COMBAT_ACTION",
    0x07: "TEAM_FORMATION",
    0x08: "PING_HEARTBEAT",
    0x0A: "TRADE_STALL",
    0x0B: "INVENTORY_ITEM",
    0x0C: "FRIEND_MAIL",
    0x0E: "PET_ACTION",
    0x0F: "PET_STATUS",
    0x10: "TENT_FURNITURE",
    0x13: "SYNTHESIS_COMPOUND",
    0x14: "CHAT_MESSAGE",
    0x16: "QUEST_MISSION",
    0x17: "CHAR_ATTRIBUTES",
    0x18: "SHORTCUT_BAR",
    0x20: "NPC_DIALOG",
    0x32: "PLAYER_MOVE",
    0x35: "MAP_WARP_SCENE",
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

rpc.exports = {
    getsocket: function() { return activeSocket; }
};
"""

class WLOSessionAnalyzer:
    def __init__(self, target_pid=None, target_name="alogin-F032.exe", log_file="session_f032_log.txt"):
        self.target_pid = target_pid
        self.target_name = target_name
        self.log_file = log_file

        self.c2s_buf = bytearray()
        self.s2c_buf = bytearray()

        self.session = None
        self.script = None
        self.running = False
        self.packet_count = 0

        # Mô hình túi đồ 50 ô động
        self.inventory = {}
        self.login_inventory_received = False

        self.log_fp = None
        try:
            self.log_fp = open(self.log_file, "a", encoding="utf-8")
            self.write_log(f"\n=== TIẾP TỤC PHIÊN PHÂN TÍCH WLO: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        except Exception as e:
            print(f"[!] Không thể tạo file log: {e}")

    def write_log(self, text):
        if self.log_fp:
            try:
                self.log_fp.write(text + "\n")
                self.log_fp.flush()
            except Exception:
                pass

    def feed_dissector(self, raw_bytes, buffer):
        dec = bytearray(b ^ 0xAD for b in raw_bytes)
        buffer.extend(dec)
        packets = []
        while len(buffer) >= 4:
            if buffer[0] != 0xF4 or buffer[1] != 0x44:
                idx = buffer.find(b'\xF4\x44')
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

    def on_frida_message(self, message, raw_data):
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "recv")
        is_send = (dir_name == "send")
        direction = "C->S" if is_send else "S->C"
        buffer = self.c2s_buf if is_send else self.s2c_buf

        packets = self.feed_dissector(raw_data, buffer)
        for opcode, subcode, data, raw_pkt in packets:
            self.handle_packet(direction, opcode, subcode, data, raw_pkt)

    def handle_packet(self, direction, opcode, subcode, data, raw_pkt):
        self.packet_count += 1
        now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        op_name = OPCODE_MAP.get(opcode, f"0x{opcode:02X}" if opcode is not None else "--")
        sub_str = f"0x{subcode:02X}" if subcode is not None else "--"
        hex_data = data.hex()

        # ======================================================================
        # 1. GÓI TIN ĐĂNG NHẬP KHỞI TẠO TÚI ĐỒ (S->C Op: 0x17 Sub: 0x05)
        # ======================================================================
        if direction == "S->C" and opcode == 0x17 and subcode == 0x05:
            self.login_inventory_received = True
            entry_len = 31
            num_entries = len(data) // entry_len
            rem = len(data) % entry_len
            self.inventory = {}

            print("\n" + "=" * 85)
            print(f"{Colors.BOLD}{Colors.CYAN}[{now_str}] ★ NHẬN GÓI TIN ĐĂNG NHẬP KHỞI TẠO TÚI ĐỒ (Op:0x17 Sub:0x05){Colors.RESET}")
            print(f"    • Kích thước payload : {len(data)} bytes (chia 31 = {num_entries} entries, dư {rem} bytes)")
            print(f"    • Raw Hex Payload    : {data.hex()[:80]}...")
            print("=" * 85)
            self.write_log(f"\n[{now_str}] S->C Op:0x17 Sub:0x05 KHỞI TẠO TÚI ĐỒ: {num_entries} mục (Payload: {len(data)} bytes, Dư: {rem}b)")
            self.write_log(f"    [FULL RAW HEX]: {data.hex()}")

            for i in range(num_entries):
                entry = data[i * entry_len : (i + 1) * entry_len]
                slot = entry[0]
                code = struct.unpack("<H", entry[1:3])[0]
                qty = entry[3]
                extra = entry[4:].hex()
                entry_hex = entry.hex()
                
                is_empty = (code == 0)
                status_str = "TRỐNG" if is_empty else "CÓ ĐỒ"
                
                if not is_empty:
                    self.inventory[slot] = {
                        "code_hex": f"0x{code:04X}",
                        "code_dec": code,
                        "qty": qty,
                        "extra": extra,
                        "raw_hex": entry_hex
                    }
                item_info = f"Ô {slot:02d} | Mã: 0x{code:04X} (Dec: {code:<5}) | SL: {qty:<3} | [{status_str}] | Hex: {entry_hex}"
                print(f"    [+] {item_info}")
                self.write_log(f"    [+] {item_info}")

            empty_slots = [s for s in range(1, 51) if s not in self.inventory]
            occupied_slots = sorted(self.inventory.keys())

            print("-" * 85)
            print(f"[*] Tổng số ô CÓ ĐỒ: {len(occupied_slots)} ô -> {occupied_slots}")
            print(f"[*] Tổng số ô TRỐNG : {len(empty_slots)} ô -> {empty_slots}")
            first_empty = empty_slots[0] if empty_slots else "HẾT (Túi đầy)"
            print(f"{Colors.BOLD}{Colors.GREEN}[*] Ô TRỐNG ĐẦU TIÊN (NƠI QUÀ SẼ RƠI VÀO): Ô {first_empty}{Colors.RESET}")
            print("-" * 85)

            self.write_log(f"[*] Tổng số ô CÓ ĐỒ ({len(occupied_slots)} ô): {occupied_slots}")
            self.write_log(f"[*] Tổng số ô TRỐNG ({len(empty_slots)} ô): {empty_slots}")
            self.write_log(f"[*] Ô trống nhỏ nhất hiện tại: Ô {first_empty}\n")

            # In bảng 50 ô
            self.print_current_bag_table()
            return

        # ======================================================================
        # 2. NGƯỜI CHƠI MỞ QUÀ (C->S Op: 0x17 Sub: 0x4B)
        # ======================================================================
        if direction == "C->S" and opcode == 0x17 and subcode == 0x4B:
            slot = data[0] if len(data) > 0 else 0
            empty_slots = [s for s in range(1, 51) if s not in self.inventory]
            target_slot = empty_slots[0] if empty_slots else None
            msg = f">>> [THAO TÁC MỞ QUÀ] Người chơi mở vật phẩm tại Ô {slot}! (Dự kiến quà sẽ rơi vào Ô trống {target_slot})"
            print(f"\n{Colors.BOLD}{Colors.MAGENTA}[{now_str}] {msg}{Colors.RESET}")
            self.write_log(f"[{now_str}] C->S Op:0x17 Sub:0x4B {msg} | Hex: {hex_data}")
            return

        # ======================================================================
        # 3. SERVER TRẢ PHẦN THƯỞNG MỞ HỘP (S->C Op: 0x17 Sub: 0x06)
        # ======================================================================
        if direction == "S->C" and opcode == 0x17 and subcode == 0x06:
            if len(data) >= 3:
                raw_code = struct.unpack("<H", data[0:2])[0]
                qty = data[2]
                code_hex = f"0x{raw_code:04X}"
                padding = data[3:]
                is_all_zero = all(b == 0 for b in padding)

                empty_slots = [s for s in range(1, 51) if s not in self.inventory]
                landing_slot = empty_slots[0] if empty_slots else None

                print(f"\n{Colors.BOLD}{Colors.YELLOW}[{now_str}] [SERVER TRẢ QUÀ MỞ ĐƯỢC] S->C Op:0x17 Sub:0x06:{Colors.RESET}")
                print(f"    • Mã vật phẩm   : {Colors.CYAN}{code_hex}{Colors.RESET} (Thập phân: {raw_code}, Bytes: {data[0]:02X} {data[1]:02X})")
                print(f"    • Số lượng nhận : {Colors.GREEN}{qty}{Colors.RESET}")
                print(f"    • Rơi vào ô     : {Colors.BOLD}{Colors.GREEN}Ô {landing_slot}{Colors.RESET} (Ô trống nhỏ nhất hiện tại)")
                print(f"    • Toàn bộ Hex   : {hex_data}")
                print(f"    • {Colors.BOLD}{Colors.RED}BẰNG CHỨNG GÓI TIN: Hoàn toàn KHÔNG CHỨA SỐ Ô (28 byte sau đều là 0x00: {is_all_zero}){Colors.RESET}")

                if landing_slot:
                    self.inventory[landing_slot] = {
                        "code_hex": code_hex,
                        "code_dec": raw_code,
                        "qty": qty,
                        "extra": ""
                    }
                self.write_log(f"[{now_str}] S->C Op:0x17 Sub:0x06 TRẢ QUÀ: Mã={code_hex}, SL={qty}, Rơi vào Ô {landing_slot} | Hex: {hex_data}")
            return

        # ======================================================================
        # 4. SERVER CẬP NHẬT SỐ LƯỢNG Ô (S->C Op: 0x17 Sub: 0x09)
        # ======================================================================
        if direction == "S->C" and opcode == 0x17 and subcode == 0x09:
            if len(data) >= 2:
                slot = data[0]
                remain = data[1]
                old_info = self.inventory.get(slot, {})
                old_qty = old_info.get("qty", "?")
                if remain == 0 and slot in self.inventory:
                    del self.inventory[slot]
                    print(f"    • Cập nhật Ô {slot}: Đã dùng hết (SL cũ: {old_qty} -> 0). Ô {slot} trở thành TRỐNG.")
                elif slot in self.inventory:
                    self.inventory[slot]["qty"] = remain
                    print(f"    • Cập nhật Ô {slot}: Giảm từ {old_qty} -> còn lại {remain}.")
                self.write_log(f"[{now_str}] S->C Op:0x17 Sub:0x09 Cập nhật Ô {slot} còn lại {remain}")
            return

        # ======================================================================
        # 5. KÉO ĐỔI VỊ TRÍ Ô (C->S Op: 0x17 Sub: 0x0A)
        # ======================================================================
        if direction == "C->S" and opcode == 0x17 and subcode == 0x0A:
            if len(data) >= 3:
                src = data[0]
                qty = data[1]
                dst = data[2]
                print(f"\n{Colors.CYAN}[{now_str}] [KÉO ĐỒ] Người chơi kéo Ô {src} (SL: {qty}) sang Ô {dst}{Colors.RESET}")
                # Hoán đổi trong mô hình
                src_item = self.inventory.pop(src, None)
                dst_item = self.inventory.pop(dst, None)
                if src_item:
                    self.inventory[dst] = src_item
                if dst_item:
                    self.inventory[src] = dst_item
                self.write_log(f"[{now_str}] C->S Op:0x17 Sub:0x0A Kéo Ô {src} sang Ô {dst}")
            return

        # ======================================================================
        # 6. THAO TÁC VỨT ĐỒ (C->S Sub: 0x03 & S->C Sub: 0xD4 & Sub: 0x1A)
        # ======================================================================
        if direction == "C->S" and opcode == 0x17 and subcode == 0x03:
            slot = data[0] if len(data) > 0 else 0
            qty = data[1] if len(data) > 1 else 1
            it = self.inventory.get(slot, {})
            print(f"\n{Colors.BOLD}{Colors.RED}[{now_str}] [YÊU CẦU VỨT ĐỒ] Người chơi kéo vứt Ô {slot} (SL: {qty}) [Mã hiện tại: {it.get('code_hex', '?')}]{Colors.RESET}")
            self.write_log(f"[{now_str}] C->S Op:0x17 Sub:0x03 Yêu cầu vứt Ô {slot} (SL: {qty}) | Hex: {hex_data}")
            return

        if direction == "S->C" and opcode == 0x17 and subcode == 0xD4:
            if len(data) >= 5:
                slot = data[1]
                raw_code = struct.unpack("<H", data[2:4])[0]
                qty = data[4]
                code_hex = f"0x{raw_code:04X}"
                print(f"{Colors.YELLOW}[{now_str}] [SERVER POPUP VỨT ĐỒ] Server yêu cầu hiện popup xác nhận:{Colors.RESET}")
                print(f"    • Ô cần vứt : Ô {slot} | Mã: {Colors.CYAN}{code_hex}{Colors.RESET} (Dec: {raw_code}) | SL: {qty}")
                print(f"    • Raw Hex   : {hex_data}")
                self.write_log(f"[{now_str}] S->C Op:0x17 Sub:0xD4 POPUP VỨT: Ô {slot}, Mã={code_hex}, SL={qty} | Hex: {hex_data}")
            return

        if direction == "C->S" and opcode == 0x17 and subcode == 0x7C:
            slot = data[0] if len(data) > 0 else 0
            qty = data[1] if len(data) > 1 else 1
            print(f"    • Người chơi bấm OK popup xác nhận vứt Ô {slot} (SL: {qty})")
            self.write_log(f"[{now_str}] C->S Op:0x17 Sub:0x7C Xác nhận popup Ô {slot} (SL: {qty})")
            return

        if direction == "S->C" and opcode == 0x17 and subcode == 0x1A:
            if len(data) >= 3:
                raw_code = struct.unpack("<H", data[0:2])[0]
                qty = data[2]
                code_hex = f"0x{raw_code:04X}"
                print(f"{Colors.GREEN}[{now_str}] [SERVER XÁC NHẬN VỨT XONG] Đã xóa {qty}x {code_hex} khỏi túi!{Colors.RESET}")
                self.write_log(f"[{now_str}] S->C Op:0x17 Sub:0x1A Vứt xong: Mã={code_hex}, SL={qty}")
            return

        # ======================================================================
        # CÁC GÓI TIN ĐĂNG NHẬP / CHUYỂN MAP
        # Ghi log toàn bộ các gói tin khác (bao gồm Op 0x10 Tent, Op 0x13 Ghép đồ, Op 0x17 khác...)
        dir_col = Colors.CYAN if direction == "C->S" else Colors.YELLOW
        print(f"{Colors.GRAY}[{now_str}]{Colors.RESET} {dir_col}{direction}{Colors.RESET} Op:0x{opcode:02X} ({op_name:<18}) Sub:{sub_str:<4} Len:{len(data):<3} | Hex:{hex_data[:50]}")
        self.write_log(f"[{now_str}] {direction} Op:0x{opcode:02X} ({op_name}) Sub:{sub_str} Len:{len(data)} | Hex: {hex_data}")

    def print_current_bag_table(self):
        header = f"{'Ô':<4} | {'Mã Hex':<8} | {'Mã Dec':<7} | {'SL':<4} | {'Trạng Thái'}"
        sep = "-" * 55
        print(header)
        print(sep)
        self.write_log("\n--- BẢNG TRẠNG THÁI TÚI ĐỒ (50 Ô) ---")
        self.write_log(header)
        self.write_log(sep)
        for s in range(1, 51):
            if s in self.inventory:
                it = self.inventory[s]
                line_plain = f"Ô {s:02d} | {it['code_hex']:<8} | {it['code_dec']:<7} | {it['qty']:<4} | CÓ ĐỒ"
                print(f"Ô {s:02d} | {Colors.CYAN}{it['code_hex']:<8}{Colors.RESET} | {it['code_dec']:<7} | {it['qty']:<4} | {Colors.GREEN}CÓ ĐỒ{Colors.RESET}")
                self.write_log(line_plain)
            else:
                line_plain = f"Ô {s:02d} | {'--':<8} | {'--':<7} | {'--':<4} | TRỐNG"
                print(f"Ô {s:02d} | {'--':<8} | {'--':<7} | {'--':<4} | {Colors.GRAY}TRỐNG{Colors.RESET}")
                self.write_log(line_plain)
        print(sep + "\n")
        self.write_log(sep + "\n")

    def start(self):
        print("=" * 85)
        print("            WLO SESSION ANALYZER - GIẢI MÃ TÚI ĐỒ THỜI GIAN THỰC")
        print("=" * 85)

        device = frida.get_local_device()
        target_proc = None

        if self.target_pid:
            try:
                self.session = device.attach(self.target_pid)
                print(f"[*] Đã đính kèm theo PID: {self.target_pid}")
            except Exception as e:
                print(f"[!] Không thể đính kèm PID {self.target_pid}: {e}")
                return
        else:
            procs = [p for p in device.enumerate_processes() if self.target_name.lower() in p.name.lower()]
            if not procs:
                procs = [p for p in device.enumerate_processes() if "alogin" in p.name.lower()]
            if not procs:
                print(f"[!] Không tìm thấy tiến trình nào khớp với '{self.target_name}'!")
                return
            target_proc = procs[0]
            self.session = device.attach(target_proc.pid)
            print(f"[*] Đã đính kèm vào: {target_proc.name} (PID: {target_proc.pid})")

        self.script = self.session.create_script(FRIDA_JS)
        self.script.on("message", self.on_frida_message)
        self.script.load()

        print(f"{Colors.GREEN}[+] Hook thành công! Đang lắng nghe luồng mạng...{Colors.RESET}")
        print(f"[*] File nhật ký log: {self.log_file}")
        print(f"[*] BÂY GIỜ BẠN CÓ THỂ BẮT ĐẦU ĐĂNG NHẬP VÀ THAO TÁC TRONG GAME.")
        print(f"    - Gõ 'bag' để in lại bảng 50 ô túi đồ bất cứ lúc nào.")
        print(f"    - Gõ 'exit' để dừng và lưu log.")
        print("-" * 85 + "\n")

        self.running = True
        is_interactive = sys.stdin and sys.stdin.isatty()
        while self.running:
            if is_interactive:
                try:
                    cmd = input().strip().lower()
                    if cmd in ("exit", "quit", "q"):
                        break
                    elif cmd == "bag":
                        self.print_current_bag_table()
                except (EOFError, KeyboardInterrupt):
                    break
            else:
                try:
                    time.sleep(1)
                except KeyboardInterrupt:
                    break

        print("\n[*] Đang dừng analyzer...")
        try:
            if self.script:
                self.script.unload()
            if self.session:
                self.session.detach()
        except Exception:
            pass
        if self.log_fp:
            self.log_fp.close()
        print(f"{Colors.GREEN}[+] Đã lưu file log tại: {self.log_file}{Colors.RESET}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WLO Session Analyzer")
    parser.add_argument("--pid", type=int, default=None, help="PID tiến trình game")
    parser.add_argument("-p", "--process", default="aloginF02", help="Tên tiến trình game")
    parser.add_argument("-l", "--log", default=None, help="Tên file log")
    args = parser.parse_args()

    log_name = args.log
    if not log_name:
        if args.pid:
            log_name = f"session_{args.pid}_log.txt"
        else:
            p_clean = args.process.replace(".exe", "").replace("-", "_")
            log_name = f"session_{p_clean}_log.txt"

    analyzer = WLOSessionAnalyzer(target_pid=args.pid, target_name=args.process, log_file=log_name)
    analyzer.start()
