import imaplib
import email
from email.message import Message
from email.header import decode_header
import re
import html
import time
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ==================== CẤU HÌNH TÀI KHOẢN ====================
# Email của bạn
GMAIL_USER = "capslock.noob@gmail.com"

# Mật khẩu ứng dụng (App Password) gồm 16 ký tự của Google
# Tạo tại: https://myaccount.google.com/apppasswords
# Bạn có thể điền trực tiếp vào đây hoặc đặt biến môi trường GMAIL_APP_PASSWORD
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "dien_mat_khau_ung_dung_o_day")

# Người gửi cần lọc
SENDER_EMAIL = "GM@wloi.org"
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
# ============================================================


def decode_mime_words(raw_header: str) -> str:
    """Giải mã tiêu đề email (subject, from...) có mã hóa MIME."""
    if not raw_header:
        return ""
    decoded_parts = []
    for part, encoding in decode_header(raw_header):
        if isinstance(part, bytes):
            charset = encoding or "utf-8"
            try:
                decoded_parts.append(part.decode(charset, errors="replace"))
            except Exception:
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(str(part))
    return "".join(decoded_parts)


def extract_body_text(msg: Message) -> str:
    """Trích xuất toàn bộ nội dung văn bản (plain text hoặc html) từ email."""
    body_parts = []
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        text = payload.decode(charset, errors="replace")
                    except Exception:
                        text = payload.decode("utf-8", errors="replace")
                    
                    if content_type == "text/plain":
                        body_parts.insert(0, text)  # Ưu tiên text/plain
                    elif content_type == "text/html":
                        body_parts.append(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                body_parts.append(payload.decode(charset, errors="replace"))
            except Exception:
                body_parts.append(payload.decode("utf-8", errors="replace"))

    return "\n".join(body_parts)


def parse_otp_code(text: str) -> str | None:
    """
    Trích xuất mã OTP 4 số từ nội dung email.
    Ví dụ: '您的驗證碼為： 0941' -> '0941'
    """
    if not text:
        return None

    # Loại bỏ thẻ HTML và giải mã ký tự HTML entities
    clean_text = re.sub(r"<[^>]+>", " ", text)
    clean_text = html.unescape(clean_text)

    # Ưu tiên 1: Tìm 4 số nằm ngay sau các từ khóa驗證碼 (Mã xác thực), code, otp
    match = re.search(r"(?:驗證碼|验证码|code|otp)[^\d\r\n]*(\d{4})", clean_text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Ưu tiên 2: Tìm chuỗi 4 chữ số độc lập
    match = re.search(r"\b(\d{4})\b", clean_text)
    if match:
        return match.group(1)

    return None


def connect_gmail(username: str, password: str) -> imaplib.IMAP4_SSL:
    """Kết nối tới máy chủ Gmail IMAP."""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(username, password)
        return mail
    except imaplib.IMAP4.error as e:
        print("\n[!] LỖI ĐĂNG NHẬP GMAIL:")
        print("  - Vui lòng kiểm tra lại Email và Mật khẩu ứng dụng (App Password).")
        print("  - Lưu ý: Không dùng mật khẩu đăng nhập Gmail thông thường.")
        print("  - Tạo App Password tại: https://myaccount.google.com/apppasswords")
        print(f"  - Chi tiết lỗi: {e}\n")
        sys.exit(1)


def get_latest_otp(username: str = GMAIL_USER, password: str = GMAIL_APP_PASSWORD, sender: str = SENDER_EMAIL) -> str | None:
    """Lấy mã OTP từ email mới nhất nhận được từ `sender`."""
    mail = connect_gmail(username, password)
    try:
        # Chọn hộp thư đến
        mail.select("INBOX")

        # Tìm các email gửi từ SENDER_EMAIL
        # Dùng tiêu chí FROM
        status, data = mail.search(None, f'(FROM "{sender}")')
        if status != "OK" or not data or not data[0]:
            print(f"[-] Không tìm thấy email nào từ {sender}.")
            return None

        email_ids = data[0].split()
        latest_id = email_ids[-1]  # Lấy email mới nhất (ID lớn nhất)

        # Lấy nội dung email
        status, msg_data = mail.fetch(latest_id, "(RFC822)")
        if status != "OK":
            print("[-] Không thể tải nội dung email.")
            return None

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = decode_mime_words(msg.get("Subject", ""))
        from_header = decode_mime_words(msg.get("From", ""))
        date_header = msg.get("Date", "")
        body = extract_body_text(msg)

        otp = parse_otp_code(body) or parse_otp_code(subject)

        print("\n" + "=" * 50)
        print(f"[*] Người gửi: {from_header}")
        print(f"[*] Tiêu đề  : {subject}")
        print(f"[*] Thời gian: {date_header}")
        print(f"[*] Mã OTP   : {otp if otp else 'Không tìm thấy mã OTP 4 số'}")
        print("=" * 50 + "\n")

        return otp

    finally:
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass


def wait_for_new_otp(timeout: int = 120, interval: int = 5,
                     username: str = GMAIL_USER, password: str = GMAIL_APP_PASSWORD, sender: str = SENDER_EMAIL) -> str | None:
    """
    Theo dõi hộp thư và chờ email OTP mới gửi đến trong vòng `timeout` giây.
    Rất thích hợp khi bạn vừa bấm 'Gửi mã' trên trang web và chạy script chờ lấy mã.
    """
    print(f"[*] Đang chờ email OTP mới từ {sender} (Tối đa {timeout} giây)...")
    mail = connect_gmail(username, password)
    mail.select("INBOX")
    
    # Lấy danh sách ID email hiện tại để phát hiện email mới
    status, data = mail.search(None, f'(FROM "{sender}")')
    initial_ids = set(data[0].split()) if status == "OK" and data[0] else set()

    start_time = time.time()
    try:
        while time.time() - start_time < timeout:
            time.sleep(interval)
            mail.select("INBOX")  # Làm mới trạng thái hòm thư
            status, data = mail.search(None, f'(FROM "{sender}")')
            if status == "OK" and data[0]:
                current_ids = set(data[0].split())
                new_ids = current_ids - initial_ids
                if new_ids:
                    # Có email mới đến
                    newest_id = sorted(list(new_ids), key=lambda x: int(x))[-1]
                    status, msg_data = mail.fetch(newest_id, "(RFC822)")
                    if status == "OK":
                        raw_email = msg_data[0][1]
                        msg = email.message_from_bytes(raw_email)
                        body = extract_body_text(msg)
                        subject = decode_mime_words(msg.get("Subject", ""))
                        otp = parse_otp_code(body) or parse_otp_code(subject)
                        if otp:
                            print(f"\n[+] ĐÃ NHẬN MÃ OTP MỚI: {otp}")
                            return otp
            print(".", end="", flush=True)

        print("\n[-] Đã hết thời gian chờ (timeout).")
        return None
    finally:
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass


import argparse
import subprocess


def copy_to_clipboard(text: str) -> bool:
    """Tự động copy mã OTP vào clipboard trên Windows."""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value '{text}'"],
            check=True,
            capture_output=True,
        )
        return True
    except Exception:
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script tự động đọc mã OTP từ mail GM@wloi.org gửi đến Gmail.")
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Chờ nhận email OTP mới (thích hợp sau khi vừa ấn 'Gửi mã' trên trang web)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Thời gian chờ email mới tối đa tính bằng giây (mặc định: 120s)",
    )
    parser.add_argument(
        "--password",
        type=str,
        default=None,
        help="Mật khẩu ứng dụng Gmail (App Password 16 ký tự). Nếu không truyền sẽ lấy từ cấu hình trong file hoặc biến môi trường.",
    )

    args = parser.parse_args()

    app_password = args.password or GMAIL_APP_PASSWORD
    if not app_password or app_password == "dien_mat_khau_ung_dung_o_day":
        print("[!] Chú ý: Bạn chưa điền 'GMAIL_APP_PASSWORD'.")
        print("    Vui lòng làm theo 2 bước sau để cấu hình:")
        print("    1. Bật 2FA và tạo Mật khẩu ứng dụng (App Password) tại: https://myaccount.google.com/apppasswords")
        print("    2. Điền mật khẩu (16 chữ cái) vào biến GMAIL_APP_PASSWORD trong file get_otp.py")
        print("       HOẶC chạy với tham số: python get_otp.py --password \"xxxx xxxx xxxx xxxx\"\n")
        sys.exit(1)

    if args.wait:
        otp = wait_for_new_otp(timeout=args.timeout, password=app_password)
    else:
        otp = get_latest_otp(password=app_password)

    if otp:
        print(f"\n[>>>] MÃ OTP CỦA BẠN: {otp}")
        if copy_to_clipboard(otp):
            print("[✓] Đã tự động sao chép mã OTP vào Clipboard! (Bạn có thể nhấn Ctrl+V để dán)")
    else:
        print("\n[-] Không lấy được mã OTP.")
