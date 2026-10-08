"""
Công cụ giám sát và ghi nhận sự kiện cửa sổ (Window Event & Pixel Monitor)
Giúp xác định chính xác thời điểm các cửa sổ mới xuất hiện và sự thay đổi giao diện game WLO,
từ đó thay thế các khoảng nghỉ cố định (sleep) bằng cơ chế tự động phát hiện (event-driven).
"""

import sys
import time
import json
import ctypes
from ctypes import wintypes
import psutil
import pyautogui

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

GetDC = user32.GetDC
ReleaseDC = user32.ReleaseDC
GetPixel = gdi32.GetPixel
GetForegroundWindow = user32.GetForegroundWindow
GetWindowTextW = user32.GetWindowTextW
GetWindowTextLengthW = user32.GetWindowTextLengthW
GetClassNameW = user32.GetClassNameW
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
GetWindowRect = user32.GetWindowRect
IsWindowVisible = user32.IsWindowVisible
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]

# Các tọa độ cần theo dõi màu sắc
WATCH_COORDS = {
    "pos_server_1": (336, 240),
    "pos_server_2": (473, 244),
    "pos_input_id": (346, 473),
    "pos_char_1":   (340, 470),
    "pos_char_2":   (745, 342),
}


def get_pixel_rgb(x: int, y: int):
    """Lấy màu RGB tại tọa độ màn hình (x, y)."""
    hdc = GetDC(0)
    color = GetPixel(hdc, x, y)
    ReleaseDC(0, hdc)
    # GetPixel trả về 0x00BBGGRR
    r = color & 0xFF
    g = (color >> 8) & 0xFF
    b = (color >> 16) & 0xFF
    return (r, g, b)


def get_window_info(hwnd):
    """Lấy thông tin chi tiết của một cửa sổ."""
    if not hwnd or not IsWindowVisible(hwnd):
        return None

    length = GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(hwnd, buff, length + 1)
    title = buff.value

    class_buff = ctypes.create_unicode_buffer(256)
    GetClassNameW(hwnd, class_buff, 256)
    class_name = class_buff.value

    pid = wintypes.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        proc_name = psutil.Process(pid.value).name()
    except Exception:
        proc_name = "unknown"

    rect = RECT()
    GetWindowRect(hwnd, ctypes.byref(rect))

    return {
        "hwnd": hwnd,
        "title": title,
        "class": class_name,
        "pid": pid.value,
        "process": proc_name,
        "rect": (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top),
    }


def get_all_wlo_windows():
    """Lấy danh sách tất cả các cửa sổ liên quan đến WLO, aProxy, PowerShell."""
    wlo_windows = {}

    def callback(hwnd, lparam):
        if IsWindowVisible(hwnd):
            info = get_window_info(hwnd)
            if info:
                pname = info["process"].lower()
                title = info["title"].lower()
                if any(k in pname for k in ["alogin", "proxy", "powershell"]) or any(k in title for k in ["verify", "wlo", "drifter"]):
                    wlo_windows[hwnd] = info
        return True

    EnumWindows(EnumWindowsProc(callback), 0)
    return wlo_windows


def monitor_loop(duration=60, interval=0.2):
    """
    Vòng lặp theo dõi sự thay đổi cửa sổ và pixel trong `duration` giây.
    """
    print("=" * 65)
    print("🔍 BẮT ĐẦU THEO DÕI SỰ KIỆN CỬA SỔ & PIXEL (MONITOR)")
    print("   • Hãy thực hiện thao tác đăng nhập như bình thường.")
    print("   • Script sẽ ghi nhận mọi cửa sổ mới và sự thay đổi màu pixel.")
    print("   • Nhấn Ctrl+C bất kỳ lúc nào để dừng lại.")
    print("=" * 65)

    start_time = time.time()
    known_windows = set()
    last_pixels = {}
    last_fore_hwnd = None

    try:
        while time.time() - start_time < duration:
            t = time.time() - start_time
            current_windows = get_all_wlo_windows()

            # 1. Phát hiện cửa sổ mới xuất hiện
            for hwnd, info in current_windows.items():
                if hwnd not in known_windows:
                    known_windows.add(hwnd)
                    print(f"[{t:05.2f}s] [CỬA SỔ MỚI] HWND: {hwnd} | Process: {info['process']} | Title: '{info['title']}' | Class: {info['class']} | Rect: {info['rect']}")

            # Phát hiện cửa sổ biến mất
            for hwnd in list(known_windows):
                if hwnd not in current_windows:
                    known_windows.remove(hwnd)
                    print(f"[{t:05.2f}s] [CỬA SỔ ĐÃ ĐÓNG] HWND: {hwnd}")

            # 2. Phát hiện cửa sổ Foreground thay đổi
            fore_hwnd = GetForegroundWindow()
            if fore_hwnd != last_fore_hwnd:
                last_fore_hwnd = fore_hwnd
                info = get_window_info(fore_hwnd)
                if info and any(k in info['process'].lower() for k in ["alogin", "proxy", "powershell"]):
                    print(f"[{t:05.2f}s] [FOCUS ĐỔI] Active Window: '{info['title']}' ({info['process']})")

            # 3. Theo dõi màu sắc các điểm pixel quan trọng
            for name, (x, y) in WATCH_COORDS.items():
                try:
                    rgb = get_pixel_rgb(x, y)
                    prev_rgb = last_pixels.get(name)
                    if prev_rgb is not None and prev_rgb != rgb:
                        # Chỉ in nếu có sự thay đổi rõ rệt (chênh lệch > 15)
                        diff = abs(rgb[0] - prev_rgb[0]) + abs(rgb[1] - prev_rgb[1]) + abs(rgb[2] - prev_rgb[2])
                        if diff > 15:
                            print(f"[{t:05.2f}s] [PIXEL ĐỔI] {name} ({x}, {y}): {prev_rgb} -> {rgb} (Diff: {diff})")
                    last_pixels[name] = rgb
                except Exception:
                    pass

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n[*] Đã dừng theo dõi.")

    print("\n" + "=" * 65)
    print("🏁 KẾT THÚC THEO DÕI.")
    print("=" * 65)


if __name__ == "__main__":
    monitor_loop(duration=120, interval=0.2)
