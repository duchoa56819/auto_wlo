#Requires AutoHotkey v2.0
CoordMode "Mouse", "Window"

; Đọc cấu hình từ file login_config.ini (nếu có)
configFile := A_ScriptDir . "\login_config.ini"
accountName := "your_account"
password := "your_password"
gamePath := "..\alogin.exe"

if FileExist(configFile) {
    accountName := IniRead(configFile, "Account", "Username", accountName)
    password := IniRead(configFile, "Account", "Password", password)
    gamePath := IniRead(configFile, "Settings", "GamePath", gamePath)
}

; Mở ứng dụng game
if FileExist(gamePath) {
    Run gamePath
} else {
    MsgBox "Không tìm thấy file alogin.exe tại:`n" . gamePath . "`n`nHãy cấu hình đúng đường dẫn game trong file login_config.ini!", "Lỗi GamePath", 16
    ExitApp
}

Sleep 2000 ; Đợi ứng dụng mở lên (có thể tăng thời gian nếu máy chậm)

; Nhấn 2 lần Enter qua màn hình giới thiệu
Send "{Enter}"
Sleep 1500
Send "{Enter}"
Sleep 3500

; Click trái chọn server / cụm máy chủ (Window: 330, 243)
Click 330, 243
Sleep 500

; Click trái chọn kênh (Window: 471, 240)
Click 471, 240
Sleep 500

; Click trái ô tài khoản (Window: 355, 476)
Click 355, 476
Sleep 500

; Gõ account (từ biến)
Send accountName
Sleep 200

; Bấm tab sang ô mật khẩu
Send "{Tab}"
Sleep 200

; Gõ password (từ biến)
Send password
Sleep 200

; Bấm enter để đăng nhập
Send "{Enter}"
Sleep 500

; Click xác nhận đăng nhập (Window: 726, 417)
Click 726, 417
