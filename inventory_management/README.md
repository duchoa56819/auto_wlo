# Inventory & Item Management (Quản lý hòm đồ & Vật phẩm WLO)

Bộ công cụ tự động hóa thao tác hòm đồ, dọn rác, sắp xếp, rèn trang bị và quản lý vật phẩm cho Wonderland Online.

---

## 🎒 Danh sách công cụ

### 1. Tự động vứt rác (Auto Discard)
- **`wlo_auto_discard.py`** (`run_auto_discard.bat`): Tự động quét hòm đồ theo cấu hình blacklist trong `wlo_auto_discard_config.json` và vứt bỏ các vật phẩm không cần thiết.
- **`wlo_realtime_auto_discard.py`** (`run_realtime_auto_discard.bat`): Chế độ chạy ngầm giám sát túi đồ theo thời gian thực (realtime) để dọn ngay khi có rác rơi vào túi đồ.
- **`wlo_auto_discard_config.json`**: File cấu hình danh sách đen (Blacklist) các vật phẩm cần vứt kèm opcode hex và mã thập phân.

### 2. Tự động chuyển vật phẩm (Auto Move Items)
- **`wlo_auto_move_items.py`** (`run_auto_move_items.bat`): Tự động chuyển vật phẩm giữa túi đồ nhân vật, kho đồ, hoặc giữa các nhân vật trong tổ đội.

### 3. Rèn trang bị nhanh (Fast Forge GUI)
- **`wlo_fast_forge_gui.py`** (`run_fast_forge.bat`): Giao diện trực quan tự động hóa thao tác rèn, nâng cấp trang bị nhanh chóng.

### 4. Thu thập & Định danh vật phẩm (Item Collector & Namer)
- **`wlo_item_collector.py`** (`run_item_collector.bat`): Công cụ tự động quét và thu thập thông tin các ID vật phẩm mới xuất hiện trong game.
- **`wlo_item_namer_gui.py`** (`run_item_namer.bat`): Giao diện tra cứu và đặt tên cho các vật phẩm dựa theo cơ sở dữ liệu.
- **`wlo_verify_inventory_sync.py`** (`run_verify_inventory.bat`): Kiểm tra và đối chiếu đồng bộ dữ liệu túi đồ giữa client và server.

### 5. Cơ sở dữ liệu & Tài liệu vật phẩm
- **`wlo_items_database.json` & `wlo_items_database.txt`**: Từ điển đầy đủ mã ID, tên và thuộc tính hàng nghìn vật phẩm trong WLO.
- **`wlo_items_dictionary.md`**: Tài liệu tra cứu chi tiết phân loại vật phẩm.
- **`wlo_action_item_slot_summary.md`**: Bảng tra cứu vị trí slot và hành động tương tác với vật phẩm.
