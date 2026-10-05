# Mail OTP Grabber (WLO)

Công cụ tự động trích xuất mã OTP 4 số từ email của ban quản trị Wonderland Online (`GM@wloi.org`) gửi đến các tài khoản Gmail.

## ✨ Tính năng chính

- **Giao diện trực quan (GUI Tkinter)**: Chạy ngay trên Windows mà không cần cài đặt thêm thư viện bên ngoài.
- **Quản lý đa tài khoản**: Thêm, sửa, xóa và chuyển đổi nhanh giữa nhiều tài khoản Gmail (Acc chính, clone, sub-acc...).
- **Tự động sao chép Clipboard**: Mã OTP sau khi nhận sẽ tự động copy vào Clipboard (nhấn `Ctrl + V` để dán).
- **2 chế độ lấy mã**:
  - **Lấy OTP gần nhất**: Đọc ngay mã từ email mới nhất trong hòm thư.
  - **Chờ OTP mới (Auto-Wait)**: Lắng nghe hòm thư trong 120s, tự động bắt mã ngay khi thư vừa đến.
- **Bảo mật**: File cấu hình `accounts.json` được tự động bỏ qua bởi `.gitignore`, không lo lộ mật khẩu khi đẩy lên Git.

---

## 🛠️ Chuẩn bị tài khoản Gmail (bắt buộc)

Google yêu cầu sử dụng **Mật khẩu ứng dụng (App Password 16 chữ cái)** để kết nối qua giao thức IMAP:

1. **Bật xác minh 2 bước (2-Step Verification)**:
   - Truy cập: [https://myaccount.google.com/security](https://myaccount.google.com/security)
   - Kích hoạt **Xác minh 2 bước** (bằng số điện thoại hoặc ứng dụng xác thực).
2. **Tạo Mật khẩu ứng dụng**:
   - Truy cập: [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   - Nhập tên ứng dụng (ví dụ: `OTP WLO`), nhấn **Tạo** (Create).
   - Lưu lại chuỗi 16 chữ cái được cấp (dạng `xxxx xxxx xxxx xxxx`).

---

## 🚀 Hướng dẫn sử dụng

### 1. Dùng Giao diện Desktop (Khuyên dùng)

- Nhấp đúp vào file `run_gui.bat` hoặc chạy lệnh:
  ```powershell
  python app_gui.py
  ```
- **Quản lý tài khoản**:
  - Chuyển sang tab **👥 Quản Lý Tài Khoản**.
  - Nhấn **➕ Thêm Tài Khoản Mới** (hoặc chọn tài khoản có sẵn rồi bấm **✏️ Sửa**).
  - Điền Gmail và dán **Mật khẩu ứng dụng** 16 chữ cái.
  - Bấm **🔍 Kiểm tra kết nối** để kiểm tra đăng nhập.
- **Lấy OTP**:
  - Trở về tab **⚡ Lấy OTP**, chọn tài khoản cần lấy mã.
  - Bấm **⚡ Lấy OTP Gần Nhất** hoặc **⏱️ Chờ OTP Mới**.

### 2. Dùng Dòng lệnh (CLI)

- Lấy mã từ email gần nhất:
  ```powershell
  python get_otp.py --password "xxxx xxxx xxxx xxxx"
  ```
- Lắng nghe và chờ email mới gửi đến:
  ```powershell
  python get_otp.py --wait --password "xxxx xxxx xxxx xxxx"
  ```
