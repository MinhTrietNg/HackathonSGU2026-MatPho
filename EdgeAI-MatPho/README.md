# TRI THỨC TOÀN DIỆN KHỐI EDGE AI (`EdgeAI-MatPho`)
## SINGLE SOURCE OF TRUTH CHO CLOUD BACKEND, FRONTEND APP & TEAM AI

> **Vị trí tài liệu**: `EdgeAI-MatPho/README.md` (Đồng bộ 100% với `docs/EDGE_AI_KNOWLEDGE_BASE.md`)  
> **Mục đích**: Đây là **Bản Tri Thức Chuẩn Hóa Duy Nhất (Single Source of Truth)** của toàn bộ khối `EdgeAI-MatPho`.  
> Bất kỳ Agent hoặc Developer nào làm việc ở **Cloud Backend (`backend/`)**, **Flutter App (`frontend/`)**, hoặc **Team AI Model (`ai_service/`)** chỉ cần đọc file này là nắm được **100% kiến trúc, luồng video, cổng mạng, schema SQLite, hợp đồng API/WebSocket và chỗ gắn model AI** mà **KHÔNG CẦN đọc lại từng file code bên trong `EdgeAI-MatPho`**.

---

## 1. TỔNG QUAN KIẾN TRÚC & VAI TRÒ KHỐI EDGE (`EdgeAI-MatPho`)

Khối `EdgeAI-MatPho` là cụm dịch vụ chạy tại hiện trường (trên Mini PC / Box AI nằm trong cùng mạng LAN với các Camera IP, hoặc chạy trên Docker local khi demo Hackathon), gồm **3 dịch vụ cốt lõi**:

1. **`mediamtx` (Edge Stream Gateway - Cổng `:8554`, `:8888`, `:8889`, `:9997`)**:
   - Nhận luồng video H.264 đã chuẩn hóa tại đường dẫn `live/{cam_id}`.
   - Tự động đóng gói sang **Low-Latency HLS (`http://<edge_host>:8888/live/{cam_id}/index.m3u8`)** để phát trực tiếp lên **Mobile/Web App**.
   - Cung cấp đầu ra **RTSP nội bộ (`rtsp://mediamtx:8554/live/{cam_id}`)** để **Khối AI (`firewatch-ai`)** đọc frame mà không cần kết nối lại vào camera thật.
2. **`edge-backend` (Autonomous Edge Controller & PyAV Stream Worker - Cổng `:8090`)**:
   - **Động cơ Video PyAV (`DecodeManager`)**: Đọc luồng RTSP gốc từ Camera IP trong LAN (hoặc nguồn giả lập `mock/cam_test`), tự động **Zero-Copy Remux** (nếu camera là H.264) hoặc **Transcode sang H.264** (nếu camera là H.265/HEVC) và đẩy vào `rtsp://mediamtx:8554/live/{cam_id}`.
   - **LAN Camera Probe (`probe.py`)**: Thăm dò trực tiếp Camera IP trong mạng LAN (Port 554), trích xuất độ phân giải, FPS, nhận diện hãng camera (Hikvision, Dahua, Imou, Ezviz...) và chụp 1 ảnh tĩnh JPEG Base64.
   - **Cơ sở dữ liệu Nội bộ (`SQLite WAL - edge_local.db`)**: Lưu danh sách camera (`local_cameras`) để tự khởi chạy khi mất mạng Internet, và hàng đợi sự kiện cháy (`offline_events_queue`) để tự động đồng bộ bù (Store-and-Forward) khi có mạng lại.
   - **Kênh WebSocket Chủ động (`ws_client.py`)**: Kết nối chiều đi (Outbound) lên Cloud Backend (`/api/v1/internal/edge/ws`) giúp điều khiển Edge xuyên tường lửa/NAT mà không cần mở port router (Zero Inbound Ports).
3. **`firewatch-ai` (Clean AI Plug-and-Play Skeleton)**:
   - Được thiết kế dạng **Khung chờ tối giản (1 Đường Input RTSP $\to$ Khung gắn Model trống $\to$ 1 Đường Output Webhook)** để Team AI độc lập gắn trọng số (`best.pt`) và thuật toán nhận diện mà không ảnh hưởng tới luồng stream video của App.

---

## 2. SƠ ĐỒ LUỒNG ĐI CỦA VIDEO & DỮ LIỆU (END-TO-END FLOW)

```mermaid
flowchart LR
    subgraph LAN ["Mạng LAN Hiện Trường / Docker Edge"]
        CAM["Camera IP Thực Tế\nhoặc scripts/mock_camera.py\n(rtsp://.../mock/cam_test)"]
        EB["edge-backend (:8090)\nPyAV Stream Worker\n+ SQLite WAL + LAN Probe"]
        MTX["MediaMTX Gateway\nPath chuẩn: live/{cam_id}"]
        AI["firewatch-ai (Skeleton)\n1 Input RTSP -> Model Slot -> 1 Output"]
    end

    subgraph CLOUD ["Cloud Backend & App"]
        BE["Cloud Backend FastAPI (:8000)\n/api/v1/internal/edge/ws\n/api/v1/internal/ai/fire-events"]
        APP["Mobile / Web App (Flutter)\nXem HLS Trực Tiếp"]
    end

    CAM -->|"1. RTSP Gốc (H.264/H.265)"| EB
    EB -->|"2. Publish H.264 chuẩn\nrtsp://mediamtx:8554/live/{cam_id}"| MTX
    MTX -->|"3a. Nhánh HLS lên App (:8888)\n/live/{cam_id}/index.m3u8"| APP
    MTX -->|"3b. Đường Input RTSP (:8554)\nrtsp://mediamtx:8554/live/{cam_id}"| AI
    AI -->|"4. Đường Output Webhook\nPOST /api/v1/internal/ai/fire-events"| BE
    EB <-->|"5. Outbound WebSocket\nSYNC_CAMERA / PROBE / HEARTBEAT"| BE
```

### 🛡️ Chốt chặn chống lỗi "Tự đọc chính mình" (Anti Self-Loopback)
- Trong `edge_backend/src/config.py` và `edge_backend/src/main.py`:
  - `source_path_template = "source/{cam_id}"`
  - `app_path_template = "live/{cam_id}"` (Đầu ra chính cho cả HLS App & RTSP AI)
  - `ai_path_template = "ai/{cam_id}"` (Chỉ dùng khi bật `ENABLE_AI_BRANCH=true`)
- Nếu một lệnh `SYNC_CAMERA` truyền nhầm `rtsp_url` trùng với đường dẫn đích `rtsp://mediamtx:8554/live/{cam_id}` hoặc chứa từ khóa `mock-camera` / `test-valid`, hàm `resolve_safe_source_url()` sẽ tự động chuyển hướng nguồn đọc về `rtsp://mediamtx:8554/mock/cam_test` để không bao giờ gây lỗi đụng độ Publisher trên MediaMTX.

---

## 3. BẢN ĐỒ CẤU TRÚC THƯ MỤC & CHỨC NĂNG TỪNG FILE

```text
EdgeAI-MatPho/
├── docker-compose.yml              # Khởi chạy toàn bộ 3 container: mediamtx, edge-backend, firewatch-ai
├── .env.example                    # Danh mục đầy đủ biến môi trường mẫu
├── README.md                       # Bản sao tri thức toàn diện của khối EdgeAI
├── mediamtx/
│   └── mediamtx.yml                # Cấu hình RTSP (:8554), Low-Latency HLS (:8888), WebRTC (:8889), API (:9997)
├── scripts/
│   └── mock_camera.py              # Script PyAV tạo luồng video H.264 giả lập đẩy vào rtsp://localhost:8554/mock/cam_test
├── edge_backend/                   # [DỊCH VỤ 2] Bộ điều khiển Edge & Động cơ xử lý luồng PyAV (Port 8090)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── src/
│   │   ├── main.py                 # FastAPI Gateway nội bộ (:8090), Lifespan, REST APIs & xử lý lệnh Cloud WS
│   │   ├── config.py               # DecoderSettings, StreamSpec, ẩn mật khẩu RTSP (redact_url) & chống Loopback
│   │   ├── db.py                   # SQLite WAL Manager: bảng local_cameras & offline_events_queue
│   │   ├── probe.py                # CameraProbeService: thăm dò RTSP LAN, đo FPS/Resolution, chụp ảnh Base64
│   │   ├── ws_client.py            # OutboundCloudWSClient: giữ kết nối WS lên Cloud & xả hàng đợi Offline
│   │   ├── manager.py              # DecodeManager: quản lý vòng đời đa luồng các phiên DecodeSession
│   │   ├── session.py              # DecodeSession: giám sát từng camera, tự động kết nối lại với ExponentialBackoff
│   │   ├── pipeline.py             # Vòng lặp demux/decode PyAV, chờ I-Frame (Keyframe), chia nhánh Live/AI
│   │   ├── branches.py             # CopyLiveBranch (H.264 zero-copy), TranscodeLiveBranch (H.265->H.264), AiBranch
│   │   ├── sinks.py                # CopySink & H264Sink: đóng gói muxer RTSP/MKV với chuẩn 90kHz clock
│   │   ├── endpoints.py            # Mở kết nối PyAV RTSP với timeout cấp C-socket (open_timeout_s, read_timeout_s)
│   │   ├── sampler.py              # FrameRateSampler: lấy mẫu khung hình theo đồng hồ PTS của nguồn
│   │   ├── scaling.py              # fit_even: tính kích thước thu phóng chẵn pixel cho bộ mã hóa H.264
│   │   ├── backoff.py              # ExponentialBackoff có jitter ngẫu nhiên chống bão kết nối
│   │   └── stats.py                # SessionStats & SessionState: theo dõi số gói tin, số frame, trạng thái luồng
│   └── tests/                      # 156 Unit & Media Integration Tests (100% PASS)
└── ai_service/                     # [DỊCH VỤ 3] Khung chờ AI tối giản (1 Input RTSP -> Model Slot -> 1 Output Webhook)
    ├── Dockerfile
    ├── requirements.txt
    ├── pytest.ini
    ├── weights/
    │   └── README.md               # Thư mục để Team AI bỏ file trọng số (ví dụ: best.pt)
    ├── src/
    │   ├── main.py                 # CameraAIWorker: đọc RTSP live/{cam_id} -> mask watch_area -> gọi Model -> bắn Webhook
    │   ├── inference_stub.py       # [CHỖ GẮN MODEL CỦA TEAM AI] MockFireModel / FireDetectionModelStub (đang để trống)
    │   ├── masking.py              # Hỗ trợ kép watch_area (Hình chữ nhật {left,top,width,height} & Đa giác [[x,y],...])
    │   ├── webhook_client.py       # CloudWebhookClient: bắn 3 HTTP Webhooks lên Cloud kèm X-Internal-Secret
    │   └── config.py               # AISettings: cấu hình RTSP input, FPS lấy mẫu, ngưỡng confidence, cooldown
    └── tests/                      # 7 Unit Tests kiểm thử masking kép, stub model & webhook (100% PASS)
```

---

## 4. HỢP ĐỒNG GIAO TIẾP VỚI CÁC KHỐI KHÁC (INTEGRATION CONTRACTS)

### A. Hợp đồng với **Mobile / Web App (`frontend/`)**
1. **Đường dẫn xem trực tiếp Camera (HLS Playback URL)**:
   - Định dạng chuẩn:
     ```text
     http://<EDGE_HOST>:8888/live/{cam_id}/index.m3u8
     ```
   - Ví dụ local/LAN: `http://localhost:8888/live/cam_01/index.m3u8` (hoặc qua domain tunnel `https://stream.matpho.vn/live/cam_01/index.m3u8`).
2. **Định dạng vùng quét `watch_area` (Tương thích kép 100%)**:
   - App ở màn hình **I5 / I8** gửi tọa độ vùng khoanh chuẩn hóa `[0.0, 1.0]`. Khối Edge hỗ trợ tự động **CẢ 2 ĐỊNH DẠNG**:
     - **Định dạng 1 — Hình chữ nhật (Rectangle Dict - Chuẩn của App & Cloud Backend)**:
       ```json
       {
         "left": 0.1,
         "top": 0.2,
         "width": 0.5,
         "height": 0.4
       }
       ```
     - **Định dạng 2 — Đa giác (Polygon List - Chuẩn mở rộng)**:
       ```json
       [
         [0.1, 0.2],
         [0.6, 0.2],
         [0.6, 0.6],
         [0.1, 0.6]
       ]
       ```

---

### B. Hợp đồng với **Cloud Backend (`backend/`)**

#### 1. Kênh Outbound WebSocket (`Edge` $\to$ `Cloud Backend`)
- **Endpoint trên Cloud Backend**: `ws://<CLOUD_HOST>/api/v1/internal/edge/ws?edge_id={EDGE_DEVICE_ID}&secret={INTERNAL_API_SECRET_KEY}`
- **Headers xác thực**: `x-internal-secret: <INTERNAL_API_SECRET_KEY>`, `x-edge-id: <EDGE_DEVICE_ID>`
- **Các bản tin Cloud Backend gửi xuống Edge (`Server -> Edge`)**:
  - **Đồng bộ / Thêm / Sửa Camera (`SYNC_CAMERA`)**:
    ```json
    {
      "action": "SYNC_CAMERA",
      "cam_id": "cam_01",
      "cam_name": "Camera Cổng Chính",
      "rtsp_url": "rtsp://admin:123456@192.168.1.50:554/Streaming/Channels/101",
      "watch_area": {"left": 0.1, "top": 0.2, "width": 0.5, "height": 0.4},
      "is_active": true
    }
    ```
  - **Xóa Camera (`REMOVE_CAMERA`)**:
    ```json
    {
      "action": "REMOVE_CAMERA",
      "cam_id": "cam_01"
    }
    ```
  - **Thăm dò Camera trong LAN (`PROBE_CAMERA`)**:
    ```json
    {
      "action": "PROBE_CAMERA",
      "request_id": "req_123",
      "rtsp_url": "rtsp://admin:123456@192.168.1.50:554/Streaming/Channels/101"
    }
    ```
- **Các bản tin Edge phản hồi lên Cloud Backend (`Edge -> Server`)**:
  - `CAMERA_STATUS`:
    ```json
    {
      "type": "CAMERA_STATUS",
      "cam_id": "cam_01",
      "status": "ONLINE",
      "hls_stream_url": "http://localhost:8888/live/cam_01/index.m3u8",
      "rtsp_output_url": "rtsp://mediamtx:8554/live/cam_01"
    }
    ```
  - `EDGE_HEARTBEAT` (định kỳ mỗi 10s):
    ```json
    {
      "type": "EDGE_HEARTBEAT",
      "edge_device_id": "edg_local_01",
      "active_streams": 2,
      "timestamp": 1730000000.0
    }
    ```
  - `PROBE_RESULT`: Trả về kết quả thăm dò camera LAN kèm ảnh `preview_snapshot_base64`.

#### 2. Các REST API Nội bộ của `edge-backend` (Cổng `:8090`)
Khi Cloud Backend và `edge-backend` chạy chung mạng local/Docker, Cloud Backend cũng có thể gọi trực tiếp HTTP sang `http://localhost:8090`:
- `GET /health` hoặc `GET /api/v1/edge/health`: Kiểm tra trạng thái sống và số luồng đang chạy.
- `GET /api/v1/status`: Xem thống kê chi tiết từng phiên giải mã PyAV (`packets_in`, `frames_decoded`, `live_packets_out`, `restarts`, `state`).
- `POST /api/v1/edge/probe`: Thăm dò RTSP camera trong LAN (`{"rtsp_url": "rtsp://..."}`).
- `GET /api/v1/edge/cameras`: Lấy danh sách camera trong SQLite kèm `hls_stream_url` và `rtsp_output_url`.
- `POST /api/v1/edge/cameras`: Thêm/cập nhật camera và khởi chạy luồng RTSP $\to$ HLS ngay lập tức.
- `DELETE /api/v1/edge/cameras/{cam_id}`: Dừng luồng và xóa camera khỏi SQLite.
- `POST /api/v1/auth/stream-ticket`: Hook xác thực vé xem luồng cho MediaMTX.
- `POST /api/v1/edge/offline-events`: Lưu sự kiện báo cháy vào hàng đợi SQLite khi đứt cáp WAN.

#### 3. Các HTTP Webhooks từ `firewatch-ai` gửi lên Cloud Backend
Tất cả request đều đính kèm Header: `X-Internal-Secret: <INTERNAL_API_SECRET_KEY>`.
1. **Báo cháy chính thức (`POST /api/v1/internal/ai/fire-events`)**:
   ```json
   {
     "cam_id": "cam_01",
     "class_name": "fire",
     "confidence": 0.92,
     "timestamp": 1730000000.123,
     "bbox": [120.0, 80.0, 340.0, 290.0],
     "image_base64": "/9j/4AAQSkZJRgABAQAAAQABAAD..."
   }
   ```
2. **Đang xác minh nghi vấn - Viền vàng E2 (`POST /api/v1/internal/ai/verifying`)**:
   ```json
   {
     "cam_id": "cam_01",
     "sign": "fire",
     "confidence": 0.65,
     "message": "Đang xác minh tín hiệu nghi vấn...",
     "steps": [{"kind": "DETECTED", "name": "Phát hiện dấu hiệu nghi vấn", "at": 1730000000.0}]
   }
   ```
3. **Báo giả / Hạ cờ báo động - Toast E4 (`POST /api/v1/internal/ai/suppressed`)**:
   ```json
   {
     "cam_id": "cam_01",
     "alert_id": null,
     "summary": "Không phải cháy",
     "detail": "AI kết luận: Ánh đèn phản chiếu hoặc vật thể bình thường."
   }
   ```

---

### C. Hợp đồng với **Team AI (`EdgeAI-MatPho/ai_service/`)**

Khối `ai_service` đã được chuẩn bị sẵn **1 Đường Input RTSP** và **1 Đường Output Webhook**. Khi Team AI tích hợp model, **chỉ cần chỉnh sửa duy nhất file `EdgeAI-MatPho/ai_service/src/inference_stub.py`**:

1. **Đường Input đã có sẵn (`main.py`)**:
   - Tự động mở luồng `rtsp://mediamtx:8554/live/{cam_id}` qua TCP.
   - Tự động cắt/tô đen vùng ngoài `watch_area` bằng `apply_watch_area_mask(frame, watch_area)`.
   - Truyền `masked_frame` (ảnh `np.ndarray` định dạng BGR của OpenCV) vào hàm `model.predict(masked_frame, conf_threshold)`.
2. **Chỗ gắn Model (`ai_service/src/inference_stub.py`)**:
   - Bỏ file trọng số (ví dụ `best.pt`) vào thư mục `EdgeAI-MatPho/ai_service/weights/`.
   - Trong `MockFireModel.__init__()`: Load model (YOLO / ONNX / PyTorch).
   - Trong `MockFireModel.predict(frame, conf_threshold)`: Trả về danh sách `List[DetectionResult]`:
     ```python
     DetectionResult(
         class_name="fire",                 # "fire" hoặc "smoke"
         confidence=0.88,                   # float từ 0.0 -> 1.0
         bbox=[120.0, 80.0, 340.0, 290.0],  # [x1, y1, x2, y2]
     )
     ```
3. **Đường Output đã có sẵn (`main.py` + `webhook_client.py`)**:
   - Ngay khi `predict()` trả về danh sách khác rỗng, `CameraAIWorker` tự động nén frame gốc sang JPEG Base64 và gọi `CloudWebhookClient.report_fire_event()` đẩy thẳng lên Cloud Backend (kèm cơ chế chống spam theo `alert_cooldown_seconds`).

---

## 5. THIẾT KẾ CƠ SỞ DỮ LIỆU NỘI BỘ SQLITE WAL (`edge_local.db`)

File DB nằm tại `EdgeAI-MatPho/edge_backend/data/edge_local.db` (hoặc `/app/data/edge_local.db` trong Docker), bật chế độ `PRAGMA journal_mode=WAL;` gồm 2 bảng:

1. **Bảng `local_cameras`**:
   | Cột | Kiểu | Mô tả |
   | :--- | :--- | :--- |
   | `cam_id` | `TEXT PRIMARY KEY` | Mã định danh camera (`cam_01`, ...) |
   | `cam_name` | `TEXT NOT NULL` | Tên hiển thị của camera |
   | `rtsp_url` | `TEXT NOT NULL` | Đường dẫn RTSP gốc trong mạng LAN |
   | `watch_area_json` | `TEXT` | Chuỗi JSON lưu Rectangle Dict hoặc Polygon List |
   | `is_active` | `INTEGER NOT NULL` | `1` (Đang chạy stream) hoặc `0` (Tạm dừng) |
   | `updated_at` | `REAL NOT NULL` | Epoch timestamp lần cập nhật cuối |

2. **Bảng `offline_events_queue` (Store-and-Forward khi mất mạng WAN)**:
   | Cột | Kiểu | Mô tả |
   | :--- | :--- | :--- |
   | `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Khóa chính tự tăng (FIFO) |
   | `cam_id` | `TEXT NOT NULL` | Mã camera phát hiện cháy |
   | `event_type` | `TEXT NOT NULL` | Loại sự kiện (`FIRE_DETECTED`) |
   | `payload_json` | `TEXT NOT NULL` | Toàn bộ JSON payload báo cháy kèm ảnh Base64 |
   | `created_at` | `REAL NOT NULL` | Thời điểm phát hiện cháy tại hiện trường |
   | `retry_count` | `INTEGER NOT NULL` | Số lần thử gửi lại |

---

## 6. BẢNG CỔNG MẠNG (PORTS) & LỆNH KHỞI CHẠY NHANH

| Dịch vụ | Cổng (Port) | Giao thức | Mục đích sử dụng |
| :--- | :---: | :---: | :--- |
| **`mediamtx`** | `8554` | RTSP (TCP/UDP) | Nhận luồng publish từ `edge-backend` & cung cấp RTSP input cho `firewatch-ai` |
| **`mediamtx`** | `8888` | HTTP (HLS) | Phát video trực tiếp lên App: `http://localhost:8888/live/{cam_id}/index.m3u8` |
| **`mediamtx`** | `8889` | HTTP (WebRTC) | Phát WebRTC WHEP độ trễ cực thấp |
| **`mediamtx`** | `9997` | HTTP REST | MediaMTX Control API nội bộ |
| **`edge-backend`** | `8090` | HTTP REST | Cổng điều khiển Edge Backend, LAN Probe, Quản lý Camera & Healthcheck |

### 🚀 Lệnh Khởi Chạy & Kiểm Thử Nhanh

1. **Chạy bằng Docker Compose**:
   ```bash
   cd EdgeAI-MatPho
   cp .env.example .env
   docker compose up -d --build
   ```
2. **Bơm luồng Camera Giả lập (khi không có Camera IP thật)**:
   ```bash
   python EdgeAI-MatPho/scripts/mock_camera.py --url rtsp://localhost:8554/mock/cam_test
   ```
   $\rightarrow$ Xem ngay luồng HLS trên trình duyệt hoặc App tại: `http://localhost:8888/live/cam_01/index.m3u8`
3. **Chạy Bộ Kiểm Thử Tự Động (163 Unit & Media Tests)**:
   ```powershell
   # Test Edge Backend & PyAV Stream Worker (156 tests)
   Push-Location EdgeAI-MatPho/edge_backend; pytest -q; Pop-Location

   # Test AI Service Skeleton & Watch Area Masking (7 tests)
   Push-Location EdgeAI-MatPho/ai_service; pytest -q; Pop-Location
   ```
