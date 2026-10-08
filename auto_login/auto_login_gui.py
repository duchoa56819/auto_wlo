"""
Giao diện đồ họa (GUI) Tự động đăng nhập Đa Client WLO (Wonderland Online)
Hỗ trợ quản lý nhiều client (alogin-*.exe), chọn Nhân vật 1 hoặc Nhân vật 2,
đăng nhập từng client hoặc đăng nhập hàng loạt tự động.
"""

import os
import sys
import json
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import auto_login

# Màu sắc giao diện (Dark Modern Theme)
THEME = {
    "bg": "#1e1e2e",
    "card_bg": "#252538",
    "card_border": "#313244",
    "fg": "#cdd6f4",
    "fg_dim": "#a6adc8",
    "accent": "#89b4fa",
    "green": "#a6e3a1",
    "red": "#f38ba8",
    "yellow": "#f9e2af",
    "blue": "#74c7ec",
    "btn_start": "#a6e3a1",
    "btn_multi": "#cba6f7",
    "btn_stop": "#f38ba8",
    "log_bg": "#181825",
    "log_fg": "#cdd6f4",
    "table_bg": "#1e1e2e",
    "table_fg": "#cdd6f4",
    "table_select": "#45475a",
}


class WloMultiClientGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WLO Multi-Client Auto Login - Quản Lý Đăng Nhập Đa Client")
        self.geometry("1060x700")
        self.minsize(980, 620)
        self.configure(bg=THEME["bg"])

        # Biến điều khiển
        self.worker_thread = None
        self.is_running = False
        self.abort_requested = False

        # Danh sách cấu hình clients
        self.clients_data = auto_login.load_clients_config()
        if not self.clients_data:
            # Tạo dữ liệu mặc định nếu chưa có
            self.clients_data = [
                {
                    "id": "f03_char1",
                    "name": "F03 - Nhân vật 1",
                    "exe": "alogin-F03.exe",
                    "user": "bgdF03",
                    "pass": "111111",
                    "email": "backspace.noob@gmail.com",
                    "char_slot": 1,
                    "enabled": True,
                },
                {
                    "id": "f03_char2",
                    "name": "F03 - Nhân vật 2",
                    "exe": "alogin-F03.exe",
                    "user": "bgdF03",
                    "pass": "111111",
                    "email": "backspace.noob@gmail.com",
                    "char_slot": 2,
                    "enabled": False,
                },
            ]
            auto_login.save_clients_config(self.clients_data)

        # Quét danh sách exe có sẵn
        self.available_exes = self.scan_available_exes()

        self.create_widgets()
        self.apply_theme()
        self.refresh_table()

    def scan_available_exes(self):
        """Quét các file alogin*.exe trong thư mục game."""
        game_dir = auto_login.DEFAULT_GAME_DIR
        exes = []
        if os.path.exists(game_dir):
            for f in os.listdir(game_dir):
                if f.lower().startswith("alogin") and f.lower().endswith(".exe"):
                    exes.append(f)
        exes.sort()
        return exes if exes else ["alogin-F03.exe", "alogin-F02.exe", "alogin-F04.exe"]

    def create_widgets(self):
        # 1. Header Bar
        header_frame = tk.Frame(self, bg=THEME["card_bg"], pady=10, padx=16)
        header_frame.pack(fill="x", padx=10, pady=(10, 5))

        title_lbl = tk.Label(
            header_frame,
            text="🎮 WLO MULTI-CLIENT AUTO LOGIN",
            font=("Segoe UI", 15, "bold"),
            bg=THEME["card_bg"],
            fg=THEME["accent"],
        )
        title_lbl.pack(side="left")

        subtitle_lbl = tk.Label(
            header_frame,
            text="Tự động mở đa client game, click chọn Nhân vật 1/2 & lấy OTP Gmail",
            font=("Segoe UI", 9),
            bg=THEME["card_bg"],
            fg=THEME["fg_dim"],
        )
        subtitle_lbl.pack(side="left", padx=15, pady=(4, 0))

        # 2. Main Paned Layout
        paned = tk.PanedWindow(self, orient="horizontal", bg=THEME["bg"], sashwidth=6)
        paned.pack(fill="both", expand=True, padx=10, pady=5)

        # Cột Trái: Danh sách Clients & Cấu hình chi tiết
        left_frame = tk.Frame(paned, bg=THEME["bg"], width=520)
        paned.add(left_frame, minsize=480)

        # Cột Phải: Điều khiển & Nhật ký hoạt động
        right_frame = tk.Frame(paned, bg=THEME["bg"], width=480)
        paned.add(right_frame, minsize=420)

        # ===== CỘT TRÁI: QUẢN LÝ CLIENTS =====
        # Card 1: Bảng danh sách các Client
        card_list = tk.LabelFrame(
            left_frame,
            text=" 📋 DANH SÁCH CLIENT CẦN ĐĂNG NHẬP ",
            font=("Segoe UI", 10, "bold"),
            bg=THEME["card_bg"],
            fg=THEME["accent"],
            padx=8,
            pady=8,
        )
        card_list.pack(fill="both", expand=True, pady=(0, 6))

        # Treeview Bảng danh sách
        columns = ("enabled", "name", "exe", "user", "char", "email")
        self.tree = ttk.Treeview(card_list, columns=columns, show="headings", height=7, selectmode="browse")

        self.tree.heading("enabled", text="Bật")
        self.tree.heading("name", text="Tên Client")
        self.tree.heading("exe", text="File EXE")
        self.tree.heading("user", text="Tài khoản")
        self.tree.heading("char", text="Nhân vật")
        self.tree.heading("email", text="Gmail nhận OTP")

        self.tree.column("enabled", width=45, anchor="center")
        self.tree.column("name", width=120, anchor="w")
        self.tree.column("exe", width=110, anchor="w")
        self.tree.column("user", width=80, anchor="w")
        self.tree.column("char", width=75, anchor="center")
        self.tree.column("email", width=150, anchor="w")

        tree_scroll = ttk.Scrollbar(card_list, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", self.on_tree_toggle)

        # Thanh nút thao tác bảng
        bar_tbl_btns = tk.Frame(left_frame, bg=THEME["bg"])
        bar_tbl_btns.pack(fill="x", pady=(0, 6))

        btn_toggle = tk.Button(
            bar_tbl_btns, text="✔️ Bật/Tắt Chọn", font=("Segoe UI", 8), bg=THEME["card_bg"], fg=THEME["fg"],
            relief="flat", cursor="hand2", padx=6, pady=3, command=self.toggle_selected_enabled
        )
        btn_toggle.pack(side="left", padx=2)

        btn_add = tk.Button(
            bar_tbl_btns, text="➕ Thêm Mới", font=("Segoe UI", 8), bg=THEME["card_bg"], fg=THEME["green"],
            relief="flat", cursor="hand2", padx=6, pady=3, command=self.add_new_client
        )
        btn_add.pack(side="left", padx=2)

        btn_del = tk.Button(
            bar_tbl_btns, text="🗑️ Xóa Client", font=("Segoe UI", 8), bg=THEME["card_bg"], fg=THEME["red"],
            relief="flat", cursor="hand2", padx=6, pady=3, command=self.delete_selected_client
        )
        btn_del.pack(side="left", padx=2)

        btn_save = tk.Button(
            bar_tbl_btns, text="💾 Lưu Cấu Hình", font=("Segoe UI", 8, "bold"), bg=THEME["card_bg"], fg=THEME["accent"],
            relief="flat", cursor="hand2", padx=6, pady=3, command=self.save_all_clients
        )
        btn_save.pack(side="right", padx=2)

        # Card 2: Form chỉnh sửa chi tiết Client đang chọn
        card_edit = tk.LabelFrame(
            left_frame,
            text=" ✏️ THÔNG TIN CHI TIẾT CLIENT ĐANG CHỌN ",
            font=("Segoe UI", 10, "bold"),
            bg=THEME["card_bg"],
            fg=THEME["accent"],
            padx=10,
            pady=8,
        )
        card_edit.pack(fill="x", pady=(0, 4))

        # Tên hiển thị
        tk.Label(card_edit, text="Tên Client:", font=("Segoe UI", 9), bg=THEME["card_bg"], fg=THEME["fg"]).grid(row=0, column=0, sticky="w", pady=3)
        self.ent_name = tk.Entry(card_edit, font=("Segoe UI", 9), bg=THEME["log_bg"], fg=THEME["fg"], insertbackground=THEME["fg"])
        self.ent_name.grid(row=0, column=1, sticky="ew", pady=3, padx=(5, 0))

        # File Exe
        tk.Label(card_edit, text="File Client Exe:", font=("Segoe UI", 9), bg=THEME["card_bg"], fg=THEME["fg"]).grid(row=1, column=0, sticky="w", pady=3)
        self.cbo_exe = ttk.Combobox(card_edit, values=self.available_exes, font=("Segoe UI", 9))
        self.cbo_exe.grid(row=1, column=1, sticky="ew", pady=3, padx=(5, 0))

        # Tài khoản Game
        tk.Label(card_edit, text="Tài khoản (User):", font=("Segoe UI", 9), bg=THEME["card_bg"], fg=THEME["fg"]).grid(row=2, column=0, sticky="w", pady=3)
        self.ent_user = tk.Entry(card_edit, font=("Segoe UI", 9), bg=THEME["log_bg"], fg=THEME["fg"], insertbackground=THEME["fg"])
        self.ent_user.grid(row=2, column=1, sticky="ew", pady=3, padx=(5, 0))

        # Mật khẩu Game
        tk.Label(card_edit, text="Mật khẩu:", font=("Segoe UI", 9), bg=THEME["card_bg"], fg=THEME["fg"]).grid(row=3, column=0, sticky="w", pady=3)
        self.ent_pass = tk.Entry(card_edit, font=("Segoe UI", 9), bg=THEME["log_bg"], fg=THEME["fg"], insertbackground=THEME["fg"])
        self.ent_pass.grid(row=3, column=1, sticky="ew", pady=3, padx=(5, 0))

        # Gmail nhận OTP
        tk.Label(card_edit, text="Gmail nhận OTP:", font=("Segoe UI", 9), bg=THEME["card_bg"], fg=THEME["fg"]).grid(row=4, column=0, sticky="w", pady=3)
        self.ent_email = tk.Entry(card_edit, font=("Segoe UI", 9), bg=THEME["log_bg"], fg=THEME["fg"], insertbackground=THEME["fg"])
        self.ent_email.grid(row=4, column=1, sticky="ew", pady=3, padx=(5, 0))

        # Chọn Nhân vật (Radio NV1 / NV2)
        tk.Label(card_edit, text="Vị trí nhân vật:", font=("Segoe UI", 9), bg=THEME["card_bg"], fg=THEME["fg"]).grid(row=5, column=0, sticky="w", pady=4)
        char_frame = tk.Frame(card_edit, bg=THEME["card_bg"])
        char_frame.grid(row=5, column=1, sticky="w", pady=4, padx=(5, 0))

        self.var_char_slot = tk.IntVar(value=1)
        rb_nv1 = tk.Radiobutton(
            char_frame, text="👤 Nhân vật 1 (Client: 337, 444)", variable=self.var_char_slot, value=1,
            bg=THEME["card_bg"], fg=THEME["fg"], selectcolor=THEME["card_border"], font=("Segoe UI", 9)
        )
        rb_nv1.pack(side="left", padx=(0, 10))

        rb_nv2 = tk.Radiobutton(
            char_frame, text="👤 Nhân vật 2 (Client: 745, 342)", variable=self.var_char_slot, value=2,
            bg=THEME["card_bg"], fg=THEME["fg"], selectcolor=THEME["card_border"], font=("Segoe UI", 9)
        )
        rb_nv2.pack(side="left")

        # Nút áp dụng sửa
        btn_apply = tk.Button(
            card_edit, text="✔️ Cập nhật thông tin vào bảng", font=("Segoe UI", 9, "bold"),
            bg=THEME["accent"], fg="#11111b", relief="flat", cursor="hand2", pady=4, command=self.apply_form_to_selected
        )
        btn_apply.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(6, 2))

        card_edit.columnconfigure(1, weight=1)

        # ===== CỘT PHẢI: ĐIỀU KHIỂN & LOG =====
        # Card Action Buttons
        card_run = tk.LabelFrame(
            right_frame,
            text=" ⚡ ĐIỀU KHIỂN ĐĂNG NHẬP ",
            font=("Segoe UI", 10, "bold"),
            bg=THEME["card_bg"],
            fg=THEME["accent"],
            padx=12,
            pady=8,
        )
        card_run.pack(fill="x", pady=(0, 6))

        # Nút Đăng nhập 1 client đang chọn
        self.btn_run_single = tk.Button(
            card_run,
            text="▶  ĐĂNG NHẬP CLIENT ĐANG CHỌN",
            font=("Segoe UI", 10, "bold"),
            bg=THEME["btn_start"],
            fg="#11111b",
            relief="flat",
            cursor="hand2",
            pady=8,
            command=self.start_single_login,
        )
        self.btn_run_single.pack(fill="x", pady=3)

        # Nút Đăng nhập Hàng loạt (Multi-client)
        self.btn_run_multi = tk.Button(
            card_run,
            text="🚀  ĐĂNG NHẬP TẤT CẢ CLIENT ĐÃ TÍCH CHỌN",
            font=("Segoe UI", 10, "bold"),
            bg=THEME["btn_multi"],
            fg="#11111b",
            relief="flat",
            cursor="hand2",
            pady=8,
            command=self.start_multi_login,
        )
        self.btn_run_multi.pack(fill="x", pady=3)

        # Hàng nút phụ: Dừng lại, OTP nhanh
        sub_action_bar = tk.Frame(card_run, bg=THEME["card_bg"])
        sub_action_bar.pack(fill="x", pady=3)

        self.btn_stop = tk.Button(
            sub_action_bar,
            text="⏹ DỪNG LẠI (ABORT)",
            font=("Segoe UI", 9, "bold"),
            bg=THEME["btn_stop"],
            fg="#11111b",
            relief="flat",
            cursor="hand2",
            pady=5,
            state="disabled",
            command=self.stop_execution,
        )
        self.btn_stop.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.btn_quick_otp = tk.Button(
            sub_action_bar,
            text="🔑 Dán OTP Vào PowerShell",
            font=("Segoe UI", 9),
            bg=THEME["blue"],
            fg="#11111b",
            relief="flat",
            cursor="hand2",
            pady=5,
            command=self.quick_inject_otp,
        )
        self.btn_quick_otp.pack(side="right", fill="x", expand=True, padx=(3, 0))

        # Trạng thái tiến trình
        status_card = tk.Frame(right_frame, bg=THEME["card_bg"], padx=10, pady=8)
        status_card.pack(fill="x", pady=(0, 6))

        self.lbl_status = tk.Label(
            status_card, text="Trạng thái: Sẵn sàng thực hiện", font=("Segoe UI", 9, "bold"),
            bg=THEME["card_bg"], fg=THEME["accent"], anchor="w"
        )
        self.lbl_status.pack(fill="x", pady=(0, 4))

        self.progress_bar = ttk.Progressbar(status_card, mode="determinate", maximum=11)
        self.progress_bar.pack(fill="x")

        # Khung Nhật ký (Log)
        card_log = tk.LabelFrame(
            right_frame,
            text=" 📋 NHẬT KÝ HOẠT ĐỘNG (LOG) ",
            font=("Segoe UI", 10, "bold"),
            bg=THEME["card_bg"],
            fg=THEME["accent"],
            padx=8,
            pady=8,
        )
        card_log.pack(fill="both", expand=True)

        self.txt_log = tk.Text(
            card_log, bg=THEME["log_bg"], fg=THEME["log_fg"], insertbackground=THEME["fg"],
            font=("Consolas", 9), wrap="word", relief="flat", padx=8, pady=8
        )
        log_scroll = ttk.Scrollbar(card_log, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=log_scroll.set)

        self.txt_log.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        self.txt_log.tag_configure("info", foreground=THEME["fg"])
        self.txt_log.tag_configure("success", foreground=THEME["green"])
        self.txt_log.tag_configure("warning", foreground=THEME["yellow"])
        self.txt_log.tag_configure("error", foreground=THEME["red"])
        self.txt_log.tag_configure("accent", foreground=THEME["accent"])

        btn_clear = tk.Button(
            right_frame, text="🗑️ Xóa Log", font=("Segoe UI", 8), bg=THEME["card_bg"], fg=THEME["fg_dim"],
            relief="flat", cursor="hand2", command=lambda: self.txt_log.delete("1.0", tk.END)
        )
        btn_clear.pack(anchor="e", pady=(2, 0))

    def apply_theme(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background=THEME["table_bg"], foreground=THEME["table_fg"], fieldbackground=THEME["table_bg"], rowheight=24)
        style.map("Treeview", background=[("selected", THEME["table_select"])])
        style.configure("Treeview.Heading", background=THEME["card_bg"], foreground=THEME["accent"], font=("Segoe UI", 9, "bold"))
        style.configure("TProgressbar", thickness=8, troughcolor=THEME["log_bg"], background=THEME["accent"])

    def refresh_table(self):
        """Làm mới dữ liệu trong Treeview."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        for client in self.clients_data:
            en_str = "✔️" if client.get("enabled", True) else "❌"
            char_str = f"NV {client.get('char_slot', 1)}"
            self.tree.insert(
                "",
                "end",
                iid=client.get("id"),
                values=(en_str, client.get("name", ""), client.get("exe", ""), client.get("user", ""), char_str, client.get("email", "")),
            )

        # Chọn dòng đầu tiên nếu có
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.on_tree_select(None)

    def on_tree_select(self, event):
        """Khi chọn một dòng trong bảng, hiển thị chi tiết lên form."""
        selected = self.tree.selection()
        if not selected:
            return
        cid = selected[0]
        client = next((c for c in self.clients_data if c.get("id") == cid), None)
        if not client:
            return

        self.ent_name.delete(0, tk.END)
        self.ent_name.insert(0, client.get("name", ""))

        self.cbo_exe.set(client.get("exe", ""))

        self.ent_user.delete(0, tk.END)
        self.ent_user.insert(0, client.get("user", ""))

        self.ent_pass.delete(0, tk.END)
        self.ent_pass.insert(0, client.get("pass", ""))

        self.ent_email.delete(0, tk.END)
        self.ent_email.insert(0, client.get("email", ""))

        self.var_char_slot.set(int(client.get("char_slot", 1)))

    def on_tree_toggle(self, event):
        """Nhấp đúp chuột vào dòng để bật/tắt checkbox chọn."""
        self.toggle_selected_enabled()

    def toggle_selected_enabled(self):
        """Bật/tắt trạng thái enable của client đang chọn."""
        selected = self.tree.selection()
        if not selected:
            return
        cid = selected[0]
        client = next((c for c in self.clients_data if c.get("id") == cid), None)
        if client:
            client["enabled"] = not client.get("enabled", True)
            self.refresh_table()
            self.tree.selection_set(cid)

    def apply_form_to_selected(self):
        """Áp dụng các thay đổi từ form vào client đang chọn."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Chưa chọn", "Vui lòng chọn 1 Client trong bảng để cập nhật!")
            return
        cid = selected[0]
        client = next((c for c in self.clients_data if c.get("id") == cid), None)
        if client:
            client["name"] = self.ent_name.get().strip()
            client["exe"] = self.cbo_exe.get().strip()
            client["user"] = self.ent_user.get().strip()
            client["pass"] = self.ent_pass.get().strip()
            client["email"] = self.ent_email.get().strip()
            client["char_slot"] = self.var_char_slot.get()

            auto_login.save_clients_config(self.clients_data)
            self.refresh_table()
            self.tree.selection_set(cid)
            self.log(f"[✓] Đã lưu thông tin cho client: {client['name']}", "success")

    def add_new_client(self):
        """Thêm một client mới."""
        new_id = f"client_{int(time.time())}"
        new_client = {
            "id": new_id,
            "name": f"Client Mới {len(self.clients_data)+1}",
            "exe": "alogin-F03.exe",
            "user": "bgdF03",
            "pass": "111111",
            "email": "backspace.noob@gmail.com",
            "char_slot": 1,
            "enabled": True,
        }
        self.clients_data.append(new_client)
        auto_login.save_clients_config(self.clients_data)
        self.refresh_table()
        self.tree.selection_set(new_id)

    def delete_selected_client(self):
        """Xóa client đang chọn khỏi danh sách."""
        selected = self.tree.selection()
        if not selected:
            return
        cid = selected[0]
        self.clients_data = [c for c in self.clients_data if c.get("id") != cid]
        auto_login.save_clients_config(self.clients_data)
        self.refresh_table()

    def save_all_clients(self):
        """Lưu toàn bộ danh sách client vào file json."""
        auto_login.save_clients_config(self.clients_data)
        messagebox.showinfo("Thành công", "Đã lưu cấu hình clients_config.json thành công!")

    def log(self, text, tag="info"):
        """Ghi log vào ô text."""
        timestamp = time.strftime("[%H:%M:%S] ")
        self.txt_log.insert(tk.END, timestamp + text + "\n", tag)
        self.txt_log.see(tk.END)

    def set_running_ui(self, running: bool):
        self.is_running = running
        if running:
            self.btn_run_single.config(state="disabled")
            self.btn_run_multi.config(state="disabled")
            self.btn_quick_otp.config(state="disabled")
            self.btn_stop.config(state="normal")
        else:
            self.btn_run_single.config(state="normal")
            self.btn_run_multi.config(state="normal")
            self.btn_quick_otp.config(state="normal")
            self.btn_stop.config(state="disabled")
            self.lbl_status.config(text="Trạng thái: Sẵn sàng thực hiện")

    def update_step_status(self, step_num: int, message: str):
        self.progress_bar["value"] = step_num
        self.lbl_status.config(text=f"Bước {step_num}/11: {message}")

    def make_logger(self):
        def ui_logger(msg):
            tag = "info"
            if "✓" in msg or "🎉" in msg or "THÀNH CÔNG" in msg:
                tag = "success"
            elif "!" in msg or "LỖI" in msg:
                tag = "error"
            elif "BƯỚC" in msg:
                tag = "accent"
                for i in range(1, 12):
                    if f"BƯỚC {i}/11" in msg:
                        self.after(0, self.update_step_status, i, msg.split("]")[-1].strip())
                        break
            elif "⏱️" in msg or "[-]" in msg:
                tag = "warning"
            self.after(0, self.log, msg, tag)
        return ui_logger

    def start_single_login(self):
        """Khởi động đăng nhập 1 client đang được chọn."""
        if self.is_running:
            return
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Chưa chọn", "Vui lòng chọn 1 Client trong bảng!")
            return
        cid = selected[0]
        client = next((c for c in self.clients_data if c.get("id") == cid), None)
        if not client:
            return

        self.abort_requested = False
        self.set_running_ui(True)
        self.progress_bar["value"] = 0

        def runner():
            try:
                auto_login.run_single_client_login(
                    client_name=client.get("name", cid),
                    exe_name=client.get("exe", "alogin-F03.exe"),
                    username=client.get("user", "bgdF03"),
                    password=client.get("pass", "111111"),
                    email_target=client.get("email", "backspace.noob@gmail.com"),
                    char_slot=int(client.get("char_slot", 1)),
                    log_fn=self.make_logger(),
                    cancel_check=lambda: self.abort_requested,
                )
            except Exception as e:
                self.after(0, self.log, f"[!] Ngoại lệ: {e}", "error")
            finally:
                self.after(0, lambda: self.set_running_ui(False))

        self.worker_thread = threading.Thread(target=runner, daemon=True)
        self.worker_thread.start()

    def start_multi_login(self):
        """Khởi động đăng nhập tất cả các client đã bật."""
        if self.is_running:
            return
        enabled_clients = [c for c in self.clients_data if c.get("enabled", True)]
        if not enabled_clients:
            messagebox.showwarning("Chưa chọn", "Không có Client nào được bật (✔️) trong bảng!")
            return

        self.abort_requested = False
        self.set_running_ui(True)
        self.progress_bar["value"] = 0

        def runner():
            try:
                auto_login.run_multi_client_logins(
                    clients_to_run=enabled_clients,
                    log_fn=self.make_logger(),
                    cancel_check=lambda: self.abort_requested,
                )
            except Exception as e:
                self.after(0, self.log, f"[!] Ngoại lệ: {e}", "error")
            finally:
                self.after(0, lambda: self.set_running_ui(False))

        self.worker_thread = threading.Thread(target=runner, daemon=True)
        self.worker_thread.start()

    def stop_execution(self):
        """Dừng tiến trình khẩn cấp."""
        if self.is_running:
            self.abort_requested = True
            self.log("[!] ĐANG YÊU CẦU DỪNG TIẾN TRÌNH...", "warning")

    def quick_inject_otp(self):
        """Lấy OTP và dán nhanh vào PowerShell."""
        selected = self.tree.selection()
        email = "backspace.noob@gmail.com"
        if selected:
            cid = selected[0]
            client = next((c for c in self.clients_data if c.get("id") == cid), None)
            if client:
                email = client.get("email", email)

        self.set_running_ui(True)

        def runner():
            try:
                self.after(0, self.log, f"[*] Lấy OTP cho {email} và dán vào PowerShell...", "accent")
                otp = auto_login.fetch_otp(
                    auto_login.DEFAULT_ACCOUNTS_PATH,
                    email,
                    auto_login.DEFAULT_AUTO_LOGIN_DIR,
                    log_fn=lambda m: self.after(0, self.log, m, "info"),
                )
                if otp:
                    auto_login.pyperclip.copy(otp)
                    self.after(0, self.log, f"[✓] Đã lấy OTP: {otp}. Đang tìm hộp thoại...", "success")
                    dialogs = auto_login.find_powershell_verify_dialog()
                    if dialogs:
                        hwnd = dialogs[0][0]
                        auto_login.force_foreground_window(hwnd)
                        time.sleep(0.5)
                        auto_login.pyautogui.hotkey("ctrl", "a")
                        time.sleep(0.1)
                        auto_login.pyautogui.hotkey("ctrl", "v")
                        time.sleep(0.2)
                        auto_login.pyautogui.press("enter")
                        self.after(0, self.log, "[🎉] Đã dán OTP và nhấn Enter thành công!", "success")
                    else:
                        self.after(0, self.log, "[-] Không tìm thấy hộp thoại PowerShell đang mở.", "warning")
                else:
                    self.after(0, self.log, "[-] Không lấy được mã OTP.", "error")
            except Exception as e:
                self.after(0, self.log, f"[-] Lỗi: {e}", "error")
            finally:
                self.after(0, lambda: self.set_running_ui(False))

        threading.Thread(target=runner, daemon=True).start()


if __name__ == "__main__":
    app = WloMultiClientGui()
    app.mainloop()
