# Packet Analysis & Sniffer Tools (Phân tích gói tin & Dò mạng WLO)

Bộ công cụ kỹ thuật đảo ngược (Reverse Engineering), giám sát gói tin (Sniffer), bắt gói tin theo opcode và phân tích cơ chế game Wonderland Online.

---

## 🔍 Danh sách công cụ

### 1. Sniffer & Packet Parsers
- **`wlo_live_sniffer.py`** (`run_live_sniffer.bat`): Công cụ bắt và giải mã gói tin thời gian thực từ card mạng / localhost.
- **`wlo_packet_parser.py`** (`run_parser.bat`): Bộ giải mã chi tiết các cấu trúc gói tin WLO (Opcode, Sub-opcode, Payload, Checksum).
- **`wlo_session_analyzer.py`** (`run_session_analyzer.bat`): Phân tích toàn bộ một phiên chơi game được ghi lại.
- **`wlo_app_gui.py`** (`run_app_gui.bat`): Giao diện đồ họa tích hợp theo dõi luồng gói tin và sự kiện game trực quan.

### 2. Capture & Target Protocol Reverse Engineering
- **`wlo_capture_w01.py` - `w04.py` / `f02.py` - `f04.py`**: Các script chuyên biệt dùng để hook và bắt luồng packet từ từng client WLO riêng biệt.
- **`wlo_capture_skills.py`**: Bắt gói tin thi triển kỹ năng để trích xuất opcode và thông số chiêu thức.
- **`wlo_capture_upgrade.py`**: Bắt và phân tích cơ chế nâng cấp đồ / tinh luyện.

### 3. Phân tích tiến trình & chuyển cảnh (Stage & Transition Extraction)
- **`analyze_all_stages.py` & `summarize_stages.py`**: Tự động tổng hợp và thống kê tất cả các giai đoạn trận đánh.
- **`extract_timeline.py` & `extract_full_stage_packets.py`**: Trích xuất dòng thời gian sự kiện gói tin theo giây.
- **`inspect_dialogues.py` & `inspect_transitions.py` & `inspect_transition_steps.py`**: Phân tích hộp thoại NPC và các bước chuyển đổi bản đồ (map transitions).
- **`deep_analyze_party.py` & `find_combats.py`**: Thuật toán tìm kiếm và tách riêng các phiên giao tranh trong file log lớn.
- **`take_screenshot.ps1`**: PowerShell script chụp ảnh màn hình tự động phục vụ debug.
