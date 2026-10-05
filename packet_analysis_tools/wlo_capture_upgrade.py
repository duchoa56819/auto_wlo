#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO Equipment Upgrade / Forge Scroll Live Sniffer & Analyzer
============================================================
Theo dõi, ghi nhận và phân tích toàn bộ gói tin (C->S, S->C) và trạng thái túi đồ
khi người chơi sử dụng Cuộn Rèn / Scroll để nâng cấp trang bị trên alogin-w01.
"""

import os
import sys
import time
import json
import struct
import argparse
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import frida
except ImportError:
    print("[!] Chua cai dat thu vien frida. Chay: pip install frida")
    sys.exit(1)

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upgrade_capture_w01.log")
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wlo_items_database.json")

# Tra cứu opcode WLO
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
    0x3E: "WEATHER_EFFECT",
    0x3F: "SCENE_TRIGGER",
    0x4B: "EXPRESSION_EMOTE",
    0x55: "DUNGEON_LOBBY",
    0x59: "UI_INIT_FEATURE",
    0x5C: "STATUS_SYNC",
}

FRIDA_JS = """
var activeSocket = -1;
var cachedBagBase = null;

function scanBag() {
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
                return items;
            }
        } catch(e) {
            cachedBagBase = null;
        }
    }

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
                        var ratio50 = count50 / cnt;
                        if (ratio50 < 0.70) {
                            candidates.push({base: base, count: cnt, items: items});
                        }
                    }
                }
            } catch(e) {}
        }
        if (candidates.length > 0) break;
    }
    if (candidates.length === 0) return {};
    candidates.sort(function(a, b) { return b.base.compare(a.base); });
    cachedBagBase = candidates[0].base;
    return candidates[0].items;
}

function hookRecv(modName) {
    try {
        var mod = Process.getModuleByName(modName);
        if (!mod) return;
        var rPtr = mod.getExportByName('recv');
        if (!rPtr) return;
        Interceptor.attach(rPtr, {
            onEnter: function(args) {
                this.buf = args[1];
                this.sock = args[0].toInt32();
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

rpc.exports = {
    scanbag: function() {
        return scanBag();
    }
};
"""

class WLOStreamDissector:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, raw_bytes):
        decrypted = bytearray(b ^ 0xAD for b in raw_bytes)
        self.buffer.extend(decrypted)
        packets = []
        while len(self.buffer) >= 4:
            if self.buffer[0] != 0xF4 or self.buffer[1] != 0x44:
                idx = self.buffer.find(b'\xF4\x44')
                if idx == -1:
                    self.buffer.clear()
                    break
                self.buffer = self.buffer[idx:]
                if len(self.buffer) < 4:
                    break

            payload_len = struct.unpack("<H", self.buffer[2:4])[0]
            total_pkt_len = 4 + payload_len

            if len(self.buffer) < total_pkt_len:
                break

            pkt_raw = bytes(self.buffer[:total_pkt_len])
            body = pkt_raw[4:]
            self.buffer = self.buffer[total_pkt_len:]

            opcode = body[0] if len(body) > 0 else None
            subcode = body[1] if len(body) > 1 else None
            data = body[2:] if len(body) > 2 else b''

            packets.append((opcode, subcode, data, pkt_raw))
        return packets

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
    ascii_chars = [chr(b) if 32 <= b <= 126 else "" for b in raw_bytes]
    text_ascii = "".join(ascii_chars).strip()
    return text_ascii if len(text_ascii) >= 3 else ""

class UpgradeSniffer:
    def __init__(self, target_pid=10744):
        self.target_pid = target_pid
        self.c2s_dissector = WLOStreamDissector()
        self.s2c_dissector = WLOStreamDissector()
        self.packet_count = 0
        self.start_time = time.time()
        self.running = False
        self.db = {}
        self.load_db()
        self.log_file = open(LOG_FILE, "w", encoding="utf-8")
        self.session = None
        self.script = None

    def load_db(self):
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    self.db = json.load(f)
            except Exception:
                pass

    def log(self, text):
        print(text, flush=True)
        if self.log_file:
            self.log_file.write(text + "\n")
            self.log_file.flush()

    def on_message(self, message, raw_data):
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "send")
        is_send = (dir_name == "send")
        dir_str = "C->S" if is_send else "S->C"
        dissector = self.c2s_dissector if is_send else self.s2c_dissector
        packets = dissector.feed(raw_data)
        for opcode, subcode, data, raw_pkt in packets:
            self.handle_packet(dir_str, opcode, subcode, data, raw_pkt)

    def handle_packet(self, direction, opcode, subcode, data, raw_pkt):
        # Bo qua Ping 0x08 de giu log sach se
        if opcode == 0x08:
            return

        self.packet_count += 1
        elapsed = time.time() - self.start_time
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        op_name = OPCODE_MAP.get(opcode, f"UNKNOWN_0x{opcode:02X}")
        sub_str = f"0x{subcode:02X}" if subcode is not None else "--"
        hex_data = data.hex()
        txt = decode_text(data)
        txt_str = f' | Text: "{txt}"' if txt else ""

        # Ghi chu giai thich nhanh cho mot so opcode quan trong
        note = ""
        if opcode == 0x17:
            if subcode == 0x4B:
                slot = data[0] if len(data) > 0 else 0
                note = f" [USE_ITEM] Dung do o Slot {slot}"
            elif subcode == 0x03:
                slot = data[0] if len(data) > 0 else 0
                note = f" [DISCARD_REQ] Yeu cau vut do Slot {slot}"
            elif subcode == 0x0A:
                s1 = data[0] if len(data) > 0 else 0
                q = data[1] if len(data) > 1 else 0
                s2 = data[2] if len(data) > 2 else 0
                note = f" [MOVE_ITEM] Keo do tu Slot {s1} sang Slot {s2} (SL: {q})"
            elif subcode == 0x05:
                note = f" [SYNC_BAG] Server dong bo lai tui do (Len: {len(data)})"
            elif subcode == 0x09:
                s = data[0] if len(data) > 0 else 0
                q = data[1] if len(data) > 1 else 0
                note = f" [UPDATE_QTY] Server cap nhat Slot {s} con SL: {q}"
        elif opcode == 0x13:
            note = f" [SYNTHESIS/FORGE] Hop thanh / Ren / Cuong hoa"

        line = f"[{timestamp}] [+{elapsed:7.2f}s] [#{self.packet_count:<5}] {direction} Op:0x{opcode:02X} ({op_name:<18}) Sub:{sub_str:<4} Len:{len(data)+2:<4} | Hex: {hex_data}{txt_str}{note}"
        self.log(line)

    def snapshot_bag(self, label="SNAPSHOT"):
        try:
            items = self.script.exports_sync.scanbag()
            self.log(f"\n{'='*70}\n[BAG {label}] Thoi diem: {datetime.now().strftime('%H:%M:%S')} - Tong so o co do: {len(items)}\n{'-'*70}")
            self.log(f"{'Slot':<6} | {'ID Dec':<8} | {'ID Hex':<8} | {'Qty':<4} | {'Ten vat pham':<30}")
            self.log(f"{'-'*70}")
            for s_str, info in sorted(items.items(), key=lambda x: int(x[0])):
                slot = int(s_str)
                code = info["code"]
                qty = info["qty"]
                hex_code = f"0x{code:04X}"
                name = self.db.get(hex_code, {}).get("name", "(Chua dat ten)")
                self.log(f"{slot:<6} | {code:<8} | {hex_code:<8} | {qty:<4} | {name:<30}")
            self.log(f"{'='*70}\n")
            return items
        except Exception as e:
            self.log(f"[!] Loi khi snapshot bag: {e}")
            return {}

    def start(self):
        self.log(f"[*] Dang dinh kem vao PID: {self.target_pid} (alogin-w01)...")
        self.session = frida.attach(self.target_pid)
        self.script = self.session.create_script(FRIDA_JS)
        self.script.on("message", self.on_message)
        self.script.load()
        self.running = True
        self.log(f"[+] Dinh kem thanh cong vao alogin-w01 (PID {self.target_pid})!")
        self.log(f"[*] File ghi log: {LOG_FILE}")
        self.log(f"[*] Bo loc: AN PING 0x08, giu lai toan bo goi tin C->S va S->C voi Full Hex Payload.")
        
        # Chup snapshot ban dau
        self.snapshot_bag("BAN DAU (TRUOC KHI NANG)")
        self.log("[*] SAN SANG! Nguoi choi co the thuc hien thao tac nang do tren alogin-w01 ngay bay gio...\n")

        try:
            while self.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.log("\n[*] Dung lang nghe goi tin...")
        # Chup snapshot cuoi cung
        try:
            self.snapshot_bag("KET THUC (SAU KHI NANG)")
        except Exception:
            pass
        if self.session:
            try:
                self.session.detach()
            except Exception:
                pass
        if self.log_file:
            self.log_file.close()
        self.log("[+] Da ngat ket noi Hook an toan.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, default=10744, help="PID cua alogin-w01")
    args = parser.parse_args()
    sniffer = UpgradeSniffer(target_pid=args.pid)
    sniffer.start()
