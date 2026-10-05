# QUY TẮC & LOGIC CHIẾN ĐẤU THÁP 29 TẦNG (SKY TOWER)

> **Cập nhật theo yêu cầu chiến thuật mới**:
> 1. **Tầng 01 đến 21**:
>    - `Wi01` & Pet, `W03` & Pet, `W04` & Pet luôn **Phòng thủ (`75ea`)** tất cả các hiệp để giữ thể lực, SP và tối ưu tốc độ trận đấu.
>    - `F04` (Char chiêu Hỏa `1f3b`, Pet chiêu `043b`) đảm nhận sát thương chủ lực gánh team.
> 2. **Ưu tiên mục tiêu của F04 & Pet (Cập nhật cốt lõi)**:
>    - **Luôn ưu tiên mục tiêu đối thủ ở Hàng 2 và Hàng 3 (Vị trí 2, 6, 3, 7)**.
>    - **Lượt 1 (Turn 1)**:
>      * `Char F04`: Chiêu Hỏa **`1f3b`** vào đối thủ ở **Hàng 2** (ưu tiên Vị trí 2; nếu chết hoặc không có -> Vị trí 6).
>      * `Pet F04`: Chiêu **`043b`** vào đối thủ ở **Hàng 3** (ưu tiên Vị trí 3; nếu chết hoặc không có -> Vị trí 7).
>    - **Những lượt sau (Turn 2+)**:
>      * Quét toàn bộ kẻ địch còn sống (`HP > 0`).
>      * **Luôn chọn mục tiêu theo danh sách ưu tiên Hàng 2 & 3 trước**:
>        `[Vị trí 2 -> Vị trí 6 -> Vị trí 3 -> Vị trí 7]`.
>      * Chỉ khi Hàng 2 và Hàng 3 đã sạch bóng quái, mới tấn công sang các hàng còn lại:
>        `[Vị trí 1 -> Vị trí 5 -> Vị trí 4 -> Vị trí 8]`.
> 3. **Tầng 22 đến 26 (Tấn công tổng lực - All-Out Attack)**:
>    - Cả 4 tài khoản cùng tham chiến dồn sát thương dứt điểm quái trâu:
>      * `W04`: Char `fb2a`, Pet `092f`
>      * `W03`: Char `fb2a`, Pet `092f` (hỗ trợ `232b`)
>      * `Wi01`: Char Phong `2b2b`, Pet `2c2b`
>      * `F04`: Char Hỏa `1f3b`, Pet `043b` / `332b` / `553b`
>    - Khi F04 và Pet ra chiêu, **vẫn tuân thủ tuyệt đối quy tắc ưu tiên Hàng 2 và Hàng 3 (`2, 6, 3, 7`)**.
> 4. **Tự động vứt phần thưởng rác theo vòng (Auto Discard Rewards)**:
>    - Sau khi hoàn thành các vòng `r5, r6, r7, r8` và nhận thưởng:
>      * **r5 (Tầng 05)**: Mã **`0x7D4A`** (`32074`) - `BubbleGum` (Kẹo cao su) -> **Vứt**
>      * **r6 (Tầng 06)**: Mã **`0x7D4B`** (`32075`) - `Chocolate` (Sô-cô-la) -> **Vứt**
>      * **r7 (Tầng 07)**: Mã **`0x7D49`** (`32073`) - `InstantNoodle` (Mì gói) -> **Vứt**
>      * **r8 (Tầng 08)**: Mã **`0x7D48`** (`32072`) - `ChocolateIceCream` (Kem sô-cô-la) -> **Vứt**
>    - Nguyên tắc: Quét RAM trực tiếp để lấy đúng ô Slot thực tế, gửi chuỗi lệnh chuẩn: Yêu cầu vứt (`0x17 Sub 0x03`) + Xác nhận popup (`0x17 Sub 0x7C`).

---

## 1. BẢNG QUY ƯỚC TỌA ĐỘ 8 VỊ TRÍ KẺ ĐỊCH (BATTLE GRID)

Sàn đấu phe địch gồm 8 vị trí chia làm 4 hàng dọc (`Row 1..4`) và 2 cột ngang (`Slot 1`: Hàng trước, `Slot 2`: Hàng sau):

```text
               HÀNG TRƯỚC (Slot 1)         HÀNG SAU (Slot 2)
Row 1:         [Vị trí 1] (01 01)          [Vị trí 5] (02 01)
Row 2:         [Vị trí 2] (01 02)          [Vị trí 6] (02 02)  <== TOP 1 ƯU TIÊN (Char F04 Lượt 1)
Row 3:         [Vị trí 3] (01 03)          [Vị trí 7] (02 03)  <== TOP 2 ƯU TIÊN (Pet F04 Lượt 1)
Row 4:         [Vị trí 4] (01 04)          [Vị trí 8] (02 04)
```

### Bảng chi tiết mã Target Packet của 8 vị trí:

| Vị trí | Hàng (Row) | Cột (Slot) | Mã Packet Target | Diễn giải & Độ ưu tiên mục tiêu của F04 |
|:---:|:---:|:---:|:---:|:---|
| **Vị trí 2** | **Hàng 2** | **Hàng trước (`Slot 1`)** | `01 02` | **Ưu tiên số 1 tuyệt đối** (Mục tiêu Char F04 Lượt 1) |
| **Vị trí 6** | **Hàng 2** | **Hàng sau (`Slot 2`)** | `02 02` | **Ưu tiên số 2** (Mục tiêu Char F04 Lượt 1 nếu Pos 2 chết) |
| **Vị trí 3** | **Hàng 3** | **Hàng trước (`Slot 1`)** | `01 03` | **Ưu tiên số 3** (Mục tiêu Pet F04 Lượt 1) |
| **Vị trí 7** | **Hàng 3** | **Hàng sau (`Slot 2`)** | `02 03` | **Ưu tiên số 4** (Mục tiêu Pet F04 Lượt 1 nếu Pos 3 chết) |
| **Vị trí 1** | Hàng 1 | Hàng trước (`Slot 1`) | `01 01` | Ưu tiên số 5 (Chỉ đánh khi Hàng 2 & 3 đã sạch) |
| **Vị trí 5** | Hàng 1 | Hàng sau (`Slot 2`) | `02 01` | Ưu tiên số 6 (Chỉ đánh khi Hàng 2 & 3 đã sạch) |
| **Vị trí 4** | Hàng 4 | Hàng trước (`Slot 1`) | `01 04` | Ưu tiên số 7 (Chỉ đánh khi Hàng 2 & 3 đã sạch) |
| **Vị trí 8** | Hàng 4 | Hàng sau (`Slot 2`) | `02 04` | Ưu tiên số 8 (Chỉ đánh khi Hàng 2 & 3 đã sạch) |

---

## 2. QUY TẮC ĐIỀU KHIỂN CHI TIẾT THEO TỪNG GIAI ĐOẠN

### Giai đoạn 1: Tầng 01 đến Tầng 21 (Solo Carry F04)

1. **`Wi01`, `W03`, `W04` (cả Char và Pet)**:
   - Tất cả 6 đối tượng này luôn **Phòng thủ (`75ea`)** nhắm vào chính mình:
     * `Wi01`: Char (`03 01 03 01 75 ea .... 00`), Pet (`04 01 04 01 75 ea .... 00`)
     * `W03`: Char (`03 03 03 03 75 ea .... 00`), Pet (`04 03 04 03 75 ea .... 00`)
     * `W04`: Char (`03 04 03 04 75 ea .... 00`), Pet (`04 04 04 04 75 ea .... 00`)

2. **`F04` (Char) & Pet**:
   - **Lượt 1 (Turn 1)**:
     * **`Char F04`**: Dùng chiêu Hỏa **`1f3b`** vào **Hàng 2**:
       - Quái tại `Vị trí 2` còn sống -> Đánh `Vị trí 2` (`03 02 01 02 1f 3b .... 00`).
       - Quái tại `Vị trí 2` đã chết hoặc trống -> Đánh `Vị trí 6` (`03 02 02 02 1f 3b .... 00`).
     * **`Pet F04`**: Dùng chiêu sát thương **`043b`** vào **Hàng 3**:
       - Quái tại `Vị trí 3` còn sống -> Đánh `Vị trí 3` (`04 02 01 03 04 3b .... 00`).
       - Quái tại `Vị trí 3` đã chết hoặc trống -> Đánh `Vị trí 7` (`04 02 02 03 04 3b .... 00`).
   - **Lượt 2 trở đi (Turn 2+)**:
     * Kiểm tra trạng thái quái còn sống (`HP > 0`).
     * Áp dụng hàng đợi ưu tiên mục tiêu:
       ```python
       PRIORITY_QUEUE = [2, 6, 3, 7, 1, 5, 4, 8]
       ```
     * `Char F04`: Chiêu Hỏa **`1f3b`** vào mục tiêu ưu tiên cao nhất còn sống.
     * `Pet F04`: Chiêu **`043b`** vào mục tiêu ưu tiên còn sống tiếp theo.

---

### Giai đoạn 2: Tầng 22 đến Tầng 26 (Tổng lực tấn công)

Từ Tầng 22, lượng máu và phòng thủ của quái tăng vọt. Toàn bộ 4 tài khoản xuất chiêu phối hợp:
- **`F04` & Pet**: Duy trì quy tắc ưu tiên hàng đầu vào **Hàng 2 và Hàng 3 (`2, 6, 3, 7`)** bằng `1f3b` và `043b`.
- **`W04`**: Char dùng `fb2a`, Pet dùng `092f`.
- **`W03`**: Char dùng `fb2a`, Pet dùng `092f` (có thể linh hoạt buff `232b`).
- **`Wi01`**: Char dùng `2b2b`, Pet dùng `2c2b`.
- Tất cả các đòn tấn công đều nhắm vào quái còn sống theo thứ tự ưu tiên dọn sạch các vị trí nguy hiểm nhất.

---

### Giai đoạn 3: Bài học & Đề xuất cải tiến cho Tầng 27+

- **Phân tích thất bại Tầng 27**:
  * Tầng 27 có quái Agi cực cao và xuất chiêu sát thương AOE mạnh.
  * Hiệp 3: `W04` ngã xuống đầu tiên. Hiệp 4: Pet `F04` và Pet `W03` ngã xuống dẫn đến vỡ trận sau 52.5s.
- **Đề xuất chiến thuật khi tái đấu Tầng 27**:
  1. Cần dùng kỹ năng khống chế / phong ấn (Freeze / Sleep / Seal) ở lượt 1 vào các quái nguy hiểm nhất.
  2. Bổ sung kỹ năng hồi sinh hoặc hồi máu diện rộng từ hệ Thủy (`W04`, `W03`).
  3. Cân nhắc buff khiên/thủ cho F04 và W04 ngay từ hiệp 1.

---

## 3. LOGIC TỰ ĐỘNG VỨT PHẦN THƯỞNG RÁC (AUTO DISCARD RULES)

Các phần thưởng rác rơi ra từ các tầng tháp chiếm dụng rất nhiều diện tích túi đồ (đặc biệt túi của W04 có lúc lên tới 48/50 ô):

| Vòng Tháp | Tầng | Mã Hex | Mã Dec | Tên vật phẩm | Số lượng | Hành động |
|:---:|:---:|:---:|:---:|:---|:---:|:---:|
| **r5** | Tầng 05 | **`0x7D4A`** | `32074` | **BubbleGum** (Kẹo cao su) | x5 | **Vứt bỏ (Discard)** |
| **r6** | Tầng 06 | **`0x7D4B`** | `32075` | **Chocolate** (Sô-cô-la) | x10 | **Vứt bỏ (Discard)** |
| **r7** | Tầng 07 | **`0x7D49`** | `32073` | **InstantNoodle** (Mì gói) | x15 | **Vứt bỏ (Discard)** |
| **r8** | Tầng 08 | **`0x7D48`** | `32072` | **ChocolateIceCream** (Kem) | x20 | **Vứt bỏ (Discard)** |

### Giao thức gói tin vứt đồ chuẩn (2 bước an toàn):
1. **Bước 1: Gửi yêu cầu vứt đồ**
   - Opcode: `0x17`, Subcode: `0x03`
   - Body: `17 03 [slot_num] [quantity] 01`
2. **Bước 2: Gửi xác nhận Popup vứt đồ (sau 120ms)**
   - Opcode: `0x17`, Subcode: `0x7C`
   - Body: `17 7C [slot_num] [quantity] 02`
3. Quét lại RAM sau khi vứt để xác nhận túi đồ đã giảm sạch 100%.

---

## 4. LOGIC TỰ ĐỘNG XUẤT CHIẾN LẠI PET KHI HẾT MÁU (AUTO RE-SUMMON PET)

Trong quá trình leo tháp (đặc biệt các tầng cao từ 22 trở đi), Pet có thể bị đối thủ dồn sát thương và hết máu (`HP = 0`), khiến Pet bị văng khỏi trận và chuyển sang trạng thái **Nghỉ ngơi / Thu hồi (Rest / Standby)**:
- Khi Pet bị hạ gục trong trận:
  * Server gửi gói tin đồng bộ trạng thái: `S->C Op: 0x0E Sub: 0x09 [PetID 4B LE, Status: 0x03]` hoặc `Op: 0x05 Sub: 0x08 [PetID 4B LE, Status: 0x03]`.
  * Trong bộ nhớ RAM của client: ô quản lý slot pet chiến đấu `playerObj + 0x2230` chuyển về `0` (không có pet xuất chiến).
- Sau khi trận đấu kết thúc (`S->C Op: 0x0B Sub: 0x00`), hệ thống tự động:
  1. Quét bộ nhớ RAM túi đồ để dọn sạch phần thưởng rác.
  2. Đọc trạng thái Pet của client (`readPetInfo` qua Frida Native Engine):
     * Nếu `activeSlot == 0` (Pet đang nghỉ ngơi):
       - Xác định Pet ID chủ lực theo cấu hình slot mặc định của từng client:
          * `Wi01`: **Slot 2 (UI)** - ID `14609` (`0x3911`, RAM Slot 3 - Pet còn lại)
          * `W04`: **Slot 4** - ID `14242` (`0x37A2`)
          * `W03`: **Slot 4** - ID `14242` (`0x37A2`)
          * `F04`: **Slot 2** - ID `14081` (`0x3701`)
        - Đóng và gửi ngay gói tin C->S kích hoạt xuất chiến:
          * **Opcode: `0x13`**, **Subcode: `0x01`**
          * **Payload (6 bytes)**: `13 01 [PetID 4B LE]`
          * Ví dụ Wi01 (Slot 2 UI): `13 01 11 39 00 00`
          * Ví dụ F04 (Slot 2): `13 01 01 37 00 00`
          * Ví dụ W04 / W03 (Slot 4): `13 01 a2 37 00 00`
     * Sau 0.4s: Quét lại RAM kiểm tra `activeSlot > 0` xác nhận Pet đã vào vị trí sẵn sàng cho tầng tiếp theo!
