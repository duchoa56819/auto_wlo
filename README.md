# auto_wlo

Bộ công cụ tự động hóa, phân tích gói tin và hỗ trợ toàn diện cho Wonderland Online (WLO).

---

## 📁 Cấu trúc dự án

Dự án được phân chia thành 6 module chuyên biệt:

### 1. [auto_login/](auto_login/) - Tự Động Đăng Nhập Đa Client & Lấy OTP Tự Động
- **Quy trình 11 bước hoàn toàn tự động**: Quản lý `aProxy.exe`, khởi chạy đa client game (`alogin-*.exe`), tự động nhận diện hình ảnh OpenCV (nút Thỏa thuận, nút Tiếp tục, bảng danh sách Server), điền thông tin tài khoản, tự động chọn Nhân vật 1 hoặc 2.
- **Tự động bắt & dán OTP**: Tự động trích xuất mã OTP 4 số từ Gmail ban quản trị `GM@wloi.org` qua IMAP, dán trực tiếp vào hộp thoại xác thực PowerShell `Verify Code` và bấm Enter.
- **Giao diện đa client hiện đại (GUI Tkinter)**: Checkbox quản lý bật/tắt từng tài khoản, radio chọn nhân vật, nút chạy từng client hoặc đăng nhập hàng loạt, log trực tiếp và dừng khẩn cấp.
- **Công cụ độc lập**: Bao gồm cả GUI tra cứu OTP Gmail thủ công (`app_gui.py`) và module dòng lệnh (`get_otp.py`).

### 2. [party_combat/](party_combat/) - Auto Tổ Đội & Tự Động Chiến Đấu (2-trong-1)
- **Giao diện hợp nhất 2-trong-1** chạy trên cùng 1 tiến trình Python tối ưu tài nguyên (`run_party_auto_combat.bat`).
- **Tab 1: Quản lý tổ đội (Party)**:
  - Tự động nhận diện tài khoản qua Char ID (`wlo_party_chars.json`).
  - Tự động mời / vào nhóm 4 client, tự giải thuật toán đường đi, đi Athena / phó bản song song.
  - Tự động dọn rác túi đồ theo danh mục vật phẩm.
- **Tab 2: Tự động chiến đấu (Combat)**:
  - Tự động chọn mục tiêu tối ưu theo lượng máu và hệ khắc chế.
  - Tự ra chiêu / buff máu / mana / hồi sinh 4 client theo cơ sở dữ liệu `wlo_skills_database.json`.
- Kèm các script bắt gói tin tổ đội (`wlo_capture_party.py`) và kiểm thử logic chiến đấu (`test_combat_logic.py`).

### 3. [dungeon_instances/](dungeon_instances/) - Tự động hóa Phó Bản & Nhiệm Vụ
- **Cursed Palace (Cung Điện Bị Nguyền Rủa / Athena)**:
  - `wlo_auto_athena_cursed_palace.py`: Chạy tự động chuỗi ải Cursed Palace.
  - `wlo_cursed_palace_monitor.py` & `wlo_cursed_palace_combat_controller.py`: Giám sát và điều phối combat từng ải.
  - `wlo_cursed_palace_auto_discard.py`: Tự dọn rác rơi trong phó bản.
- **Tower 29 (Tháp 29 Tầng)**:
  - `wlo_tower_29_monitor.py` & `wlo_tower_29_combat_controller.py`: Giám sát và tự động leo tháp 29 tầng.
  - Dữ liệu compiled stages và báo cáo chi tiết từng tầng.
- **Dungeon 30009 & Party Instance Hub**:
  - `wlo_dungeon_30009_gui.py`: GUI điều khiển phó bản 30009.
  - `wlo_party_dungeon_hub_gui.py`: Hub quản lý đa phó bản cho tổ đội.
- **National Treasure (Bảo Vật Quốc Gia)**:
  - `wlo_national_treasure_auto.py`: Tự động chuỗi nhiệm vụ Bảo Vật Quốc Gia.
- **Reward Analyzer**: Phân tích tỷ lệ mở hộp và rơi phần thưởng.

### 4. [inventory_management/](inventory_management/) - Quản Lý Túi Đồ & Vật Phẩm
- **Auto Discard**: Dọn túi đồ theo blacklist cấu hình (`wlo_auto_discard.py`, `wlo_realtime_auto_discard.py`).
- **Auto Move Items**: Tự động chuyển và sắp xếp vật phẩm giữa túi đồ, kho, và đồng đội (`wlo_auto_move_items.py`).
- **Fast Forge GUI**: Giao diện rèn và nâng cấp trang bị nhanh (`wlo_fast_forge_gui.py`).
- **Item Collector & Namer**: Công cụ thu thập ID vật phẩm mới và gán tên (`wlo_item_collector.py`, `wlo_item_namer_gui.py`).
- **Dictionary & Database**: Từ điển đầy đủ mã ID và phân loại hàng ngàn vật phẩm WLO (`wlo_items_database.json`, `wlo_items_dictionary.md`).

### 5. [packet_analysis_tools/](packet_analysis_tools/) - Giám Sát & Phân Tích Gói Tin
- **Live Sniffer & Parser**: Bắt và phân tích gói tin mạng theo thời gian thực (`wlo_live_sniffer.py`, `wlo_packet_parser.py`).
- **Client Capture Hooks**: Hook và bắt luồng gói tin chuyên biệt cho từng cửa sổ game (`w01`-`w04`, `f02`-`f04`).
- **Stage & Transition Analytics**: Bộ công cụ bóc tách giai đoạn, phân tích chuyển cảnh map và hội thoại NPC.

### 6. [WLO_Auto_Framework/](WLO_Auto_Framework/) - Proxy Can Thiệp Tầng Mạng (TCP Layer)
- Local AsyncIO TCP Proxy (`127.0.0.1:6415` -> `6414`).
- Tự động giải mã / mã hóa lại các gói tin WLO (XOR 173, Signature `0x44F4`).
- Cho phép hook, lọc opcode, can thiệp hoặc tự động bơm (inject) gói tin lên server game trong `auto_logic.py`.

---

## 🔒 Bảo mật thông tin cá nhân
File cấu hình nhạy cảm chứa mật khẩu ứng dụng Gmail (`accounts.json`) và file cấu hình tài khoản game cá nhân được cấu hình tự động trong `.gitignore`, đảm bảo an toàn tuyệt đối khi lưu trữ trên GitHub.
