# ==============================================================================
# KHU VỰC VIẾT LOGIC AUTO (By Antigravity)
# ==============================================================================
# Tại đây bạn có thể dễ dàng viết code để chặn, xem, hoặc tự động hóa hành động.
# ==============================================================================
import logging
from wlo_crypto import build_packet

logger = logging.getLogger("WLO_Auto")

def on_server_to_client(packet: bytes):
    """
    Xử lý các gói tin từ Server gửi về cho Client (BOT/Game).
    - Trả về `packet` nếu muốn cho qua bình thường.
    - Trả về `None` nếu muốn xóa/chặn (Drop) gói tin.
    """
    if len(packet) > 0:
        opcode = packet[0]
        
        # Ví dụ: Theo dõi gói tin cập nhật chỉ số (Opcode 0x32, 0x33, v.v...)
        # if opcode in [0x32, 0x33]:
        #     logger.info(f"[Server -> Client] Cập nhật: {packet.hex(' ')}")
        
        # Ví dụ: Theo dõi gói tin di chuyển (Opcode 0x06)
        # if opcode == 0x06:
        #     logger.info(f"[Server -> Client] Di chuyển: {packet.hex(' ')}")
        pass
        
    return packet

def on_client_to_server(packet: bytes):
    """
    Xử lý các gói tin từ Client (BOT/Game) gửi lên Server.
    - Trả về `packet` nếu muốn cho qua.
    - Trả về `None` nếu muốn chặn lệnh từ BOT gửi đi.
    """
    if len(packet) > 0:
        opcode = packet[0]
        
        # Ví dụ: In ra các lệnh BOT đang gửi đi (Trừ lệnh ping 0x14 cho đỡ rác)
        if opcode != 0x14:
            logger.info(f"[Client -> Server] Lệnh (Opcode {hex(opcode)}): {packet.hex(' ')}")
            
    return packet

def get_auto_actions():
    """
    [NÂNG CAO] Hàm này được Proxy gọi liên tục. 
    Nếu bạn muốn tự động bơm một gói tin lên Server mà không cần chờ Client, 
    bạn có thể trả về danh sách các payload tại đây.
    Ví dụ trả về: [ bytes([0x24, 0x01, 0x00, 0x00]) ]
    """
    return []
