#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WLO ALL-IN-ONE: AUTO PARTY MANAGER & AUTO COMBAT ASSISTANT
===========================================================
Giao diện hợp nhất 2-trong-1 (Chạy chung 1 tiến trình Python duy nhất):
- Tab 1: 👥 Quản Lý Tổ Đội (Auto-Party Manager, Relog & Sync, Nhận diện tài khoản)
- Tab 2: ⚔️ Tự Động Chiến Đấu (Auto Combat 4 Client, Chọn mục tiêu, Ra chiêu)
-> Tiết kiệm 50% RAM & CPU, không mở thêm cửa sổ Command Prompt thừa.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox

# Đảm bảo UTF-8 trên Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

# Thêm đường dẫn thư mục hiện tại vào sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from wlo_party_gui import WLOPartyGUI, THEME as PARTY_THEME
from wlo_auto_combat_gui import WLOAutoCombatApp, THEME as COMBAT_THEME

# Bảng màu chung giao diện Dark Gaming
THEME = {
    "bg_dark": "#11111b",
    "bg_main": "#181825",
    "bg_card": "#1e1e2e",
    "bg_hover": "#313244",
    "primary": "#89b4fa",
    "green": "#a6e3a1",
    "red": "#f38ba8",
    "text_main": "#cdd6f4",
    "text_muted": "#a6adc8",
    "border": "#45475a",
}

class WLOUnifiedApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🛡️ WLO All-in-One: Quản Lý Tổ Đội & Tự Động Chiến Đấu (Party + Combat)")
        self.root.geometry("1400x920")
        self.root.minsize(1100, 750)
        self.root.configure(bg=THEME["bg_dark"])

        self.setup_notebook_style()

        # Thanh tiêu đề hợp nhất (Master Top Bar)
        self.create_top_bar()

        # Hệ thống Tab Notebook
        self.notebook = ttk.Notebook(self.root, style="Dark.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Khung Tab 1: Party
        self.tab_party = tk.Frame(self.notebook, bg=THEME["bg_main"])
        self.notebook.add(self.tab_party, text="   👥 1. QUẢN LÝ TỔ ĐỘI (PARTY)   ")

        # Khung Tab 2: Combat
        self.tab_combat = tk.Frame(self.notebook, bg=THEME["bg_main"])
        self.notebook.add(self.tab_combat, text="   ⚔️ 2. TỰ ĐỘNG CHIẾN ĐẤU (COMBAT)   ")

        # Khởi tạo 2 hệ thống con bên trong 2 Tab
        self.party_app = WLOPartyGUI(self.root, parent=self.tab_party)
        self.combat_app = WLOAutoCombatApp(self.root, parent=self.tab_combat)

    def setup_notebook_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        style.configure("Dark.TNotebook",
                        background=THEME["bg_dark"],
                        borderwidth=0)
        style.configure("Dark.TNotebook.Tab",
                        background=THEME["bg_card"],
                        foreground=THEME["text_muted"],
                        font=("Segoe UI", 10, "bold"),
                        padding=[20, 9],
                        borderwidth=0)
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", THEME["primary"]), ("active", THEME["bg_hover"])],
                  foreground=[("selected", "#11111b"), ("active", "#ffffff")])

    def create_top_bar(self):
        bar = tk.Frame(self.root, bg=THEME["bg_dark"], height=38, padx=12, pady=4)
        bar.pack(fill="x", side="top")

        lbl_logo = tk.Label(bar, text="🛡️ WLO ALL-IN-ONE ASSISTANT", font=("Segoe UI", 11, "bold"),
                            bg=THEME["bg_dark"], fg=THEME["primary"])
        lbl_logo.pack(side="left")

        lbl_info = tk.Label(bar, text="|  Tiến trình hợp nhất (1 Process Duy Nhất) - Tiết kiệm RAM & CPU",
                            font=("Segoe UI", 9), bg=THEME["bg_dark"], fg=THEME["text_muted"])
        lbl_info.pack(side="left", padx=8)

        # Trạng thái tổng quan góc phải
        lbl_mode = tk.Label(bar, text="● Sẵn sàng", font=("Segoe UI", 9, "bold"),
                            bg=THEME["bg_dark"], fg=THEME["green"])
        lbl_mode.pack(side="right", padx=10)

        # Nút Dọn Rác nhanh trên thanh tiêu đề
        btn_top_sweep = tk.Button(bar, text="🧹 DỌN RÁC TÚI ĐỒ (ALL ACC)", font=("Segoe UI", 9, "bold"),
                                  bg=THEME["red"], fg="#ffffff", activebackground="#f87171",
                                  relief="flat", padx=12, pady=2, cursor="hand2",
                                  command=self.trigger_sweep_trash_all)
        btn_top_sweep.pack(side="right", padx=(0, 10))

    def trigger_sweep_trash_all(self):
        if hasattr(self, "party_app") and hasattr(self.party_app, "action_sweep_trash_all"):
            self.party_app.action_sweep_trash_all()

    def on_closing(self):
        try:
            if hasattr(self.party_app, "stop_all_nodes"):
                self.party_app.stop_all_nodes()
        except Exception:
            pass
        try:
            if hasattr(self.combat_app, "stop_all"):
                self.combat_app.stop_all()
        except Exception:
            pass
        self.root.destroy()

def main():
    root = tk.Tk()
    app = WLOUnifiedApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
