import struct

XOR_KEY = 173
SIGNATURE = 0x44F4

def xor_crypt(data: bytes) -> bytes:
    """Mã hóa / Giải mã gói tin WLO."""
    return bytes(b ^ XOR_KEY for b in data)

def parse_packets(data: bytes):
    """
    Tách luồng dữ liệu (sau khi giải mã) thành các packet hoàn chỉnh.
    Trả về: (danh_sách_packet, dữ_liệu_còn_thừa_chưa_đủ)
    """
    packets = []
    offset = 0
    while offset + 4 <= len(data):
        sig, length = struct.unpack_from('<HH', data, offset)
        if sig != SIGNATURE:
            # Nếu mất đồng bộ (mất header), nhích lên 1 byte để tìm lại
            offset += 1
            continue
        
        if offset + 4 + length <= len(data):
            # Đã nhận đủ payload của packet này
            payload = data[offset+4 : offset+4+length]
            packets.append(payload)
            offset += 4 + length
        else:
            # Chưa nhận đủ byte, chờ lần đọc sau
            break
            
    return packets, data[offset:]

def build_packet(payload: bytes) -> bytes:
    """
    Nhận payload thô, gắn Header (F4 44 + Length), sau đó mã hóa XOR.
    Sử dụng hàm này khi bạn muốn tự tạo gói tin gửi lên Server.
    """
    header = struct.pack('<HH', SIGNATURE, len(payload))
    full_packet = header + payload
    return xor_crypt(full_packet)
