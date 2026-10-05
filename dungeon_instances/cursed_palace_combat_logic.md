# QUY TẮC & LOGIC CHIẾN ĐẤU MỚI: CURSED PALACE (ẢI 02 ĐẾN ẢI 13)

> **Cập nhật theo yêu cầu mới**:
> 1. **Từ Ải 2 đến 13**: `Wi01` và Pet luôn **Phòng thủ (`75ea`)**.
> 2. **Từ Ải 2 đến 10**: `W03` & Pet, `W04` & Pet luôn **Phòng thủ (`75ea`)**.
> 3. **Ải 11, 12, 13**: Kiểm tra kẻ địch nào chưa bị tiêu diệt (`HP > 0`) thì dùng chiêu tấn công **`d861`** của Char `W04` & `W03`, chiêu tấn công **`a33a`** của Pet `W04` & `W03` lên kẻ địch đó.
> 4. **Từ Ải 2 đến 13 (F04 & Pet)**:
>    - **Lượt 1**:
>      * Char `F04`: Chiêu Hỏa **`1f3b`** lên kẻ địch ở **Hàng 2** (Vị trí 2 hoặc 6).
>      * Pet `F04`: Chiêu **`043b`** lên kẻ địch ở **Hàng 3** (Vị trí 3 hoặc 7).
>    - **Những lượt sau**: Kiểm tra kẻ địch nào chưa bị tiêu diệt thì dùng lên mục tiêu đó, **ưu tiên kẻ địch ở Hàng 2 (Vị trí 2 hoặc 6) và Hàng 3 (Vị trí 3 hoặc 7)**.

---

## 1. BẢNG QUY ƯỚC TỌA ĐỘ 8 VỊ TRÍ KẺ ĐỊCH (BATTLE GRID)

Trong Wonderland Online, sàn đấu của phe địch gồm 8 vị trí chia làm 4 hàng (`Row 1..4`) và 2 cột (`Slot 1`: Hàng trước, `Slot 2`: Hàng sau):

```text
               HÀNG TRƯỚC (Slot 1)         HÀNG SAU (Slot 2)
Row 1:         [Vị trí 1] (01 01)          [Vị trí 5] (02 01)
Row 2:         [Vị trí 2] (01 02)          [Vị trí 6] (02 02)  <-- Ưu tiên Char F04 lượt 1
Row 3:         [Vị trí 3] (01 03)          [Vị trí 7] (02 03)  <-- Ưu tiên Pet F04 lượt 1
Row 4:         [Vị trí 4] (01 04)          [Vị trí 8] (02 04)
```

### Bảng chi tiết mã Hex Slot & Row của 8 vị trí:

| Vị trí (Pos) | Hàng (Row) | Cột / Hàng trước - sau | Mã Packet Target | Diễn giải |
|:---:|:---:|:---:|:---:|:---|
| **Vị trí 1** | Hàng 1 (`Row 1`) | Hàng trước (`Slot 1`) | `01 01` | Quái hàng trước trên cùng |
| **Vị trí 2** | **Hàng 2 (`Row 2`)** | **Hàng trước (`Slot 1`)** | `01 02` | **Mục tiêu ưu tiên 1 của Char F04** |
| **Vị trí 3** | **Hàng 3 (`Row 3`)** | **Hàng trước (`Slot 1`)** | `01 03` | **Mục tiêu ưu tiên 1 của Pet F04** |
| **Vị trí 4** | Hàng 4 (`Row 4`) | Hàng trước (`Slot 1`) | `01 04` | Quái hàng trước dưới cùng |
| **Vị trí 5** | Hàng 1 (`Row 1`) | Hàng sau (`Slot 2`) | `02 01` | Quái hàng sau trên cùng |
| **Vị trí 6** | **Hàng 2 (`Row 2`)** | **Hàng sau (`Slot 2`)** | `02 02` | **Mục tiêu ưu tiên 2 của Char F04 (nếu Pos 2 chết)** |
| **Vị trí 7** | **Hàng 3 (`Row 3`)** | **Hàng sau (`Slot 2`)** | `02 03` | **Mục tiêu ưu tiên 2 của Pet F04 (nếu Pos 3 chết)** |
| **Vị trí 8** | Hàng 4 (`Row 4`) | Hàng sau (`Slot 2`) | `02 04` | Quái hàng sau dưới cùng |

---

## 2. QUY TẮC CHI TIẾT CHO TỪNG NHÂN VẬT & PET

### 1. Wi01 (Hàng 1) & Thú cưng
- **Ải áp dụng**: **Từ Ải 2 đến Ải 13**.
- **Quy tắc mọi lượt (Lượt 1, Lượt 2, ...)**:
  * `Char Wi01`: **100% Phòng thủ (`75ea`)** nhắm vào chính mình:
    - Packet: `03 01 03 01 75 ea .... 00` (Actor: Slot 3 R1 -> Target: Slot 3 R1).
  * `Pet Wi01`: **100% Phòng thủ (`75ea`)** nhắm vào chính mình:
    - Packet: `04 01 04 01 75 ea .... 00` (Actor: Slot 4 R1 -> Target: Slot 4 R1).

---

### 2. W03 (Hàng 3) & W04 (Hàng 4)
- **Giai đoạn 1 (Từ Ải 2 đến Ải 10)**:
  * `W03` (Char & Pet): **100% Phòng thủ (`75ea`)** nhắm vào chính mình.
    - Char: `03 03 03 03 75 ea .... 00`
    - Pet: `04 03 04 03 75 ea .... 00`
  * `W04` (Char & Pet): **100% Phòng thủ (`75ea`)** nhắm vào chính mình.
    - Char: `03 04 03 04 75 ea .... 00`
    - Pet: `04 04 04 04 75 ea .... 00`

- **Giai đoạn 2 (Ải 11, Ải 12, Ải 13)**:
  * Quét danh sách quái chưa bị tiêu diệt (`HP > 0`).
  * Mục tiêu tấn công được chọn theo thứ tự ưu tiên của team:
    - Ưu tiên 1: Kẻ địch Hàng 2 (`Vị trí 2` -> `Vị trí 6`).
    - Ưu tiên 2: Kẻ địch Hàng 3 (`Vị trí 3` -> `Vị trí 7`).
    - Ưu tiên 3: Các kẻ địch còn lại (`Vị trí 1, 5, 4, 8`).
  * **Hành động xuất chiêu**:
    - **`Char W04`**: Dùng chiêu tấn công **`d861`** lên mục tiêu còn sống.
    - **`Pet W04`**: Dùng chiêu tấn công **`a33a`** lên mục tiêu còn sống.
    - **`Char W03`**: Dùng chiêu tấn công **`d861`** lên mục tiêu còn sống.
    - **`Pet W03`**: Dùng chiêu tấn công **`a33a`** lên mục tiêu còn sống.

---

### 3. F04 (Hàng 2) & Pet (Sát thương chủ lực)
- **Ải áp dụng**: **Từ Ải 2 đến Ải 13**.

#### A. Lượt 1 (Turn 1):
1. **`Char F04`**: Tấn công hệ Hỏa bằng chiêu **`1f3b`** vào kẻ địch ở **Hàng 2**:
   - Nếu `Vị trí 2` (`Slot 1 Row 2`) còn sống: Đánh `Vị trí 2` (Packet: `03 02 01 02 1f 3b .... 00`).
   - Nếu `Vị trí 2` không có quái hoặc đã chết: Đánh `Vị trí 6` (`Slot 2 Row 2`) (Packet: `03 02 02 02 1f 3b .... 00`).
   - *(Trường hợp ngoại lệ Hàng 2 không có quái: Chuyển sang mục tiêu còn sống ở Hàng 3)*.
2. **`Pet F04`**: Tấn công bằng chiêu **`043b`** vào kẻ địch ở **Hàng 3**:
   - Nếu `Vị trí 3` (`Slot 1 Row 3`) còn sống: Đánh `Vị trí 3` (Packet: `04 02 01 03 04 3b .... 00`).
   - Nếu `Vị trí 3` không có quái hoặc đã chết: Đánh `Vị trí 7` (`Slot 2 Row 3`) (Packet: `04 02 02 03 04 3b .... 00`).
   - *(Trường hợp ngoại lệ Hàng 3 không có quái: Chuyển sang mục tiêu còn sống ở Hàng 2)*.

#### B. Những lượt sau (Turn 2 trở đi):
- Quét danh sách tất cả kẻ địch còn sống (`HP > 0`).
- **Thang điểm ưu tiên chọn mục tiêu (Target Priority Queue)**:
  1. **Top 1 - Hàng 2**:
     - `Vị trí 2` (`Slot 1, Row 2`)
     - `Vị trí 6` (`Slot 2, Row 2`)
  2. **Top 2 - Hàng 3**:
     - `Vị trí 3` (`Slot 1, Row 3`)
     - `Vị trí 7` (`Slot 2, Row 3`)
  3. **Top 3 - Các hàng còn lại**:
     - Hàng 1: `Vị trí 1` (`Slot 1, Row 1`) -> `Vị trí 5` (`Slot 2, Row 1`)
     - Hàng 4: `Vị trí 4` (`Slot 1, Row 4`) -> `Vị trí 8` (`Slot 2, Row 4`)
- **Ra chiêu**:
  - `Char F04`: Chiêu Hỏa **`1f3b`** lên mục tiêu ưu tiên số 1 còn sống.
  - `Pet F04`: Chiêu **`043b`** lên mục tiêu ưu tiên còn sống (cùng dồn dame hoặc dọn tiếp).

---

## 3. BẢNG TỔNG HỢP THEO TỪNG ẢI (ẢI 02 ĐẾN ẢI 13)

| Ải | Wi01 & Pet | W03 & Pet | W04 & Pet | F04 Char (Skill `1f3b`) | F04 Pet (Skill `043b`) |
|:---:|:---:|:---:|:---:|:---|:---|
| **Ải 02** | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Lượt 1: Hàng 2 (Pos 2/6)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 | Lượt 1: Hàng 3 (Pos 3/7)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 |
| **Ải 03** | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Lượt 1: Hàng 2 (Pos 2/6)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 | Lượt 1: Hàng 3 (Pos 3/7)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 |
| **Ải 04** | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Lượt 1: Hàng 2 (Pos 2/6)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 | Lượt 1: Hàng 3 (Pos 3/7)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 |
| **Ải 05** | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Lượt 1: Hàng 2 (Pos 2/6)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 | Lượt 1: Hàng 3 (Pos 3/7)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 |
| **Ải 06** | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Lượt 1: Hàng 2 (Pos 2/6)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 | Lượt 1: Hàng 3 (Pos 3/7)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 |
| **Ải 07** | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Lượt 1: Hàng 2 (Pos 2/6)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 | Lượt 1: Hàng 3 (Pos 3/7)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 |
| **Ải 08** | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Lượt 1: Hàng 2 (Pos 2/6)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 | Lượt 1: Hàng 3 (Pos 3/7)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 |
| **Ải 09** | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Lượt 1: Hàng 2 (Pos 2/6)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 | Lượt 1: Hàng 3 (Pos 3/7)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 |
| **Ải 10** | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Full Thủ (`75ea`) | Lượt 1: Hàng 2 (Pos 2/6)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 | Lượt 1: Hàng 3 (Pos 3/7)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 |
| **Ải 11** | Full Thủ (`75ea`) | **Tấn công quái sống**<br>(Char: `d861`, Pet: `a33a`) | **Tấn công quái sống**<br>(Char: `d861`, Pet: `a33a`) | Lượt 1: Hàng 2 (Pos 2/6)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 | Lượt 1: Hàng 3 (Pos 3/7)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 |
| **Ải 12** | Full Thủ (`75ea`) | **Tấn công quái sống**<br>(Char: `d861`, Pet: `a33a`) | **Tấn công quái sống**<br>(Char: `d861`, Pet: `a33a`) | Lượt 1: Hàng 2 (Pos 2/6)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 | Lượt 1: Hàng 3 (Pos 3/7)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 |
| **Ải 13** | Full Thủ (`75ea`) | **Tấn công quái sống**<br>(Char: `d861`, Pet: `a33a`) | **Tấn công quái sống**<br>(Char: `d861`, Pet: `a33a`) | Lượt 1: Hàng 2 (Pos 2/6)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 | Lượt 1: Hàng 3 (Pos 3/7)<br>Lượt sau: Ưu tiên Hàng 2 -> 3 |

---

## 4. CƠ CHẾ KIỂM TRA QUÁI CHƯA BỊ TIÊU DIỆT (ALIVE ENEMY CHECK)

Kẻ địch được xác định là **chưa bị tiêu diệt** khi thỏa mãn một trong hai phương pháp:
1. **Phương pháp đọc trực tiếp từ bộ nhớ RAM của Client (Khuyến nghị - Độ chính xác 100%)**:
   - Quét mảng Battle Entity của 8 slot quái (Offset trong `alogin.exe`).
   - Điều kiện còn sống: `Current_HP > 0` và `NPC_ID != 0`.
2. **Phương pháp phân tích Packet thời gian thực**:
   - Khởi tạo danh sách quái xuất hiện từ gói `Op: 0x0B Sub: 0xFA`.
   - Lắng nghe gói `Op: 0x0B Sub: 0x01` (`[Slot] [Row] 00`): Khi nhận gói này, đánh dấu quái tại vị trí `(Slot, Row)` đó đã bị tiêu diệt và xóa khỏi danh sách mục tiêu.
   - Nhờ đó, bot không bao giờ xuất chiêu vào ô trống hoặc quái đã chết.
