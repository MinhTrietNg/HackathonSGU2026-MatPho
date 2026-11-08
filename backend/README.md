# Mắt Phố - Backend (Cloud Core Stack)

Thư mục chứa toàn bộ mã nguồn và cấu hình Docker phục vụ cho **Cloud Backend** của hệ thống Mắt Phố.

---

## 1. Ranh Giới Kiến Trúc (Architecture Boundary: Backend vs Edge)

Hệ thống Mắt Phố được thiết kế theo mô hình **Hybrid Cloud & Edge**:
- **Cụm Backend (Thư mục này)**:
  - **FastAPI Core Gateway**: Quản lý người dùng, nhóm, phân quyền, API đăng ký/thăm dò camera, nhận webhook báo cháy từ Edge, điều phối còi báo động khẩn cấp 2 tầng qua Firebase Cloud Messaging (FCM) & WebSocket, và điều phối cuộc gọi 114.
  - **Redis Cache**: Quản lý in-memory debounce state (khóa chống trùng lặp FCM theo sự cố) và heartbeat. Tín hiệu cháy được ghép theo luật "một camera một sự cố đang mở" (`src/services/incident_rules.py`, cửa sổ `INCIDENT_MERGE_WINDOW_S`, mặc định 900 s).
  - **MediaMTX (Cloud Stream Gateway)**: Tiếp nhận luồng HLS/WebRTC và cấp quyền chiếu xem trực tiếp cho Flutter Mobile App & Web Dashboard.
- **Cụm EdgeAI (Riêng biệt - On-premise LAN)**:
  - Chạy tại hiện trường (Mini PC / Box AI kết nối trực tiếp Camera IP qua mạng LAN nội bộ).
  - Chứa container AI FireWatch (YOLO26 + VotingEngine + Gemini VLM) và Edge Backend để xử lý tại chỗ và gửi webhook về Cloud Backend.
  - **Lưu ý**: Docker của Backend và Docker của EdgeAI là **2 hệ thống hoàn toàn độc lập**, không chạy chung compose.

---

## 2. Các Thành Phần Docker Của Backend

| Dịch vụ | Image / Dockerfile | Cổng Host:Container | Mục đích |
|---|---|---|---|
| `backend` | `./Dockerfile` (Python 3.11-slim) | `8000:8000` | REST API, WebSocket Server, Quản lý nghiệp vụ |
| `redis` | `redis:7-alpine` | `6379:6379` | Debounce Lock, Token Cache, Rate Limiting |
| `mediamtx` | `bluenviron/mediamtx:latest` | `8554` (RTSP), `8888` (HLS), `8889` (WebRTC), `9997` (API) | Gateway truyền phát video cho Mobile App & Web |

---

## 3. Khởi Động Docker Tự Động (One-Click)

Bạn có thể chạy toàn bộ cụm Backend với 1 lệnh duy nhất (script tự kiểm tra Docker daemon, tự copy `.env`, kiểm tra chứng chỉ Firebase, khởi động container và chờ kiểm tra sức khỏe API):

- **Cách 1: Windows PowerShell (Khuyến nghị)**:
  ```powershell
  .\run_docker.ps1
  ```
  *Các cờ tiện ích:*
  - Build lại image: `.\run_docker.ps1 -Build`
  - Xem logs thời gian thực: `.\run_docker.ps1 -Logs`
  - Khởi động lại: `.\run_docker.ps1 -Restart`
  - Dừng hệ thống: `.\run_docker.ps1 -Down`

- **Cách 2: Windows Double-Click (File .bat)**:
  - Nhấp đúp chuột vào file `run_docker.bat` để chạy.
  - Nhấp đúp chuột vào file `stop_docker.bat` để dừng.

- **Cách 3: Linux / macOS / Git Bash**:
  ```bash
  chmod +x run_docker.sh
  ./run_docker.sh
  ```

- **Cách 4: Sử dụng Docker Compose thủ công**:
  ```bash
  docker compose up -d
  ```

---

## 4. Kiểm Tra & Truy Cập Dịch Vụ
- **Swagger API Docs**: `http://localhost:8000/docs`
- **Healthcheck**: `http://localhost:8000/api/v1/health`
- **Redis Cache**: `localhost:6379`
- **MediaMTX Control API**: `http://localhost:9997`
- **MediaMTX HLS Playback**: `http://localhost:8888`
