# WLO Party & Auto Combat System (2-trong-1)

Hệ thống tự động hóa toàn diện cho Wonderland Online: Quản lý tổ đội (Auto-Party) & Tự động chiến đấu (Auto Combat 4 Client) trên cùng 1 tiến trình Python tối ưu RAM/CPU.

---

## 🌟 Tính năng chính

### 1. Tab 1: 👥 Quản Lý Tổ Đội (Party Manager)
- **Auto Sync & Relog**: Tự động nhận diện tài khoản qua Char ID (`wlo_party_chars.json`).
- **Tự động mời và chấp nhận tổ đội** giữa 4 client game.
- **Tự động di chuyển / giải thuật toán đường đi**: Hỗ trợ đi Athena, phó bản song song.
- **Dọn rác túi đồ tự động** dựa trên danh mục vật phẩm `wlo_items_database.json`.

### 2. Tab 2: ⚔️ Tự Động Chiến Đấu (Auto Combat)
- **Quản lý 4 client chiến đấu**: Tự động chọn mục tiêu tối ưu theo máu, hệ khắc chế.
- **Ra chiêu thức / kỹ năng tự động** theo cấu hình `wlo_skills_database.json`.
- **Hỗ trợ buff máu, mana, hồi sinh đồng đội** và pet theo điều kiện cài đặt trước.

---

## 🛠️ Hướng dẫn cài đặt trên máy mới

1. **Cài đặt Python**:
   - Tải Python (bản 3.10 - 3.12 64-bit) từ [python.org](https://www.python.org/).
   - **Lưu ý quan trọng**: Tích chọn `Add python.exe to PATH` khi cài đặt.
2. **Cài đặt thư viện bổ trợ**:
   - Nhấp đúp vào file `install_dependencies.bat` (sẽ tự động cài đặt thư viện `frida`).

---

## 🚀 Cách sử dụng

1. Copy toàn bộ các file trong thư mục này vào chung thư mục chứa game Wonderland Online (nơi có các file `alogin.exe`, `alogin-F02.exe`, `alogin-F04.exe`...).
2. Đăng nhập các cửa sổ game Wonderland Online.
3. Nhấp đúp vào file:
   ```cmd
   run_party_auto_combat.bat
   ```
   *(Hoặc có thể chạy riêng từng giao diện bằng `run_party_gui.bat` hoặc `run_auto_combat.bat`)*.

---

## 📋 Danh sách tệp tin

| Tên tệp | Chức năng |
|---|---|
| `run_party_auto_combat.bat` | Khởi động giao diện hợp nhất 2-trong-1 |
| `wlo_party_combat_gui.py` | Mã nguồn giao diện chính tích hợp |
| `wlo_party_gui.py` | Module quản lý tổ đội & di chuyển |
| `wlo_auto_combat_gui.py` | Module tự động chiến đấu |
| `wlo_party_chars.json` | Cấu hình Char ID tương ứng với từng client |
| `wlo_skills_database.json` | Cơ sở dữ liệu mã chiêu thức/kỹ năng |
| `wlo_items_database.json` | Cơ sở dữ liệu danh mục vật phẩm |
| `install_dependencies.bat` | Script 1-click cài đặt môi trường thư viện |
| `requirements.txt` | Khai báo thư viện cần thiết (`frida`) |
