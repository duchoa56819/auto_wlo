"""
Auto Login WLO (Wonderland Online)
Tự động đăng nhập game Wonderland Online với aProxy, alogin client và xác thực OTP qua Gmail.
Hỗ trợ đa tài khoản (multi-client), chọn Nhân vật 1 hoặc Nhân vật 2,
quét template màn hình '伺服器列表' bằng OpenCV để tối ưu tốc độ và điền thông tin chính xác.
"""

import os
import sys
import time
import json
import ctypes
from ctypes import wintypes
import subprocess
import argparse
import threading

# Thiết lập encoding utf-8 cho console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import psutil
import pyautogui
import pyperclip

# Tắt failsafe của pyautogui để không ngắt khi con trỏ chuột ở góc (0, 0)
pyautogui.FAILSAFE = False

# ==================== ĐƯỜNG DẪN MẶC ĐỊNH ====================
DEFAULT_GAME_DIR = r"D:\_Games\WLO_International_Client\WLOI - Eng"
DEFAULT_APROXY_PATH = os.path.join(DEFAULT_GAME_DIR, "aProxy.exe")
DEFAULT_AUTO_LOGIN_DIR = os.path.join(DEFAULT_GAME_DIR, "auto_login")
DEFAULT_ACCOUNTS_PATH = os.path.join(DEFAULT_AUTO_LOGIN_DIR, "accounts.json")
DEFAULT_GET_OTP_PATH = os.path.join(DEFAULT_AUTO_LOGIN_DIR, "get_otp.py")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CLIENTS_CONFIG = os.path.join(CURRENT_DIR, "clients_config.json")
if not os.path.exists(DEFAULT_CLIENTS_CONFIG):
    DEFAULT_CLIENTS_CONFIG = os.path.join(DEFAULT_AUTO_LOGIN_DIR, "clients_config.json")

# Đường dẫn file ảnh mẫu giao diện
BTN_ENTER1_TEMPLATE_PATH = os.path.join(CURRENT_DIR, "btn_enter1.png")
if not os.path.exists(BTN_ENTER1_TEMPLATE_PATH):
    BTN_ENTER1_TEMPLATE_PATH = os.path.join(DEFAULT_AUTO_LOGIN_DIR, "btn_enter1.png")

BTN_ENTER2_TEMPLATE_PATH = os.path.join(CURRENT_DIR, "btn_enter2.png")
if not os.path.exists(BTN_ENTER2_TEMPLATE_PATH):
    BTN_ENTER2_TEMPLATE_PATH = os.path.join(DEFAULT_AUTO_LOGIN_DIR, "btn_enter2.png")

BANNER_TEMPLATE_PATH = os.path.join(CURRENT_DIR, "server_list_banner.png")
if not os.path.exists(BANNER_TEMPLATE_PATH):
    BANNER_TEMPLATE_PATH = os.path.join(DEFAULT_AUTO_LOGIN_DIR, "server_list_banner.png")

# ==================== TỌA ĐỘ VÀ VỊ TRÍ NHÂN VẬT ====================
COORDS = {
    "click_1": (336, 240),      # Screen: 336, 240 (Chọn Server WLOI)
    "click_2": (473, 244),      # Screen: 473, 244 (Nút Xác nhận / Vào tiếp)
    "input_user": (346, 473),   # Screen: 346, 473 (Ô nhập ID - Double Click)
}

CHAR_COORDS = {
    1: {
        "name": "Nhân vật 1",
        "screen": (340, 470),
        "window": (340, 470),
        "client": (337, 444),
    },
    2: {
        "name": "Nhân vật 2",
        "screen": (1051, 549),
        "window": (753, 373),
        "client": (745, 342),
    }
}

# ==================== WIN32 API HELPERS ====================
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
GetWindowTextW = user32.GetWindowTextW
GetWindowTextLengthW = user32.GetWindowTextLengthW
GetClassNameW = user32.GetClassNameW
IsWindowVisible = user32.IsWindowVisible
IsWindow = user32.IsWindow
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
ShowWindow = user32.ShowWindow
SetForegroundWindow = user32.SetForegroundWindow
BringWindowToTop = user32.BringWindowToTop
AttachThreadInput = user32.AttachThreadInput
ClientToScreen = user32.ClientToScreen
GetWindowRect = user32.GetWindowRect

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def init_dpi():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass

init_dpi()


def force_foreground_window(hwnd: int):
    """Đưa cửa sổ lên phía trên và kích hoạt focus mạnh mẽ."""
    try:
        cur_thread = kernel32.GetCurrentThreadId()
        fore_hwnd = user32.GetForegroundWindow()
        fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None)

        if fore_thread != cur_thread:
            AttachThreadInput(fore_thread, cur_thread, True)

        ShowWindow(hwnd, 9)  # SW_RESTORE
        SetForegroundWindow(hwnd)
        BringWindowToTop(hwnd)

        if fore_thread != cur_thread:
            AttachThreadInput(fore_thread, cur_thread, False)
    except Exception:
        pass


def is_process_running(proc_name: str) -> bool:
    for p in psutil.process_iter(['name']):
        try:
            if p.info['name'] and p.info['name'].lower() == proc_name.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False


def find_powershell_verify_dialog():
    """Tìm cửa sổ hộp thoại nhập mã xác thực OTP của PowerShell ('Verify Code')."""
    found = []
    def callback(hwnd, lparam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            pid = wintypes.DWORD()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                pname = psutil.Process(pid.value).name().lower()
            except Exception:
                pname = ""
            if "verify code" in title.lower():
                found.insert(0, (hwnd, title, pname, pid.value))
            elif pname == "powershell.exe" and title:
                found.append((hwnd, title, pname, pid.value))
        return True

    EnumWindows(EnumWindowsProc(callback), 0)
    return found


def find_game_window(proc_name: str = "alogin"):
    """Tìm cửa sổ của game WLO client."""
    found = []
    clean_proc = os.path.basename(proc_name).lower().replace(".exe", "")

    def callback(hwnd, lparam):
        if IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                pname = psutil.Process(pid.value).name().lower()
            except Exception:
                pname = ""
            c_buff = ctypes.create_unicode_buffer(256)
            GetClassNameW(hwnd, c_buff, 256)
            cname = c_buff.value

            if clean_proc in pname or "alogin" in pname or cname in ("TForm3", "TForm1"):
                found.append((hwnd, pname, pid.value, cname))
        return True

    EnumWindows(EnumWindowsProc(callback), 0)
    return found[0] if found else None


def get_game_window_pos(exe_name: str = "alogin"):
    """
    Tìm vị trí (left, top) của cửa sổ game thực tế (TForm1).
    Nếu cửa sổ ở vị trí chuẩn góc trên bên trái màn hình (left ~ 0, top ~ 0) thì trả về (0, 0).
    Nếu cửa sổ thứ 2 được xếp lệch (ví dụ 298, 176) thì trả về (left, top).
    """
    clean_proc = os.path.basename(exe_name).lower().replace(".exe", "")
    found_pos = None

    def callback(hwnd, lparam):
        nonlocal found_pos
        if IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                pname = psutil.Process(pid.value).name().lower()
            except Exception:
                pname = ""
            c_buff = ctypes.create_unicode_buffer(256)
            GetClassNameW(hwnd, c_buff, 256)
            cname = c_buff.value

            if (clean_proc in pname or "alogin" in pname) and cname == "TForm1":
                r = RECT()
                GetWindowRect(hwnd, ctypes.byref(r))
                if (r.right - r.left) >= 600 and (r.bottom - r.top) >= 400:
                    left = max(0, r.left) if abs(r.left) < 15 else r.left
                    top = max(0, r.top) if abs(r.top) < 15 else r.top
                    found_pos = (left, top)
                    return False
        return True

    EnumWindows(EnumWindowsProc(callback), 0)
    return found_pos


def load_clients_config(config_path: str = DEFAULT_CLIENTS_CONFIG) -> list:
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_clients_config(clients: list, config_path: str = DEFAULT_CLIENTS_CONFIG):
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(clients, f, indent=2, ensure_ascii=False)


def load_account_from_json(accounts_json_path: str, target_email: str):
    if not os.path.exists(accounts_json_path):
        raise FileNotFoundError(f"Không tìm thấy: {accounts_json_path}")
    with open(accounts_json_path, "r", encoding="utf-8") as f:
        accounts = json.load(f)
    for acc in accounts:
        if acc.get("email", "").strip().lower() == target_email.strip().lower():
            return acc
    for acc in accounts:
        if any(k in acc.get("label", "").lower() for k in ["f03", "f02", "f04", "w03", "w04"]):
            return acc
    if accounts:
        return accounts[0]
    raise ValueError(f"Không tìm thấy tài khoản {target_email} trong {accounts_json_path}")


def fetch_otp(accounts_json_path: str, target_email: str, get_otp_dir: str, log_fn=print) -> str | None:
    acc_info = load_account_from_json(accounts_json_path, target_email)
    email_user = acc_info["email"]
    app_pwd = acc_info["password"]
    sender = acc_info.get("sender", "GM@wloi.org")

    if get_otp_dir not in sys.path:
        sys.path.insert(0, get_otp_dir)
    import get_otp

    otp = None
    try:
        otp = get_otp.get_latest_otp(username=email_user, password=app_pwd, sender=sender)
    except Exception as e:
        log_fn(f"[-] get_latest_otp: {e}")

    if not otp:
        try:
            otp = get_otp.wait_for_new_otp(timeout=20, interval=2, username=email_user, password=app_pwd, sender=sender)
        except Exception as e:
            log_fn(f"[-] wait_for_new_otp: {e}")
    return otp


# ==================== SCAN TEMPLATE BẰNG OPENCV ====================

def scan_for_image_template(
    template_path: str,
    name: str = "ảnh mẫu",
    timeout: float = 20.0,
    confidence: float = 0.80,
    interval: float = 0.15,
    log_fn=print,
    cancel_check=lambda: False,
) -> tuple[bool, tuple[int, int] | None]:
    """
    Liên tục scan màn hình để tìm template_path bằng OpenCV matchTemplate.
    Trả về (True, (center_x, center_y)) nếu tìm thấy, hoặc (False, None) nếu timeout.
    """
    if not os.path.exists(template_path):
        log_fn(f"  [-] Không tìm thấy file mẫu {name}: {template_path}. Chờ 3s...")
        for _ in range(3):
            if cancel_check(): return False, None
            time.sleep(1.0)
        return False, None

    log_fn(f"  [*] Đang scan tìm {name}...")
    start_time = time.time()

    try:
        import cv2
        import numpy as np
        from PIL import ImageGrab
        template = cv2.imread(template_path)
        if template is None:
            log_fn(f"  [-] Lỗi: Không thể đọc file ảnh {template_path}")
            return False, None
        th, tw = template.shape[:2]
    except Exception as e:
        log_fn(f"  [-] Lỗi thư viện OpenCV/PIL: {e}. Chờ 3s...")
        time.sleep(3.0)
        return False, None

    while time.time() - start_time < timeout:
        if cancel_check():
            return False, None
        try:
            screenshot = ImageGrab.grab()
            screen_np = np.array(screenshot)
            screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)

            res = cv2.matchTemplate(screen_bgr, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val >= confidence:
                dt = time.time() - start_time
                cx = max_loc[0] + tw // 2
                cy = max_loc[1] + th // 2
                log_fn(f"  [⚡] ĐÃ PHÁT HIỆN {name} sau {dt:.2f}s! (Độ khớp: {max_val*100:.1f}%)")
                return True, (cx, cy)
        except Exception:
            pass

        time.sleep(interval)

    log_fn(f"  [-] Hết thời gian scan {name} (timeout {timeout:.0f}s), tiếp tục thực hiện...")
    return False, None


def scan_for_server_list_banner(template_path=BANNER_TEMPLATE_PATH, timeout=25.0, confidence=0.82, log_fn=print, cancel_check=lambda: False) -> bool:
    """
    Liên tục scan màn hình để tìm banner '伺服器列表' (Server List).
    Ngay khi phát hiện -> Thông báo và cho phép chuyển tiếp ngay lập tức!
    """
    found, _ = scan_for_image_template(
        template_path=template_path,
        name="Bảng '伺服器列表'",
        timeout=timeout,
        confidence=confidence,
        interval=0.2,
        log_fn=log_fn,
        cancel_check=cancel_check,
    )
    if found:
        time.sleep(0.5)
    return found


# ==================== QUY TRÌNH ĐĂNG NHẬP 1 CLIENT ====================

def run_single_client_login(
    client_name="F03 - Nhân vật 1",
    game_dir=DEFAULT_GAME_DIR,
    aproxy_exe=DEFAULT_APROXY_PATH,
    exe_name="alogin-F03.exe",
    username="bgdF03",
    password="111111",
    email_target="backspace.noob@gmail.com",
    char_slot=1,
    accounts_json=DEFAULT_ACCOUNTS_PATH,
    otp_script_dir=DEFAULT_AUTO_LOGIN_DIR,
    log_fn=print,
    cancel_check=lambda: False,
) -> bool:
    """
    Thực thi quy trình đăng nhập 1 client cụ thể (11 bước).
    """
    alogin_exe_path = os.path.join(game_dir, exe_name) if not os.path.isabs(exe_name) else exe_name
    char_info = CHAR_COORDS.get(char_slot, CHAR_COORDS[1])

    start_total_time = time.time()
    log_fn("==================================================")
    log_fn(f"🚀 BẮT ĐẦU ĐĂNG NHẬP: {client_name}")
    log_fn(f"   • File EXE: {os.path.basename(alogin_exe_path)}")
    log_fn(f"   • Tài khoản: {username} | Mật khẩu: {password}")
    log_fn(f"   • {char_info['name']} (Slot {char_slot})")
    log_fn(f"   • Email OTP: {email_target}")
    log_fn("==================================================")

    # -------------------------------------------------------------------------
    # BƯỚC 1: Kiểm tra xem aProxy.exe đã chạy chưa
    # -------------------------------------------------------------------------
    if cancel_check(): return False
    log_fn("\n[BƯỚC 1/11] Kiểm tra tiến trình aProxy.exe...")
    if is_process_running("aProxy.exe"):
        log_fn("  [✓] aProxy.exe ĐÃ ĐANG CHẠY. Bỏ qua khởi động aProxy.")
    else:
        log_fn(f"  [+] Đang khởi động: {aproxy_exe}")
        if not os.path.exists(aproxy_exe):
            log_fn(f"  [!] LỖI: Không tìm thấy file {aproxy_exe}!")
            return False
        subprocess.Popen([aproxy_exe], cwd=game_dir)
        time.sleep(2.0)
        log_fn("  [+] Bấm phím ENTER trên aProxy...")
        pyautogui.press("enter")
        time.sleep(1.0)
        log_fn("  [✓] Đã khởi chạy aProxy.exe thành công.")

    # -------------------------------------------------------------------------
    # BƯỚC 2: Mở client game exe tương ứng
    # -------------------------------------------------------------------------
    if cancel_check(): return False
    log_fn(f"\n[BƯỚC 2/11] Mở game client: {os.path.basename(alogin_exe_path)}...")
    if not os.path.exists(alogin_exe_path):
        log_fn(f"  [!] LỖI: Không tìm thấy file {alogin_exe_path}!")
        return False

    game_proc = subprocess.Popen([alogin_exe_path], cwd=game_dir)
    log_fn(f"  [*] Đã kích hoạt {os.path.basename(alogin_exe_path)} (PID: {game_proc.pid}).")
    # -------------------------------------------------------------------------
    # BƯỚC 3: Bấm 2 lần Enter (Scan theo hình ảnh nút) & Scan '伺服器列表'
    # -------------------------------------------------------------------------
    if cancel_check(): return False
    log_fn("\n[BƯỚC 3/11] Bấm 2 lần Enter (Scan theo hình ảnh nút)...")

    # --- LẦN ENTER 1: Scan ảnh nút Thỏa thuận (btn_enter1.png) ---
    log_fn("  [*] Đang scan tìm nút Thỏa thuận (cho lần Enter 1)...")
    scan_for_image_template(
        BTN_ENTER1_TEMPLATE_PATH,
        name="Nút Thỏa thuận (Enter 1)",
        timeout=20.0,
        confidence=0.80,
        log_fn=log_fn,
        cancel_check=cancel_check
    )

    gw = find_game_window(exe_name)
    if gw:
        force_foreground_window(gw[0])
        time.sleep(0.3)

    log_fn("  [+] Bấm Enter lần 1...")
    pyautogui.press("enter")
    time.sleep(0.5)

    # --- LẦN ENTER 2: Scan ảnh nút Tiếp tục (btn_enter2.png) ---
    if cancel_check(): return False
    log_fn("  [*] Đang scan tìm nút Tiếp tục (cho lần Enter 2)...")
    scan_for_image_template(
        BTN_ENTER2_TEMPLATE_PATH,
        name="Nút Tiếp tục (Enter 2)",
        timeout=20.0,
        confidence=0.80,
        log_fn=log_fn,
        cancel_check=cancel_check
    )

    gw = find_game_window(exe_name)
    if gw:
        force_foreground_window(gw[0])
        time.sleep(0.3)

    log_fn("  [+] Bấm Enter lần 2...")
    pyautogui.press("enter")
    time.sleep(0.5)

    # SCAN TỰ ĐỘNG BẰNG OPENCV: Tìm bảng '伺服器列表'
    log_fn("  [*] Chờ game tải giao diện danh sách Server...")
    scan_for_server_list_banner(timeout=25.0, log_fn=log_fn, cancel_check=cancel_check)

    # Đảm bảo cửa sổ game active trước khi click
    gw = find_game_window(exe_name)
    if gw:
        game_hwnd = gw[0]
        force_foreground_window(game_hwnd)
        time.sleep(0.5)

    # -------------------------------------------------------------------------
    # BƯỚC 4: Click trái 1 lần vào vị trí 1: Screen (336, 240) -> chờ 1.0s
    # -------------------------------------------------------------------------
    if cancel_check(): return False
    pos1 = COORDS["click_1"]
    log_fn(f"\n[BƯỚC 4/11] Click Screen: {pos1} (Chọn Server WLOI)...")
    pyautogui.click(pos1[0], pos1[1])
    time.sleep(1.0)

    # -------------------------------------------------------------------------
    # BƯỚC 5: Click trái 1 lần vào vị trí 2: Screen (473, 244) -> chờ 1.0s
    # -------------------------------------------------------------------------
    if cancel_check(): return False
    pos2 = COORDS["click_2"]
    log_fn(f"\n[BƯỚC 5/11] Click Screen: {pos2}...")
    pyautogui.click(pos2[0], pos2[1])
    time.sleep(1.0)

    # -------------------------------------------------------------------------
    # BƯỚC 6: Double-Click Screen: (346, 473) vào ô ID -> chờ 0.5s
    # -------------------------------------------------------------------------
    if cancel_check(): return False
    pos3 = COORDS["input_user"]
    log_fn(f"\n[BƯỚC 6/11] Double-Click Screen: {pos3} (Vào ô ID)...")
    pyautogui.doubleClick(pos3[0], pos3[1])
    time.sleep(0.5)

    # -------------------------------------------------------------------------
    # BƯỚC 7: Điền thông tin đăng nhập: gõ ID, tab, pass, enter
    # -------------------------------------------------------------------------
    if cancel_check(): return False
    log_fn(f"\n[BƯỚC 7/11] Điền thông tin đăng nhập...")
    # Giải phóng mọi phím bổ trợ (Ctrl/Alt/Shift) đề phòng bị kẹt phím trong game
    for k in ("ctrl", "alt", "shift"):
        try:
            pyautogui.keyUp(k)
        except Exception:
            pass
    time.sleep(0.05)

    # Xóa ký tự cũ nếu có
    for _ in range(12):
        pyautogui.press("backspace")
    time.sleep(0.1)

    log_fn(f"  [+] Gõ ID tài khoản: '{username}'...")
    pyautogui.write(username, interval=0.05)
    time.sleep(0.2)

    log_fn("  [+] Bấm phím Tab chuyển sang ô mật khẩu...")
    pyautogui.press("tab")
    time.sleep(0.2)

    for _ in range(12):
        pyautogui.press("backspace")
    time.sleep(0.1)

    log_fn(f"  [+] Gõ mật khẩu: '{password}'...")
    pyautogui.write(password, interval=0.05)
    time.sleep(0.2)

    log_fn("  [+] Bấm phím Enter...")
    pyautogui.press("enter")
    time.sleep(1.5)

    # -------------------------------------------------------------------------
    # BƯỚC 8: Click chọn Nhân vật 1 hoặc Nhân vật 2 (Kích hoạt gửi OTP)
    # -------------------------------------------------------------------------
    if cancel_check(): return False
    log_fn(f"\n[BƯỚC 8/11] Chọn {char_info['name']} (Kích hoạt gửi OTP)...")

    # Xác định tọa độ click chính xác:
    # Nhân vật 1: Screen (340, 470)
    # Nhân vật 2: Screen (1051, 549) (hoặc tính theo độ lệch cửa sổ game nếu cửa sổ 2 mở tại 298, 176)
    win_pos = get_game_window_pos(exe_name)
    if win_pos and (win_pos[0] > 50 or win_pos[1] > 50):
        wx, wy = char_info["window"]
        target_click = (win_pos[0] + wx, win_pos[1] + wy)
        log_fn(f"  [*] Cửa sổ game ở vị trí lệch {win_pos} -> Tọa độ Screen: {target_click}")
    else:
        target_click = char_info["screen"]

    log_fn(f"  [+] Click: Screen {target_click} ({char_info['name']})")
    pyautogui.click(target_click[0], target_click[1])

    # -------------------------------------------------------------------------
    # BƯỚC 9: Chờ khoảng 10 giây để máy chủ WLO gửi mã OTP
    # -------------------------------------------------------------------------
    if cancel_check(): return False
    log_fn("\n[BƯỚC 9/11] Chờ 10 giây để máy chủ WLO gửi mã OTP về email...")
    for sec in range(10, 0, -1):
        if cancel_check(): return False
        log_fn(f"  ⏱️ Còn {sec} giây...")
        time.sleep(1.0)

    # -------------------------------------------------------------------------
    # BƯỚC 10: Lấy OTP từ script get_otp.py
    # -------------------------------------------------------------------------
    if cancel_check(): return False
    log_fn("\n[BƯỚC 10/11] Lấy mã OTP từ email...")
    otp = fetch_otp(accounts_json, email_target, otp_script_dir, log_fn=log_fn)

    if not otp:
        log_fn("  [!] LỖI: Không thể lấy được mã OTP từ email! Quy trình dừng lại.")
        return False

    log_fn(f"  [✓] MÃ OTP NHẬN ĐƯỢC: {otp}")
    pyperclip.copy(otp)
    log_fn("  [✓] Đã sao chép mã OTP vào Clipboard.")

    # -------------------------------------------------------------------------
    # BƯỚC 11: Dán vào hộp thoại powershell.exe đang mở rồi bấm Enter
    # -------------------------------------------------------------------------
    if cancel_check(): return False
    log_fn("\n[BƯỚC 11/11] Tìm hộp thoại PowerShell ('Verify Code') và dán OTP...")

    ps_hwnd = None
    start_wait = time.time()
    while time.time() - start_wait < 15:
        if cancel_check(): return False
        dialogs = find_powershell_verify_dialog()
        if dialogs:
            ps_hwnd = dialogs[0][0]
            log_fn(f"  [✓] Đã tìm thấy hộp thoại OTP (HWND: {ps_hwnd}, Title: '{dialogs[0][1]}')")
            break
        time.sleep(0.5)

    if not ps_hwnd:
        log_fn("  [-] Cảnh báo: Không tìm thấy cửa sổ 'Verify Code' theo tiêu đề.")
        log_fn("  [*] Thử dán trực tiếp phím tắt Ctrl+V và bấm Enter...")
        time.sleep(0.5)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
        pyautogui.press("enter")
    else:
        log_fn("  [*] Đang đưa hộp thoại lên trên cùng...")
        force_foreground_window(ps_hwnd)
        time.sleep(0.5)

        log_fn(f"  [*] Dán mã OTP '{otp}' vào hộp thoại...")
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
        log_fn("  [+] Bấm phím Enter để xác nhận mã OTP...")
        pyautogui.press("enter")

    total_time = time.time() - start_total_time
    log_fn("\n" + "=" * 50)
    log_fn(f"🎉 HOÀN TẤT ĐĂNG NHẬP [{client_name}] THÀNH CÔNG! (Tổng thời gian: {total_time:.1f}s)")
    log_fn("==================================================")
    return True


# ==================== ĐĂNG NHẬP HÀNG LOẠT (MULTI-CLIENT) ====================

def run_multi_client_logins(clients_to_run: list, log_fn=print, cancel_check=lambda: False) -> int:
    total = len(clients_to_run)
    success_count = 0
    log_fn(f"\n🚀 BẮT ĐẦU ĐĂNG NHẬP HÀNG LOẠT ({total} CLIENT)...")

    for idx, client in enumerate(clients_to_run):
        if cancel_check():
            log_fn("\n[!] Đã hủy đăng nhập hàng loạt.")
            break

        c_name = client.get("name", f"Client #{idx+1}")
        c_exe = client.get("exe", "alogin-F03.exe")
        c_user = client.get("user", "bgdF03")
        c_pass = client.get("pass", "111111")
        c_email = client.get("email", "backspace.noob@gmail.com")
        c_slot = int(client.get("char_slot", 1))

        log_fn(f"\n>>> [{idx+1}/{total}] TIẾN HÀNH ĐĂNG NHẬP: {c_name} <<<")

        success = run_single_client_login(
            client_name=c_name,
            exe_name=c_exe,
            username=c_user,
            password=c_pass,
            email_target=c_email,
            char_slot=c_slot,
            log_fn=log_fn,
            cancel_check=cancel_check,
        )

        if success:
            success_count += 1
            if idx < total - 1 and not cancel_check():
                log_fn("\n[*] Chờ 3s trước khi chuyển sang client tiếp theo...")
                time.sleep(3.0)
        else:
            log_fn(f"[!] Đăng nhập gặp sự cố cho {c_name}.")
            if cancel_check():
                break

    log_fn(f"\n🏁 KẾT QUẢ: {success_count}/{total} client đăng nhập thành công.")
    return success_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tự động đăng nhập WLO (Wonderland Online)")
    parser.add_argument("--client", help="ID của client trong clients_config.json")
    parser.add_argument("--all", action="store_true", help="Đăng nhập tất cả client đã bật")
    parser.add_argument("--exe", default="alogin-F03.exe", help="Tên file exe client")
    parser.add_argument("--account", default="bgdF03", help="Tên tài khoản")
    parser.add_argument("--password", default="111111", help="Mật khẩu tài khoản")
    parser.add_argument("--email", default="backspace.noob@gmail.com", help="Gmail nhận OTP")
    parser.add_argument("--char", type=int, default=1, choices=[1, 2], help="Nhân vật: 1 hoặc 2")
    parser.add_argument("--only-otp", action="store_true", help="Chỉ lấy OTP và dán vào PowerShell")

    args = parser.parse_args()

    if args.only_otp:
        print("[*] Chế độ: Chỉ lấy OTP và dán vào PowerShell...")
        otp = fetch_otp(DEFAULT_ACCOUNTS_PATH, args.email, DEFAULT_AUTO_LOGIN_DIR, log_fn=print)
        if otp:
            pyperclip.copy(otp)
            print(f"[✓] Đã lấy OTP: {otp}. Đang tìm hộp thoại...")
            dialogs = find_powershell_verify_dialog()
            if dialogs:
                hwnd = dialogs[0][0]
                force_foreground_window(hwnd)
                time.sleep(0.3)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.2)
                pyautogui.press("enter")
                print("[✓] Đã dán OTP và bấm Enter thành công!")
            else:
                print("[-] Không thấy hộp thoại PowerShell đang mở.")
        else:
            print("[-] Không lấy được OTP.")

    elif args.all:
        configs = load_clients_config()
        enabled_clients = [c for c in configs if c.get("enabled", True)]
        if not enabled_clients:
            print("[-] Không có client nào được bật (enabled: true) trong clients_config.json!")
        else:
            run_multi_client_logins(enabled_clients)

    elif args.client:
        configs = load_clients_config()
        match = next((c for c in configs if c.get("id") == args.client), None)
        if match:
            run_single_client_login(
                client_name=match.get("name", match["id"]),
                exe_name=match.get("exe", "alogin-F03.exe"),
                username=match.get("user", "bgdF03"),
                password=match.get("pass", "111111"),
                email_target=match.get("email", "backspace.noob@gmail.com"),
                char_slot=int(match.get("char_slot", 1)),
            )
        else:
            print(f"[-] Không tìm thấy client ID '{args.client}' trong clients_config.json!")

    else:
        run_single_client_login(
            exe_name=args.exe,
            username=args.account,
            password=args.password,
            email_target=args.email,
            char_slot=args.char,
        )
