import sys
import struct

XOR_KEY = 173

def decrypt(data):
    return bytes(b ^ XOR_KEY for b in data)

count = 0
with open('payloads.txt', 'r') as f:
    for idx, line in enumerate(f):
        line = line.strip()
        if not line:
            continue
        for p in line.split(','):
            if not p: continue
            try:
                raw = bytes.fromhex(p)
                decrypted = decrypt(raw)
                
                offset = 0
                while offset + 4 <= len(decrypted):
                    sig, length = struct.unpack_from('<HH', decrypted, offset)
                    if sig == 0x44F4:
                        packet_data = decrypted[offset+4 : offset+4+length]
                        print(f"Pkt {idx:03d} (Len={length:03d}): {packet_data.hex(' ')}")
                        offset += 4 + length
                        count += 1
                        if count > 30:
                            sys.exit(0)
                    else:
                        print(f"Pkt {idx:03d} Invalid Sig: {decrypted[offset:offset+10].hex(' ')}...")
                        break
            except Exception as e:
                pass
