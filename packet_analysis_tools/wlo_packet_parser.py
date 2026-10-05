#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO Packet Parser & Analyzer
============================
Công cụ giải mã, bóc tách opcode và cấu trúc dữ liệu gói tin game Wonderland Online (WLO).

Đặc tả gói tin:
- Khóa giải mã: XOR 0xAD toàn bộ gói tin.
- Magic Header: 0xF4 0x44 (Raw trên đường truyền: 0x59 0xE9 sau khi XOR 0xAD).
- Chiều dài dữ liệu (Payload Length): 2 bytes (uint16 Little-Endian).
- Cấu trúc Body:
    - Byte 0: Opcode (Mã lệnh chính)
    - Byte 1: Subcode (Mã lệnh phụ)
    - Byte 2..N: Dữ liệu (Data Payload / Big5 text / Little-Endian integers)
"""

import os
import sys
import struct
import argparse
import subprocess
from collections import defaultdict

# Tranh loi UnicodeEncodeError tren console Windows (cp1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


# Bảng tra cứu Opcode Wonderland Online
OPCODE_MAP = {
    0x01: "SYSTEM_HANDSHAKE",    # Kết nối ban đầu, thông tin server, phiên bản
    0x02: "ACCOUNT_CHAR_LIST",   # Danh sách nhân vật, thông báo server (Have fun, Ver...)
    0x03: "CHANNEL_INFO",        # Thông tin kênh / server list
    0x04: "SKILL_EFFECT",        # Hiệu ứng kỹ năng, âm thanh
    0x05: "LOGIN_AUTH",          # Đăng nhập, khởi tạo nhân vật vào game
    0x06: "COMBAT_ACTION",       # Thao tác chiến đấu (đánh, đỡ, bỏ chạy, dùng kỹ năng)
    0x07: "TEAM_FORMATION",      # Đội hình chiến đấu
    0x08: "PING_HEARTBEAT",      # Giữ kết nối Ping/Pong (Sub 0x01, 0x02)
    0x0A: "TRADE_STALL",         # Giao dịch, mở sạp bán hàng
    0x0B: "INVENTORY_ITEM",      # Túi đồ, trang bị, vật phẩm
    0x0C: "FRIEND_MAIL",         # Bạn bè, thư tín
    0x0E: "PET_ACTION",          # Thao tác thú cưng / bạn đồng hành
    0x0F: "PET_STATUS",          # Chỉ số pet / tình trạng pet
    0x10: "TENT_FURNITURE",      # Lều bạt, đồ nội thất lều
    0x13: "SYNTHESIS_COMPOUND",  # Chế tạo, hợp thành vật phẩm
    0x14: "CHAT_MESSAGE",        # Kênh chat (Thế giới, Đội, Bang, Mật, Hệ thống)
    0x16: "QUEST_MISSION",       # Nhiệm vụ
    0x17: "CHAR_ATTRIBUTES",     # Chỉ số nhân vật (HP, SP, EXP, Level, Tọa độ)
    0x18: "SHORTCUT_BAR",        # Thanh phím tắt
    0x19: "PK_SYSTEM",           # Hệ thống PK / tỉ thí
    0x1A: "GUILD_SYSTEM",        # Bang hội
    0x20: "NPC_DIALOG",          # Đối thoại NPC, lựa chọn nhiệm vụ
    0x23: "MAP_OBJECT",          # Vật thể trên bản đồ (rương, tài nguyên)
    0x32: "PLAYER_MOVE",         # Di chuyển nhân vật (tọa độ đích click chuột)
    0x33: "ENTITY_MOVE_SYNC",    # Đồng bộ di chuyển người chơi khác / NPC
    0x34: "ENTITY_ACTION_SYNC",  # Đồng bộ hành động (ngồi, đứng, xoay hướng)
    0x35: "MAP_WARP_SCENE",      # Chuyển cảnh, đổi map, spawn vị trí
    0x3E: "WEATHER_EFFECT",      # Hiệu ứng thời tiết / ngày đêm
    0x3F: "SCENE_TRIGGER",       # Kích hoạt sự kiện trên map
    0x4B: "EXPRESSION_EMOTE",    # Biểu cảm emote
    0x55: "SYSTEM_FEATURE",      # Tính năng mở rộng hệ thống
    0xB7: "SPECIAL_EXT",         # Giao thức mở rộng proxy / anti-cheat
}

class WLOPacket:
    def __init__(self, frame, rel_time, direction, port, opcode, subcode, data, raw_decrypted):
        self.frame = frame
        self.time = rel_time
        self.direction = direction
        self.port = port
        self.opcode = opcode
        self.subcode = subcode
        self.data = data
        self.raw_decrypted = raw_decrypted
        self.op_name = OPCODE_MAP.get(opcode, f"UNKNOWN_0x{opcode:02X}") if opcode is not None else "NO_OPCODE"

    def get_text_preview(self):
        """Thử giải mã chuỗi Big5 hoặc ASCII từ payload."""
        if not self.data:
            return ""
        try:
            # Thử decode Big5 (bảng mã chuẩn của WLO)
            text = self.data.decode("big5")
            filtered = "".join([c for c in text if c.isprintable()])
            if len(filtered) >= 2:
                return filtered
        except Exception:
            pass
        
        # Thử chuỗi ASCII
        ascii_chars = [chr(c) if 32 <= c <= 126 else "" for c in self.data]
        text_ascii = "".join(ascii_chars).strip()
        return text_ascii if len(text_ascii) >= 3 else ""

    def __str__(self):
        sub_str = f"0x{self.subcode:02X}" if self.subcode is not None else "--"
        text = self.get_text_preview()
        text_part = f' | "{text}"' if text else ""
        hex_data = self.data.hex()[:32]
        if len(self.data) > 16:
            hex_data += "..."
        return f"[{self.time:8.3f}s] [F:{self.frame:<5}] {self.direction:<3} (Port {self.port}) " \
               f"Op:0x{self.opcode:02X} ({self.op_name:<18}) Sub:{sub_str:<4} Len:{len(self.data)+2:<4} | Hex:{hex_data}{text_part}"

class WLOStreamDissector:
    """Tái ghép luồng TCP và giải mã gói tin WLO."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, raw_hex_bytes):
        # Giải mã XOR 0xAD
        decrypted = bytearray(b ^ 0xAD for b in raw_hex_bytes)
        self.buffer.extend(decrypted)

        packets = []
        while len(self.buffer) >= 4:
            # Tìm header magic 0xF4 0x44
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

def parse_pcap(pcap_path, tshark_path=r"C:\Program Files\Wireshark\tshark.exe"):
    if not os.path.isfile(pcap_path):
        print(f"[!] File khong ton tai: {pcap_path}")
        return []

    cmd = [
        tshark_path, "-r", pcap_path,
        "-Y", "tcp.payload and (tcp.port == 6414 or tcp.port == 6416)",
        "-T", "fields",
        "-e", "frame.number",
        "-e", "frame.time_relative",
        "-e", "ip.src",
        "-e", "tcp.srcport",
        "-e", "ip.dst",
        "-e", "tcp.dstport",
        "-e", "tcp.payload"
    ]

    print(f"[*] Dang doc goi tin tu file: {pcap_path} ...")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if res.returncode != 0:
        print(f"[!] Loi khi chay tshark: {res.stderr}")
        return []

    lines = [l for l in res.stdout.strip().split("\n") if l.strip()]
    c2s_dissector = WLOStreamDissector()
    s2c_dissector = WLOStreamDissector()

    all_packets = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        frame, rel_time, s_ip, s_port, d_ip, d_port, payload_hex = parts[:7]
        rel_time = float(rel_time)
        frame = int(frame)

        is_c2s = (d_port in ("6414", "6416"))
        direction = "C->S" if is_c2s else "S->C"
        port = int(d_port) if is_c2s else int(s_port)
        dissector = c2s_dissector if is_c2s else s2c_dissector

        raw_bytes = bytes.fromhex(payload_hex)
        pkts = dissector.feed(raw_bytes)

        for opcode, subcode, data, raw_dec in pkts:
            all_packets.append(WLOPacket(
                frame=frame,
                rel_time=rel_time,
                direction=direction,
                port=port,
                opcode=opcode,
                subcode=subcode,
                data=data,
                raw_decrypted=raw_dec
            ))

    return all_packets

def print_summary(packets):
    print("\n" + "="*80)
    print(f" THONG KE GOI TIN WLO (Tong cong: {len(packets)} goi tin da boc tach)")
    print("="*80)
    stats = defaultdict(lambda: {"count": 0, "dirs": set(), "subcodes": defaultdict(int), "total_bytes": 0})
    for p in packets:
        if p.opcode is None:
            continue
        stats[p.opcode]["count"] += 1
        stats[p.opcode]["dirs"].add(p.direction)
        stats[p.opcode]["total_bytes"] += len(p.data) + 2
        if p.subcode is not None:
            stats[p.opcode]["subcodes"][p.subcode] += 1

    print(f"{'Opcode':<6} | {'Ten chuc nang':<22} | {'Huong':<7} | {'So luong':<8} | {'Chi tiet Subcode'}")
    print("-" * 80)
    for op, s in sorted(stats.items(), key=lambda x: -x[1]["count"]):
        name = OPCODE_MAP.get(op, "UNKNOWN")
        dirs = "/".join(sorted(s["dirs"]))
        sub_list = [f"0x{k:02X}({v})" for k, v in sorted(s["subcodes"].items())[:6]]
        if len(s["subcodes"]) > 6:
            sub_list.append(f"...+{len(s['subcodes'])-6}")
        sub_str = ", ".join(sub_list)
        print(f"0x{op:02X}   | {name:<22} | {dirs:<7} | {s['count']:<8} | {sub_str}")
    print("="*80 + "\n")

def main():
    parser = argparse.ArgumentParser(description="WLO Packet Dissector & Opcode Analyzer")
    parser.add_argument("-f", "--file", default=r"g:\WLOI_beta\WLOI\captures\game_traffic_20260908_192209.pcapng", help="Duong dan file pcapng")
    parser.add_argument("-o", "--opcode", type=lambda x: int(x, 0), default=None, help="Loc theo Opcode (VD: 0x14 hoac 20)")
    parser.add_argument("-d", "--dir", choices=["C->S", "S->C"], default=None, help="Loc theo chieu gui (C->S hoac S->C)")
    parser.add_argument("-n", "--limit", type=int, default=100, help="Gioi han so goi tin hien thi (mac dinh: 100, 0 la tat ca)")
    parser.add_argument("--save", default=None, help="Luu ket qua log vao file txt")
    parser.add_argument("--summary", action="store_true", help="Chi hien thi bang thong ke Opcode")
    parser.add_argument("--no-ping", action="store_true", help="An cac goi tin Ping/Heartbeat (0x08)")

    args = parser.parse_args()

    packets = parse_pcap(args.file)
    if not packets:
        print("[!] Khong tim thay goi tin nao hop le.")
        return

    print_summary(packets)

    if args.summary:
        return

    # Loc goi tin
    filtered = packets
    if args.opcode is not None:
        filtered = [p for p in filtered if p.opcode == args.opcode]
    if args.dir is not None:
        filtered = [p for p in filtered if p.direction == args.dir]
    if args.no_ping:
        filtered = [p for p in filtered if p.opcode != 0x08]

    print(f"[*] Hien thi {len(filtered)} goi tin (gioi han {args.limit if args.limit > 0 else 'tat ca'}):")
    output_lines = []
    count = 0
    for p in filtered:
        line = str(p)
        output_lines.append(line)
        print(line)
        count += 1
        if args.limit > 0 and count >= args.limit:
            break

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write("\n".join(output_lines))
        print(f"\n[+] Da luu {len(output_lines)} dong log vao: {args.save}")

if __name__ == "__main__":
    main()
