# Dungeon & Instance Automation (Phó bản & Nhiệm vụ WLO)

Thư mục chứa các script và công cụ tự động hóa vượt phó bản, leo tháp, và làm nhiệm vụ trong Wonderland Online.

---

## 🏰 Danh sách phó bản hỗ trợ

### 1. Cursed Palace (Cung Điện Bị Nguyền Rủa / Athena)
- **`wlo_auto_athena_cursed_palace.py`** (`run_auto_athena_cursed_palace.bat`): Script tự động chạy toàn bộ quy trình đi Cursed Palace cho team 4 acc.
- **`wlo_cursed_palace_monitor.py`** (`run_cursed_palace_monitor.bat`): Giám sát trạng thái trận đánh, vị trí người chơi và NPC trong Cursed Palace thời gian thực.
- **`wlo_cursed_palace_combat_controller.py`**: Điều phối chiến đấu thông minh từng ải Cursed Palace.
- **`wlo_cursed_palace_auto_discard.py`** (`run_discard_palace_trash.bat`): Tự động vứt các vật phẩm rác rơi ra từ Cursed Palace để tránh đầy hòm đồ.
- **Tài liệu & Dữ liệu**:
  - `cursed_palace_combat_logic.json` & `cursed_palace_combat_logic.md`: Logic và thứ tự target/kỹ năng từng stage.
  - `cursed_palace_analysis_report.md`: Báo cáo phân tích cấu trúc ải và gói tin packet.

### 2. Tower 29 (Tháp 29 Tầng)
- **`wlo_tower_29_monitor.py`**: Giám sát tiến độ leo tháp 29 tầng.
- **`wlo_tower_29_combat_controller.py`**: Bộ điều khiển tự động đánh boss và quái từng tầng.
- **`wlo_tower_29_auto_discard.py`** (`run_discard_tower_trash.bat`): Tự động dọn dẹp vật phẩm rác rơi ra khi leo tháp.
- **`compile_tower_stages.py` & `generate_tower_report.py`**: Công cụ biên dịch dữ liệu và xuất báo cáo phân tích 29 tầng.
- **Tài liệu & Dữ liệu**:
  - `tower_29_compiled_stages.json` & `tower_29_parsed_battles.json`: Dữ liệu phân tích quái, HP, vị trí từng tầng.
  - `tower_29_combat_logic.md` & `tower_29_analysis_report.md`: Phân tích chi tiết chiến thuật.

### 3. Dungeon 30009 & Party Instance Hub
- **`wlo_dungeon_30009_gui.py`** (`run_dungeon_30009.bat`): Giao diện trực quan tự động điều khiển phó bản 30009.
- **`wlo_party_dungeon_hub_gui.py`** (`run_party_dungeon_hub.bat`): Trung tâm điều phối đa phó bản cho tổ đội.
- **`wlo_capture_party_instance.py`** (`run_capture_party_instance.bat`): Bắt gói tin phân tích cơ chế các phó bản tổ đội.
- **`wlo_simulate_dungeon.py`** (`run_simulator.bat`): Giả lập tiến trình phó bản để kiểm thử logic trước khi chạy thực tế.
- **`exact_dungeon_scripts.json` & `export_exact_dungeon_scripts.py`**: Dữ liệu kịch bản tọa độ di chuyển chính xác.

### 4. National Treasure (Bảo Vật Quốc Gia)
- **`wlo_national_treasure_auto.py`** (`run_national_treasure_auto.bat`): Tự động nhận và làm chuỗi nhiệm vụ Bảo Vật Quốc Gia.
- **`wlo_national_treasure_monitor.py`** (`run_national_treasure_monitor.bat`): Giám sát tiến trình làm nhiệm vụ.
- **`national_treasure_analysis_report.md`**: Báo cáo phân tích nhiệm vụ.

### 5. Reward Analyzer (Phân tích phần thưởng)
- **`wlo_w04_reward_analyzer.py`** (`run_w04_reward_analyzer.bat`): Công cụ phân tích tỷ lệ mở hộp quà / nhận thưởng từ phó bản.
