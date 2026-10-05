# Auto Login WLO (AutoHotkey v2)

Script tự động mở game `alogin.exe`, điều hướng menu và nhập thông tin đăng nhập tự động bằng AutoHotkey v2.

## 📋 Yêu cầu
- Đã cài đặt **AutoHotkey v2.0+**: [Tải tại autohotkey.com](https://www.autohotkey.com/)

## ⚙️ Cấu hình
1. Đổi tên hoặc copy file `login_config.example.ini` thành `login_config.ini`.
2. Mở `login_config.ini` và điền:
   - `Username`: Tên tài khoản game
   - `Password`: Mật khẩu tài khoản game
   - `GamePath`: Đường dẫn tới file `alogin.exe` trên máy tính của bạn

*(File `login_config.ini` đã được cấu hình trong `.gitignore`, đảm bảo an toàn không bị lộ thông tin lên GitHub).*

## 🚀 Sử dụng
- Nhấp đúp vào file `login.ahk` để khởi chạy.
- Script sẽ tự động:
  1. Khởi động `alogin.exe`.
  2. Bỏ qua màn hình giới thiệu.
  3. Chọn cụm máy chủ và kênh.
  4. Điền tài khoản, mật khẩu và bấm Đăng nhập.
