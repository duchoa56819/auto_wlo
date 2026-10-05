# auto_wlo

Bộ công cụ tự động hóa và hỗ trợ chơi Wonderland Online (WLO).

## Cấu trúc dự án

- **`mail_otp/`**: Công cụ tự động lấy mã xác thực OTP 4 số từ email `GM@wloi.org` gửi đến Gmail.
  - Hỗ trợ đa tài khoản Gmail (không giới hạn số lượng).
  - Giao diện trực quan (GUI Tkinter) & Script dòng lệnh (CLI).
  - Tự động sao chép mã OTP vào Clipboard (`Ctrl + V`).
  - Chế độ chờ thư mới (Realtime Auto-Wait).

---

Chi tiết hướng dẫn sử dụng từng module vui lòng xem trong thư mục tương ứng (ví dụ: [`mail_otp/README.md`](mail_otp/README.md)).
