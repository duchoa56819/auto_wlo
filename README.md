# auto_wlo

Bộ công cụ tự động hóa toàn diện cho Wonderland Online (WLO).

## 📁 Cấu trúc dự án

Dự án bao gồm các module độc lập phục vụ từng nhu cầu tự động hóa khác nhau:

### 1. [mail_otp/](mail_otp/) - Tự động lấy mã OTP Gmail
- Tự động lấy mã xác minh 4 số từ email ban quản trị `GM@wloi.org`.
- Hỗ trợ quản lý đăng nhập nhiều tài khoản Gmail.
- Có giao diện người dùng Desktop (Tkinter GUI) và script dòng lệnh (CLI).
- Tự động sao chép mã OTP vào Clipboard (`Ctrl + V`).
- Chế độ chờ email mới (Realtime Auto-Wait).

### 2. [WLO_Auto_Framework/](WLO_Auto_Framework/) - Proxy can thiệp tầng mạng (TCP Layer)
- Local AsyncIO TCP Proxy trung gian (`127.0.0.1:6415` -> `6414`).
- Tự động giải mã / mã hóa các gói tin WLO (XOR 173, Signature `0x44F4`).
- Can thiệp, bóc tách opcode, chặn hoặc tự động bơm (inject) gói tin lên server game trong `auto_logic.py`.
- Kèm công cụ phân tích log gói tin `parse_wlo.py`.

### 3. [auto_login/](auto_login/) - Tự động đăng nhập Game (AutoHotkey v2)
- Script AutoHotkey v2 tự động chạy `alogin.exe`, chọn máy chủ, kênh và đăng nhập tài khoản.
- Hỗ trợ tách file cấu hình riêng (`login_config.ini`), bảo mật tài khoản game khi đẩy lên git.

---

## 🔒 Bảo mật thông tin cá nhân
Các file cấu hình chứa thông tin nhạy cảm (mật khẩu Gmail `accounts.json`, tài khoản/mật khẩu game `login_config.ini`) đã được khai báo trong `.gitignore` để đảm bảo không bị rò rỉ khi đẩy lên GitHub.
