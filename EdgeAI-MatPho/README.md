# EdgeAI-MatPho: Khối Tính Toán Biên Tự Hành (Master Spec v4.0)

Cụm máy tính biên hiện trường (On-Premise Device / Mini PC / Box AI) cho nền tảng Giám sát Camera & Cảnh báo Cháy Khẩn cấp (Mắt Phố).
Tài liệu kiến trúc đồng bộ 100% với [`docs/EDGE_ARCHITECTURE_SPECIFICATION.md`](../docs/EDGE_ARCHITECTURE_SPECIFICATION.md) và [`docs/EDGE_PHASED_IMPLEMENTATION_PLAN.md`](../docs/EDGE_PHASED_IMPLEMENTATION_PLAN.md).

---

## 1. Lộ Trình Triển Khai 5 Phase Nhỏ

* [x] **Phase 4.1: Hạ tầng Docker & Media Gateway (MediaMTX + Mock Camera)**
  * `mediamtx/mediamtx.yml`: Quản trị RTSP Ingest (`:8554`), HLS On-demand (`:8888`), Control API (`:9997`) với chuẩn hóa `live/{cam_id}`.
  * `docker-compose.yml`: Cụm multi-container với các profile `mock`, `tunnel`, `ai`.
  * `scripts/mock_camera.py`: Sinh luồng RTSP 1080p@25fps có đồng hồ OSD đếm giây để test offline.
* [x] **Phase 4.2: Tầng Lưu Trữ SQLite Bền Vững & Hàng Đợi Ngoại Tuyến (HOÀN THÀNH)**
  * `edge_backend/src/db.py`: SQLite WAL mode, bảng `local_cameras` & bảng `offline_events_queue`.
  * `edge_backend/tests/test_db.py`: Bộ kiểm thử toàn diện SQLite và offline resilience (3/3 PASS).
* [x] **Phase 4.3: Động Cơ Stream Worker (Zero-Copy Remux & Fallback Transcode) (HOÀN THÀNH)**
  * PyAV Stream Worker: Remux H.264 (CPU < 1%), Transcode fallback khi codec khác, Auto-reconnect Backoff (`test_config.py`, `test_manager.py` 6/6 PASS).
* [x] **Phase 4.4: Edge Controller, LAN RTSP Probe & Kênh Outbound WebSocket (HOÀN THÀNH)**
  * `probe.py`: Đo đạc RTSP LAN, đoán hãng camera, chụp ảnh JPEG Base64.
  * `ws_client.py`: Duy trì kênh WebSocket 2 chiều với Cloud Backend (`SYNC_CAMERA`, `PROBE_CAMERA`).
  * `main.py`: FastAPI server Lifespan + Security hook `stream-ticket` (`test_probe.py`, `test_api.py` 7/7 PASS).
* [x] **Phase 4.5: Hộp Đen AI FireWatch & Bộ Phát Tín Hiệu Khẩn Cấp (Webhooks) (HOÀN THÀNH)**
  * AI Service: 1 FPS sampling, `watch_area` polygon masking, 3 Webhooks (`/fire-events`, `/verifying`, `/suppressed`) (`test_ai_service.py` 6/6 PASS).

---

## 2. Hướng Dẫn Khởi Chạy & Kiểm Thử Phase 4.1

### Khởi Chạy MediaMTX & Mock Camera Simulator
Khởi động container MediaMTX và camera giả lập độc lập:

```bash
cd EdgeAI-MatPho

# 1. Tạo file .env từ mẫu
cp .env.example .env

# 2. Khởi chạy MediaMTX (chạy nền)
docker compose up -d mediamtx

# 3. Chạy Mock Camera Generator (trực tiếp trên máy hoặc qua container)
python scripts/mock_camera.py --url rtsp://localhost:8554/mock/cam_test
```

### Kiểm Tra Luồng Video Bằng VLC Media Player
1. Mở phần mềm **VLC Media Player**.
2. Chọn menu `Media` ➔ `Open Network Stream...` (hoặc nhấn `Ctrl + N`).
3. Nhập URL RTSP gốc:
   ```text
   rtsp://localhost:8554/mock/cam_test
   ```
4. Hoặc nhập URL HLS xem trực tiếp theo quy ước chuẩn:
   ```text
   http://localhost:8888/live/cam_mock/index.m3u8
   ```
5. Bấm **Play**: Video camera giả lập hiển thị khung giám sát Slate Dark, đồng hồ OSD thời gian thực, bộ đếm giây tăng dần và radar chuyển động mượt mà ở 25 FPS!
