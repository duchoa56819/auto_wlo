# WLO Auto Framework (Local TCP Proxy & Interceptor)

Khung làm việc tự động hóa Wonderland Online (WLO) can thiệp ở tầng mạng (TCP Protocol Layer).

## 🌟 Cơ chế hoạt động

Proxy hoạt động như một cầu nối trung gian giữa Game Client/BOT và Server game (hoặc aProxy):

```
Client (BOT / Game) ---> [WLO Proxy: 127.0.0.1:6415] ---> aProxy (127.0.0.1:6414) / Server Thật
```

- **Mã hóa / Giải mã**: Toàn bộ gói tin được giải mã và mã hóa lại theo thuật toán XOR (Key: 173, Signature: `0x44F4`).
- **Hook gói tin**: Bạn có thể xem, chỉnh sửa, lọc bỏ (drop) hoặc tự tạo gói tin mới gửi lên Server trong `auto_logic.py`.

---

## 📁 Cấu trúc thư mục

- **`wlo_proxy.py`**: Local AsyncIO TCP Proxy lắng nghe tại cổng `6415`, giải mã và chuyển tiếp gói tin đến `6414`.
- **`wlo_crypto.py`**: Các thuật toán giải mã XOR, bóc tách packet `0x44F4`, và đóng gói packet.
- **`auto_logic.py`**: Nơi bạn viết logic tự động hóa (chặn gói tin, theo dõi opcode, tự động bơm lệnh lên server).
- **`Run_Proxy.bat`**: File batch chạy nhanh Proxy.
- **`parse_wlo.py`**: Công cụ phân tích và dịch ngược dữ liệu packet từ file `payloads.txt`.
- **`payloads.txt`**: Dữ liệu log packet mẫu dùng để phân tích opcode.

---

## 🚀 Hướng dẫn sử dụng

1. **Khởi động Proxy**:
   - Nhấp đúp vào `Run_Proxy.bat` (hoặc chạy `python wlo_proxy.py`).
2. **Cấu hình Client / BOT**:
   - Trong file `SERVER.INI` hoặc cấu hình IP của BOT, đổi IP thành `127.0.0.1` và Port thành `6415`.
3. **Viết logic Auto**:
   - Mở file `auto_logic.py`:
     - `on_server_to_client(packet)`: Xử lý hoặc chặn gói tin từ Server trả về.
     - `on_client_to_server(packet)`: Xử lý hoặc chặn lệnh từ BOT gửi đi.
     - `get_auto_actions()`: Tự động tạo và gửi packet lên Server định kỳ.
