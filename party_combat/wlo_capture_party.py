#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO PARTY PACKET CAPTURE & DISSECTOR (DUAL CLIENT)
==================================================
Lắng nghe và bóc tách toàn bộ gói tin khi thiết lập tổ đội (Party/Team)
giữa 2 tiến trình aloginF02 và alogin-F04 trong thời gian thực.
"""

import os
import sys
import time
import struct
import threading
from datetime import datetime

# Tránh lỗi Unicode trên Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    print("[!] Chưa cài đặt thư viện frida.")
    sys.exit(1)

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "party_capture_log.txt")

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
"""

OPCODE_NAMES = {
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
    0x0D: "PARTY_SYSTEM",
    0x0E: "PET_ACTION",
    0x0F: "PET_STATUS",
    0x10: "TENT_FURNITURE",
    0x13: "SYNTHESIS_COMPOUND",
    0x14: "CHAT_MESSAGE",
    0x16: "QUEST_MISSION",
    0x17: "CHAR_ATTRIBUTES",
    0x18: "SHORTCUT_BAR",
    0x19: "PK_SYSTEM",
    0x1A: "GUILD_SYSTEM",
    0x20: "NPC_DIALOG",
    0x23: "MAP_OBJECT",
    0x32: "PLAYER_MOVE",
    0x33: "ENTITY_MOVE_SYNC",
    0x34: "ENTITY_ACTION_SYNC",
    0x35: "MAP_WARP_SCENE",
    0x4B: "EXPRESSION_EMOTE",
    0x55: "DUNGEON_LOBBY",
}

class ClientSniffer:
    def __init__(self, proc_name, pid, log_fp, log_lock):
        self.proc_name = proc_name
        self.pid = pid
        self.log_fp = log_fp
        self.log_lock = log_lock
        self.c2s_buf = bytearray()
        self.s2c_buf = bytearray()
        self.session = None
        self.script = None

    def feed_dissector(self, raw_bytes, buffer):
        dec = bytearray(b ^ 0xAD for b in raw_bytes)
        buffer.extend(dec)
        packets = []
        while len(buffer) >= 4:
            if buffer[0] != 0xF4 or buffer[1] != 0x44:
                idx = buffer.find(bytes([0xF4, 0x44]))
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

    def on_message(self, message, raw_data):
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "recv")
        is_send = (dir_name == "send")
        direction = "C->S" if is_send else "S->C"
        buffer = self.c2s_buf if is_send else self.s2c_buf

        packets = self.feed_dissector(raw_data, buffer)
        for opcode, subcode, data, raw_pkt in packets:
            # Bỏ qua Ping Heartbeat 0x08 để tránh làm loãng log
            if opcode == 0x08:
                continue

            now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            op_name = OPCODE_NAMES.get(opcode, f"0x{opcode:02X}")
            sub_hex = f"0x{subcode:02X}" if subcode is not None else "--"
            op_hex = f"0x{opcode:02X}" if opcode is not None else "--"

            # Cố gắng giải mã text (Big5 / ASCII) nếu có
            text_preview = ""
            try:
                txt = data.decode("big5", errors="ignore")
                clean = "".join(c for c in txt if c.isprintable()).strip()
                if len(clean) >= 2:
                    text_preview = f" | Text: '{clean}'"
            except Exception:
                pass

            # Đánh dấu sao nếu liên quan đến Party / Team (0x07, 0x14, 0x17, 0x1A...)
            is_team_candidate = opcode in [0x07, 0x14, 0x17, 0x1A, 0x0C, 0x02, 0x5C]
            star = " ★ [TEAM CANDIDATE]" if is_team_candidate else ""

            line = (
                f"[{now_str}] [{self.proc_name:<14} | {direction}] "
                f"Op:{op_hex} ({op_name:<16}) Sub:{sub_hex} Len:{len(data):<3} | Hex: {data.hex()}{text_preview}{star}"
            )

            print(line, flush=True)

            with self.log_lock:
                try:
                    self.log_fp.write(line + "\\n")
                    self.log_fp.flush()
                except Exception:
                    pass

    def start(self):
        dev = frida.get_local_device()
        self.session = dev.attach(self.pid)
        self.script = self.session.create_script(FRIDA_JS)
        self.script.on("message", self.on_message)
        self.script.load()

    def stop(self):
        try:
            if self.script:
                self.script.unload()
            if self.session:
                self.session.detach()
        except Exception:
            pass

def run_cli_mode():
    print("=" * 85, flush=True)
    print("        WLO PARTY PACKET SNIFFER (CLI MODE - MULTI CLIENT)", flush=True)
    print("=" * 85, flush=True)

    dev = frida.get_local_device()
    procs = dev.enumerate_processes()
    
    target_procs = []
    for p in procs:
        pname_lower = p.name.lower()
        if "alogin" in pname_lower or pname_lower.startswith("wlo"):
            target_procs.append(p)

    if not target_procs:
        print("[!] Không tìm thấy tiến trình alogin*.exe nào để hook. Thoát.", flush=True)
        sys.exit(1)

    print(f"[+] Tìm thấy {len(target_procs)} tiến trình WLO:")
    for p in target_procs:
        print(f"    - {p.name} (PID: {p.pid})")

    log_fp = open(LOG_FILE, "a", encoding="utf-8")
    log_lock = threading.Lock()
    log_fp.write(f"\n\n=== BẮT ĐẦU BẮT GÓI TỔ ĐỘI: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    log_fp.flush()

    sniffers = []
    for p in target_procs:
        s = ClientSniffer(p.name, p.pid, log_fp, log_lock)
        try:
            s.start()
            sniffers.append(s)
            print(f"[+] Đã hook thành công vào {p.name} (PID {p.pid})", flush=True)
        except Exception as e:
            print(f"[!] Lỗi khi hook {p.name} (PID {p.pid}): {e}", flush=True)

    if not sniffers:
        print("[!] Không thể hook tiến trình nào. Thoát.", flush=True)
        log_fp.close()
        sys.exit(1)

    print("\n" + "=" * 85, flush=True)
    print("  >>> ĐANG LẮNG NGHE! BÂY GIỜ BẠN HÃY THỰC HIỆN MỜI VÀ NHẬN TỔ ĐỘI TRONG GAME <<<", flush=True)
    print("  (Toàn bộ gói tin gửi/nhận giữa các client sẽ được in trực tiếp bên dưới)", flush=True)
    print("=" * 85 + "\n", flush=True)

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[*] Đang dừng sniffer...", flush=True)
    finally:
        for s in sniffers:
            s.stop()
        log_fp.close()
        print("[+] Đã đóng kết nối an toàn.", flush=True)

def main():
    # Kiểm tra cờ --cli hoặc --terminal
    if "--cli" in sys.argv or "--terminal" in sys.argv:
        run_cli_mode()
        return

    # Mặc định khởi chạy giao diện đồ họa WLO Packet Studio GUI
    try:
        import tkinter as tk
        from wlo_capture_party_gui import WLOPacketStudioGUI
        root = tk.Tk()
        app = WLOPacketStudioGUI(root)
        root.mainloop()
    except Exception as e:
        print(f"[!] Không thể mở giao diện đồ họa ({e}). Chuyển về chế độ CLI...", flush=True)
        run_cli_mode()

if __name__ == "__main__":
    main()
