# WLO Auto Login & OTP Grabber

Bộ công cụ tự động hóa quy trình đăng nhập đa client Wonderland Online (WLO) tích hợp tự động trích xuất mã OTP từ email quản trị (`GM@wloi.org`) và tự động dán vào hộp thoại xác thực.

---

## ✨ Tính năng chính

1. **Tự động hóa hoàn toàn 11 bước đăng nhập**:
   - Tự động kiểm tra và khởi chạy `aProxy.exe`.
   - Khởi chạy từng file client game tương ứng (`alogin-F03.exe`, `alogin-F02.exe`, `alogin-W03.exe`,...).
   - **Tối ưu nhận diện hình ảnh (OpenCV Template Matching)**:
     - Quét nút Thỏa thuận (`btn_enter1.png`) -> Bấm Enter 1 ngay khi hiển thị.
     - Quét nút Tiếp tục (`btn_enter2.png`) -> Bấm Enter 2 ngay khi hiển thị.
     - Quét bảng danh sách Server (`server_list_banner.png` - "伺服器列表") -> Kích hoạt chuỗi click tức thì (không cần độ trễ cố định).
   - Tự động click chọn Server WLOI `(336, 240)` và nút xác nhận `(473, 244)`.
   - Tự động Double-click ô ID `(346, 473)`, xóa ký tự cũ an toàn bằng chuỗi Backspace (chống kẹt phím DirectInput/Delphi), điền tên tài khoản, bấm Tab, điền mật khẩu và bấm Enter.
   - Hỗ trợ chọn **Nhân vật 1** `(340, 470)` hoặc **Nhân vật 2** `(1051, 549)` (tự động tính toán bù trừ tọa độ khi cửa sổ xếp tầng).
   - Tự động kích hoạt gửi OTP và chờ email.
   - Tự động đọc mã OTP 4 số từ Gmail qua giao thức IMAP an toàn.
   - Tự động tìm kiếm cửa sổ PowerShell `Verify Code` do aProxy mở ra, đưa lên tiền cảnh, dán mã OTP từ Clipboard và bấm Enter hoàn tất đăng nhập.

2. **Giao diện quản lý Đa Client (Tkinter Modern Dark GUI)**:
   - File: `auto_login_gui.py` (khởi chạy bằng `run_auto_login_gui.bat`).
   - Hỗ trợ danh sách đa client với checkbox bật/tắt từng tài khoản.
   - Cho phép chọn nhanh Nhân vật 1 hoặc Nhân vật 2 cho từng tài khoản.
   - Hỗ trợ chạy từng client riêng lẻ hoặc chạy hàng loạt toàn bộ danh sách được chọn.
   - Nút **Dừng khẩn cấp** an toàn ngắt tiến trình bất kỳ lúc nào.
   - Nút **Lấy & Dán OTP nhanh** thủ công khi cần.

3. **Công cụ Mail OTP Grabber độc lập**:
   - `app_gui.py` (khởi chạy bằng `run_gui.bat`): Giao diện quản lý email và tra cứu OTP.
   - `get_otp.py`: Module / CLI trích xuất mã OTP từ Gmail.

---

## 📁 Cấu trúc thư mục

```
auto_login/
├── auto_login.py               # Core automation engine (11 bước)
├── auto_login_gui.py           # Giao diện Desktop quản lý đăng nhập đa client
├── get_otp.py                  # Module trích xuất OTP từ Gmail qua IMAP
├── app_gui.py                  # Giao diện phụ quản lý tài khoản email và OTP
├── clients_config.json         # Cấu hình danh sách các client (User, Pass, Exe, Slot, Email)
├── clients_config.example.json # File mẫu cấu hình client
├── accounts.json               # Cấu hình tài khoản Gmail & App Password (bị ignore trên Git)
├── accounts.example.json       # File mẫu cấu hình Gmail
├── btn_enter1.png              # Ảnh mẫu nút Thỏa thuận (Enter 1)
├── btn_enter2.png              # Ảnh mẫu nút Tiếp tục (Enter 2)
├── server_list_banner.png      # Ảnh mẫu bảng '伺服器列表'
├── run_auto_login_gui.bat      # 1-Click mở giao diện Multi-Client Auto Login
├── run_auto_login_f03.bat      # 1-Click chạy nhanh client F03
├── run_gui.bat                 # 1-Click mở GUI tra cứu OTP
├── monitor_events.py           # Công cụ soi tọa độ và pixel cửa sổ game
├── run_monitor_events.bat      # 1-Click mở monitor
└── README.md                   # Hướng dẫn chi tiết
```

---

## 🛠️ Cài đặt & Chuẩn bị

### 1. Cài đặt thư viện Python
Yêu cầu Python 3.10+:
```powershell
pip install pyautogui opencv-python pillow psutil pyperclip pywin32
```

### 2. Cấu hình Email nhận OTP
Google yêu cầu sử dụng **Mật khẩu ứng dụng (App Password 16 chữ cái)**:
1. Bật xác minh 2 bước trên Gmail: [https://myaccount.google.com/security](https://myaccount.google.com/security)
2. Tạo mật khẩu ứng dụng: [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Điền vào file `accounts.json` (tạo từ `accounts.example.json`):
```json
[
  {
    "email": "your_email@gmail.com",
    "password": "xxxx xxxx xxxx xxxx",
    "name": "Acc Chính"
  }
]
```

### 3. Cấu hình danh sách Clients
Chỉnh sửa trong file `clients_config.json`:
```json
[
  {
    "id": "f03_char1",
    "name": "F03 - Nhân vật 1",
    "exe": "alogin-F03.exe",
    "user": "bgdF03",
    "pass": "111111",
    "email": "your_email@gmail.com",
    "char_slot": 1,
    "enabled": true
  }
]
```

---

## 🚀 Khởi chạy

- **Chạy giao diện quản lý đa client (Khuyên dùng)**:
  Nhấp đúp vào `run_auto_login_gui.bat`.
- **Chạy trực tiếp dòng lệnh**:
  ```powershell
  python auto_login.py --client F03 --char 1
  ```
