# auto_wlo

Bộ công cụ tự động hóa toàn diện cho Wonderland Online (WLO).

---

## 📁 Cấu trúc dự án

Dự án được phân chia thành 3 module chuyên biệt:

### 1. [auto_login/](auto_login/) - Tự động đọc mã OTP từ Gmail
- **Chức năng**: Tự động lấy mã xác thực 4 số từ email ban quản trị `GM@wloi.org` gửi đến Gmail để hỗ trợ đăng nhập game.
- Quản lý và lưu trữ đa tài khoản Gmail (không giới hạn).
- Giao diện trực quan Desktop (Tkinter GUI) & Script dòng lệnh (CLI).
- Tự động sao chép mã OTP vào Clipboard (`Ctrl + V`).
- Chế độ Realtime Auto-Wait chờ email mới đến trong 120s.

### 2. [party_combat/](party_combat/) - Auto Tổ Đội & Tự Động Chiến Đấu (2-trong-1)
- **Giao diện hợp nhất 2-trong-1** chạy trên cùng 1 tiến trình Python tối ưu tài nguyên (chạy bằng `run_party_auto_combat.bat`).
- **Tab 1: Quản lý tổ đội (Party)**:
  - Tự động nhận diện tài khoản qua Char ID (`wlo_party_chars.json`).
  - Tự động mời / vào nhóm 4 client, tự giải đường đi, đi Athena / phó bản song song.
  - Tự động dọn rác túi đồ theo danh mục vật phẩm.
- **Tab 2: Tự động chiến đấu (Combat)**:
  - Tự động chọn mục tiêu tối ưu, tự ra chiêu / buff máu / mana / hồi sinh 4 client.
  - Cơ sở dữ liệu kỹ năng đầy đủ trong `wlo_skills_database.json`.

### 3. [WLO_Auto_Framework/](WLO_Auto_Framework/) - Proxy can thiệp tầng mạng (TCP Layer)
- Local AsyncIO TCP Proxy (`127.0.0.1:6415` -> `6414`).
- Tự động giải mã / mã hóa lại các gói tin WLO (XOR 173, Signature `0x44F4`).
- Cho phép hook, lọc opcode, can thiệp hoặc tự động bơm (inject) gói tin lên server game trong `auto_logic.py`.
- Kèm công cụ phân tích log gói tin `parse_wlo.py`.

---

## 🔒 Bảo mật thông tin cá nhân
File cấu hình nhạy cảm chứa mật khẩu ứng dụng Gmail (`accounts.json`) được cấu hình tự động trong `.gitignore`, đảm bảo an toàn tuyệt đối không bị đẩy lên GitHub.
