# BÁO CÁO PHÂN TÍCH TOÀN DIỆN: PHỤ BẢN QUỐC BẢO (NATIONAL TREASURE)

---

## 1. TỔNG QUAN PHIÊN HOẠT ĐỘNG
- **Thời gian thực hiện**: 19:30:22 - 19:37:46 (Tổng thời gian ~7 phút 24 giây).
- **Đội hình tham gia**: 4 tài khoản kết hợp hoàn hảo:
  * `W04` (Đội trưởng - Hệ Thủy)
  * `W03` (Hệ Thủy)
  * `F04` (Hệ Hỏa - Sát thương chủ lực)
  * `Wi01` (Hệ Phong)
- **Kết quả chung**: Vượt ải thành công 100%, chiến thắng toàn bộ 3 trận đánh, giải mã trọn vẹn các cơ quan câu đố và thu về trọn bộ rương báu quý hiếm (Trứng Ma Thuật Lớn, Trứng Ma Thuật, Thuốc x4/x3 EXP, Chuồn Chuồn Mini).

---

## 2. CẤU TRÚC BẢN ĐỒ & HỆ THỐNG MÊ CUNG

Qua luồng gói tin chuyển cảnh (`S->C Op: 0x35 Sub: 0x05`), National Treasure được thiết kế thành một hệ thống mê cung 4 Tầng/Khu vực theo ma trận ID chuẩn:

| Khu vực | Mã Hex Map | Mã Dec Map | Đặc điểm chức năng |
| :--- | :---: | :---: | :--- |
| **Khu vực 1 (Area 1)** | `0x0102`, `0x0103`, `0x0104` | `258`, `259`, `260` | Tầng khởi đầu, phòng đối thoại & Trận chiến #1 |
| **Khu vực 2 (Area 2)** | `0x0201`, `0x0202`, `0x0203`, `0x0204` | `513`, `514`, `515`, `516` | Tầng cơ quan trung gian & Trận chiến #2 |
| **Khu vực 3 (Area 3)** | `0x0301`, `0x0302`, `0x0303`, `0x0304` | `769`, `770`, `771`, `772` | Tầng mê cung câu đố & gom Dấu ấn bảo vật |
| **Khu vực 4 (Area 4)** | `0x0401`, `0x0402`, `0x0403`, `0x0404` | `1025`, `1026`, `1027`, `1028` | Điện thờ bảo vật & Trận Đại Trùm Cuối (Boss Battle) |

---

## 3. PHÂN TÍCH CHI TIẾT 3 TRẬN ĐÁNH

### ⚔️ TRẬN ĐÁNH #1: QUÁI TIỀN TRẠM SƠ CẤP
- **Thời điểm**: 19:33:49 | **Thời gian hạ gục**: 29.5 giây.
- **Danh sách quái vật (4 Quái Cấp 40)**:
  * Quái ID `20136` (`0x4EA8`): Level 40 | Hàng 1 Sau (Slot 2 Row 1 - Pos 5) | HP: `440` | SP: `319`
  * Quái ID `20137` (`0x4EA9`): Level 40 | Hàng 2 Trước (Slot 1 Row 2 - Pos 2) | HP: `411` | SP: `307`
  * Quái ID `20138` (`0x4EAA`): Level 40 | Hàng 3 Trước (Slot 1 Row 3 - Pos 3) | HP: `428` | SP: `307`
  * Quái ID `20139` (`0x4EAB`): Level 40 | Hàng 4 Sau (Slot 2 Row 4 - Pos 8) | HP: `408` | SP: `330`
- **Diễn biến**: Quái sơ cấp lượng máu rất thấp, bị tiêu diệt gọn gàng ngay lượt đầu tiên.

---

### ⚔️ TRẬN ĐÁNH #2: QUÁI TRUNG CẤP CƠ QUAN
- **Thời điểm**: 19:34:41 | **Thời gian hạ gục**: Siêu tốc **8.5 giây** (4 lượt đánh).
- **Danh sách quái vật (4 Quái Cấp 62 - 68)**:
  * Quái ID `20124` (`0x4E9C`): Level 68 | Hàng 1 Sau (Slot 2 Row 1 - Pos 5) | HP: `855` | SP: `518`
  * Quái ID `20122` (`0x4E9A`): Level 64 | Hàng 2 Trước (Slot 1 Row 2 - Pos 2) | HP: `889` | SP: `508`
  * Quái ID `20123` (`0x4E9B`): Level 62 | Hàng 3 Trước (Slot 1 Row 3 - Pos 3) | HP: `841` | SP: `528`
  * Quái ID `20125` (`0x4E9D`): Level 66 | Hàng 4 Sau (Slot 2 Row 4 - Pos 8) | HP: `832` | SP: `540`
- **Diễn biến**: F04 và các Pet dồn sát thương kết liễu toàn bộ quái chỉ trong 1 hiệp đấu.

---

### ⚔️ TRẬN ĐÁNH #3: TRẬN ĐẠI CHIẾN TRÙM CUỐI (BOSS BATTLE)
- **Thời điểm**: 19:35:55 | **Thời gian hạ gục**: Xuất sắc **22.4 giây** (8 lượt đánh).
- **Đội hình địch (6 Quái: 2 Siêu Boss & 4 Hộ Vệ Cực Mạnh)**:
  * 👑 **SIÊU BOSS 1** (ID `20134` - `0x4EA6`): **Level 184** | Hàng 2 Trước (Slot 1 Row 2 - Pos 2) | **HP: 51,463** | SP: `2,500`
  * 👑 **SIÊU BOSS 2** (ID `20135` - `0x4EA7`): **Level 181** | Hàng 3 Trước (Slot 1 Row 3 - Pos 3) | **HP: 52,489** | SP: `2,500`
  * 🛡️ **Hộ Vệ 1** (ID `20140` - `0x4EAC`): **Level 143** | Hàng 2 Sau (Slot 2 Row 2 - Pos 6) | **HP: 22,314** | SP: `1,545`
  * 🛡️ **Hộ Vệ 2** (ID `20141` - `0x4EAD`): **Level 142** | Hàng 3 Sau (Slot 2 Row 3 - Pos 7) | **HP: 20,843** | SP: `1,606`
  * 🛡️ **Hộ Vệ 3** (ID `20143` - `0x4EAF`): **Level 145** | Hàng 4 Trước (Slot 1 Row 4 - Pos 4) | **HP: 20,072** | SP: `1,633`
  * 🛡️ **Hộ Vệ 4** (ID `20142` - `0x4EAE`): **Level 148** | Hàng 4 Sau (Slot 2 Row 4 - Pos 8) | **HP: 21,456** | SP: `1,595`
- **Phân tích chiến thuật thi triển**:
  * **Hiệp 1**: F04 (Char chiêu Hỏa `1f3b` và Pet chiêu `043b`) lập tức tấn công chính xác vào **Hàng 2 Vị trí 2** (Siêu Boss Level 184). Các nhân vật khác và Pet (Wi01, W04, W03) thi triển thế thủ chuẩn xác `75ea` để bảo toàn sinh lực.
  * **Hiệp 2**: Các Pet W04 & W03 tung chiêu sát thương `2d2b`, Pet F04 bồi tiếp chiêu `043b`, dọn sạch dàn quái chỉ trong 2 hiệp ngắn ngủi.

---

## 4. HỆ THỐNG CÂU ĐỐ & DẤU ẤN QUỐC BẢO (RELICS / KEYS)

Trong quá trình vượt các phòng mê cung, hệ thống ghi nhận các chuỗi đối thoại mở khóa (`Opcode 0x20 Subcode 0x02`):
- **Các lựa chọn đáp án câu đố đã giải**: `0x0B`, `0x0F`, `0x09`, `0x0A`.
- **Chuỗi 5 Dấu ấn / Chìa khóa Quốc Bảo nhận được theo tiến độ**:
  1. `0x75AE` (`30126`): **National Treasure Key 1** (Nhận được tại 19:33:37)
  2. `0x75AF` (`30127`): **National Treasure Key 2** (Nhận được sau Trận 1 lúc 19:34:25)
  3. `0x75B0` (`30128`): **National Treasure Key 3** (Nhận được sau Trận 2 lúc 19:34:52)
  4. `0x75B1` (`30129`): **National Treasure Key 4** (Nhận được lúc 19:35:10)
  5. `0x75B2` (`30130`): **National Treasure Key 5** (Nhận được lúc 19:35:28)

---

## 5. BẢNG TỔNG HỢP TOÀN BỘ PHẦN THƯỞNG ĐẠT ĐƯỢC

### Bảng chi tiết từng nhân vật:

| Vật phẩm | Mã Hex / Dec | W04 | W03 | F04 | Wi01 | Tổng cộng cả đội |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **BigMagicalEgg** (Trứng ma thuật lớn) | `0x855D` (`34141`) | x1 | x1 | x1 | x1 | **x4** 🌟 |
| **MagicalEgg** (Trứng ma thuật) | `0x855E` (`34142`) | x1 | x1 | x1 | x1 | **x4** 🌟 |
| **4xPotion** (Thuốc x4 EXP) | `0x855F` (`34143`) | - | x1 | - | - | **x1** |
| **3xPotion** (Thuốc x3 EXP) | `0x8553` (`34131`) | x1 | x1 | - | x2 | **x4** |
| **MiniDragonfly** (Chuồn chuồn mini) | `0x861C` (`34332`) | - | x1 | x1 | x1 | **x3** |
| **PetReturnScroll** (Cuộn quay về Pet) | `0x855B` (`34139`) | x1 | x1 | - | x1 | **x3** |
| **DarkChocolate** (Sô-cô-la đen) | `0x8525` (`34085`) | - | - | x1 | - | **x1** |
| **Rương bảo vật 858C** | `0x858C` (`34188`) | x2 | - | - | x2 | **x4** |
| **Rương bảo vật 858D** | `0x858D` (`34189`) | - | x1 | x1 | - | **x2** |
| **Rương bảo vật 858E** | `0x858E` (`34190`) | - | - | x1 | x1 | **x2** |
| **Rương bảo vật 855C** | `0x855C` (`34140`) | x1 | - | x2 | - | **x3** |
| **Rương bảo vật 8560** | `0x8560` (`34144`) | x1 | - | - | - | **x1** |
| **Rương bảo vật 8562** | `0x8562` (`34146`) | x1 | x2 | x1 | - | **x4** |
| **Dấu ấn Quốc Bảo 1** | `0x75AE` (`30126`) | x1 | x1 | x1 | x1 | **x4** |
| **Dấu ấn Quốc Bảo 2** | `0x75AF` (`30127`) | x1 | x1 | x2 | x1 | **x5** |
| **Dấu ấn Quốc Bảo 3** | `0x75B0` (`30128`) | x1 | x1 | x1 | x1 | **x4** |
| **Dấu ấn Quốc Bảo 4** | `0x75B1` (`30129`) | - | - | x1 | - | **x1** |
| **Dấu ấn Quốc Bảo 5** | `0x75B2` (`30130`) | x1 | x1 | x1 | x1 | **x4** |
