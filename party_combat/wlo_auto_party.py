#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO AUTO PARTY BOT / MANAGER
============================
Tự động thiết lập tổ đội (Auto-Invite & Auto-Accept) cho 4 tài khoản:
- aloginF02 (Đội trưởng: 0x00002EC8)
- alogin-F04 (Thành viên 1: 0x00002ECB)
- alogin-W03 (Thành viên 2)
- alogin-W04 (Thành viên 3)

Quy trình tự động:
1. Đính kèm Frida vào cả 4 cửa sổ game.
2. Thiết lập bộ lọc chặn & tự động phản hồi gói Op: 0x0D (Party):
   - Khi alogin-W03 hoặc alogin-W04 nhận được lời mời: Tự động gửi Sub: 0x03 [0x01, LeaderID] trong 0.04s.
   - Khi aloginF02 nhận được yêu cầu xin vào nhóm: Tự động gửi Sub: 0x03 [0x01, ApplicantID] trong 0.04s.
   - Cho phép bấm phím nóng [1] trên console để aloginF02 tự động bắn lệnh mời W03 & W04,
     hoặc phím [2] để W03 & W04 tự động bắn lệnh xin vào nhóm của aloginF02!
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

# Mã nhân vật đã biết
KNOWN_CHAR_IDS = {
    "aloginF02": 0x00002EC8,   # 11976 (c8 2e 00 00)
    "alogin-F04": 0x00002ECB,  # 11979 (cb 2e 00 00)
}

FRIDA_PARTY_JS = """
var activeSocket = -1;
var isInjected = false;

var ws2 = Process.getModuleByName('ws2_32.dll');
var sendPtr = ws2 ? ws2.getExportByName('send') : null;
var sendFunc = sendPtr ? new NativeFunction(sendPtr, 'int', ['int', 'pointer', 'int', 'int']) : null;

function hookMod(modName) {
    try {
        var mod = Process.getModuleByName(modName);
        if (!mod) return;
        var rPtr = mod.getExportByName('recv');
        if (rPtr) {
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
        }
        var sPtr = mod.getExportByName('send');
        if (sPtr) {
            Interceptor.attach(sPtr, {
                onEnter: function(args) {
                    var sock = args[0].toInt32();
                    if (sock > 0) activeSocket = sock;
                    if (isInjected) return;
                    var len = args[2].toInt32();
                    if (len > 0) {
                        try {
                            var buf = args[1].readByteArray(len);
                            send({dir: 'send', len: len, sock: sock}, buf);
                        } catch(e) {}
                    }
                }
            });
        }
    } catch(e) {}
}

hookMod('wsock32.dll');
hookMod('ws2_32.dll');

function doSendRaw(hexBytes) {
    if (activeSocket <= 0) {
        return {success: false, error: "Chưa có socket active"};
    }
    if (!sendFunc) {
        return {success: false, error: "Không tìm thấy hàm send trong ws2_32.dll"};
    }
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
        return {success: true, ret: ret};
    } catch(e) {
        isInjected = false;
        return {success: false, error: e.toString()};
    }
}

rpc.exports = {
    getsocket: function() { return activeSocket; },
    sendraw: function(hexBytes) { return doSendRaw(hexBytes); }
};
"""

def pack_wlo_packet(body_bytes):
    """Đóng gói Magic Header 0xF4 0x44, Length LE và XOR 0xAD toàn bộ."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain_packet = header + body_bytes
    return bytes(b ^ 0xAD for b in plain_packet)

class PartyClientNode:
    def __init__(self, name, proc, manager):
        self.name = name
        self.proc = proc
        self.pid = proc.pid
        self.manager = manager
        self.char_id = KNOWN_CHAR_IDS.get(name, None)
        self.c2s_buf = bytearray()
        self.s2c_buf = bytearray()
        self.session = None
        self.script = None
        self.active_socket = -1

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

    def send_packet(self, body_bytes):
        enc = pack_wlo_packet(body_bytes)
        try:
            res = self.script.exports_sync.sendraw(enc.hex())
            return res
        except Exception as e:
            return {"success": False, "error": str(e)}

    def accept_party(self, partner_id):
        """Gửi lệnh C->S Op: 0x0D Sub: 0x03 [0x01, PartnerID] để chấp thuận vào nhóm."""
        body = bytes([0x0D, 0x03, 0x01]) + struct.pack("<I", partner_id)
        res = self.send_packet(body)
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{now}] [{self.name}] ★ ĐÃ TỰ ĐỘNG CHẤP THUẬN VÀO NHÓM CỦA ID 0x{partner_id:08X}! | Kết quả: {res}", flush=True)

    def request_join_or_invite(self, target_id):
        """Gửi lệnh C->S Op: 0x0D Sub: 0x01 [TargetID] để Mời hoặc Xin vào nhóm."""
        body = bytes([0x0D, 0x01]) + struct.pack("<I", target_id)
        res = self.send_packet(body)
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{now}] [{self.name}] -> Đã gửi yêu cầu tổ đội tới ID 0x{target_id:08X}! | Kết quả: {res}", flush=True)

    def on_message(self, message, raw_data):
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "recv")
        sock = payload.get("sock", -1)
        if sock > 0:
            self.active_socket = sock

        is_send = (dir_name == "send")
        buffer = self.c2s_buf if is_send else self.s2c_buf
        packets = self.feed_dissector(raw_data, buffer)

        for opcode, subcode, data, raw_pkt in packets:
            now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
            # Bắt gói tin tổ đội (Op: 0x0D)
            if opcode == 0x0D:
                direction = "C->S" if is_send else "S->C"
                
                # Server gửi lời mời hoặc yêu cầu vào nhóm: S->C Op: 0x0D Sub: 0x01 [Sender_ID]
                if direction == "S->C" and subcode == 0x01 and len(data) >= 4:
                    sender_id = struct.unpack("<I", data[:4])[0]
                    print(f"\n[{now_str}] [{self.name}] [NHẬN YÊU CẦU TỔ ĐỘI] từ ID: 0x{sender_id:08X} (Dec: {sender_id})", flush=True)
                    # Nếu là thành viên (W03, W04) hoặc Đội trưởng (F02) -> Tự động chấp thuận ngay!
                    time.sleep(0.05)
                    self.accept_party(sender_id)

                # Server xác nhận chấp thuận: S->C Op: 0x0D Sub: 0x03 [0x01, Member_ID]
                elif direction == "S->C" and subcode == 0x03 and len(data) >= 5:
                    status = data[0]
                    mem_id = struct.unpack("<I", data[1:5])[0]
                    print(f"[{now_str}] [{self.name}] [XÁC NHẬN] Thành viên 0x{mem_id:08X} đã vào nhóm (Status: {status})!", flush=True)

                # Server đồng bộ cặp thành viên: S->C Op: 0x0D Sub: 0x05 [Member_ID, Leader_ID]
                elif direction == "S->C" and subcode == 0x05 and len(data) >= 8:
                    mem_id = struct.unpack("<I", data[:4])[0]
                    lead_id = struct.unpack("<I", data[4:8])[0]
                    print(f"[{now_str}] [{self.name}] [ĐỒNG BỘ ĐỘI HÌNH] Thành viên: 0x{mem_id:08X} | Đội trưởng: 0x{lead_id:08X}", flush=True)

                # Server đồng bộ thanh máu & giao diện: S->C Op: 0x0D Sub: 0x06
                elif direction == "S->C" and subcode == 0x06 and len(data) >= 9:
                    mem_id = struct.unpack("<I", data[:4])[0]
                    lead_id = struct.unpack("<I", data[5:9])[0]
                    print(f"[{now_str}] [{self.name}] [CẬP NHẬT TỔ ĐỘI] Thành viên 0x{mem_id:08X} đang ở trong đội của 0x{lead_id:08X} ★", flush=True)

    def start(self):
        dev = frida.get_local_device()
        self.session = dev.attach(self.pid)
        self.script = self.session.create_script(FRIDA_PARTY_JS)
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

class AutoPartyManager:
    def __init__(self):
        self.nodes = {}

    def scan_and_attach(self):
        dev = frida.get_local_device()
        procs = dev.enumerate_processes()
        
        target_names = ["aloginf02", "alogin-f04", "alogin-w03", "alogin-w04"]
        for p in procs:
            plow = p.name.lower()
            for t in target_names:
                if t in plow:
                    # Gán tên chuẩn
                    std_name = "aloginF02" if "f02" in t else ("alogin-F04" if "f04" in t else ("alogin-W03" if "w03" in t else "alogin-W04"))
                    if std_name not in self.nodes:
                        node = PartyClientNode(std_name, p, self)
                        try:
                            node.start()
                            self.nodes[std_name] = node
                            print(f"[+] Đã hook thành công: {std_name:<12} (PID: {p.pid})", flush=True)
                        except Exception as e:
                            print(f"[!] Lỗi khi hook {std_name} (PID {p.pid}): {e}", flush=True)

    def stop_all(self):
        for n in self.nodes.values():
            n.stop()
        print("[*] Đã ngắt hook toàn bộ tiến trình an toàn.", flush=True)

def main():
    print("=" * 80, flush=True)
    print("      WLO AUTO PARTY MANAGER - TỰ ĐỘNG THIẾT LẬP TỔ ĐỘI 4 CLIENT", flush=True)
    print("=" * 80, flush=True)
    print("[*] Đang quét các cửa sổ game aloginF02, alogin-F04, alogin-W03, alogin-W04...", flush=True)

    mgr = AutoPartyManager()
    mgr.scan_and_attach()

    if not mgr.nodes:
        print("[!] Không tìm thấy tiến trình nào phù hợp. Thoát.", flush=True)
        sys.exit(1)

    print("\n" + "=" * 80, flush=True)
    print("  ★ TÍNH NĂNG TỰ ĐỘNG ĐANG BẬT:", flush=True)
    print("    1. Auto-Accept 100%: Khi aloginF02 mời W03/W04 -> W03/W04 tự đồng ý trong 0.05s!")
    print("    2. Auto-Accept 100%: Khi W03/W04 xin vào đội -> aloginF02 tự duyệt trong 0.05s!")
    print("=" * 80, flush=True)
    print("\n[HƯỚNG DẪN ĐIỀU KHIỂN]:")
    print("  • Nhập [1] + Enter: alogin-W03 & alogin-W04 chủ động gửi lệnh XIN VÀO NHÓM của aloginF02.")
    print("  • Nhập [2] + Enter: Kiểm tra trạng thái socket và nhân vật.")
    print("  • Nhập [0] hoặc Ctrl+C: Thoát ứng dụng.\n", flush=True)

    leader_id = KNOWN_CHAR_IDS["aloginF02"]  # 0x00002EC8

    try:
        while True:
            cmd = input(">>> Nhập lệnh [1: Xin vào nhóm | 2: Kiểm tra | 0: Thoát]: ").strip()
            if cmd == "0":
                break
            elif cmd == "1":
                print("\n[*] Đang gửi lệnh xin gia nhập tổ đội của aloginF02 (0x2EC8)...", flush=True)
                for w_name in ["alogin-W03", "alogin-W04"]:
                    if w_name in mgr.nodes:
                        node = mgr.nodes[w_name]
                        node.request_join_or_invite(leader_id)
                    else:
                        print(f"[!] {w_name} chưa được hook!", flush=True)
                print("[*] Đã gửi lệnh xong. Đang chờ phản hồi từ Server...\n", flush=True)
            elif cmd == "2":
                print("\n--- TRẠNG THÁI HIỆN TẠI ---", flush=True)
                for name, node in mgr.nodes.items():
                    print(f"  • {name:<12}: PID={node.pid}, ActiveSocket={node.active_socket}", flush=True)
                print("---------------------------\n", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        mgr.stop_all()

if __name__ == "__main__":
    main()
