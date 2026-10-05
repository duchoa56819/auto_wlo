#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate comprehensive Sky Tower 27 floors report
"""
import json
import sys

with open("tower_29_compiled_stages.json", "r", encoding="utf-8") as f:
    stages = json.load(f)

lines = []
lines.append("# BÁO CÁO PHÂN TÍCH DIỄN BIẾN & PHẦN THƯỞNG THÁP 29 TẦNG (SKY TOWER)")
lines.append("")
lines.append("## 1. TỔNG QUAN PHIÊN LEO THÁP")
lines.append("")
lines.append("- **Thời gian diễn ra**: `16:13:55` -> `16:40:05` (~26.2 phút).")
lines.append("- **Tổng số tầng tham chiến**: 27 tầng.")
lines.append("- **Kết quả**: **Vượt qua thành công 26 tầng (Tầng 01 đến 26)**, dừng bước tại **Tầng 27**.")
lines.append("- **Đội hình tham gia**: 4 tài khoản")
lines.append("  1. `alogin-W04.exe` (W04 - Trưởng nhóm)")
lines.append("  2. `alogin-W03.exe` (W03 - Hỗ trợ / Tấn công tầng cao)")
lines.append("  3. `alogin-F04.exe` (F04 - Sát thương Hỏa chủ lực gánh team)")
lines.append("  4. `alogin-Wi01.exe` (Wi01 - Phòng thủ / Sát thương hỗ trợ tầng cao)")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## 2. BẢNG TỔNG HỢP CHI TIẾT 27 TẦNG (THỜI GIAN, SỐ HIỆP, PHẦN THƯỞNG)")
lines.append("")
lines.append("| Tầng | Bắt đầu | Thời gian | Số hiệp | Kết quả | Danh sách Mã Phần thưởng nhận được (Hex & Dec) |")
lines.append("|:---:|:---:|:---:|:---:|:---:|:---|")

for s in stages:
    num = s["num"]
    st = s["start"]
    dur = s["dur"]
    rnd = s["rounds"]
    is_win = (num < 27)
    res_str = "Thắng" if is_win else "Thua"
    
    r_items = s.get("rewards", [])
    if r_items:
        r_str = ", ".join([f"Mã `0x{r['hex']}` (`{r['id']}`) x{r['qty']}" for r in r_items])
    else:
        r_str = "*(Không có item)*" if is_win else "*(Thất bại - Không có)*"
        
    lines.append(f"| **Tầng {num:02d}** | `{st}` | `{dur:.1f}s` | {rnd:2d} hiệp | {res_str} | {r_str} |")

lines.append("")
lines.append("---")
lines.append("")
lines.append("## 3. PHÂN TÍCH CHIẾN THUẬT & DIỄN BIẾN TỪNG GIAI ĐOẠN")
lines.append("")
lines.append("### Giai đoạn 1: Tầng 01 -> Tầng 21 (Chiến thuật Solo Carry bằng F04)")
lines.append("- **Đặc điểm**: Quái ở mức độ vừa phải.")
lines.append("- **Hành động của team**:")
lines.append("  * **`W04`, `W03`, `Wi01` (cả Người & Pet)**: **100% duy trì Phòng thủ (`75ea`)** ở tất cả các hiệp để giữ trọn vẹn HP/SP và không tốn thời gian ra chiêu thừa.")
lines.append("  * **`F04` (Sát thương Hỏa)**: Một mình F04 (Char dùng chiêu Hỏa `1f3b`, Pet dùng chiêu `043b`) gánh toàn bộ sát thương, quét sạch 21 tầng liên tiếp chỉ mất từ 12s đến 33s mỗi tầng.")
lines.append("")
lines.append("### Giai đoạn 2: Tầng 22 -> Tầng 26 (Tổng lực tấn công - All-Out Attack)")
lines.append("- **Đặc điểm**: Từ tầng 22, quái bắt đầu rất trâu máu, kháng cao và sát thương lớn, một mình F04 không thể dứt điểm nhanh.")
lines.append("- **Chuyển đổi chiến thuật**:")
lines.append("  * Cả 4 tài khoản đồng loạt bỏ phòng thủ, chuyển sang tấn công tổng lực:")
lines.append("    - **`W04`**: Char tung chiêu `fb2a`, Pet tung chiêu `092f`.")
lines.append("    - **`W03`**: Char tung chiêu `fb2a`, Pet tung chiêu `092f` (có lượt hỗ trợ `232b`).")
lines.append("    - **`Wi01`**: Char tung chiêu Phong `2b2b`, Pet tung chiêu `2c2b`.")
lines.append("    - **`F04`**: Char duy trì Hỏa `1f3b`, Pet kết hợp các chiêu `043b`, `332b`, `553b`.")
lines.append("  * **Điểm nhấn Tầng 26**: Đây là trận chiến căng thẳng nhất phiên đánh, kéo dài tới **223.1 giây (~3.7 phút)** qua **12 hiệp đấu** dồn dame liên tục mới quét sạch toàn bộ quái để giành chiến thắng.")
lines.append("")
lines.append("### Giai đoạn 3: Tầng 27 (Thất bại)")
lines.append("- **Thời gian diễn ra**: `16:35:26` -> `16:36:19` (kéo dài 52.5 giây, qua 4 hiệp).")
lines.append("- **Nguyên nhân vỡ trận**:")
lines.append("  * Đội hình quái ở tầng 27 có Agi cao và lượng sát thương diện rộng cực lớn.")
lines.append("  * **Thứ tự các thành viên ngã xuống**:")
lines.append("    - **Hiệp 3 (16:39:03)**: `W04` (cả Char `Slot 3 Row 4` và Pet `Slot 4 Row 4`) bị dồn sát thương tử trận đầu tiên.")
lines.append("    - **Hiệp 4 (16:40:05)**: Pet của `F04` (`Slot 4 Row 2`) và Pet của `W03` (`Slot 4 Row 3`) tiếp tục bị hạ gục.")
lines.append("  * Sau khi mất đi nguồn hồi phục/hỗ trợ và dàn tanker, đội hình còn lại không thể trụ vững trước lượng sát thương của quái và chấp nhận dừng bước tại tầng 27.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## 4. TỔNG KẾT VẬT PHẨM THU HOẠCH ĐƯỢC SAU 26 TẦNG")
lines.append("")
lines.append("| STT | Mã Vật phẩm (Hex) | Mã Vật phẩm (Dec) | Tổng số lượng nhận được |")
lines.append("|:---:|:---:|:---:|:---:|")

# Aggregate total reward items across all 26 floors
totals = {}
for s in stages:
    for r in s.get("rewards", []):
        k = (r["hex"], r["id"])
        totals[k] = totals.get(k, 0) + r["qty"]

for idx, ((hx, d_id), q) in enumerate(sorted(totals.items(), key=lambda x: x[0][1]), 1):
    lines.append(f"| {idx:02d} | `0x{hx}` | `{d_id}` | **x{q}** |")

lines.append("")

with open("tower_29_analysis_report.md", "w", encoding="utf-8") as f_out:
    f_out.write("\n".join(lines))

print("Successfully generated tower_29_analysis_report.md")
