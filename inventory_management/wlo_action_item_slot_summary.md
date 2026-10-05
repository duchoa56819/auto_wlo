# BẢNG TỔNG HỢP GIAO THỨC TÚI ĐỒ, ĐỊNH DANH HÀNH ĐỘNG, SLOT VÀ ITEM ID WONDERLAND ONLINE (WLO)

Tài liệu được trích xuất và giải mã trực tiếp từ:
- Nhật ký gói tin thực nghiệm: `live_packet_log.txt`
- Cơ sở dữ liệu vật phẩm gốc của game: `data/Item.Dat`

---

## I. BẢNG MÃ HÀNH ĐỘNG (ACTION CODES & PACKET STRUCTURE)

Toàn bộ thao tác túi đồ gửi từ Client lên Server (`C->S`) sử dụng **Opcode chính `0x17`** (trong WLO là nhóm lệnh quản lý Tương tác nhân vật & Túi đồ).

| Tên thao tác | Opcode | Subcode | Chiều dài | Cấu trúc Payload (Hex) | Ý nghĩa chi tiết các Byte |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **Kéo / Dồn ô vật phẩm**<br>*(Move / Drag / Stack Item)* | `0x17`<br>(23) | `0x0A`<br>(10) | 5 bytes | `[SourceSlot] [Quantity] [DestSlot]` | • **Byte 0 (`SourceSlot`)**: Ô đồ nguồn (1-indexed)<br>• **Byte 1 (`Quantity`)**: Số lượng vật phẩm chuyển<br>• **Byte 2 (`DestSlot`)**: Ô đồ đích đến (1-indexed) |
| **Mở / Sử dụng vật phẩm**<br>*(Use / Open Item)* | `0x17`<br>(23) | `0x4B`<br>(75) | 4 bytes | `[Slot] [Target/Mode]` | • **Byte 0 (`Slot`)**: Ô chứa vật phẩm cần mở/dùng<br>• **Byte 1 (`Target/Mode`)**: Thường là `0x00` (dùng lên bản thân / mở quà tự do) |
| **Yêu cầu Vứt vật phẩm**<br>*(Request Discard Item)* | `0x17`<br>(23) | `0x03`<br>(3) | 5 bytes | `[Slot] [Quantity] [ActionFlag]` | • **Byte 0 (`Slot`)**: Ô chứa vật phẩm cần vứt<br>• **Byte 1 (`Quantity`)**: Số lượng vứt<br>• **Byte 2 (`ActionFlag`)**: Cờ thao tác bắt đầu vứt (`0x01`) |
| **Xác nhận Vứt đồ có cảnh báo**<br>*(Confirm Drop Popup)* | `0x17`<br>(23) | `0x7C`<br>(124) | 5 bytes | `[Slot] [Quantity] [ConfirmFlag]` | • **Byte 0 (`Slot`)**: Ô trùng với lệnh Sub `0x03` trước đó<br>• **Byte 1 (`Quantity`)**: Số lượng trùng với Sub `0x03`<br>• **Byte 2 (`ConfirmFlag`)**: Cờ xác nhận bấm nút OK (`0x02`) |
| **Âm thanh cảnh nền / BGM**<br>*(Ambient Audio / Music)* | `0x3E`<br>(62) | `0x3D`<br>(61) | 13 bytes | `01000000 + ASCII` | Tên chuỗi hiệu ứng âm thanh (ví dụ `BGM0011`) |

### Cơ chế phân loại Vứt đồ (Discard Filtering Mechanism):
1. **Vật phẩm thông thường (Consumables / Food thông thường):**
   - *Bao gồm:* Meatballs, Poisonous Potion, Fruit Crepe, Millet Wine.
   - *Quy trình:* Chỉ gửi duy nhất gói `Sub: 0x03`. Game lập tức xóa khỏi túi, không bật popup xác nhận.
2. **Vật phẩm đặc biệt / Có giá trị / Sự kiện (Special / Rare / Event Items):**
   - *Bao gồm:* Gum, Chocolate, Fun Token, Love Picnic Lunch, Latania Peel.
   - *Quy trình 2 bước:*
     1. Client gửi `Sub: 0x03` $\rightarrow$ Game bật cửa sổ popup hỏi: *"Bạn có chắc chắn muốn vứt vật phẩm này?"*.
     2. Người chơi bấm nút **OK** $\rightarrow$ Client gửi tiếp `Sub: 0x7C` mang cờ `0x02` để Server thực hiện hủy đồ.

---

## II. BẢNG TRA CỨU CÁC SLOT TÚI ĐỒ (INVENTORY SLOTS)

Game Wonderland Online quy ước chỉ số các ô đồ trong túi bắt đầu từ **1 (1-indexed)**:

| Slot (Hex) | Slot (Thập phân) | Mô tả vai trò trong phiên thao tác |
| :---: | :---: | :--- |
| `0x01` | **Ô 1** | Ô ban đầu chứa 5 cái Gum (đã vứt) $\rightarrow$ Sau đó được dùng làm ô đích để kéo Đào (Peach) và Trứng (Egg) về đây mở. |
| `0x03` | **Ô 3** | Ô ban đầu chứa 10 cái Chocolate (đã vứt) $\rightarrow$ Trở thành **ô trống đầu tiên** trong túi $\rightarrow$ Tất cả các vật phẩm mở ra từ Đào đều tự động rơi vào ô này để bạn vứt. |
| `0x14` | **Ô 20** | Ô chứa 9 quả Strange Peach ban đầu trước khi kéo về Ô 1. |
| `0x1C` | **Ô 28** | Ô chứa 5 quả Magical Egg ban đầu trước khi kéo về Ô 1 $\rightarrow$ Sau khi các ô trống phía trên đã lấp đầy bởi các món giữ lại, món **Latania Peel** mở ra đã rơi vào ô 28 này. |
| `0x1F` | **Ô 31** | Ô chứa 13 quả Big Magical Egg trước khi kéo về Ô 1. |

> **Nguyên tắc phân bổ ô trống (Inventory Slot Allocation):**
> Khi bạn mở một vật phẩm tạo ra món mới, hệ thống game luôn ưu tiên nhét món mới vào **ô trống có số thứ tự nhỏ nhất** (Lowest empty slot index).

---

## III. BẢNG DANH MỤC ITEM VÀ ITEM ID (ITEM DATABASE)

Tra cứu chính xác từ cấu trúc nhị phân 451-byte của `Item.Dat`:

| Tên tiếng Việt | Tên gốc trong game | Item ID (Thập phân) | Item ID (Hex) | Ghi chú & Thao tác trong phiên |
| :--- | :--- | :---: | :---: | :--- |
| **Kẹo cao su** | `Gum` | **3929** | `0x0F59` | Có ở Ô 1 (vứt 5 cái, cần xác nhận Sub 0x7C) |
| **Sô-cô-la** | `Chocolate` | **3930** | `0x0F5A` | Có ở Ô 3 (vứt 10 cái, cần xác nhận Sub 0x7C) |
| **Đào kỳ dị** | `Strange Peach` | **4351** | `0x10FF` | Có 9 quả ở Ô 20, kéo về Ô 1 và mở hết |
| **Thịt viên** | `Meatballs` | **3885** | `0x0F2D` | Mở từ Đào ra 20 viên $\rightarrow$ Vứt ngay (không cần 0x7C) |
| **Thuốc độc** | `Poisonous Potion` | **4219** | `0x107B` | Mở từ Đào ra 5 bình $\rightarrow$ Vứt ngay |
| **Xu giải trí** | `Fun Token` | **4284** | `0x10BC` | Mở từ Đào ra 1 cái $\rightarrow$ Vứt (có popup Sub 0x7C) |
| **Bữa trưa picnic tình yêu**| `Love Picnic Lunch` | **4339** | `0x10F3` | Mở từ Đào ra 1 cái $\rightarrow$ Vứt (có popup Sub 0x7C) |
| **Bánh crepe trái cây** | `Fruit Crepe` | **3900** | `0x0F3C` | Mở từ Đào ra 20 cái $\rightarrow$ Vứt ngay |
| **Lông chim bất tử** | `Undead Bird Feather` | **4233** | `0x1089` | Mở từ Đào $\rightarrow$ **GIỮ LẠI TRONG TÚI** |
| **Rượu kê** | `Millet Wine` | **3958** | `0x0F76` | Mở từ Đào ra 30 bình $\rightarrow$ Vứt ngay |
| **Trứng ma thuật** | `Magical Egg` | **4413** | `0x113D` | Có 5 quả ở Ô 28, kéo về Ô 1 và mở hết |
| **Thuốc nhân đôi kinh nghiệm**| `2x EXP Potion` | **4379** | `0x111B` | Mở từ Trứng lần 1 $\rightarrow$ **GIỮ LẠI TRONG TÚI** |
| **Cuộn hồi quy thú cưng** | `Pet Return Scroll` | **4410** | `0x113A` | Mở từ Trứng lần 2 $\rightarrow$ **GIỮ LẠI TRONG TÚI** |
| **Viên nang 1% kinh nghiệm** | `1% EXP Capsule` | **4407** | `0x1137` | Mở từ Trứng lần 3 $\rightarrow$ **GIỮ LẠI TRONG TÚI** |
| **Vỏ cây Latania** | `Latania Peel` | **4248** | `0x1098` | Mở từ Trứng lần 4 rơi vào Ô 28 $\rightarrow$ Vứt (có popup Sub 0x7C) |
| **Đá ngọc ma** | `Demon Jade Stone` | **5249** | `0x1481` | Mở từ Trứng lần 5 $\rightarrow$ **GIỮ LẠI TRONG TÚI** |
| **Trứng ma thuật lớn** | `Big Magical Egg` | **4412** | `0x113C` | Có 13 quả ở Ô 31, kéo về Ô 1 |

---

## IV. BẢNG ĐỐI CHIẾU CHI TIẾT 36 GÓI TIN VỚI 19 HÀNH ĐỘNG

| STT Gói | Thời gian | Hướng | Opcode | Subcode | Payload Hex | Hành động tương ứng của người chơi |
| :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **#1** | 08:26:26 | C->S | `0x17` | `0x03` | `01 05 01` | Yêu cầu vứt Gum ở Ô 1 (số lượng 5) |
| **#2** | 08:26:27 | C->S | `0x17` | `0x7C` | `01 05 02` | Bấm OK popup xác nhận vứt Gum ở Ô 1 |
| **#3** | 08:26:31 | C->S | `0x17` | `0x03` | `03 0a 01` | Yêu cầu vứt Chocolate ở Ô 3 (số lượng 10) |
| **#4** | 08:26:34 | C->S | `0x17` | `0x7C` | `03 0a 02` | Bấm OK popup xác nhận vứt Chocolate ở Ô 3 |
| **#5** | 08:26:51 | C->S | `0x17` | `0x0A` | `14 09 01` | Kéo 9 quả Đào từ Ô 20 (`0x14`) sang Ô 1 (`0x01`) |
| **#6** | 08:26:53 | C->S | `0x17` | `0x4B` | `01 00` | Mở quả đào thứ 1 ở Ô 1 |
| **#7** | 08:27:01 | C->S | `0x17` | `0x03` | `03 14 01` | Vứt 20 Meatballs rơi vào Ô 3 (vứt ngay) |
| **#8** | 08:28:18 | C->S | `0x17` | `0x4B` | `01 00` | Mở quả đào thứ 2 ở Ô 1 |
| **#9** | 08:28:22 | C->S | `0x17` | `0x03` | `03 05 01` | Vứt 5 Poisonous Potion rơi vào Ô 3 (vứt ngay) |
| **#10** | 08:28:36 | C->S | `0x17` | `0x4B` | `01 00` | Mở quả đào thứ 3 ở Ô 1 |
| **#11** | 08:28:50 | C->S | `0x17` | `0x03` | `03 01 01` | Yêu cầu vứt 1 Fun Token rơi vào Ô 3 |
| **#12** | 08:28:52 | C->S | `0x17` | `0x7C` | `03 01 02` | Bấm OK popup xác nhận vứt Fun Token ở Ô 3 |
| **#13** | 08:28:53 | C->S | `0x17` | `0x4B` | `01 00` | Mở quả đào thứ 4 ở Ô 1 |
| **#14** | 08:28:56 | C->S | `0x17` | `0x03` | `03 01 01` | Yêu cầu vứt 1 Fun Token rơi vào Ô 3 |
| **#15** | 08:28:57 | C->S | `0x17` | `0x7C` | `03 01 02` | Bấm OK popup xác nhận vứt Fun Token ở Ô 3 |
| **#16** | 08:28:59 | C->S | `0x17` | `0x03` | `01 01 01` | Nhấp nhầm định vứt Đào ở Ô 1 $\rightarrow$ Hủy (không có 0x7C) |
| **#17** | 08:29:01 | C->S | `0x17` | `0x4B` | `01 00` | Mở quả đào thứ 5 ở Ô 1 |
| **#18** | 08:29:32 | C->S | `0x17` | `0x03` | `03 01 01` | Yêu cầu vứt 1 Love Picnic rơi vào Ô 3 |
| **#19** | 08:29:33 | C->S | `0x17` | `0x7C` | `03 01 02` | Bấm OK popup xác nhận vứt Love Picnic ở Ô 3 |
| **#20** | 08:29:34 | C->S | `0x17` | `0x4B` | `01 00` | Mở quả đào thứ 6 ở Ô 1 |
| **#21** | 08:29:38 | C->S | `0x17` | `0x03` | `03 14 01` | Vứt 20 Fruit Crepe rơi vào Ô 3 (vứt ngay) |
| **#22** | 08:29:50 | C->S | `0x17` | `0x4B` | `01 00` | Mở quả đào thứ 7 ở Ô 1 ra Undead Bird Feather (giữ lại) |
| **#23** | 08:30:10 | C->S | `0x17` | `0x4B` | `01 00` | Mở quả đào thứ 8 ở Ô 1 |
| **#24** | 08:30:16 | C->S | `0x17` | `0x03` | `03 1e 01` | Vứt 30 Millet Wine rơi vào Ô 3 (vứt ngay) |
| **#25** | 08:30:34 | C->S | `0x17` | `0x4B` | `01 00` | Mở quả đào thứ 9 ở Ô 1 |
| **#26** | 08:30:43 | C->S | `0x17` | `0x03` | `03 14 01` | Vứt 20 Meatballs rơi vào Ô 3 (vứt ngay) |
| **#27** | 08:30:54 | C->S | `0x3E` | `0x3D` | `BGM0011` | Kích hoạt hiệu ứng âm thanh nền game |
| **#28** | 08:30:55 | C->S | `0x17` | `0x0A` | `1c 05 01` | Kéo 5 quả Trứng từ Ô 28 (`0x1C`) sang Ô 1 (`0x01`) |
| **#29** | 08:30:57 | C->S | `0x17` | `0x4B` | `01 00` | Mở quả trứng thứ 1 ra 2x EXP Potion (giữ lại) |
| **#30** | 08:31:44 | C->S | `0x17` | `0x4B` | `01 00` | Mở quả trứng thứ 2 ra Pet Return Scroll (giữ lại) |
| **#31** | 08:32:05 | C->S | `0x17` | `0x4B` | `01 00` | Mở quả trứng thứ 3 ra 1% EXP Capsule (giữ lại) |
| **#32** | 08:32:24 | C->S | `0x17` | `0x4B` | `01 00` | Mở quả trứng thứ 4 ra Latania Peel (rơi vào Ô 28) |
| **#33** | 08:32:32 | C->S | `0x17` | `0x03` | `1c 01 01` | Yêu cầu vứt 1 Latania Peel ở Ô 28 (`0x1C`) |
| **#34** | 08:32:37 | C->S | `0x17` | `0x7C` | `1c 01 02` | Bấm OK popup xác nhận vứt Latania Peel ở Ô 28 |
| **#35** | 08:32:52 | C->S | `0x17` | `0x4B` | `01 00` | Mở quả trứng thứ 5 ra Demon Jade Stone (giữ lại) |
| **#36** | 08:33:31 | C->S | `0x17` | `0x0A` | `1f 0d 01` | Kéo 13 quả Trứng lớn từ Ô 31 (`0x1F`) sang Ô 1 (`0x01`) |
