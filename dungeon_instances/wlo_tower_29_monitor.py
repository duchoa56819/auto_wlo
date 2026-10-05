#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO 29-Floor Sky Tower (Tháp 29 Tầng) Live Monitor & Analyzer
============================================================
Theo dõi, phân tích và ghi nhận thời gian thực toàn bộ hành trình Tháp 29 tầng:
- Đính kèm tự động 4 tiến trình: alogin-W04, alogin-W03, alogin-F04, alogin-Wi01.
- Ghi nhận chi tiết:
  * Di chuyển / Chuyển tầng (Map Warp 0x35)
  * Đối thoại NPC / Kích hoạt tháp (0x20, 0x06)
  * Bắt đầu trận chiến & Danh sách quái (0x0B Sub 0xFA / 0x02)
  * Chi tiết lượt đánh, kỹ năng, mục tiêu của từng nhân vật & pet (0x32 Sub 0x01)
  * Quái bị tiêu diệt (0x0B Sub 0x01)
  * Phần thưởng từng tầng (0x17 Sub 0x06 / 0x0B Sub 0x08 / 0x14)
  * Kết thúc trận & thời gian hoàn thành (0x0B Sub 0x00)
"""

import os
import sys
import time
import struct
import threading
from datetime import datetime

# Thiết lập encoding console UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

try:
    import frida
except ImportError:
    print("[!] Chưa cài đặt frida. Chạy lệnh: pip install frida")
    sys.exit(1)

LOG_FILE = "tower_29_live_analysis.log"
SUMMARY_FILE = "tower_29_stages_summary.txt"
EVENTS_FILE = "tower_29_extracted_events.txt"

TARGET_CLIENTS = {
    "alogin-W04.exe": "W04",
    "alogin-W03.exe": "W03",
    "alogin-F04.exe": "F04",
    "alogin-Wi01.exe": "Wi01",
}

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

hookRecv('ws2_32.dll');
hookSend('ws2_32.dll');
hookRecv('wsock32.dll');
hookSend('wsock32.dll');
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

class Tower29Analyzer:
    def __init__(self):
        self.lock = threading.Lock()
        self.log_file = open(LOG_FILE, "a", encoding="utf-8")
        self.summary_file = open(SUMMARY_FILE, "a", encoding="utf-8")
        self.events_file = open(EVENTS_FILE, "a", encoding="utf-8")
        self.start_time = time.time()
        self.current_floor = 0

        self.client_states = {}
        for proc, nick in TARGET_CLIENTS.items():
            self.client_states[proc] = {
                "nick": nick,
                "c2s_dissector": WLOStreamDissector(),
                "s2c_dissector": WLOStreamDissector(),
                "in_battle": False,
                "battle_count": 0,
                "turn_count": 0,
                "last_battle_start": 0,
                "last_map_id": 0,
            }

        header = f"\n{'='*90}\n=== PHIÊN GIÁM SÁT THÁP 29 TẦNG [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ===\n{'='*90}\n"
        self._write_all(header)

    def _write_all(self, text):
        with self.lock:
            self.log_file.write(text + "\n")
            self.log_file.flush()
            self.summary_file.write(text + "\n")
            self.summary_file.flush()
            print(text, flush=True)

    def log_packet(self, client_name, direction, opcode, subcode, data, raw_pkt):
        nick = TARGET_CLIENTS.get(client_name, client_name[:4])
        t_offset = time.time() - self.start_time
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        sub_str = f"Sub:0x{subcode:02X}" if subcode is not None else "Sub:--"
        hex_data = data.hex()
        data_preview = hex_data[:48] + ("..." if len(hex_data) > 48 else "")

        line = f"[{timestamp}] [+ {t_offset:6.1f}s] [{nick:<4}] {direction} Op:0x{opcode:02X} {sub_str:<8} Len:{len(raw_pkt):<3} | Hex: {data_preview}"

        event_desc = self.analyze_event(client_name, nick, direction, opcode, subcode, data)
        if event_desc:
            line += f"  | ★ {event_desc}"
            with self.lock:
                self.events_file.write(f"[{timestamp}] [{nick:<4}] {direction} Op:0x{opcode:02X} {sub_str} | {event_desc} | Hex: {hex_data}\n")
                self.events_file.flush()

        with self.lock:
            self.log_file.write(line + "\n")
            self.log_file.flush()

        if event_desc:
            print(f"[{timestamp}] [{nick:<4}] {direction} | {event_desc}", flush=True)

    def analyze_event(self, client_name, nick, direction, opcode, subcode, data):
        state = self.client_states[client_name]
        desc = ""

        # 1. BẮT ĐẦU VÀO TRẬN ĐÁNH (BATTLE START)
        if opcode == 0x0B and subcode in (0x02, 0xFA):
            if not state["in_battle"]:
                state["in_battle"] = True
                state["battle_count"] += 1
                state["turn_count"] = 0
                state["last_battle_start"] = time.time()
                desc = f"⚔️ [BẮT ĐẦU TRẬN ĐÁNH #{state['battle_count']}] ({nick}) | Len: {len(data)}"
                self._write_all(f"\n{'*'*70}\n[{nick}] BẮT ĐẦU TRẬN ĐÁNH #{state['battle_count']} (Lúc {datetime.now().strftime('%H:%M:%S')})\n{'*'*70}")

        # 2. THAO TÁC LƯỢT ĐÁNH (COMBAT ACTION)
        elif opcode == 0x32 and subcode == 0x01 and direction == "C->S":
            state["turn_count"] += 1
            actor_slot = data[0] if len(data) >= 1 else 0
            actor_row = data[1] if len(data) >= 2 else 0
            target_slot = data[2] if len(data) >= 3 else 0
            target_row = data[3] if len(data) >= 4 else 0
            skill_code = data[4:8].hex() if len(data) >= 8 else data[4:].hex()

            actor_role = "Pet" if actor_slot == 4 else "Char"
            is_defend = (actor_slot == target_slot and actor_row == target_row and skill_code.startswith("75ea"))
            action_type = "🛡️ PHÒNG THỦ" if is_defend else "⚡ TẤN CÔNG / SKILL"

            desc = f"{action_type} [LƯỢT {state['turn_count']:02d}] {actor_role}(S{actor_slot}R{actor_row}) -> Mục tiêu: Slot {target_slot} Row {target_row} | Skill: {skill_code}"

        # 3. QUÁI BỊ TIÊU DIỆT / RỜI SÀN ĐẤU (MONSTER DEFEATED)
        elif opcode == 0x0B and subcode == 0x01 and direction == "S->C":
            if len(data) >= 2:
                d_slot = data[0]
                d_row = data[1]
                desc = f"💀 [QUÁI TỬ TRẬN] Kẻ địch tại Slot {d_slot} Row {d_row} đã bị hạ gục!"

        # 4. KẾT THÚC TRẬN ĐÁNH (BATTLE END)
        elif opcode == 0x0B and subcode == 0x00 and direction == "S->C":
            if state["in_battle"]:
                state["in_battle"] = False
                dur = time.time() - state["last_battle_start"]
                desc = f"🏆 [KẾT THÚC TRẬN] ({nick}: {dur:.1f}s, {state['turn_count']} hiệp/lượt)"
                self._write_all(f"[{nick}] HOÀN THÀNH TRẬN #{state['battle_count']} trong {dur:.1f}s ({state['turn_count']} hiệp)!\n")

        # 5. CHUYỂN TẦNG / MAP MỚI (MAP WARP)
        elif opcode == 0x35:
            map_id = struct.unpack("<H", data[:2])[0] if len(data) >= 2 else 0
            state["last_map_id"] = map_id
            if direction == "S->C":
                desc = f"🚪 [CHUYỂN CẢNH / MAP] Map ID: {map_id} (0x{map_id:04X})"
                self._write_all(f"[{nick}] CHUYỂN MAP MỚI: ID {map_id} (0x{map_id:04X})")

        # 6. ĐỐI THOẠI NPC / KÍCH HOẠT LEO THÁP
        elif opcode == 0x20:
            if subcode == 0x01:
                desc = "💬 [MỞ ĐỐI THOẠI NPC / BẢNG CHỌN]"
            elif subcode == 0x02:
                opt = data[0] if len(data) > 0 else 0
                desc = f"💬 [CHỌN MENU ĐỐI THOẠI] Lựa chọn: 0x{opt:02X}"
            txt = decode_text(data)
            if txt:
                desc += f' Thoại: "{txt}"'

        # 7. PHẦN THƯỞNG ITEM TRAO TẶNG
        elif opcode == 0x17 and subcode == 0x06 and direction == "S->C":
            item_id = struct.unpack("<H", data[:2])[0] if len(data) >= 2 else 0
            qty = data[2] if len(data) >= 3 else 1
            desc = f"🎁 [NHẬN THƯỞNG VẬT PHẨM] Item ID: {item_id} (0x{item_id:04X}), SL: {qty}"
            self._write_all(f"  🎁 [{nick}] NHẬN THƯỞNG: Mã 0x{item_id:04X} ({item_id}) x{qty}")

        # 8. TIN NHẮN HỆ THỐNG / THÔNG BÁO THẮNG
        elif opcode == 0x14:
            txt = decode_text(data)
            if txt:
                desc = f'📢 [THÔNG BÁO] "{txt}"'
                txt_lower = txt.lower()
                if any(w in txt_lower for w in ["exp", "nhận", "được", "thắng", "tầng", "tháp"]):
                    self._write_all(f"  📢 [{nick}] {txt}")

        return desc

    def close(self):
        try:
            self.log_file.close()
            self.summary_file.close()
            self.events_file.close()
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
            self.session = frida.attach(self.proc_name)
            self.script = self.session.create_script(FRIDA_HOOK_JS)
            self.script.on("message", self.on_message)
            self.script.load()
            print(f"[+] ✔ Hook thành công vào [{nick}] (PID: {self.session._impl.pid})!", flush=True)
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
    print("      WLO THÁP 29 TẦNG (SKY TOWER) - HỆ THỐNG GIÁM SÁT & PHÂN TÍCH TRỰC TIẾP")
    print("=" * 90)
    print("  Đội hình theo dõi:")
    print("    1. alogin-W04.exe (W04 - Trưởng nhóm)")
    print("    2. alogin-W03.exe (W03)")
    print("    3. alogin-F04.exe (F04 - Sát thương Hỏa)")
    print("    4. alogin-Wi01.exe (Wi01)")
    print("-" * 90)
    print(f"  • Log chi tiết  : {LOG_FILE}")
    print(f"  • Tóm tắt tầng  : {SUMMARY_FILE}")
    print(f"  • Sự kiện bóc tách: {EVENTS_FILE}")
    print("=" * 90)

    analyzer = Tower29Analyzer()
    threads = []

    for proc in TARGET_CLIENTS:
        t = ClientListener(proc, analyzer)
        t.start()
        threads.append(t)

    print("\n[+] ĐÃ HOOK HOÀN TẤT VÀO CẢ 4 TÀI KHOẢN!")
    print("[*] Bạn có thể bắt đầu dịch chuyển sang Tháp và đánh từng tầng.")
    print("[*] Mọi thông tin (Map, chuyển tầng, vào trận, lượt đánh, skill, quái chết, thưởng) đang được bắt theo thời gian thực.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Đang dừng hệ thống giám sát...")
        for t in threads:
            t.stop()
        analyzer.close()
        print("[+] Đã lưu toàn bộ dữ liệu phân tích Tháp 29 tầng!")

if __name__ == "__main__":
    main()
