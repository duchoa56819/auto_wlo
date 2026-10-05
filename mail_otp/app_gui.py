import os
import sys
import json
import time
import re
import html
import imaplib
import email
from email.message import Message
from email.header import decode_header
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

# Thiết lập UTF-8 cho Windows console nếu có
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounts.json")
DEFAULT_SENDER = "GM@wloi.org"


# =====================================================================
# HÀM XỬ LÝ EMAIL & OTP
# =====================================================================

def decode_mime_words(raw_header: str) -> str:
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
                        body_parts.insert(0, text)
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
    if not text:
        return None
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = html.unescape(clean)
    # Tìm 4 số sau từ khóa驗證碼 hoặc code/otp
    match = re.search(r"(?:驗證碼|验证码|code|otp)[^\d\r\n]*(\d{4})", clean, re.IGNORECASE)
    if match:
        return match.group(1)
    # Fallback: bất kỳ 4 số đứng độc lập
    match = re.search(r"\b(\d{4})\b", clean)
    if match:
        return match.group(1)
    return None


def copy_to_clipboard(text: str) -> bool:
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value '{text}'"],
                check=True,
                capture_output=True,
            )
            return True
    except Exception:
        pass
    return False


# =====================================================================
# QUẢN LÝ DỮ LIỆU TÀI KHOẢN (ACCOUNTS.JSON)
# =====================================================================

def load_accounts() -> list[dict]:
    if not os.path.exists(CONFIG_FILE):
        default_data = [
            {
                "id": "1",
                "label": "Tài khoản chính",
                "email": "capslock.noob@gmail.com",
                "password": "",
                "sender": DEFAULT_SENDER,
            }
        ]
        save_accounts(default_data)
        return default_data
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_accounts(accounts: list[dict]):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)


# =====================================================================
# GIAO DIỆN CHÍNH (TKINTER GUI)
# =====================================================================

class OtpGrabberApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Gmail OTP Manager - GM@wloi.org")
        self.root.geometry("860x650")
        self.root.minsize(760, 560)

        # Trạng thái
        self.accounts = load_accounts()
        self.is_listening = False
        self.listen_thread = None
        self.stop_listening_event = threading.Event()

        # Thiết lập Style
        self.setup_styles()

        # Xây dựng giao diện
        self.build_ui()

    def setup_styles(self):
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # Màu sắc chủ đạo
        self.c_bg = "#f4f6f9"
        self.c_card = "#ffffff"
        self.c_primary = "#2563eb"
        self.c_primary_hover = "#1d4ed8"
        self.c_text = "#1e293b"
        self.c_text_muted = "#64748b"
        self.c_border = "#e2e8f0"
        self.c_accent_green = "#16a34a"

        self.root.configure(bg=self.c_bg)

        # Style configurations
        self.style.configure(".", font=("Segoe UI", 10), background=self.c_bg)
        self.style.configure("TNotebook", background=self.c_bg)
        self.style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=[16, 8])
        
        self.style.configure("Card.TFrame", background=self.c_card, relief="flat")
        self.style.configure("Header.TLabel", font=("Segoe UI", 15, "bold"), foreground=self.c_text, background=self.c_bg)
        self.style.configure("SubHeader.TLabel", font=("Segoe UI", 9), foreground=self.c_text_muted, background=self.c_bg)

        # Nút chính
        self.style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=[12, 7])
        self.style.configure("Success.TButton", font=("Segoe UI", 10, "bold"), padding=[12, 7])

        # Treeview
        self.style.configure("Treeview", font=("Segoe UI", 9), rowheight=28)
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def build_ui(self):
        # 1. Top Header Bar
        header_frame = tk.Frame(self.root, bg="#1e293b", height=60, padx=20, pady=12)
        header_frame.pack(fill="x")

        title_lbl = tk.Label(
            header_frame,
            text="✉️ Gmail OTP Grabber - Đa Tài Khoản",
            font=("Segoe UI", 14, "bold"),
            fg="#f8fafc",
            bg="#1e293b"
        )
        title_lbl.pack(side="left")

        # Checkbox Always on top
        self.always_on_top_var = tk.BooleanVar(value=False)
        top_check = tk.Checkbutton(
            header_frame,
            text="Ghim cửa sổ trên cùng",
            variable=self.always_on_top_var,
            command=self.toggle_always_on_top,
            fg="#cbd5e1",
            bg="#1e293b",
            selectcolor="#0f172a",
            activebackground="#1e293b",
            activeforeground="#f8fafc",
            font=("Segoe UI", 9)
        )
        top_check.pack(side="right")

        # 2. Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=12)

        # Tab 1: Trang Lấy OTP (Dashboard)
        self.tab_dashboard = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_dashboard, text="  ⚡ Lấy OTP  ")
        self.build_dashboard_tab()

        # Tab 2: Quản lý tài khoản (Accounts)
        self.tab_accounts = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_accounts, text="  👥 Quản Lý Tài Khoản  ")
        self.build_accounts_tab()

        # Tab 3: Lịch sử OTP (History)
        self.tab_history = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_history, text="  📜 Lịch Sử OTP  ")
        self.build_history_tab()

        # 3. Status Bar
        self.status_bar = tk.Label(
            self.root,
            text="Sẵn sàng.",
            bd=1,
            relief="sunken",
            anchor="w",
            font=("Segoe UI", 9),
            bg="#f1f5f9",
            fg="#475569",
            padx=10,
            pady=4
        )
        self.status_bar.pack(side="bottom", fill="x")

    def toggle_always_on_top(self):
        self.root.attributes("-topmost", self.always_on_top_var.get())

    # =================================================================
    # TAB 1: DASHBOARD
    # =================================================================
    def build_dashboard_tab(self):
        dash = tk.Frame(self.tab_dashboard, bg=self.c_bg, padx=16, pady=16)
        dash.pack(fill="both", expand=True)

        # --- Card 1: Chọn tài khoản thao tác ---
        acc_box = tk.LabelFrame(
            dash,
            text=" 1. Chọn tài khoản Gmail ",
            font=("Segoe UI", 10, "bold"),
            bg=self.c_card,
            fg=self.c_text,
            padx=16,
            pady=12,
            relief="solid",
            bd=1
        )
        acc_box.pack(fill="x", pady=(0, 14))

        row1 = tk.Frame(acc_box, bg=self.c_card)
        row1.pack(fill="x")

        tk.Label(row1, text="Tài khoản:", bg=self.c_card, font=("Segoe UI", 10)).pack(side="left", padx=(0, 8))
        self.acc_combobox_var = tk.StringVar()
        self.acc_combobox = ttk.Combobox(
            row1,
            textvariable=self.acc_combobox_var,
            state="readonly",
            width=42,
            font=("Segoe UI", 10)
        )
        self.acc_combobox.pack(side="left", padx=(0, 12))
        self.acc_combobox.bind("<<ComboboxSelected>>", self.on_account_selected)

        # Nút chuyển nhanh sang quản lý tài khoản
        btn_manage = ttk.Button(row1, text="➕ Thêm / Quản lý tài khoản", command=lambda: self.notebook.select(self.tab_accounts))
        btn_manage.pack(side="left")

        # Chi tiết tài khoản đang chọn
        self.lbl_acc_detail = tk.Label(
            acc_box,
            text="Người gửi mục tiêu: GM@wloi.org",
            font=("Segoe UI", 9, "italic"),
            fg=self.c_text_muted,
            bg=self.c_card,
            anchor="w"
        )
        self.lbl_acc_detail.pack(fill="x", pady=(8, 0))

        # --- Card 2: Kết quả OTP Nổi Bật ---
        otp_box = tk.LabelFrame(
            dash,
            text=" 2. Kết quả mã OTP ",
            font=("Segoe UI", 10, "bold"),
            bg=self.c_card,
            fg=self.c_text,
            padx=16,
            pady=16,
            relief="solid",
            bd=1
        )
        otp_box.pack(fill="x", pady=(0, 14))

        otp_center = tk.Frame(otp_box, bg=self.c_card)
        otp_center.pack(expand=True)

        self.lbl_otp_display = tk.Label(
            otp_center,
            text="----",
            font=("Consolas", 42, "bold"),
            fg="#2563eb",
            bg="#eff6ff",
            width=9,
            relief="groove",
            bd=2,
            pady=6
        )
        self.lbl_otp_display.pack(pady=(0, 10))

        # Khung nút Copy và tự động copy
        copy_row = tk.Frame(otp_box, bg=self.c_card)
        copy_row.pack()

        self.btn_copy_otp = tk.Button(
            copy_row,
            text="📋 Sao Chép Mã (Ctrl+V)",
            font=("Segoe UI", 10, "bold"),
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            relief="flat",
            padx=18,
            pady=6,
            command=self.copy_current_otp,
            cursor="hand2"
        )
        self.btn_copy_otp.pack(side="left", padx=6)

        self.auto_copy_var = tk.BooleanVar(value=True)
        chk_auto_copy = tk.Checkbutton(
            copy_row,
            text="Tự động copy vào Clipboard khi có mã",
            variable=self.auto_copy_var,
            bg=self.c_card,
            font=("Segoe UI", 9)
        )
        chk_auto_copy.pack(side="left", padx=10)

        # Thông tin email chứa OTP
        self.lbl_otp_info = tk.Label(
            otp_box,
            text="Chưa có mã OTP nào được lấy.",
            font=("Segoe UI", 9),
            fg=self.c_text_muted,
            bg=self.c_card
        )
        self.lbl_otp_info.pack(pady=(8, 0))

        # --- Card 3: Thao tác & Hành động ---
        action_box = tk.Frame(dash, bg=self.c_bg)
        action_box.pack(fill="x", pady=4)

        self.btn_fetch_now = tk.Button(
            action_box,
            text="⚡ Lấy OTP Gần Nhất (Email Hiện Có)",
            font=("Segoe UI", 11, "bold"),
            bg="#059669",
            fg="white",
            activebackground="#047857",
            activeforeground="white",
            relief="flat",
            padx=16,
            pady=9,
            command=self.action_fetch_latest,
            cursor="hand2"
        )
        self.btn_fetch_now.pack(side="left", padx=(0, 10))

        self.btn_listen_otp = tk.Button(
            action_box,
            text="⏱️ Chờ OTP Mới (Auto-Wait 120s)",
            font=("Segoe UI", 11, "bold"),
            bg="#0284c7",
            fg="white",
            activebackground="#0369a1",
            activeforeground="white",
            relief="flat",
            padx=16,
            pady=9,
            command=self.toggle_listen_otp,
            cursor="hand2"
        )
        self.btn_listen_otp.pack(side="left")

        # Nạp danh sách tài khoản ban đầu vào combobox
        self.refresh_account_combobox()

    def refresh_account_combobox(self):
        values = []
        for acc in self.accounts:
            lbl = f"{acc.get('label', '')} ({acc.get('email', '')})"
            values.append(lbl)
        self.acc_combobox["values"] = values
        if values:
            if not self.acc_combobox_var.get() or self.acc_combobox_var.get() not in values:
                self.acc_combobox.current(0)
            self.on_account_selected()
        else:
            self.acc_combobox_var.set("")
            self.lbl_acc_detail.config(text="Chưa có tài khoản nào. Vui lòng thêm tài khoản.")

    def get_selected_account(self) -> dict | None:
        idx = self.acc_combobox.current()
        if 0 <= idx < len(self.accounts):
            return self.accounts[idx]
        return None

    def on_account_selected(self, event=None):
        acc = self.get_selected_account()
        if acc:
            sender = acc.get("sender", DEFAULT_SENDER)
            has_pw = "Đã nhập" if acc.get("password") else "CHƯA NHẬP MẬT KHẨU"
            pw_color = "black" if acc.get("password") else "red"
            self.lbl_acc_detail.config(
                text=f"Email: {acc.get('email')}  |  Người gửi cần lọc: {sender}  |  Mật khẩu ứng dụng: {has_pw}"
            )

    def copy_current_otp(self):
        otp = self.lbl_otp_display.cget("text")
        if otp and otp != "----":
            self.root.clipboard_clear()
            self.root.clipboard_append(otp)
            copy_to_clipboard(otp)
            self.set_status(f"[✓] Đã sao chép mã {otp} vào Clipboard!")
            messagebox.showinfo("Thành công", f"Đã sao chép mã {otp} vào Clipboard!")

    def set_status(self, text: str):
        self.status_bar.config(text=text)

    # =================================================================
    # FETCH OTP THREADS
    # =================================================================
    def action_fetch_latest(self):
        acc = self.get_selected_account()
        if not acc:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn hoặc thêm tài khoản Gmail trước.")
            return

        if not acc.get("password"):
            messagebox.showwarning(
                "Chưa có mật khẩu",
                f"Tài khoản {acc.get('email')} chưa có Mật khẩu ứng dụng (App Password 16 số).\n"
                "Vui lòng chuyển qua tab 'Quản Lý Tài Khoản' để cập nhật."
            )
            return

        self.btn_fetch_now.config(state="disabled")
        self.btn_listen_otp.config(state="disabled")
        self.set_status(f"Đang kết nối IMAP tới {acc.get('email')} để lấy OTP...")
        self.lbl_otp_display.config(text="....", fg="#94a3b8")

        thread = threading.Thread(target=self._worker_fetch_latest, args=(acc,), daemon=True)
        thread.start()

    def _worker_fetch_latest(self, acc: dict):
        email_addr = acc.get("email")
        password = acc.get("password")
        sender = acc.get("sender") or DEFAULT_SENDER

        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            mail.login(email_addr, password)
            mail.select("INBOX")

            status, data = mail.search(None, f'(FROM "{sender}")')
            if status != "OK" or not data or not data[0]:
                self.root.after(0, self._on_fetch_finish, None, None, f"Không tìm thấy email nào từ {sender}")
                return

            email_ids = data[0].split()
            latest_id = email_ids[-1]

            status, msg_data = mail.fetch(latest_id, "(RFC822)")
            if status != "OK":
                self.root.after(0, self._on_fetch_finish, None, None, "Không thể tải thư.")
                return

            msg = email.message_from_bytes(msg_data[0][1])
            subject = decode_mime_words(msg.get("Subject", ""))
            from_h = decode_mime_words(msg.get("From", ""))
            date_h = msg.get("Date", "")
            body = extract_body_text(msg)

            otp = parse_otp_code(body) or parse_otp_code(subject)

            mail.close()
            mail.logout()

            info = {
                "email": email_addr,
                "sender": from_h,
                "subject": subject,
                "date": date_h,
            }
            self.root.after(0, self._on_fetch_finish, otp, info, None)

        except imaplib.IMAP4.error as err:
            self.root.after(0, self._on_fetch_finish, None, None, f"Lỗi xác thực Gmail: {err}")
        except Exception as err:
            self.root.after(0, self._on_fetch_finish, None, None, f"Lỗi kết nối: {err}")

    def _on_fetch_finish(self, otp: str | None, info: dict | None, error: str | None):
        self.btn_fetch_now.config(state="normal")
        self.btn_listen_otp.config(state="normal")

        if error:
            self.lbl_otp_display.config(text="----", fg="#ef4444")
            self.set_status(f"[!] {error}")
            messagebox.showerror("Lỗi", error)
            return

        if otp:
            self.lbl_otp_display.config(text=otp, fg="#16a34a")
            self.lbl_otp_info.config(
                text=f"Từ: {info.get('sender')} | Tiêu đề: {info.get('subject')} | Lúc: {info.get('date')}"
            )
            self.set_status(f"[✓] Đã lấy thành công mã OTP: {otp}")

            if self.auto_copy_var.get():
                self.root.clipboard_clear()
                self.root.clipboard_append(otp)
                copy_to_clipboard(otp)

            # Lưu vào lịch sử
            self.add_history_record(info.get("email"), info.get("sender"), otp, info.get("subject"), info.get("date"))
        else:
            self.lbl_otp_display.config(text="----", fg="#f59e0b")
            self.lbl_otp_info.config(
                text=f"Email mới nhất: {info.get('subject')} (Không tìm thấy 4 số OTP trong nội dung)"
            )
            self.set_status("[-] Đã nhận thư nhưng không tìm thấy 4 số OTP.")

    # --- Live Listen / Chờ OTP ---
    def toggle_listen_otp(self):
        if self.is_listening:
            # Dừng lắng nghe
            self.stop_listening_event.set()
            self.is_listening = False
            self.btn_listen_otp.config(text="⏱️ Chờ OTP Mới (Auto-Wait 120s)", bg="#0284c7")
            self.btn_fetch_now.config(state="normal")
            self.set_status("Đã dừng chế độ chờ.")
        else:
            acc = self.get_selected_account()
            if not acc:
                messagebox.showwarning("Cảnh báo", "Vui lòng chọn tài khoản Gmail.")
                return
            if not acc.get("password"):
                messagebox.showwarning("Chưa có mật khẩu", "Tài khoản chưa có App Password.")
                return

            self.is_listening = True
            self.stop_listening_event.clear()
            self.btn_listen_otp.config(text="⏹️ DỪNG CHỜ (Đang quét...)", bg="#dc2626")
            self.btn_fetch_now.config(state="disabled")
            self.lbl_otp_display.config(text="....", fg="#94a3b8")
            self.set_status(f"Đang chờ email mới từ {acc.get('sender')} gửi đến {acc.get('email')}...")

            self.listen_thread = threading.Thread(target=self._worker_listen, args=(acc,), daemon=True)
            self.listen_thread.start()

    def _worker_listen(self, acc: dict):
        email_addr = acc.get("email")
        password = acc.get("password")
        sender = acc.get("sender") or DEFAULT_SENDER
        timeout = 120
        start_time = time.time()

        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            mail.login(email_addr, password)
            mail.select("INBOX")

            status, data = mail.search(None, f'(FROM "{sender}")')
            initial_ids = set(data[0].split()) if status == "OK" and data[0] else set()

            while not self.stop_listening_event.is_set() and (time.time() - start_time < timeout):
                time.sleep(3)
                if self.stop_listening_event.is_set():
                    break

                remaining = int(timeout - (time.time() - start_time))
                self.root.after(0, self.set_status, f"Đang chờ mail OTP mới từ {sender}... (Còn {remaining}s)")

                mail.select("INBOX")
                status, data = mail.search(None, f'(FROM "{sender}")')
                if status == "OK" and data[0]:
                    current_ids = set(data[0].split())
                    new_ids = current_ids - initial_ids
                    if new_ids:
                        newest_id = sorted(list(new_ids), key=lambda x: int(x))[-1]
                        status, msg_data = mail.fetch(newest_id, "(RFC822)")
                        if status == "OK":
                            msg = email.message_from_bytes(msg_data[0][1])
                            subject = decode_mime_words(msg.get("Subject", ""))
                            from_h = decode_mime_words(msg.get("From", ""))
                            date_h = msg.get("Date", "")
                            body = extract_body_text(msg)
                            otp = parse_otp_code(body) or parse_otp_code(subject)

                            mail.close()
                            mail.logout()

                            info = {
                                "email": email_addr,
                                "sender": from_h,
                                "subject": subject,
                                "date": date_h,
                            }
                            self.root.after(0, self._on_listen_success, otp, info)
                            return

            mail.close()
            mail.logout()
            self.root.after(0, self._on_listen_timeout)

        except Exception as err:
            self.root.after(0, self._on_listen_error, str(err))

    def _on_listen_success(self, otp: str | None, info: dict):
        self.is_listening = False
        self.btn_listen_otp.config(text="⏱️ Chờ OTP Mới (Auto-Wait 120s)", bg="#0284c7")
        self.btn_fetch_now.config(state="normal")

        if otp:
            self.lbl_otp_display.config(text=otp, fg="#16a34a")
            self.lbl_otp_info.config(
                text=f"Vừa nhận: {info.get('subject')} | Lúc: {info.get('date')}"
            )
            self.set_status(f"[✓] ĐÃ BẮT ĐƯỢC MÃ OTP MỚI: {otp}")

            if self.auto_copy_var.get():
                self.root.clipboard_clear()
                self.root.clipboard_append(otp)
                copy_to_clipboard(otp)

            self.add_history_record(info.get("email"), info.get("sender"), otp, info.get("subject"), info.get("date"))
            messagebox.showinfo("Đã nhận OTP!", f"Mã xác thực mới của bạn: {otp}\n(Đã tự động sao chép)")
        else:
            self.lbl_otp_display.config(text="----", fg="#f59e0b")
            self.set_status("[-] Có email mới nhưng không tìm thấy 4 số OTP.")

    def _on_listen_timeout(self):
        if self.is_listening:
            self.is_listening = False
            self.btn_listen_otp.config(text="⏱️ Chờ OTP Mới (Auto-Wait 120s)", bg="#0284c7")
            self.btn_fetch_now.config(state="normal")
            self.set_status("Hết thời gian chờ (120s). Không nhận được email mới.")
            messagebox.showinfo("Hết giờ", "Không có email OTP mới nào gửi đến trong 120 giây.")

    def _on_listen_error(self, err_msg: str):
        self.is_listening = False
        self.btn_listen_otp.config(text="⏱️ Chờ OTP Mới (Auto-Wait 120s)", bg="#0284c7")
        self.btn_fetch_now.config(state="normal")
        self.set_status(f"[!] Lỗi khi chờ OTP: {err_msg}")
        messagebox.showerror("Lỗi", f"Lỗi trong quá trình lắng nghe: {err_msg}")

    # =================================================================
    # TAB 2: QUẢN LÝ TÀI KHOẢN (ACCOUNTS TAB)
    # =================================================================
    def build_accounts_tab(self):
        acc_frame = tk.Frame(self.tab_accounts, bg=self.c_bg, padx=16, pady=16)
        acc_frame.pack(fill="both", expand=True)

        # Hướng dẫn nhanh
        help_lbl = tk.Label(
            acc_frame,
            text="💡 Mẹo: Dùng 'Mật khẩu ứng dụng' (App Password 16 số của Google), không dùng mật khẩu Gmail thường.\n"
                 "Tạo tại: https://myaccount.google.com/apppasswords (yêu cầu bật xác minh 2 bước).",
            font=("Segoe UI", 9),
            fg="#0369a1",
            bg="#e0f2fe",
            padx=12,
            pady=8,
            justify="left",
            relief="solid",
            bd=1
        )
        help_lbl.pack(fill="x", pady=(0, 12))

        # Thanh nút thao tác
        btn_bar = tk.Frame(acc_frame, bg=self.c_bg)
        btn_bar.pack(fill="x", pady=(0, 8))

        btn_add = tk.Button(
            btn_bar,
            text="➕ Thêm Tài Khoản Mới",
            font=("Segoe UI", 9, "bold"),
            bg="#2563eb",
            fg="white",
            relief="flat",
            padx=12,
            pady=5,
            command=self.open_add_account_dialog,
            cursor="hand2"
        )
        btn_add.pack(side="left", padx=(0, 8))

        btn_edit = tk.Button(
            btn_bar,
            text="✏️ Sửa",
            font=("Segoe UI", 9),
            bg="#475569",
            fg="white",
            relief="flat",
            padx=12,
            pady=5,
            command=self.open_edit_account_dialog,
            cursor="hand2"
        )
        btn_edit.pack(side="left", padx=(0, 8))

        btn_delete = tk.Button(
            btn_bar,
            text="🗑️ Xóa",
            font=("Segoe UI", 9),
            bg="#dc2626",
            fg="white",
            relief="flat",
            padx=12,
            pady=5,
            command=self.delete_selected_account,
            cursor="hand2"
        )
        btn_delete.pack(side="left", padx=(0, 8))

        btn_test = tk.Button(
            btn_bar,
            text="🔍 Kiểm tra kết nối",
            font=("Segoe UI", 9),
            bg="#0891b2",
            fg="white",
            relief="flat",
            padx=12,
            pady=5,
            command=self.test_selected_account_connection,
            cursor="hand2"
        )
        btn_test.pack(side="left")

        # Bảng danh sách tài khoản (Treeview)
        tree_frame = tk.Frame(acc_frame)
        tree_frame.pack(fill="both", expand=True)

        columns = ("label", "email", "password_status", "sender")
        self.acc_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")

        self.acc_tree.heading("label", text="Tên gợi nhớ")
        self.acc_tree.heading("email", text="Email (Gmail)")
        self.acc_tree.heading("password_status", text="Mật khẩu ứng dụng")
        self.acc_tree.heading("sender", text="Lọc người gửi")

        self.acc_tree.column("label", width=140, anchor="w")
        self.acc_tree.column("email", width=240, anchor="w")
        self.acc_tree.column("password_status", width=150, anchor="center")
        self.acc_tree.column("sender", width=150, anchor="w")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.acc_tree.yview)
        self.acc_tree.configure(yscrollcommand=scrollbar.set)

        self.acc_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.refresh_accounts_table()

    def refresh_accounts_table(self):
        for item in self.acc_tree.get_children():
            self.acc_tree.delete(item)

        for acc in self.accounts:
            pw_status = "••••••••••••••••" if acc.get("password") else "❌ Chưa có"
            self.acc_tree.insert(
                "",
                "end",
                iid=acc["id"],
                values=(
                    acc.get("label", ""),
                    acc.get("email", ""),
                    pw_status,
                    acc.get("sender", DEFAULT_SENDER),
                ),
            )

    def open_add_account_dialog(self):
        self._account_form_dialog(None)

    def open_edit_account_dialog(self):
        selected = self.acc_tree.selection()
        if not selected:
            messagebox.showwarning("Chọn tài khoản", "Vui lòng chọn một tài khoản từ danh sách để sửa.")
            return
        acc_id = selected[0]
        acc = next((a for a in self.accounts if a["id"] == acc_id), None)
        if acc:
            self._account_form_dialog(acc)

    def _account_form_dialog(self, edit_acc: dict | None):
        dialog = tk.Toplevel(self.root)
        is_edit = edit_acc is not None
        dialog.title("Sửa Tài Khoản" if is_edit else "Thêm Tài Khoản Mới")
        dialog.geometry("480x360")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        frame = tk.Frame(dialog, padx=20, pady=20)
        frame.pack(fill="both", expand=True)

        # 1. Tên gợi nhớ
        tk.Label(frame, text="Tên gợi nhớ (Ví dụ: Acc 1, Clone Game...):", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        e_label = ttk.Entry(frame, width=45)
        e_label.pack(fill="x", pady=(2, 10))
        if is_edit:
            e_label.insert(0, edit_acc.get("label", ""))

        # 2. Email
        tk.Label(frame, text="Địa chỉ Gmail:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        e_email = ttk.Entry(frame, width=45)
        e_email.pack(fill="x", pady=(2, 10))
        if is_edit:
            e_email.insert(0, edit_acc.get("email", ""))

        # 3. Mật khẩu ứng dụng (App Password)
        tk.Label(frame, text="Mật khẩu ứng dụng (16 ký tự Google):", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        e_password = ttk.Entry(frame, width=45, show="*")
        e_password.pack(fill="x", pady=(2, 10))
        if is_edit:
            e_password.insert(0, edit_acc.get("password", ""))

        # 4. Người gửi cần lọc
        tk.Label(frame, text="Email người gửi OTP (Mặc định: GM@wloi.org):", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        e_sender = ttk.Entry(frame, width=45)
        e_sender.pack(fill="x", pady=(2, 16))
        if is_edit:
            e_sender.insert(0, edit_acc.get("sender", DEFAULT_SENDER))
        else:
            e_sender.insert(0, DEFAULT_SENDER)

        # Nút Lưu
        def on_save():
            label = e_label.get().strip() or "Tài khoản Gmail"
            email_val = e_email.get().strip()
            password_val = e_password.get().strip()
            sender_val = e_sender.get().strip() or DEFAULT_SENDER

            if not email_val:
                messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập địa chỉ Gmail.", parent=dialog)
                return

            if is_edit:
                edit_acc["label"] = label
                edit_acc["email"] = email_val
                edit_acc["password"] = password_val
                edit_acc["sender"] = sender_val
            else:
                new_id = str(int(time.time() * 1000))
                self.accounts.append({
                    "id": new_id,
                    "label": label,
                    "email": email_val,
                    "password": password_val,
                    "sender": sender_val,
                })

            save_accounts(self.accounts)
            self.refresh_accounts_table()
            self.refresh_account_combobox()
            dialog.destroy()
            self.set_status("[✓] Đã lưu thông tin tài khoản.")

        btn_row = tk.Frame(frame)
        btn_row.pack(fill="x")
        tk.Button(
            btn_row,
            text="Lưu Tài Khoản",
            bg="#2563eb",
            fg="white",
            relief="flat",
            padx=14,
            pady=6,
            command=on_save
        ).pack(side="right")
        tk.Button(
            btn_row,
            text="Hủy",
            relief="flat",
            padx=14,
            pady=6,
            command=dialog.destroy
        ).pack(side="right", padx=8)

    def delete_selected_account(self):
        selected = self.acc_tree.selection()
        if not selected:
            messagebox.showwarning("Chọn tài khoản", "Vui lòng chọn tài khoản cần xóa.")
            return

        acc_id = selected[0]
        acc = next((a for a in self.accounts if a["id"] == acc_id), None)
        if not acc:
            return

        confirm = messagebox.askyesno(
            "Xác nhận xóa",
            f"Bạn có chắc muốn xóa tài khoản '{acc.get('label')}' ({acc.get('email')})?"
        )
        if confirm:
            self.accounts = [a for a in self.accounts if a["id"] != acc_id]
            save_accounts(self.accounts)
            self.refresh_accounts_table()
            self.refresh_account_combobox()
            self.set_status("[✓] Đã xóa tài khoản.")

    def test_selected_account_connection(self):
        selected = self.acc_tree.selection()
        if not selected:
            messagebox.showwarning("Chọn tài khoản", "Vui lòng chọn tài khoản cần kiểm tra.")
            return
        acc_id = selected[0]
        acc = next((a for a in self.accounts if a["id"] == acc_id), None)
        if not acc:
            return

        if not acc.get("password"):
            messagebox.showwarning("Lỗi", "Tài khoản này chưa nhập App Password.")
            return

        self.set_status(f"Đang kiểm tra kết nối tới {acc.get('email')}...")

        def _test():
            try:
                mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
                mail.login(acc.get("email"), acc.get("password"))
                mail.logout()
                self.root.after(0, lambda: messagebox.showinfo(
                    "Thành công", f"Đăng nhập IMAP tài khoản {acc.get('email')} thành công!"
                ))
                self.root.after(0, lambda: self.set_status(f"[✓] Kết nối {acc.get('email')} thành công."))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(
                    "Thất bại", f"Không thể đăng nhập vào {acc.get('email')}.\nChi tiết: {e}"
                ))
                self.root.after(0, lambda: self.set_status(f"[!] Kết nối {acc.get('email')} thất bại: {e}"))

        threading.Thread(target=_test, daemon=True).start()

    # =================================================================
    # TAB 3: LỊCH SỬ OTP (HISTORY TAB)
    # =================================================================
    def build_history_tab(self):
        hist_frame = tk.Frame(self.tab_history, bg=self.c_bg, padx=16, pady=16)
        hist_frame.pack(fill="both", expand=True)

        top_bar = tk.Frame(hist_frame, bg=self.c_bg)
        top_bar.pack(fill="x", pady=(0, 8))

        tk.Label(top_bar, text="Danh sách các mã OTP đã lấy:", font=("Segoe UI", 10, "bold"), bg=self.c_bg).pack(side="left")

        btn_clear = tk.Button(
            top_bar,
            text="🧹 Xóa lịch sử",
            font=("Segoe UI", 9),
            relief="flat",
            bg="#64748b",
            fg="white",
            padx=10,
            pady=4,
            command=self.clear_history
        )
        btn_clear.pack(side="right")

        table_frame = tk.Frame(hist_frame)
        table_frame.pack(fill="both", expand=True)

        cols = ("time", "account", "otp", "sender", "subject")
        self.hist_tree = ttk.Treeview(table_frame, columns=cols, show="headings")

        self.hist_tree.heading("time", text="Thời gian")
        self.hist_tree.heading("account", text="Tài khoản nhận")
        self.hist_tree.heading("otp", text="Mã OTP")
        self.hist_tree.heading("sender", text="Người gửi")
        self.hist_tree.heading("subject", text="Tiêu đề email")

        self.hist_tree.column("time", width=140, anchor="center")
        self.hist_tree.column("account", width=200, anchor="w")
        self.hist_tree.column("otp", width=90, anchor="center")
        self.hist_tree.column("sender", width=150, anchor="w")
        self.hist_tree.column("subject", width=220, anchor="w")

        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.hist_tree.yview)
        self.hist_tree.configure(yscrollcommand=scroll.set)

        self.hist_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # Double click vào hàng để copy OTP
        self.hist_tree.bind("<Double-1>", self.on_history_double_click)

    def add_history_record(self, account: str, sender: str, otp: str, subject: str, mail_date: str):
        now_str = time.strftime("%H:%M:%S %d/%m/%Y")
        self.hist_tree.insert(
            "",
            0,
            values=(now_str, account, otp, sender, subject)
        )

    def on_history_double_click(self, event):
        selected = self.hist_tree.selection()
        if selected:
            vals = self.hist_tree.item(selected[0], "values")
            if vals and len(vals) >= 3:
                otp = vals[2]
                self.root.clipboard_clear()
                self.root.clipboard_append(otp)
                copy_to_clipboard(otp)
                messagebox.showinfo("Đã sao chép", f"Đã sao chép mã {otp} vào Clipboard!")

    def clear_history(self):
        for item in self.hist_tree.get_children():
            self.hist_tree.delete(item)
        self.set_status("Đã làm trống lịch sử OTP.")


# =====================================================================
# CHẠY ỨNG DỤNG
# =====================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = OtpGrabberApp(root)
    root.mainloop()
