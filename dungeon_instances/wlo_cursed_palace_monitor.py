#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO CURSED PALACE MULTI-CLIENT LIVE MONITOR & ANALYZER
======================================================
Lắng nghe, ghi nhận và phân tích trực tiếp toàn bộ gói tin & diễn biến trận đánh
của từng Ải Cursed Palace trên cả 4 tài khoản:
- alogin-F04.exe
- alogin-W03.exe
- alogin-W04.exe
- alogin-Wi01.exe
"""

import os
import sys
import time
import struct
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
    print("[!] Chưa cài đặt thư viện frida. Vui lòng cài: pip install frida")
    sys.exit(1)

TARGET_CLIENTS = [
    "alogin-F04.exe",
    "alogin-W03.exe",
    "alogin-W04.exe",
    "alogin-Wi01.exe",
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "cursed_palace_live_analysis.log")
SUMMARY_FILE = os.path.join(SCRIPT_DIR, "cursed_palace_stages_summary.txt")

FRIDA_HOOK_JS = """
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
                var len = args[2].toInt32();
                if (len > 0) {
                    try {
                        var buf = args[1].readByteArray(len);
                        send({dir: 'send', len: len, sock: args[0].toInt32()}, buf);
                    } catch(e) {}
                }
            }
        });
    } catch(e) {}
}

hookRecv('wsock32.dll');
hookRecv('ws2_32.dll');
hookSend('ws2_32.dll');
"""

def decode_text(raw_bytes):
    if not raw_bytes:
        return ""
    try:
        text = raw_bytes.decode("big5")
        filtered = "".join(c for c in text if c.isprintable())
        if len(filtered) >= 2:
            return filtered
    except Exception:
        pass
    try:
        ascii_chars = [chr(b) if 32 <= b <= 126 else "" for b in raw_bytes]
        text_ascii = "".join(ascii_chars).strip()
        return text_ascii if len(text_ascii) >= 3 else ""
    except Exception:
        return ""

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

class CursedPalaceAnalyzer:
    def __init__(self):
        self.lock = threading.Lock()
        self.log_file = open(LOG_FILE, "a", encoding="utf-8")
        self.summary_file = open(SUMMARY_FILE, "a", encoding="utf-8")
        self.start_time = time.time()
        
        # State tracking per client
        self.client_states = {}
        for c in TARGET_CLIENTS:
            nick = c.replace("alogin-", "").replace(".exe", "")
            self.client_states[c] = {
                "nick": nick,
                "in_battle": False,
                "current_floor": 1,
                "battle_count": 0,
                "turn_count": 0,
                "c2s_dissector": WLOStreamDissector(),
                "s2c_dissector": WLOStreamDissector(),
                "last_battle_start": 0,
                "last_map_id": None,
            }

        self.global_stage = 1

        header = f"\n{'='*90}\n=== PHIÊN GIÁM SÁT CURSED PALACE [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ===\n{'='*90}\n"
        self._write_both(header)

    def _write_both(self, text):
        with self.lock:
            self.log_file.write(text + "\n")
            self.log_file.flush()
            self.summary_file.write(text + "\n")
            self.summary_file.flush()

    def log_packet(self, client_name, direction, opcode, subcode, data, raw_pkt):
        if opcode == 0x08:
            return

        state = self.client_states.get(client_name)
        nick = state["nick"] if state else client_name
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        elapsed = time.time() - self.start_time
        sub_str = f"0x{subcode:02X}" if subcode is not None else "--"
        hex_data = data.hex()

        event_desc = self.analyze_event(client_name, nick, direction, opcode, subcode, data)

        line = f"[{timestamp}] [+{elapsed:6.1f}s] [{nick:<4}] {direction} Op:0x{opcode:02X} Sub:{sub_str} Len:{len(data)+2:<3}"
        if event_desc:
            line += f" | ★ {event_desc}"
        line += f" | Hex: {hex_data[:64]}" + ("..." if len(hex_data) > 64 else "")

        with self.lock:
            self.log_file.write(line + "\n")
            self.log_file.flush()

        if event_desc:
            print(f"[{timestamp}] [{nick:<4}] {direction} | {event_desc}", flush=True)

    def analyze_event(self, client_name, nick, direction, opcode, subcode, data):
        state = self.client_states[client_name]
        desc = ""

        # 1. BẮT ĐẦU VÀO TRẬN ĐÁNH (BATTLE START)
        if opcode == 0x0B and subcode == 0x02:
            state["in_battle"] = True
            state["battle_count"] += 1
            state["turn_count"] = 0
            state["last_battle_start"] = time.time()
            desc = f"⚔️ [BẮT ĐẦU TRẬN ĐÁNH] (Trận #{state['battle_count']} của {nick}) | Data: {data.hex()}"
            self._write_both(f"\n{'*'*70}\n[{nick}] BẮT ĐẦU TRẬN ĐÁNH #{state['battle_count']} (Lúc {datetime.now().strftime('%H:%M:%S')})\n{'*'*70}")

        # 2. THAO TÁC LƯỢT ĐÁNH (COMBAT ROUND / ACTION)
        elif opcode == 0x32 and subcode == 0x01 and direction == "C->S":
            state["turn_count"] += 1
            actor_slot = data[0] if len(data) >= 1 else 0
            actor_row = data[1] if len(data) >= 2 else 0
            tgt_slot = data[2] if len(data) >= 3 else 0
            tgt_row = data[3] if len(data) >= 4 else 0
            actor_type = "Char" if actor_slot == 3 else ("Pet" if actor_slot == 4 else f"Slot {actor_slot}")
            action_code = data[4:8].hex() if len(data) >= 8 else data[4:].hex()

            skill_name = "Defend (75ea)" if action_code.startswith("75ea") else (
                         "F04 Fire (1f3b)" if action_code.startswith("1f3b") else (
                         "F04 Pet (043b)" if action_code.startswith("043b") else (
                         "Water Char (d861)" if action_code.startswith("d861") else (
                         "Water Pet (a33a)" if action_code.startswith("a33a") else action_code))))

            desc = f"⚡ [LƯỢT {state['turn_count']:02d}] {nick} {actor_type}(R{actor_row}) -> Mục tiêu: Slot {tgt_slot} R{tgt_row} | Skill: {skill_name}"
            self._write_both(f"  • [{nick}] Lượt {state['turn_count']:02d}: {actor_type}(R{actor_row}) -> Slot {tgt_slot} R{tgt_row} | Skill: {skill_name} ({action_code})")

        # 3. KẾT THÚC TRẬN ĐÁNH (BATTLE END / VICTORY / ESCAPE)
        elif opcode == 0x0B and subcode == 0x00 and direction == "S->C":
            if state["in_battle"]:
                state["in_battle"] = False
                dur = time.time() - state["last_battle_start"]
                desc = f"🏆 [KẾT THÚC TRẬN ĐÁNH] ({nick}: {dur:.1f}s, {state['turn_count']} lượt)"
                self._write_both(f"🏆 [{nick}] HOÀN THÀNH TRẬN ĐÁNH #{state['battle_count']} trong {dur:.1f}s ({state['turn_count']} lượt)!\n")

        # 4. CHUYỂN MAP / WARP / LÊN TẦNG TIẾP THEO
        elif opcode == 0x35:
            map_id = struct.unpack("<H", data[:2])[0] if len(data) >= 2 else 0
            state["last_map_id"] = map_id
            if direction == "S->C":
                desc = f"🚪 [CHUYỂN CẢNH / MAP MỚI] Map ID: {map_id} (0x{map_id:04X})"
                self._write_both(f"[{nick}] CHUYỂN MAP MỚI: ID {map_id} (0x{map_id:04X})")

        # 5. CỔNG DỊCH CHUYỂN / CLICK CỬA HOẶC PHA LÊ
        elif opcode == 0x06 and subcode == 0x02 and direction == "C->S":
            desc = f"🌀 [TƯƠNG TÁC CỔNG / MAP TRIGGER] Data: {data.hex()}"

        # 6. ĐỐI THOẠI NPC / LỰA CHỌN THOẠI
        elif opcode == 0x20:
            if subcode == 0x01:
                desc = f"💬 [MỞ ĐỐI THOẠI NPC / SỰ KIỆN]"
            elif subcode == 0x02:
                opt = data[0] if len(data) > 0 else 0
                desc = f"💬 [CHỌN MENU ĐỐI THOẠI] Lựa chọn: 0x{opt:02X}"
            txt = decode_text(data)
            if txt:
                desc += f' Thoại: "{txt}"'

        # 7. TIN NHẮN HỆ THỐNG / PHẦN THƯỞNG / EXP / CHAT
        elif opcode == 0x14:
            txt = decode_text(data)
            if txt:
                desc = f'📢 [THÔNG BÁO / CHAT] "{txt}"'
                txt_lower = txt.lower()
                if any(w in txt_lower for w in ["exp", "kinh nghiệm", "nhận", "được", "item", "chiến thắng", "thắng"]):
                    self._write_both(f"  🎁 [{nick}] {txt}")

        # 8. THAY ĐỔI VẬT PHẨM / TÚI ĐỒ (DROP ITEM, TIÊU HAO, DỜI ĐỒ)
        elif opcode == 0x17:
            if subcode == 0x09 and len(data) >= 2:
                desc = f"🎟️ [TIÊU HAO VẬT PHẨM] Ô Slot {data[0]} - Số lượng {data[1]}"
                self._write_both(f"  🎟️ [{nick}] Tiêu hao ô Slot {data[0]}, SL: {data[1]}")
            elif subcode == 0x05:
                desc = f"🎒 [CẬP NHẬT TÚI ĐỒ] Data: {data.hex()}"
                self._write_both(f"  🎒 [{nick}] Nhận vật phẩm/Cập nhật túi đồ: {data.hex()}")
            elif subcode == 0x0A and len(data) >= 2:
                desc = f"🔄 [DỜI ĐỒ TÚI] Từ Slot {data[0]} -> Slot {data[1]}"
                self._write_both(f"  🔄 [{nick}] Dời đồ: Slot {data[0]} -> Slot {data[1]}")

        # 9. THÔNG TIN QUÁI VẬT & CHIẾN TRƯỜNG (0x0B Subcodes)
        elif opcode == 0x0B:
            if subcode == 0xFA:
                desc = f"👾 [XUẤT HIỆN KẺ ĐỊCH] Data: {data.hex()}"
                self._write_both(f"  👾 [{nick}] Quái vật xuất hiện: {data.hex()}")
            elif subcode == 0x01:
                desc = f"💥 [SÁT THƯƠNG / DIỄN BIẾN COMBAT] Data: {data.hex()}"
            elif subcode == 0x03:
                desc = f"⏳ [LƯỢT ĐÁNH MỚI] Data: {data.hex()}"

        return desc

    def close(self):
        try:
            self.log_file.close()
            self.summary_file.close()
        except Exception:
            pass

class ClientListener(threading.Thread):
    def __init__(self, proc_name, analyzer):
        super().__init__(daemon=True)
        self.proc_name = proc_name
        self.analyzer = analyzer
        self.session = None
        self.script = None
        self.running = True

    def run(self):
        state = self.analyzer.client_states[self.proc_name]
        nick = state["nick"]
        print(f"[*] Đang đính kèm và hook vào [{nick}] ({self.proc_name})...", flush=True)

        try:
            dev = frida.get_local_device()
            target_pid = None
            for p in dev.enumerate_processes():
                if p.name.lower() == self.proc_name.lower():
                    target_pid = p.pid
                    break
            if not target_pid:
                print(f"[-] ❌ Không tìm thấy tiến trình {self.proc_name}", flush=True)
                return
            self.session = dev.attach(target_pid)
            self.script = self.session.create_script(FRIDA_HOOK_JS)
            self.script.on("message", self.on_message)
            self.script.load()
            print(f"[+] ✔ Hook thành công vào [{nick}] (PID: {target_pid})!", flush=True)
        except Exception as e:
            print(f"[-] ❌ Lỗi kết nối [{nick}]: {e}", flush=True)
            return

        while self.running:
            time.sleep(0.5)

    def on_message(self, message, raw_data):
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "send")
        is_send = (dir_name == "send")
        direction_str = "C->S" if is_send else "S->C"

        state = self.analyzer.client_states[self.proc_name]
        dissector = state["c2s_dissector"] if is_send else state["s2c_dissector"]
        packets = dissector.feed(raw_data)

        for opcode, subcode, data, raw_pkt in packets:
            self.analyzer.log_packet(self.proc_name, direction_str, opcode, subcode, data, raw_pkt)

    def stop(self):
        self.running = False
        try:
            if self.session:
                self.session.detach()
        except Exception:
            pass

def main():
    print("=" * 90)
    print("      WLO CURSED PALACE - HỆ THỐNG GIÁM SÁT & PHÂN TÍCH TRỰC TIẾP 4 TIẾN TRÌNH")
    print("=" * 90)
    print("  Mục tiêu theo dõi:")
    print("    1. alogin-F04.exe (F04)")
    print("    2. alogin-W03.exe (W03)")
    print("    3. alogin-W04.exe (W04)")
    print("    4. alogin-Wi01.exe (Wi01)")
    print("-" * 90)
    print(f"  • File Log chi tiết: {LOG_FILE}")
    print(f"  • File Tóm tắt ải   : {SUMMARY_FILE}")
    print("=" * 90)

    analyzer = CursedPalaceAnalyzer()
    threads = []

    for proc in TARGET_CLIENTS:
        t = ClientListener(proc, analyzer)
        t.start()
        threads.append(t)

    print("\n[+] ĐÃ KÍCH HOẠT ĐẦY ĐỦ 4 TIẾN TRÌNH THEO DÕI!")
    print("[*] Bạn có thể bắt đầu đánh từng Ải ngay trong game.")
    print("[*] Toàn bộ gói tin, lượt đánh, skill, sát thương, kết quả và chuyển tầng đang được ghi lại.")
    print("[*] Bấm Ctrl+C bất kỳ lúc nào để dừng và xuất báo cáo tổng kết.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Đang dừng hệ thống giám sát và đóng file log...")
        for t in threads:
            t.stop()
        analyzer.close()
        print("[+] Đã lưu toàn bộ dữ liệu phân tích thành công!")

if __name__ == "__main__":
    main()
