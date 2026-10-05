#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
WLO AUTO PARTY DUNGEON HUB - QUẢN LÝ 4 PHỤ BẢN TỔ ĐỘI TỰ ĐỘNG
=============================================================================
Tự động hóa toàn diện quy trình chạy 4 Phụ Bản tổ đội:
  1. Phụ bản 30039 (0x7557) - 5 Ải
  2. Phụ bản 30025 (0x7549) - 4 Ải
  3. Phụ bản 30021 (0x7545) - 9 Ải
  4. Phụ bản 30013 (0x753D) - 9 Ải (Boss Cuối)

Tính năng chính:
  - Tự động quét và kết nối Frida đồng thời cả 4 client (1 Leader + 3 Members).
  - Tự động mở sảnh, bắt Room ID và kéo toàn bộ thành viên vào sảnh (Op 0x55).
  - Tự động lập tổ đội khi vào bản đồ phụ bản (Op 0x0D).
  - Tự động di chuyển chuẩn tọa độ và kích hoạt đối thoại NPC từng ải.
  - Logic chiến đấu thông minh theo yêu cầu người dùng:
      * Pet của bgdf02, bgdf04, bgdw01, sincospro: Dùng chiêu 043b (nhắm hàng 2 & 3: vị trí 2, 3, 6, 7).
      * Toàn bộ pet còn lại: Dùng chiêu phòng thủ 75ea.
      * Toàn bộ nhân vật (kể cả F04, bgdf02, bgdw01, sincospro,...): Dùng chiêu phòng thủ 75ea.
  - Tự động nhận thưởng cho từng thành viên sau khi vượt qua phụ bản.
  - Chế độ chạy liên hoàn 4 phụ bản hoặc chạy đơn lẻ từng phụ bản.
=============================================================================
"""

import os
import sys
import time
import json
import queue
import struct
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# Thiết lập UTF-8 console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

try:
    import frida
except ImportError:
    print("[!] Chưa cài đặt frida. Vui lòng chạy: pip install frida")
    sys.exit(1)

# Giao diện Theme Catppuccin Mocha / Dark
THEME = {
    "bg_dark": "#181825",
    "bg_card": "#1e1e2e",
    "bg_input": "#313244",
    "text_light": "#cdd6f4",
    "text_muted": "#a6adc8",
    "primary": "#89b4fa",
    "green": "#a6e3a1",
    "red": "#f38ba8",
    "orange": "#fab387",
    "yellow": "#f9e2af",
    "purple": "#cba6f7",
    "cyan": "#94e2d5",
    "border": "#45475a",
}

FONT_FAMILY = "Segoe UI"
FONT_TITLE = (FONT_FAMILY, 13, "bold")
FONT_HEADER = (FONT_FAMILY, 10, "bold")
FONT_BODY = (FONT_FAMILY, 9)
FONT_CONSOLE = ("Consolas", 9)

# Kỹ năng định nghĩa chuẩn 4 bytes (Little Endian) theo Cursed Palace & Tháp 29 Tầng
SKILL_DEFEND = bytes.fromhex("75ea0000")        # Phòng thủ (Target chính mình)
SKILL_FIRE_1F3B = bytes.fromhex("1f3b0000")     # Chiêu Hỏa của Char (Hỏa Long Kích)
SKILL_PET_FIRE_043B = bytes.fromhex("043b0000") # Chiêu sát thương của Pet Hỏa (043b)

# Đường dẫn file log vĩnh viễn
LOG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "party_dungeon_run.log")
_LOG_LOCK = threading.Lock()

def log_to_file(level, message):
    """Ghi nhật ký vĩnh viễn vào file party_dungeon_run.log kèm timestamp chi tiết và flush tức thì."""
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"[{now_str}] [{level:<7}] {message}\n"
        with _LOG_LOCK:
            with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
    except Exception:
        pass

# Frida Script dùng chung (Kế thừa từ run_dungeon_30009)
FRIDA_JS = """
var activeSocket = -1;
var isInjected = false;

var ws2 = Process.getModuleByName('ws2_32.dll');
var sendPtr = ws2 ? ws2.getExportByName('send') : null;
var getpeernamePtr = ws2 ? ws2.getExportByName('getpeername') : null;
var sendFunc = sendPtr ? new NativeFunction(sendPtr, 'int', ['int', 'pointer', 'int', 'int']) : null;
var getpeernameFunc = getpeernamePtr ? new NativeFunction(getpeernamePtr, 'int', ['pointer', 'pointer', 'pointer']) : null;

function getSocketPort(sock) {
    if (!getpeernameFunc || sock <= 0) return -1;
    var sockaddr = Memory.alloc(32);
    var lenPtr = Memory.alloc(4);
    lenPtr.writeU32(32);
    var ret = getpeernameFunc(ptr(sock), sockaddr, lenPtr);
    if (ret === 0) {
        return (sockaddr.add(2).readU8() << 8) | sockaddr.add(3).readU8();
    }
    return -1;
}

function scanActiveSocket() {
    if (activeSocket > 0 && getSocketPort(activeSocket) === 6414) {
        return activeSocket;
    }
    if (!getpeernameFunc) return -1;
    
    // Pass 1: Quét ưu tiên tìm chính xác port game 6414
    for (var h = 4; h < 65536; h += 4) {
        var p = getSocketPort(h);
        if (p === 6414) {
            activeSocket = h;
            return h;
        }
    }
    // Pass 2: Fallback nếu port game là port khác > 1024
    for (var h = 4; h < 65536; h += 4) {
        var p = getSocketPort(h);
        if (p > 1024) {
            activeSocket = h;
            return h;
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
                if (sock > 0) {
                    if (activeSocket <= 0 || getSocketPort(sock) === 6414) {
                        activeSocket = sock;
                    }
                }
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
                if (sock > 0) {
                    if (activeSocket <= 0 || getSocketPort(sock) === 6414) {
                        activeSocket = sock;
                    }
                }
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
    } catch(e) {}
}

hookRecv('wsock32.dll');
hookRecv('ws2_32.dll');
hookSend('ws2_32.dll');
scanActiveSocket();

function doSendRaw(hexBytes) {
    if (activeSocket <= 0) scanActiveSocket();
    if (activeSocket <= 0) return {success: false, error: "Chưa tìm thấy active socket"};
    if (!sendFunc) return {success: false, error: "Không tìm thấy send trong ws2_32.dll"};

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

rpc.exports = {
    getsocket: function() { return scanActiveSocket(); },
    sendraw: function(hex) { return doSendRaw(hex); }
};
"""

def pack_wlo_packet(body_bytes):
    """Đóng gói Magic Header 0xF4 0x44, uint16 LE Length và XOR 0xAD."""
    header = struct.pack("<HH", 0x44F4, len(body_bytes))
    plain = header + body_bytes
    return bytes(b ^ 0xAD for b in plain)


def parse_wlo_packets(raw_bytes, buffer):
    """Bóc tách packet WLO (Magic 0xF4 0x44, 2B LE length, XOR 0xAD)."""
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

# =============================================================================
# DỮ LIỆU ĐỊNH NGHĨA 4 PHỤ BẢN
# =============================================================================
DUNGEON_CONFIGS = {
    "30039": {
        "id": 30039,
        "name": "Phụ bản 30039 (5 Ải)",
        "hex_id": "577500",
        "stages_count": 5,
        "reward_item": "Tinh Tú Lệnh 1 (0xCC82) x5",
    },
    "30025": {
        "id": 30025,
        "name": "Phụ bản 30025 (4 Ải)",
        "hex_id": "497500",
        "stages_count": 4,
        "reward_item": "Tinh Tú Lệnh 2 (0xCC54) x5",
    },
    "30021": {
        "id": 30021,
        "name": "Phụ bản 30021 (9 Ải)",
        "hex_id": "457500",
        "stages_count": 9,
        "reward_item": "Tinh Tú Lệnh 3 (0xCBED) x5",
    },
    "30013": {
        "id": 30013,
        "name": "Phụ bản 30013 (9 Ải - Boss)",
        "hex_id": "3d7500",
        "stages_count": 9,
        "reward_item": "Tinh Tú Lệnh 4 (0xCC78) x5",
    }
}

class ClientNode:
    """Đại diện cho 1 client WLO được Frida hook."""
    def __init__(self, pid, name, is_leader=False):
        self.pid = pid
        self.name = name
        self.display_name = name.replace("alogin-", "").replace(".exe", "").lower()
        self.is_leader = is_leader
        self.session = None
        self.script = None
        self.active_socket = -1
        self.c2s_buf = bytearray()
        self.s2c_buf = bytearray()
        self.char_id = 0
        self.in_combat = False
        self.combat_row = 1 if is_leader else 2
        self.party_members = set()
        self.is_in_party = is_leader
        self.current_map = None
        self.ready_lobby = False
        self.last_room_id = None
        self.enemy_positions = [] # [(col, row)]
        self.rewards_received = []
        self.map_loaded_time = 0

        # Dự đoán trước Char ID từ tên tiến trình
        clow = self.name.lower()
        if "f02" in clow:
            self.char_id = 0x00002EC8
        elif "f04" in clow:
            self.char_id = 0x00002ECB
        elif "w01" in clow:
            self.char_id = 0x00002EC9
        elif "w03" in clow:
            self.char_id = 0x00002EE3
        elif "w04" in clow:
            self.char_id = 0x00002EE4
        elif "wi01" in clow:
            self.char_id = 0x00002EE8
        elif "sincospro" in clow:
            self.char_id = 0x00002ECC
        elif "f032" in clow:
            self.char_id = 0x00002ECD
        elif "f03" in clow:
            self.char_id = 0x00002ECA

    def connect(self, dev):
        try:
            self.session = dev.attach(self.pid)
            self.script = self.session.create_script(FRIDA_JS)
            self.script.on("message", self._on_message)
            self.script.load()

            # Quét tìm socket ngay khi đính kèm
            try:
                sock = self.script.exports_sync.getsocket()
                if sock and sock > 0:
                    self.active_socket = sock
            except Exception:
                pass

            return True
        except Exception as e:
            print(f"[!] Lỗi kết nối Frida {self.name} (PID {self.pid}): {e}")
            return False

    def refresh_socket(self):
        """Quét và làm mới socket mạng đang hoạt động."""
        if not self.script:
            return -1
        try:
            sock = self.script.exports_sync.getsocket()
            if sock and sock > 0:
                self.active_socket = sock
            return self.active_socket
        except Exception:
            return -1

    def disconnect(self):
        try:
            if self.script:
                self.script.unload()
            if self.session:
                self.session.detach()
        except Exception:
            pass

    def send_packet(self, data_bytes):
        """Gửi packet WLO (tự động bọc Magic Header 0xF4 0x44 và mã hóa XOR 0xAD)."""
        if not self.script:
            return False

        # Tách bỏ header cũ nếu đã có
        if len(data_bytes) >= 4 and data_bytes[0] == 0xF4 and data_bytes[1] == 0x44:
            body_bytes = data_bytes[4:]
        else:
            body_bytes = data_bytes

        enc = pack_wlo_packet(body_bytes)
        try:
            res = self.script.exports_sync.sendraw(enc.hex())
            if isinstance(res, dict) and res.get("success"):
                if res.get("sock") and res.get("sock") > 0:
                    self.active_socket = res.get("sock")
                return True
            else:
                # Thử refresh socket và gửi lại 1 lần
                self.refresh_socket()
                res = self.script.exports_sync.sendraw(enc.hex())
                if isinstance(res, dict) and res.get("success"):
                    if res.get("sock") and res.get("sock") > 0:
                        self.active_socket = res.get("sock")
                    return True
                return False
        except Exception:
            return False

    def _on_message(self, message, raw_data):
        if not raw_data:
            return
        payload = message.get("payload", {})
        dir_name = payload.get("dir", "recv")
        sock = payload.get("sock", -1)
        if sock > 0:
            self.active_socket = sock

        is_send = (dir_name == "send")
        buf = self.c2s_buf if is_send else self.s2c_buf
        packets = parse_wlo_packets(raw_data, buf)

        for opcode, subcode, data, raw_pkt in packets:
            self._handle_packet(dir_name, opcode, subcode, data)

    def _handle_packet(self, direction, opcode, subcode, data):
        # 1. Nhận diện ID nhân vật (Chỉ khi chưa có Char ID)
        if not self.char_id:
            if opcode == 0x05 and subcode == 0x08 and len(data) >= 4:
                cid = struct.unpack("<I", data[:4])[0]
                if cid > 1000:
                    self.char_id = cid
            elif opcode == 0x05 and subcode == 0x1E and len(data) >= 10:
                cid = struct.unpack("<I", data[6:10])[0]
                if cid > 1000:
                    self.char_id = cid
            elif opcode == 0x17 and subcode == 0x4D and len(data) >= 4:
                cid = struct.unpack("<I", data[:4])[0]
                if cid > 1000:
                    self.char_id = cid

        # 2. Sảnh phụ bản (Room ID 2 bytes)
        if opcode == 0x55:
            if subcode == 0x08 and len(data) >= 3:
                self.last_room_id = data[1:3].hex()
            elif subcode == 0x0B and len(data) >= 3:
                self.last_room_id = data[1:3].hex()
            elif subcode == 0x05 and len(data) >= 4:
                self.last_room_id = data[2:4].hex()
            elif subcode == 0x07 and len(data) >= 8:
                self.last_room_id = data[6:8].hex()
            elif subcode == 0x04 and len(data) >= 2:
                self.last_room_id = data[:2].hex()
            elif subcode == 0x01 and len(data) >= 5:
                # Gói danh sách phòng sảnh: data[0]=page, data[1]=max_page, data[2]=count
                # data[3:5] = room_id (2 bytes)
                room_count = data[2]
                if room_count > 0 and len(data) >= 6:
                    self.last_room_id = data[3:5].hex()

        # 3. Quản lý Tổ đội (Opcode 0x0D)
        if opcode == 0x0D:
            if direction == "recv":
                # Nhận thông báo xin vào hoặc mời nhóm (Sub 0x01: <partner_id 4B>)
                if subcode == 0x01 and len(data) >= 4:
                    partner_id = struct.unpack("<I", data[:4])[0]
                    log_to_file("PARTY", f"[{self.name}] Nhận yêu cầu/lời mời tổ đội từ 0x{partner_id:08X} -> Tự động đồng ý (0D 03 01)")
                    self.party_members.add(partner_id)
                    self.is_in_party = True
                    def do_auto_accept(pdata=data[:4]):
                        time.sleep(0.04)
                        self.send_packet(bytes.fromhex("0d0301") + pdata)
                    threading.Thread(target=do_auto_accept, daemon=True).start()

                # Thành viên nhận xác nhận gia nhập thành công (Sub 0x03)
                elif subcode == 0x03 and len(data) >= 5:
                    status = data[0]
                    partner_id = struct.unpack("<I", data[1:5])[0]
                    if status == 1:
                        self.is_in_party = True
                        self.party_members.add(partner_id)
                        log_to_file("PARTY", f"[{self.name}] Xác nhận vào tổ đội thành công với 0x{partner_id:08X} (Sub 0x03)")

                # Cập nhật danh sách thành viên trong nhóm (Sub 0x05)
                elif subcode == 0x05 and len(data) >= 4:
                    self.is_in_party = True
                    for i in range(0, len(data), 4):
                        if i + 4 <= len(data):
                            pid = struct.unpack("<I", data[i:i+4])[0]
                            if pid > 1000:
                                self.party_members.add(pid)
                    log_to_file("PARTY", f"[{self.name}] Cập nhật danh sách đội (Sub 0x05): {[f'0x{m:08X}' for m in self.party_members]}")

                # Thành viên mới gia nhập nhóm / đồng bộ giao diện tổ đội (Sub 0x06)
                elif subcode == 0x06 and len(data) >= 4:
                    self.is_in_party = True
                    # Trích xuất tất cả Char ID hợp lệ trong gói tin Sub 0x06
                    for off in range(0, len(data) - 3):
                        val = struct.unpack("<I", data[off:off+4])[0]
                        if 1000 < val < 0x10000000:
                            self.party_members.add(val)
                    log_to_file("PARTY", f"[{self.name}] Cập nhật danh sách đội (Sub 0x06): {[f'0x{m:08X}' for m in self.party_members]}")

                # Giải tán nhóm hoặc rời nhóm
                elif subcode in (0x02, 0x04, 0x0A, 0x0F):
                    self.party_members.clear()
                    self.is_in_party = False
                    log_to_file("PARTY", f"[{self.name}] Rời nhóm / Giải tán nhóm (Sub 0x{subcode:02X})")

        # Bản đồ / Cảnh mới (Opcode 0x16)
        if opcode == 0x16 and subcode == 0x04:
            self.map_loaded_time = time.time()

        # 4. Chiến đấu (Opcode 0x0B)
        if opcode == 0x0B:
            if subcode in (0xFA, 0x02):
                self.in_combat = True
                # Bóc tách danh sách vị trí quái vật
                self._parse_combat_layout(data)
            elif subcode == 0x00:
                self.in_combat = False
                self.enemy_positions.clear()

        # 4. Nhận thưởng
        if opcode == 0x17 and subcode == 0x06 and len(data) >= 2:
            item_code = struct.unpack("<H", data[:2])[0]
            qty = struct.unpack("<H", data[2:4])[0] if len(data) >= 4 else 1
            if item_code > 0:
                self.rewards_received.append((item_code, qty))

    def _parse_combat_layout(self, data):
        """Bóc tách sơ đồ quái vật từ gói 0x0B Sub 0xFA."""
        self.enemy_positions.clear()
        # Trong WLO 0x0B Sub 0xFA, các entity có cấu trúc slot, row, HP, ID
        # Chúng ta quét vị trí đối thủ ở Cột 1 và Cột 2
        # Cấu trúc mặc định các vị trí đối thủ: Col 1 & 2, Row 1..4
        # Mặc định thêm các vị trí khả dĩ nếu có quái
        for r in [2, 3, 1, 4]:
            self.enemy_positions.append((1, r))
            self.enemy_positions.append((2, r))

# =============================================================================
# ENGINE TỰ ĐỘNG HÓA TỔ ĐỘI
# =============================================================================
class PartyDungeonEngine:
    def __init__(self, app):
        self.app = app
        self.is_running = False
        self.is_paused = False
        self.leader_node = None
        self.member_nodes = []
        self.stage_packets_db = {}
        self._load_stage_packets()

    def _load_stage_packets(self):
        """Nạp database gói tin chi tiết các ải từ full_stage_packets.json."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        json_file = os.path.join(script_dir, "full_stage_packets.json")
        if os.path.exists(json_file):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    self.stage_packets_db = json.load(f)
                print(f"[+] Đã nạp thành công dữ liệu di chuyển & ải từ full_stage_packets.json")
            except Exception as e:
                print(f"[!] Lỗi đọc full_stage_packets.json: {e}")

    def log(self, level, text):
        self.app.log_event(level, text)

    def start_automation(self, mode, loops=1):
        if self.is_running:
            return
        self.is_running = True
        self.is_paused = False
        threading.Thread(target=self._run_thread, args=(mode, loops), daemon=True).start()

    def stop_automation(self):
        self.is_running = False
        self.log("WARNING", "⏹ Tiến trình Auto đã nhận lệnh DỪNG từ người dùng.")

    def _run_thread(self, mode, loops):
        self.log("PRIMARY", f"🚀 KHỞI ĐỘNG TIẾN TRÌNH AUTO TỔ ĐỘI [Chế độ: {mode}] - Số vòng: {loops}")

        dungeon_queue = []
        if mode == "ALL":
            dungeon_queue = ["30039", "30025", "30021", "30013"]
        elif mode in DUNGEON_CONFIGS:
            dungeon_queue = [mode]
        else:
            dungeon_queue = ["30039"]

        current_loop = 0
        while self.is_running and (loops == 0 or current_loop < loops):
            current_loop += 1
            self.log("PRIMARY", f"🔄 === BẮT ĐẦU VÒNG LẶP {current_loop}/{loops if loops > 0 else '∞'} ===")

            for did in dungeon_queue:
                if not self.is_running:
                    break
                dcfg = DUNGEON_CONFIGS[did]
                self.log("PRIMARY", f"\n▶ BƯỚC VÀO: {dcfg['name']} (ID: {did})")
                
                success = self._run_single_dungeon(did, dcfg)
                if not success:
                    self.log("ERROR", f"❌ Không thể hoàn thành {dcfg['name']}. Đang thử xử lý an toàn...")
                    time.sleep(3.0)
                else:
                    self.log("SUCCESS", f"🏆 HOÀN THÀNH TOÀN DIỆN {dcfg['name']}!")
                    time.sleep(4.0)

            if loops > 0 and current_loop >= loops:
                break
            time.sleep(2.0)

        self.is_running = False
        self.log("SUCCESS", "🏁 TẤT CẢ TIẾN TRÌNH AUTO ĐÃ HOÀN TẤT THÀNH CÔNG!")
        self.app.update_run_buttons()

    def _run_single_dungeon(self, did, dcfg):
        """Thực thi trọn gói 1 phụ bản: Sảnh -> Lập nhóm -> Di chuyển & Đánh các ải -> Nhận thưởng -> Thoát."""
        leader = self.leader_node
        if not leader or not leader.script:
            self.log("ERROR", "Leader chưa kết nối Frida!")
            return False

        if leader.active_socket <= 0:
            leader.refresh_socket()

        members = []
        for m in self.member_nodes:
            if m and m.script:
                if m.active_socket <= 0:
                    m.refresh_socket()
                members.append(m)

        # -------------------------------------------------------------
        # BƯỚC 1: SẢNH PHỤ BẢN (LOBBY & TẠO PHÒNG)
        # -------------------------------------------------------------
        self.log("INFO", f"🏛️ [BƯỚC 1] Leader [{leader.name}] đang mở Sảnh và tạo phòng ID {did}...")
        leader.last_room_id = None
        for mem in members:
            mem.last_room_id = None

        # 1. Leader mở sảnh phụ bản và kiểm tra phòng hiện tại hoặc tạo phòng
        leader.send_packet(bytes.fromhex("5501"))
        time.sleep(0.6)

        # Nếu chưa có phòng từ sảnh, Leader gửi lệnh tạo phòng
        if not leader.last_room_id:
            leader.send_packet(bytes.fromhex(f"5503{dcfg['hex_id']}"))
            time.sleep(0.6)

        # 2. Bắt Room ID (từ Leader hoặc bất kỳ Member nào nhận được broadcast)
        room_id_hex = None
        start_wait_room = time.time()
        while time.time() - start_wait_room < 5.0 and self.is_running:
            for node in [leader] + members:
                if node.last_room_id:
                    room_id_hex = node.last_room_id
                    break
            if room_id_hex:
                break
            time.sleep(0.3)

        # Nếu chưa có Room ID, thử gửi lại lệnh tạo phòng
        if not room_id_hex and self.is_running:
            self.log("WARNING", "⚠️ Chưa bắt được Room ID, đang mở lại sảnh và gửi lại lệnh tạo phòng...")
            leader.send_packet(bytes.fromhex("5501"))
            time.sleep(0.5)
            leader.send_packet(bytes.fromhex(f"5503{dcfg['hex_id']}"))
            time.sleep(0.6)
            start_wait_room = time.time()
            while time.time() - start_wait_room < 5.0 and self.is_running:
                for node in [leader] + members:
                    if node.last_room_id:
                        room_id_hex = node.last_room_id
                        break
                if room_id_hex:
                    break
                time.sleep(0.3)

        if not room_id_hex:
            self.log("ERROR", f"❌ Không thể lấy Room ID cho Phụ bản {did}! Vui lòng đảm bảo các client đang đứng ở sảnh phụ bản.")
            return False

        self.log("SUCCESS", f"★ Room ID tạo phòng thành công: 0x{room_id_hex}")

        # 3. Các thành viên vào phòng
        time.sleep(0.5)
        for mem in members:
            self.log("INFO", f"👉 Thành viên [{mem.name}] đang vào phòng 0x{room_id_hex}...")
            mem.send_packet(bytes.fromhex(f"5504{room_id_hex}"))
            time.sleep(0.35)
            mem.send_packet(bytes.fromhex(f"5505{room_id_hex}"))
            time.sleep(0.35)

        time.sleep(1.0)

        # 4. Leader gửi lệnh chat 'go' (0202676f) và toàn đội xác nhận Bắt Đầu vào Dungeon
        self.log("INFO", "💬 Leader bấm 'go' (0202676f) sẵn sàng phòng...")
        leader.send_packet(bytes.fromhex("0202676f"))
        time.sleep(0.6)

        self.log("PRIMARY", "🚀 Tất cả thành viên xác nhận BẮT ĐẦU Phụ Bản (550201)...")
        for mem in members:
            mem.send_packet(bytes.fromhex("550201"))
            time.sleep(0.15)
        leader.send_packet(bytes.fromhex("550201"))

        # Chờ 10 giây để tất cả các client nạp xong bản đồ Dungeon (theo yêu cầu người dùng và wlo_party_gui)
        self.log("INFO", "⏳ Đã bấm 'go' và xuất phát, đang chờ đủ 10 giây để toàn bộ client nạp xong hoàn toàn bản đồ vào trong Dungeon...")
        time.sleep(10.0)

        # -------------------------------------------------------------
        # BƯỚC 2: LẬP TỔ ĐỘI Ở TRONG DUNGEON (PARTY FORMATION IN DUNGEON)
        # -------------------------------------------------------------
        self.log("PRIMARY", "👥 [BƯỚC 2] ĐÃ VÀO TRONG DUNGEON - KIỂM TRA & HOÀN TẤT TỔ ĐỘI...")
        log_to_file("PRIMARY", f"=== [BƯỚC 2] ĐÃ VÀO DUNGEON {did} - BẮT ĐẦU QUY TRÌNH TỔ ĐỘI ===")

        leader_id_bytes = struct.pack("<I", leader.char_id) if leader.char_id > 0 else None
        if not leader_id_bytes:
            self.log("ERROR", f"❌ Không có Char ID của Leader [{leader.name}]! Không thể lập tổ đội.")
            return False

        # Đóng hộp thoại phòng ngừa popup/cutscene làm chặn lời mời
        self.log("INFO", "💬 Đang đóng hộp thoại NPC/Cutscene cho toàn bộ thành viên trước khi kết nạp...")
        for node in [leader] + members:
            node.send_packet(bytes.fromhex("2003"))
            time.sleep(0.08)
            node.send_packet(bytes.fromhex("1406"))
            time.sleep(0.08)
        time.sleep(0.5)

        leader.party_members.add(leader.char_id)

        def is_member_in_party(m):
            return (m.char_id in leader.party_members) or (m.is_in_party and (leader.char_id in m.party_members or len(m.party_members) > 1))

        # Kiểm tra xem tổ đội đã được server tự động kết nạp từ sảnh chưa
        if all(is_member_in_party(m) for m in members):
            self.log("SUCCESS", f"✓ Toàn bộ tổ đội ({len(members) + 1} thành viên) đã tự động kết nạp đầy đủ từ sảnh!")
            log_to_file("SUCCESS", f"Toàn bộ tổ đội tự động kết nạp đầy đủ: {[f'0x{m:08X}' for m in leader.party_members]}")
        else:
            self.log("INFO", f"👥 Bắt đầu quy trình kết nạp tổ đội chuẩn (Tham khảo wlo_party_gui.py)...")
            max_rounds = 5
            for rnd in range(1, max_rounds + 1):
                if not self.is_running:
                    return False
                missing = [m for m in members if not is_member_in_party(m)]
                if not missing:
                    break

                self.log("INFO", f"🔄 [VÒNG LẬP ĐỘI {rnd}/{max_rounds}] Các thành viên còn thiếu: {[m.name for m in missing]}...")

                # Bước A: Từng thành viên chưa trong nhóm gửi yêu cầu 0D 01 tới Leader
                for m in missing:
                    self.log("INFO", f"👉 [{m.name}] gửi lời xin gia nhập nhóm Leader [{leader.name}] (0x{leader.char_id:08X})...")
                    log_to_file("PARTY", f"Thành viên [{m.name}] gửi 0D 01 tới Leader [{leader.name}] (0x{leader.char_id:08X})")
                    m.send_packet(bytes.fromhex("0d01") + leader_id_bytes)
                    time.sleep(0.1)

                time.sleep(0.6)

                # Bước B: Leader phản hồi đồng ý kết nạp (0D 03 01 <mem_id>)
                for m in missing:
                    mem_id_bytes = struct.pack("<I", m.char_id)
                    leader.send_packet(bytes.fromhex("0d0301") + mem_id_bytes)
                    time.sleep(0.1)

                time.sleep(1.2)

                # Bước C: Nếu vẫn còn thiếu, Leader chủ động gửi lời mời 0D 01 tới Member
                still_missing = [m for m in members if not is_member_in_party(m)]
                if still_missing:
                    for m in still_missing:
                        self.log("INFO", f"👑 Leader [{leader.name}] gửi lời mời tổ đội tới [{m.name}] (0x{m.char_id:08X})...")
                        log_to_file("PARTY", f"Leader [{leader.name}] gửi 0D 01 tới [{m.name}] (0x{m.char_id:08X})")
                        leader.send_packet(bytes.fromhex("0d01") + struct.pack("<I", m.char_id))
                        time.sleep(0.1)
                    time.sleep(0.6)
                    for m in still_missing:
                        m.send_packet(bytes.fromhex("0d0301") + leader_id_bytes)
                        time.sleep(0.1)
                    time.sleep(1.2)

        # Xác thực cuối cùng: ĐỦ 100% THÀNH VIÊN
        missing = [m for m in members if not is_member_in_party(m)]
        if missing:
            self.log("ERROR", f"❌ Thiếu thành viên trong tổ đội: {', '.join([m.name for m in missing])}! DỪNG LẠI, TUYỆT ĐỐI KHÔNG ĐI LẺ!")
            log_to_file("ERROR", f"Chưa đủ thành viên: {[m.name for m in missing]}. Dừng tiến trình di chuyển.")
            return False

        self.log("SUCCESS", f"★ ĐÃ HOÀN TẤT KẾT NẠP TOÀN BỘ TỔ ĐỘI ({len(members) + 1} THÀNH VIÊN ĐỦ MẶT)! SẴN SÀNG XUẤT PHÁT.")
        log_to_file("SUCCESS", f"Hoàn tất kết nạp toàn bộ tổ đội ({len(members) + 1} thành viên đủ mặt)!")
        time.sleep(2.0)

        # -------------------------------------------------------------
        # BƯỚC 3: DI CHUYỂN & VƯỢT TỪNG ẢI
        # -------------------------------------------------------------
        stages_data = self.stage_packets_db.get(did, [])
        stages_count = len(stages_data) if stages_data else dcfg["stages_count"]

        for s_idx in range(stages_count):
            if not self.is_running:
                return False

            stage_num = s_idx + 1
            self.log("PRIMARY", f"\n🚩 === [ẢI {stage_num}/{stages_count}] BẮT ĐẦU DI CHUYỂN & KÍCH HOẠT ===")

            st_info = stages_data[s_idx] if s_idx < len(stages_data) else None
            packets_list = st_info.get("packets", []) if st_info else []

            # Lọc bỏ các gói sảnh (55), tổ đội (0D) dư thừa từ capture nếu là Ải 1
            valid_packets = []
            for p in packets_list:
                op = p.get("op", "")
                h = p.get("hex", "")
                if s_idx == 0 and (op in ("55", "0D") or (op == "02" and h == "676f")):
                    continue
                valid_packets.append(p)

            # Tách riêng: pre_packets (mở cổng), move_packets (bước đi op 06), dialog_packets (thoại boss)
            first_06_idx = -1
            last_06_idx = -1
            for i, p in enumerate(valid_packets):
                if p.get("op") == "06":
                    if first_06_idx == -1: first_06_idx = i
                    last_06_idx = i

            if first_06_idx >= 0:
                pre_packets = valid_packets[:first_06_idx]
                move_packets = [p for p in valid_packets[first_06_idx:last_06_idx + 1] if p.get("op") == "06"]
                dialog_packets = valid_packets[last_06_idx + 1:]
            else:
                pre_packets = []
                move_packets = []
                dialog_packets = valid_packets

            def _send_pkt(pkt):
                op_hex = pkt.get("op", "")
                sub_hex = pkt.get("sub", "").replace("0x", "")
                body_hex = pkt.get("hex", "")
                full_hex = op_hex + sub_hex + body_hex
                try:
                    leader.send_packet(bytes.fromhex(full_hex))
                except Exception:
                    pass

            def _trigger_dialog():
                for dp in dialog_packets:
                    if not self.is_running or self._is_party_in_combat():
                        break
                    _send_pkt(dp)
                    time.sleep(0.3)

            stage_cleared = False
            attempt = 0
            max_attempts = 10  # Lặp lại tối đa 10 lần di chuyển lại, TUYỆT ĐỐI không bỏ qua ải

            while self.is_running and not stage_cleared and attempt < max_attempts:
                attempt += 1
                if attempt > 1:
                    self.log("WARNING", f"⚠️ Chưa nhận được tín hiệu combat tại Ải {stage_num}! Đang thực hiện DI CHUYỂN LẠI (Lần thử {attempt}/{max_attempts})...")

                # 1. DI CHUYỂN THEO LỘ TRÌNH
                if move_packets:
                    self.log("INFO", f"🚶 Leader đang di chuyển theo lộ trình ghi nhận ({len(move_packets)} bước)...")
                    for p in move_packets:
                        if not self.is_running:
                            return False
                        if self._is_party_in_combat():
                            # Nếu quái xuất hiện ngay trên đường đi, ngắt bước chân ngay
                            break
                        _send_pkt(p)
                        op_hex = p.get("op", "")
                        if op_hex == "06":
                            time.sleep(0.28) # Pacing bước chân chuẩn WLO
                        else:
                            time.sleep(0.20)

                # Kiểm tra nếu quái xuất hiện khi đang di chuyển
                if self._is_party_in_combat():
                    self.log("WARNING", f"⚔️ [TRẬN ĐÁNH ẢI {stage_num}] Quái vật xuất hiện khi di chuyển! Bắt đầu combat...")
                    self._handle_combat_loop()
                    self.log("SUCCESS", f"🏁 [ẢI {stage_num}] Chiến thắng hoàn tất!")
                    stage_cleared = True
                    time.sleep(2.0)
                    break

                # 2. ĐỢI NHÂN VẬT ĐẾN ĐÍCH
                time.sleep(1.2)

                # 3. KÍCH HOẠT ĐỐI THOẠI
                if dialog_packets:
                    self.log("INFO", f"💬 Gửi lệnh đối thoại/kích hoạt Ải {stage_num}...")
                    _trigger_dialog()

                # 4. CHỜ VÀO TRẬN ĐẤU (TỰ ĐỘNG GỬI LẠI THOẠI SAU MỖI 3.5S)
                self.log("INFO", f"⏳ Đang chờ tín hiệu bắt đầu trận đánh ải {stage_num}...")
                start_w = time.time()
                timeout_w = 12.0
                last_retry_t = start_w

                while (time.time() - start_w) < timeout_w and self.is_running:
                    if self._is_party_in_combat():
                        break
                    # Sau 3.5s chưa vào trận thì thử gửi lại thoại NPC
                    if dialog_packets and (time.time() - last_retry_t) >= 3.5:
                        self.log("INFO", f"🔄 Chưa thấy vào trận sau 3.5s, gửi lại thoại NPC Ải {stage_num}...")
                        _trigger_dialog()
                        last_retry_t = time.time()
                    time.sleep(0.2)

                if self._is_party_in_combat():
                    self.log("WARNING", f"⚔️ [TRẬN ĐÁNH ẢI {stage_num}] Quái vật xuất hiện! Bắt đầu combat...")
                    self._handle_combat_loop()
                    self.log("SUCCESS", f"🏁 [ẢI {stage_num}] Chiến thắng hoàn tất!")
                    stage_cleared = True
                    time.sleep(2.0)
                    break
                else:
                    self.log("WARNING", f"⚠️ Hết thời gian chờ {timeout_w}s không có tín hiệu combat tại Ải {stage_num}!")

            if not stage_cleared:
                self.log("ERROR", f"❌ Không thể kích hoạt trận đánh Ải {stage_num} sau {max_attempts} lần thử di chuyển!")
                return False

        # -------------------------------------------------------------
        # BƯỚC 4: NHẬN THƯỞNG PHỤ BẢN & THOÁT
        # -------------------------------------------------------------
        self.log("PRIMARY", f"\n🎁 [BƯỚC 4] BẮT ĐẦU NHẬN THƯỞNG PHỤ BẢN {did}...")
        self._claim_dungeon_rewards(did)
        time.sleep(3.0)

        return True

    def _is_party_in_combat(self):
        """Kiểm tra xem Leader hoặc bất kỳ Member nào đã vào trạng thái chiến đấu chưa."""
        if self.leader_node and self.leader_node.in_combat:
            return True
        for m in self.member_nodes:
            if m and m.in_combat:
                return True
        return False

    def _wait_for_combat_start(self, timeout_sec=10):
        """Chờ bất kỳ thành viên nào nhận được tín hiệu bắt đầu trận đánh."""
        start_t = time.time()
        while time.time() - start_t < timeout_sec and self.is_running:
            if self._is_party_in_combat():
                return True
            time.sleep(0.2)
        return False

    def _handle_combat_loop(self):
        """Vòng lặp ra chiêu chiến đấu tự động theo đúng logic người dùng yêu cầu."""
        combat_turn = 0
        all_nodes = [self.leader_node] + [m for m in self.member_nodes if m]

        while self.is_running:
            # Kiểm tra xem còn ai trong trận không
            any_in_combat = any(n.in_combat for n in all_nodes if n and n.active_socket > 0)
            if not any_in_combat:
                break

            combat_turn += 1
            self.log("INFO", f"⚡ [COMBAT HIỆP {combat_turn}] Đang điều phối toàn đội ra chiêu...")

            # 1. Xác định mục tiêu ưu tiên: Hàng 2 & 3 (vị trí 2, 3, 6, 7)
            # Vị trí 2 = (Col 1, Row 2), Vị trí 3 = (Col 1, Row 3)
            # Vị trí 6 = (Col 2, Row 2), Vị trí 7 = (Col 2, Row 3)
            PRIORITY_TARGETS = [
                (1, 2), # Vị trí 2 (Cột 1, Hàng 2)
                (1, 3), # Vị trí 3 (Cột 1, Hàng 3)
                (2, 2), # Vị trí 6 (Cột 2, Hàng 2)
                (2, 3), # Vị trí 7 (Cột 2, Hàng 3)
            ]
            t_idx = (combat_turn - 1) % len(PRIORITY_TARGETS)
            target_col, target_row = PRIORITY_TARGETS[t_idx]

            # 2. Gửi lệnh ra chiêu cho từng account
            for node in all_nodes:
                if not node or node.active_socket <= 0:
                    continue

                dname = node.display_name
                row = node.combat_row

                # A. LOGIC PET:
                # Pet của bgdf02, bgdf04, bgdw01, sincospro: Dùng chiêu [043b] (Nhắm Hàng 2 & 3: vị trí 2, 3, 6, 7)
                # Tất cả pet còn lại: Dùng chiêu Phòng thủ [75ea]
                pet_uses_attack = any(k in dname for k in ["f02", "f04", "w01", "sincospro", "bgdf02", "bgdf04", "bgdw01"])
                if pet_uses_attack:
                    # Pet dùng 043b nhắm vào target_col, target_row (vị trí 2, 3, 6, 7)
                    pkt_pet = bytes([0x32, 0x01, 0x04, row, target_col, target_row]) + SKILL_PET_FIRE_043B + bytes([0x00])
                    node.send_packet(pkt_pet)
                else:
                    # Pet dùng 75ea (Phòng thủ trên chính mình: Target slot 4, row chính mình)
                    pkt_pet = bytes([0x32, 0x01, 0x04, row, 0x04, row]) + SKILL_DEFEND + bytes([0x00])
                    node.send_packet(pkt_pet)

                time.sleep(0.05)

                # B. LOGIC NHÂN VẬT:
                # TOÀN BỘ nhân vật (kể cả F04, bgdf02, bgdw01, sincospro,...): ĐỀU dùng chiêu Phòng thủ [75ea]
                pkt_char = bytes([0x32, 0x01, 0x03, row, 0x03, row]) + SKILL_DEFEND + bytes([0x00])
                node.send_packet(pkt_char)

                # Thông báo chiêu thức hiệp đầu để người dùng dễ theo dõi
                if combat_turn == 1:
                    p_desc = f"Chiêu Pet 043b nhắm ({target_col},{target_row})" if pet_uses_attack else "Thủ 75ea"
                    self.log("INFO", f"  🛡️ [{dname}] Row {row}: Char Slot 3 [Thủ (75ea)] | Pet Slot 4 [{p_desc}]")
                    log_to_file("COMBAT", f"  [{dname}] Row {row}: Char Slot 3 [Thủ 75ea: {pkt_char.hex()}] | Pet Slot 4 [{p_desc}: {pkt_pet.hex()}]")

                time.sleep(0.05)

            # Chờ round trôi qua (chu kỳ 3.2s)
            start_round = time.time()
            while time.time() - start_round < 3.2 and self.is_running:
                if not any(n.in_combat for n in all_nodes if n and n.active_socket > 0):
                    break
                time.sleep(0.2)

            if combat_turn >= 100:
                self.log("WARNING", "⚠️ Trận đánh đã kéo dài 100 hiệp! Tạm dừng để kiểm tra an toàn.")
                log_to_file("WARNING", "Trận đánh vượt quá 100 hiệp! Ngắt vòng lặp an toàn.")
                break

        # Đảm bảo reset trạng thái chiến đấu của toàn đội sau khi kết thúc trận
        for n in all_nodes:
            if n:
                n.in_combat = False
                n.enemy_positions.clear()
        self.log("SUCCESS", f"🏁 Kết thúc trận đánh sau {combat_turn} hiệp!")
        log_to_file("SUCCESS", f"Kết thúc trận đánh hoàn tất sau {combat_turn} hiệp.")

    def _claim_dungeon_rewards(self, did):
        """Gửi chuỗi đối thoại nhận thưởng cho Leader và từng Member."""
        leader = self.leader_node
        members = [m for m in self.member_nodes if m and m.active_socket > 0]

        # Chuỗi nhận thưởng theo từng Dungeon
        if did == "30039":
            self.log("REWARD", "🎁 Đang nhận thưởng Phụ Bản 30039...")
            leader.send_packet(bytes.fromhex("14010100"))
            time.sleep(0.4)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("200209"))
            time.sleep(0.4)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(1.0)
            leader.send_packet(bytes.fromhex("200209"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("200209"))
            time.sleep(1.5)

            for mem in members:
                time.sleep(0.6)
                mem.send_packet(bytes.fromhex("14010100"))
                time.sleep(0.4)
                mem.send_packet(bytes.fromhex("200209"))
                time.sleep(0.4)
                mem.send_packet(bytes.fromhex("1406"))
                time.sleep(0.3)
                mem.send_packet(bytes.fromhex("1406"))
                time.sleep(1.0)
                mem.send_packet(bytes.fromhex("200209"))
                time.sleep(0.3)
                mem.send_packet(bytes.fromhex("1406"))
                time.sleep(0.3)
                mem.send_packet(bytes.fromhex("200209"))
                time.sleep(1.5)

        elif did == "30025":
            self.log("REWARD", "🎁 Đang nhận thưởng Phụ Bản 30025...")
            # Leader thoát ra sảnh và nhận thưởng
            leader.send_packet(bytes.fromhex("14010100"))
            time.sleep(0.4)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("20020e"))
            time.sleep(0.4)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(1.0)
            leader.send_packet(bytes.fromhex("20020e"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("20020e"))
            time.sleep(1.5)

            for idx, mem in enumerate(members):
                time.sleep(0.6)
                mem.send_packet(bytes.fromhex("14010100"))
                time.sleep(0.4)
                opt = "20020e" if ("w01" in mem.name.lower() or idx == 0) else "20020c"
                mem.send_packet(bytes.fromhex(opt))
                time.sleep(0.4)
                mem.send_packet(bytes.fromhex("1406"))
                time.sleep(0.3)
                mem.send_packet(bytes.fromhex("1406"))
                time.sleep(1.0)
                mem.send_packet(bytes.fromhex(opt))
                time.sleep(0.3)
                mem.send_packet(bytes.fromhex("1406"))
                time.sleep(0.3)
                mem.send_packet(bytes.fromhex(opt))
                time.sleep(1.5)

        elif did == "30021":
            self.log("REWARD", "🎁 Đang nhận thưởng Phụ Bản 30021...")
            leader.send_packet(bytes.fromhex("14010100"))
            time.sleep(0.4)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("200209"))
            time.sleep(0.4)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(1.0)
            leader.send_packet(bytes.fromhex("200209"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("200209"))
            time.sleep(1.5)

            for mem in members:
                time.sleep(0.6)
                mem.send_packet(bytes.fromhex("14012800"))
                time.sleep(0.4)
                mem.send_packet(bytes.fromhex("20020b"))
                time.sleep(0.4)
                mem.send_packet(bytes.fromhex("1406"))
                time.sleep(0.3)
                mem.send_packet(bytes.fromhex("1406"))
                time.sleep(1.0)
                mem.send_packet(bytes.fromhex("20020b"))
                time.sleep(0.3)
                mem.send_packet(bytes.fromhex("1406"))
                time.sleep(0.3)
                mem.send_packet(bytes.fromhex("20020b"))
                time.sleep(1.5)

        elif did == "30013":
            self.log("REWARD", "🎁 Đang nhận thưởng Phụ Bản 30013 (Boss Cuối)...")
            leader.send_packet(bytes.fromhex("14010100"))
            time.sleep(0.4)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("20020e"))
            time.sleep(0.4)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(1.0)
            leader.send_packet(bytes.fromhex("20020e"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("1406"))
            time.sleep(0.3)
            leader.send_packet(bytes.fromhex("20020e"))
            time.sleep(1.5)

            for idx, mem in enumerate(members):
                time.sleep(0.6)
                mem.send_packet(bytes.fromhex("14010100"))
                time.sleep(0.4)
                opt = "20020f" if idx == 0 else "20020e"
                mem.send_packet(bytes.fromhex(opt))
                time.sleep(0.4)
                mem.send_packet(bytes.fromhex("1406"))
                time.sleep(0.3)
                mem.send_packet(bytes.fromhex("1406"))
                time.sleep(1.0)
                mem.send_packet(bytes.fromhex(opt))
                time.sleep(0.3)
                mem.send_packet(bytes.fromhex("1406"))
                time.sleep(0.3)
                mem.send_packet(bytes.fromhex(opt))
                time.sleep(1.5)

        self.log("SUCCESS", "★ Đã hoàn tất gửi lệnh nhận thưởng cho tất cả thành viên!")

# =============================================================================
# GIAO DIỆN ĐỒ HỌA TKINTER HIỆN ĐẠI
# =============================================================================
class WLOPartyDungeonHubApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WLO AUTO PARTY DUNGEON HUB - QUẢN LÝ 4 PHỤ BẢN TỔ ĐỘI")
        self.root.geometry("1120x780")
        self.root.minsize(980, 680)
        self.root.configure(bg=THEME["bg_dark"])

        self.dev = None
        self.running_procs = {} # name -> proc
        self.nodes = {} # name -> ClientNode
        self.engine = PartyDungeonEngine(self)

        self._build_ui()
        self._auto_detect_clients()

    def _build_ui(self):
        # 1. Header Banner
        header = tk.Frame(self.root, bg=THEME["bg_card"], padx=16, pady=12, highlightthickness=1, highlightbackground=THEME["border"])
        header.pack(fill=tk.X, padx=12, pady=(12, 6))

        h_left = tk.Frame(header, bg=THEME["bg_card"])
        h_left.pack(side=tk.LEFT)

        tk.Label(h_left, text="⚡ WLO AUTO PARTY DUNGEON HUB", font=FONT_TITLE, fg=THEME["primary"], bg=THEME["bg_card"]).pack(anchor="w")
        tk.Label(h_left, text="Quản lý tự động 4 Phụ Bản Tổ Đội: 30039, 30025, 30021, 30013 | Phối hợp 4 Client", 
                 font=FONT_BODY, fg=THEME["text_muted"], bg=THEME["bg_card"]).pack(anchor="w")

        h_right = tk.Frame(header, bg=THEME["bg_card"])
        h_right.pack(side=tk.RIGHT)

        self.lbl_status_badge = tk.Label(h_right, text="SẴN SÀNG", font=(FONT_FAMILY, 9, "bold"), 
                                         bg=THEME["bg_input"], fg=THEME["green"], padx=12, pady=4)
        self.lbl_status_badge.pack(side=tk.RIGHT)

        # 2. Main Content Split
        content = tk.Frame(self.root, bg=THEME["bg_dark"])
        content.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        left_col = tk.Frame(content, bg=THEME["bg_dark"], width=420)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 6))

        right_col = tk.Frame(content, bg=THEME["bg_dark"])
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))

        # LEFT COL: A. Client Assignment Panel
        acc_frame = tk.LabelFrame(left_col, text="  👥 ĐỘI HÌNH THAM GIA (1 LEADER + 3 MEMBERS)  ", 
                                  bg=THEME["bg_card"], fg=THEME["primary"], font=FONT_HEADER, padx=12, pady=10)
        acc_frame.pack(fill=tk.X, pady=(0, 8))

        # Leader Selector
        tk.Label(acc_frame, text="👑 Đội Trưởng (Leader):", font=FONT_BODY, fg=THEME["yellow"], bg=THEME["bg_card"]).grid(row=0, column=0, sticky="w", pady=4)
        self.combo_leader = ttk.Combobox(acc_frame, state="readonly", width=24)
        self.combo_leader.grid(row=0, column=1, sticky="ew", pady=4, padx=6)

        # Member 1
        tk.Label(acc_frame, text="Thành viên #1:", font=FONT_BODY, fg=THEME["text_light"], bg=THEME["bg_card"]).grid(row=1, column=0, sticky="w", pady=4)
        self.combo_m1 = ttk.Combobox(acc_frame, state="readonly", width=24)
        self.combo_m1.grid(row=1, column=1, sticky="ew", pady=4, padx=6)

        # Member 2
        tk.Label(acc_frame, text="Thành viên #2:", font=FONT_BODY, fg=THEME["text_light"], bg=THEME["bg_card"]).grid(row=2, column=0, sticky="w", pady=4)
        self.combo_m2 = ttk.Combobox(acc_frame, state="readonly", width=24)
        self.combo_m2.grid(row=2, column=1, sticky="ew", pady=4, padx=6)

        # Member 3
        tk.Label(acc_frame, text="Thành viên #3:", font=FONT_BODY, fg=THEME["text_light"], bg=THEME["bg_card"]).grid(row=3, column=0, sticky="w", pady=4)
        self.combo_m3 = ttk.Combobox(acc_frame, state="readonly", width=24)
        self.combo_m3.grid(row=3, column=1, sticky="ew", pady=4, padx=6)

        btn_scan = tk.Button(acc_frame, text="🔄 Quét lại Client", font=FONT_BODY, bg=THEME["bg_input"], 
                             fg=THEME["text_light"], relief="flat", padx=8, pady=4, command=self._auto_detect_clients)
        btn_scan.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 2))

        # LEFT COL: B. Dungeon Mode & Settings
        mode_frame = tk.LabelFrame(left_col, text="  🏛️ CẤU HÌNH PHỤ BẢN & LƯỢT CHẠY  ", 
                                   bg=THEME["bg_card"], fg=THEME["primary"], font=FONT_HEADER, padx=12, pady=10)
        mode_frame.pack(fill=tk.X, pady=4)

        tk.Label(mode_frame, text="Chế độ Phụ Bản:", font=FONT_BODY, fg=THEME["text_light"], bg=THEME["bg_card"]).grid(row=0, column=0, sticky="w", pady=4)
        self.var_dungeon_mode = tk.StringVar(value="ALL")
        self.combo_mode = ttk.Combobox(mode_frame, textvariable=self.var_dungeon_mode, state="readonly", width=24)
        self.combo_mode["values"] = [
            "ALL - Chạy Liên Hoàn Cả 4 Phụ Bản",
            "30039 - Phụ bản 30039 (5 Ải)",
            "30025 - Phụ bản 30025 (4 Ải)",
            "30021 - Phụ bản 30021 (9 Ải)",
            "30013 - Phụ bản 30013 (9 Ải - Boss)",
        ]
        self.combo_mode.current(0)
        self.combo_mode.grid(row=0, column=1, sticky="ew", pady=4, padx=6)

        tk.Label(mode_frame, text="Số Vòng Lặp:", font=FONT_BODY, fg=THEME["text_light"], bg=THEME["bg_card"]).grid(row=1, column=0, sticky="w", pady=4)
        self.var_loops = tk.StringVar(value="1")
        self.combo_loops = ttk.Combobox(mode_frame, textvariable=self.var_loops, state="readonly", width=8)
        self.combo_loops["values"] = ["1", "2", "3", "5", "10", "∞ (Không Giới Hạn)"]
        self.combo_loops.current(0)
        self.combo_loops.grid(row=1, column=1, sticky="w", pady=4, padx=6)

        # LEFT COL: C. Combat Rule Reminder Card
        rule_frame = tk.LabelFrame(left_col, text="  ⚔️ LOGIC CHIẾN ĐẤU ĐƯỢC THIẾT LẬP  ", 
                                   bg=THEME["bg_card"], fg=THEME["primary"], font=FONT_HEADER, padx=10, pady=8)
        rule_frame.pack(fill=tk.X, pady=4)

        rule_text = (
            "• Toàn bộ Nhân vật (100% Characters kể cả F04):\n"
            "  ➔ Dùng chiêu [Phòng thủ 75ea]\n"
            "• Pet của bgdf02, bgdf04, bgdw01, sincospro:\n"
            "  ➔ Dùng chiêu [043b] (Nhắm Hàng 2 & 3: Pos 2, 3, 6, 7)\n"
            "• Toàn bộ Pet còn lại (bgdw03, w04, wi01,...):\n"
            "  ➔ Dùng chiêu [Phòng thủ 75ea]"
        )
        tk.Label(rule_frame, text=rule_text, font=("Segoe UI", 8), justify=tk.LEFT, 
                 fg=THEME["cyan"], bg=THEME["bg_card"]).pack(anchor="w")

        # LEFT COL: D. Action Buttons
        ctl_frame = tk.Frame(left_col, bg=THEME["bg_dark"])
        ctl_frame.pack(fill=tk.X, pady=(10, 0))

        self.btn_start = tk.Button(ctl_frame, text="▶  BẮT ĐẦU AUTO TỔ ĐỘI", font=(FONT_FAMILY, 11, "bold"),
                                   bg=THEME["green"], fg=THEME["bg_dark"], relief="flat", padx=14, pady=8,
                                   command=self.action_start_auto)
        self.btn_start.pack(fill=tk.X, pady=(0, 4))

        self.btn_stop = tk.Button(ctl_frame, text="⏹  DỪNG LẠI", font=FONT_HEADER,
                                  bg=THEME["red"], fg=THEME["bg_dark"], relief="flat", padx=10, pady=6,
                                  state=tk.DISABLED, command=self.action_stop_auto)
        self.btn_stop.pack(fill=tk.X)

        btn_open_log = tk.Button(ctl_frame, text="📂  MỞ FILE LOG CHI TIẾT", font=(FONT_FAMILY, 9),
                                 bg=THEME["bg_input"], fg=THEME["cyan"], relief="flat", padx=8, pady=5,
                                 command=self.action_open_log_file)
        btn_open_log.pack(fill=tk.X, pady=(6, 0))

        # RIGHT COL: Real-time Event Console & Status
        log_frame = tk.LabelFrame(right_col, text="  📜 NHẬT KÝ HOẠT ĐỘNG THỜI GIAN THỰC (LƯU RA party_dungeon_run.log)  ", 
                                  bg=THEME["bg_card"], fg=THEME["primary"], font=FONT_HEADER, padx=10, pady=8)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.txt_log = scrolledtext.ScrolledText(log_frame, bg="#11111b", fg=THEME["text_light"],
                                                 font=FONT_CONSOLE, insertbackground="white", wrap=tk.WORD)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        # Tags màu log
        self.txt_log.tag_config("INFO", foreground="#89dceb")
        self.txt_log.tag_config("PRIMARY", foreground="#89b4fa")
        self.txt_log.tag_config("SUCCESS", foreground="#a6e3a1")
        self.txt_log.tag_config("WARNING", foreground="#fab387")
        self.txt_log.tag_config("ERROR", foreground="#f38ba8")
        self.txt_log.tag_config("REWARD", foreground="#f9e2af")

        self.log_event("SUCCESS", "WLO Auto Party Dungeon Hub đã sẵn sàng!")
        self.log_event("INFO", f"Nhật ký chạy tự động sẽ được lưu vĩnh viễn tại: {LOG_FILE_PATH}")
        self.log_event("INFO", "Hệ thống hỗ trợ 4 Phụ Bản (30039, 30025, 30021, 30013) liên hoàn.")

    def action_open_log_file(self):
        """Mở file party_dungeon_run.log bằng trình xem văn bản mặc định của Windows."""
        try:
            if not os.path.exists(LOG_FILE_PATH):
                with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
                    f.write(f"=== WLO AUTO PARTY DUNGEON RUN LOG - Khởi tạo {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            os.startfile(LOG_FILE_PATH)
        except Exception as e:
            messagebox.showerror("Lỗi mở log", f"Không thể mở file log: {e}")

    def log_event(self, level, message):
        """Ghi nhận sự kiện ra giao diện console, stdout và file party_dungeon_run.log."""
        t_str = datetime.now().strftime("%H:%M:%S")
        prefix = f"[{t_str}] [{level:<7}] "
        print(f"{prefix}{message}", flush=True)
        try:
            self.txt_log.insert(tk.END, prefix, level)
            self.txt_log.insert(tk.END, message + "\n", level)
            self.txt_log.see(tk.END)
        except Exception:
            pass
        log_to_file(level, message)

    def _auto_detect_clients(self):
        """Tự động phát hiện các tiến trình alogin-*.exe đang chạy."""
        try:
            self.dev = frida.get_local_device()
            procs = self.dev.enumerate_processes()
        except Exception as e:
            self.log_event("ERROR", f"Không thể lấy danh sách tiến trình Frida: {e}")
            return

        self.running_procs.clear()
        client_names = []

        for p in procs:
            pname = p.name.lower()
            if "alogin" in pname or "wlo" in pname:
                self.running_procs[p.name] = p
                client_names.append(f"{p.name} (PID: {p.pid})")

        if not client_names:
            self.log_event("WARNING", "Không tìm thấy client alogin nào đang chạy!")
            return

        self.combo_leader["values"] = client_names
        self.combo_m1["values"] = ["<Không dùng>"] + client_names
        self.combo_m2["values"] = ["<Không dùng>"] + client_names
        self.combo_m3["values"] = ["<Không dùng>"] + client_names

        # Tự động gán mặc định thông minh
        for idx, cname in enumerate(client_names):
            clow = cname.lower()
            if "f02" in clow:
                self.combo_leader.current(idx)
            elif "w01" in clow:
                self.combo_m1.set(cname)
            elif "f04" in clow:
                self.combo_m2.set(cname)
            elif "f03" in clow and "f032" not in clow:
                self.combo_m3.set(cname)
            elif ("f032" in clow or "w03" in clow or "w04" in clow or "wi01" in clow or "sincos" in clow) and not self.combo_m3.get():
                self.combo_m3.set(cname)

        if not self.combo_leader.get() and client_names:
            self.combo_leader.current(0)

        self.log_event("SUCCESS", f"Đã quét thấy {len(client_names)} client WLO: {', '.join([p.name for p in self.running_procs.values()])}")

    def _connect_selected_clients(self):
        """Kết nối Frida vào Leader và các Members được chọn."""
        def _get_proc(val_str):
            if not val_str or "<" in val_str:
                return None
            pname = val_str.split(" (PID:")[0].strip()
            return self.running_procs.get(pname)

        l_proc = _get_proc(self.combo_leader.get())
        m1_proc = _get_proc(self.combo_m1.get())
        m2_proc = _get_proc(self.combo_m2.get())
        m3_proc = _get_proc(self.combo_m3.get())

        if not l_proc:
            messagebox.showwarning("Thiếu Leader", "Vui lòng chọn 1 tiến trình làm Đội Trưởng (Leader)!")
            return False

        # Dọn dẹp phiên kết nối cũ trước khi kết nối mới
        if self.engine.leader_node:
            self.engine.leader_node.disconnect()
            self.engine.leader_node = None
        for m in self.engine.member_nodes:
            if m:
                m.disconnect()
        self.engine.member_nodes.clear()

        # Khởi tạo Node Leader
        leader_node = ClientNode(l_proc.pid, l_proc.name, is_leader=True)
        if not leader_node.connect(self.dev):
            self.log_event("ERROR", f"Không thể hook Frida vào Leader [{l_proc.name}]!")
            return False
        self.engine.leader_node = leader_node
        if leader_node.active_socket > 0:
            self.log_event("SUCCESS", f"✓ Đã hook Leader [{l_proc.name}] (PID: {l_proc.pid}) - Socket #{leader_node.active_socket}")
        else:
            self.log_event("SUCCESS", f"✓ Đã hook Leader [{l_proc.name}] (PID: {l_proc.pid})")

        # Khởi tạo Member Nodes (Lọc trùng và loại bỏ tiến trình Leader)
        seen_pids = {l_proc.pid}
        member_procs = []
        for p in [m1_proc, m2_proc, m3_proc]:
            if p and p.pid not in seen_pids:
                seen_pids.add(p.pid)
                member_procs.append(p)
        
        for idx, mproc in enumerate(member_procs):
            mnode = ClientNode(mproc.pid, mproc.name, is_leader=False)
            mnode.combat_row = idx + 2  # Leader là Row 1, Thành viên lần lượt là Row 2, Row 3, Row 4
            if mnode.connect(self.dev):
                self.engine.member_nodes.append(mnode)
                if mnode.active_socket > 0:
                    self.log_event("SUCCESS", f"✓ Đã hook Thành viên [{mproc.name}] (PID: {mproc.pid}) - Socket #{mnode.active_socket} - Slot/Row {mnode.combat_row}")
                else:
                    self.log_event("SUCCESS", f"✓ Đã hook Thành viên [{mproc.name}] (PID: {mproc.pid}) - Slot/Row {mnode.combat_row}")
            else:
                self.log_event("WARNING", f"Không thể hook Thành viên [{mproc.name}]")

        return True

    def action_start_auto(self):
        """Bắt đầu chạy Auto."""
        ok = self._connect_selected_clients()
        if not ok:
            return

        raw_mode = self.combo_mode.get()
        mode = "ALL"
        for did in ["30039", "30025", "30021", "30013"]:
            if did in raw_mode:
                mode = did
                break

        loop_val = self.var_loops.get()
        loops = 0 if "∞" in loop_val else int(loop_val.split()[0])

        self.lbl_status_badge.config(text="ĐANG CHẠY AUTO", bg=THEME["green"], fg=THEME["bg_dark"])
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)

        self.engine.start_automation(mode, loops)

    def action_stop_auto(self):
        """Dừng chạy Auto."""
        self.engine.stop_automation()
        self.update_run_buttons()

    def update_run_buttons(self):
        self.lbl_status_badge.config(text="ĐÃ DỪNG", bg=THEME["bg_input"], fg=THEME["red"])
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="WLO Auto Party Dungeon Hub")
    parser.add_argument("--auto-start", "-a", action="store_true", help="Tự động bắt đầu chạy auto ngay sau khi khởi động")
    parser.add_argument("--mode", "-m", type=str, default=None, help="Chế độ phụ bản (ALL, 30039, 30025, 30021, 30013)")
    args = parser.parse_args()

    root = tk.Tk()
    app = WLOPartyDungeonHubApp(root)
    if args.auto_start:
        if args.mode:
            for idx, val in enumerate(app.combo_mode["values"]):
                if args.mode in val:
                    app.combo_mode.current(idx)
                    break
        root.after(1500, app.action_start_auto)
    root.mainloop()

if __name__ == "__main__":
    main()

