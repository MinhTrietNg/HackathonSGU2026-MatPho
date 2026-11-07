# 🎥 Mắt Phố - RTSP Virtual Camera Fleet Studio

Ứng dụng Python GUI chuyên dụng cho phép **mô phỏng đồng thời hàng loạt camera IP vật lý** từ các tệp video (`.mp4`, `.avi`, `.mkv`, `.mov`) trên máy tính cục bộ và phát trực tiếp dưới dạng chuẩn luồng RTSP (H.264/RTSP) vào MediaMTX / Edge Backend.

---

## 🌟 Tính Năng Nổi Bật

1. **Phát Hàng Loạt Camera Độc Lập**:
   - Mỗi file video tương ứng với một camera RTSP riêng biệt (VD: `rtsp://localhost:8554/source/cam_01`, `rtsp://localhost:8554/source/cam_02`,...).
   - Hỗ trợ thêm từng video hoặc quét tự động cả một thư mục video.
2. **Điều Khiển Thời Gian Thực (Interactive Real-Time Controls)**:
   - **Tua thời gian (Seek Slider)**: Kéo thanh tua để nhảy tới bất kỳ thời điểm nào trong video ngay lập tức.
   - **Điều chỉnh tốc độ (Speed Multiplier)**: Chọn các mốc tốc độ `0.25x`, `0.5x`, `1.0x` (chuẩn), `2.0x`, `4.0x`.
   - **Tạm dừng thông minh (Zero-Drop Pause)**: Khi bấm Pause, luồng RTSP không bị ngắt kết nối socket mà gửi frame freeze với timestamp tịnh tiến, giúp MediaMTX, AI Model và người xem trên Web/App không bị gián đoạn hay crash.
   - **Vòng lặp vô tận (Auto-Loop)**: Hết video tự động tua lại từ đầu mà không làm gián đoạn luồng stream.
   - **Đổi video nóng (Hot Swap)**: Thay thế tệp video mới ngay khi đang chạy mà không cần khởi động lại tool.
3. **Giao Diện Trực Quan (Desktop GUI)**:
   - Live Thumbnail Preview cho từng camera theo thời gian thực.
   - Nút **Copy URL** trực tiếp vào clipboard.
   - Hiển thị Timecode hiện tại / Tổng thời lượng / Tốc độ.
4. **Tích Hợp 1-Click Với Edge Backend (:8090)**:
   - Nút **"Sync Edge"** tự động gọi API `POST /api/v1/edge/cameras` để đăng ký camera vào Edge AI Backend mà không cần cấu hình thủ công.
   - Nút **"Sync All -> Edge"** đồng bộ toàn bộ danh sách camera chỉ với 1 cú click.
5. **Quản Lý Preset**:
   - Lưu trạng thái và danh sách camera ra file `.json` (`Lưu Preset`) và nạp lại khi cần (`Mở Preset`).
6. **Bộ Video Mẫu Tự Sinh (Synthetic Benchmark Videos)**:
   - Nút **"Tạo 2 Video Mẫu"** tự động vẽ và kết xuất 2 video benchmark 1080p có timecode, vạch kẻ đường giao thông và hiệu ứng mô phỏng cháy (để test còi báo cháy AI).

---

## 🏗️ Kiến Trúc Hệ Thống & Luồng Mạng

```
+-------------------------------------------------------------------------+
|                              LOCAL MACHINE                              |
|                                                                         |
|  [Video MP4/MKV]                                                        |
|         │                                                               |
|         ▼                                                               |
|  [VirtualCamWorker] (PyAV Muxer + Frame Rate Clock)                     |
|         │                                                               |
|         ▼ RTSP TCP (Port 8554)                                          |
|  [MediaMTX Server] (Đường dẫn: rtsp://localhost:8554/source/cam_xx)     |
|         ▲                                                               |
|         │ Mạng Docker Nội Bộ (rtsp://mediamtx:8554/source/cam_xx)       |
|  [Edge AI Backend + YOLO] (Port 8090)                                   |
|         │                                                               |
|         ▼                                                               |
|  [Cloudflare Tunnel / WebRTC / HLS]                                     |
+-------------------------------------------------------------------------+
```

---

## 🚀 Hướng Dẫn Khởi Chạy

### Cách 1: Chạy bằng 1 click chuột (Khuyên dùng)
- Click đúp vào file:
  - `run_rtsp_tool.bat` (Windows Command Prompt)
  - Hoặc click chuột phải chọn **Run with PowerShell** file `run_rtsp_tool.ps1`

### Cách 2: Chạy bằng dòng lệnh Terminal
```powershell
# Chuyển về thư mục gốc HackathonSGU2026-MatPho
cd D:\Project\Team_Project\NOD89\Hackathon\HackathonSGU2026-MatPho

# Thiết lập PYTHONPATH và chạy module GUI
$env:PYTHONPATH="."
& D:\Project\Team_Project\NOD89\MatPho-Draft\backend\.venv\Scripts\python.exe -m tool_test_rtsp.src.gui_app
```

---

## 🧪 Chạy Kiểm Thử Tự Động (Pytest)

Toàn bộ hệ thống được bảo chứng với bộ test tự động (Unit & Integration tests):
```powershell
$env:PYTHONPATH="."
& D:\Project\Team_Project\NOD89\MatPho-Draft\backend\.venv\Scripts\pytest.exe -v tool_test_rtsp/tests/
```
Kết quả kiểm thử: **11/11 tests PASS 100%**.
