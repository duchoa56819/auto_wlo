import asyncio
import logging
from wlo_crypto import xor_crypt, parse_packets, build_packet
import auto_logic

# Cấu hình logging để hiển thị đẹp mắt
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(name)s | %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("WLO_Proxy")

# Port mà Proxy của chúng ta sẽ lắng nghe
LOCAL_PROXY_PORT = 6415
# Port của aProxy (hoặc server WLO thật)
TARGET_HOST = '127.0.0.1'
TARGET_PORT = 6414

class WloInterceptor:
    async def handle_client(self, client_reader, client_writer):
        client_addr = client_writer.get_extra_info('peername')
        logger.info(f"[+] Có Client (BOT/Game) kết nối từ {client_addr}")

        try:
            # Kết nối tới aProxy (6414)
            server_reader, server_writer = await asyncio.open_connection(TARGET_HOST, TARGET_PORT)
            logger.info(f"[+] Đã kết nối nối tiếp tới aProxy / Server thật tại {TARGET_HOST}:{TARGET_PORT}")
        except Exception as e:
            logger.error(f"[-] Không thể kết nối tới aProxy ({TARGET_PORT}): {e}. Hãy đảm bảo aProxy đang chạy!")
            client_writer.close()
            return

        async def forward(src_reader, dst_writer, direction, logic_func):
            buffer_decrypted = b""
            while True:
                try:
                    data = await src_reader.read(4096)
                    if not data:
                        break # Mất kết nối
                    
                    # 1. Giải mã gói tin
                    decrypted_chunk = xor_crypt(data)
                    buffer_decrypted += decrypted_chunk
                    
                    # 2. Bóc tách từng packet
                    packets, buffer_decrypted = parse_packets(buffer_decrypted)
                    
                    for pkt in packets:
                        # 3. Chạy logic do người dùng viết (bên file auto_logic.py)
                        modified_pkt = logic_func(pkt)
                        
                        # 4. Nếu logic không chặn (return None), thì mã hóa và gửi đi tiếp
                        if modified_pkt is not None:
                            encrypted = build_packet(modified_pkt)
                            dst_writer.write(encrypted)
                            await dst_writer.drain()

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Lỗi khi forward dữ liệu ({direction}): {e}")
                    break
            
            dst_writer.close()
            logger.info(f"[-] Kết nối bị đóng ({direction})")

        # Khởi chạy 2 luồng chuyển tiếp đồng thời
        task_c2s = asyncio.create_task(forward(client_reader, server_writer, "C->S", auto_logic.on_client_to_server))
        task_s2c = asyncio.create_task(forward(server_reader, client_writer, "S->C", auto_logic.on_server_to_client))
        
        # Luồng chạy ngầm để gửi auto actions (nếu có định nghĩa trong hàm get_auto_actions)
        async def auto_loop():
            while not client_writer.is_closing() and not server_writer.is_closing():
                try:
                    actions = auto_logic.get_auto_actions()
                    for pkt in actions:
                        server_writer.write(build_packet(pkt))
                        await server_writer.drain()
                        logger.info(f"[Auto-Inject] Đã tự động bơm gói tin: {pkt.hex(' ')}")
                except Exception as e:
                    pass
                await asyncio.sleep(0.1)
                
        task_auto = asyncio.create_task(auto_loop())

        await asyncio.gather(task_c2s, task_s2c)
        task_auto.cancel()

async def main():
    interceptor = WloInterceptor()
    server = await asyncio.start_server(interceptor.handle_client, '127.0.0.1', LOCAL_PROXY_PORT)
    
    print("="*60)
    print("   🚀 WLO AUTO FRAMEWORK (LOCAL PROXY) BY ANTIGRAVITY 🚀   ")
    print("="*60)
    print(f"[*] Proxy đang lắng nghe tại: 127.0.0.1:{LOCAL_PROXY_PORT}")
    print(f"[*] Chuyển hướng dữ liệu tới : {TARGET_HOST}:{TARGET_PORT} (aProxy)")
    print("[!] HƯỚNG DẪN: Hãy sửa IP trong BOT hoặc SERVER.INI của bạn thành 127.0.0.1 và Port thành 6415.")
    print("[!] Bấm Ctrl+C để dừng.")
    print("="*60)
    
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nĐã dừng phần mềm.")
