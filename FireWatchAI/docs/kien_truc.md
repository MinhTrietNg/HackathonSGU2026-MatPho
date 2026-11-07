# Kiến trúc FireWatch

Viết từ mã trong `src/firewatch/` và README nguồn (`Model-Mat-Pho-` @ `afa5a70`, mục 7).
Có hai sơ đồ ngày 05/11/2026, giữ nguyên như lúc vẽ:

- `so_do/MatPho_Architecture.png`: toàn hệ thống (hiện trường, cloud backend, app).
- `so_do/MatPho_AI_Infrastructure.png`: khối FireWatch theo mô hình C4 (vận hành và MLOps).

Mục cuối của tài liệu này liệt kê những điểm đã khác so với hai sơ đồ.

## Luồng chính

```
nguồn video → [1] heartbeat → [2] detector YOLO26n → [3] voting k-of-M
            → [4] xác minh VLM → [5] event: JSON + ảnh, REST, WebSocket, webhook
                                          → console người trực → ack
```

Mỗi tầng là một module. Tầng sau chỉ nhận dữ liệu từ tầng trước, nên voting và schema
event test được mà không cần model. Ba module lõi `sources.py`, `detector.py`,
`voting.py` được đối chiếu SHA-256 với bản gốc trong `docs/nguon_goc.md` và không sửa.

## Các khối

**Nguồn và heartbeat (`sources.py`).** Đọc file, webcam hoặc RTSP và lấy mẫu một khung
mỗi `heartbeat.interval_s` **theo timestamp video**, trên lưới cố định 0, T, 2T…. Nguồn
live đọc bằng thread riêng, chỉ giữ khung mới nhất, và tự nối lại với back-off. Vòng
heartbeat giữ thêm vài khung gần nhất (`ring_buffer`) để tầng 4 chọn keyframe.

**Detector (`detector.py`).** Bọc YOLO26n của ultralytics, chạy `.pt` hoặc ONNX trên CPU.
Module này lọc lớp `fire`/`smoke`, áp ngưỡng theo lớp và đo ms mỗi lần suy luận. ONNX
được export một lần thành `models/<tên>_<imgsz>.onnx` và export lại khi file `.pt` mới
hơn. Model và cách kiểm ở `models/README.md`.

**Voting (`voting.py`).** Máy trạng thái k-of-M cho từng vùng lửa/khói (track ghép bằng
IoU). Một track lên CONFIRMED khi có `k_enter` phiếu trong `window_m` heartbeat. Mức
CRITICAL cần `k_fire` heartbeat có box lửa. Module có hai lớp cooldown (theo track và theo
cảnh), nhắc lại `STILL_BURNING` khi còn cháy, và báo `DEFERRED` khi hết cooldown cảnh.
Đây là logic thuần.

**Xác minh VLM (`vlm.py`).** Khi track vào CONFIRMED, keyframe và vùng nghi ngờ được gửi
tới Gemini qua REST (hoặc `mock`) trên thread pool riêng. Alert chờ tối đa `vlm.grace_s`,
sau đó phát `UNVERIFIED`; kết quả về sau được vá vào cùng event. VLM chỉ quyết
`verification`, không hạ severity.

**Verifier bền vững (`xac_minh_nen.py`, `cau_dao.py`), sau cờ `verifier.ben_vung`.**
Cờ bật thì cảnh báo được giao cho `DieuPhoiXacMinh`: hàng chờ giới hạn khoá theo
`event_id`, worker gọi VLM với timeout bằng ngân sách còn lại, luồng hẹn giờ riêng phát
`created` (`PENDING`) ở `vlm.grace_s` và `updated` (`VLM_TIMEOUT`) ở `verifier.ngan_sach_s`
dù nguồn video treo. `CauDao` mở sau `loi_lien_tiep` thất bại liên tiếp, khi mở thì event
nhận `VLM_OFF`. Thống kê cửa sổ 10 phút đi vào `/health` qua `PipelineHealth`.

**Event và phát (`alerts.py`, `server.py`).** `EventStore` ghi JSON và ảnh keyframe, rồi
đẩy event tới các bên đăng ký: WebSocket (`Broadcaster`), webhook (`WebhookSink`, thread
riêng), và cập nhật cùng `event_id`. `server.py` là ứng dụng FastAPI: REST, `WS /ws`,
`/health`, `/snapshots`, `/console`. Hợp đồng với backend ở `docs/ban_giao_backend.md`.

**Người trực (`acks.py`, `hitl.py`, `static/console.html`).** Console hiện cảnh báo mới
nhất với ba nút: Xác nhận, Bỏ qua (lửa có kiểm soát), Theo dõi. Ack lưu tách khỏi event.
CRITICAL chưa ai trả lời được gửi lại theo `alerts.escalation_s`. "Bỏ qua (lửa có kiểm
soát)" xuất ảnh làm hard negative.

**Vòng lặp chính (`pipeline.py`, `__main__.py`).** `pipeline.py` nối các tầng, giữ các
alert đang chờ VLM, và ghi `summary.json`. `__main__.py` là CLI `python -m firewatch run |
serve`. `PipelineHealth` cấp số liệu cho `/health`.

**Cấu hình (`config.py`, `config.yaml`).** Một file cấu hình duy nhất, kiểm bằng pydantic
(sai tên khoá là lỗi). `--set` ghi đè tại chỗ.

**Module phục vụ dữ liệu và đánh giá.** Các module `camsim`, `irsim`, `datamix`,
`dataaudit`, `leakcheck`, `scenegroup`, `trainlists`, `evalkit`, `eventmetrics`,
`eventreport`, `eventruns`, `episodes`, `stats`, `claims`, `noninferiority`, `tiers`,
`agreement` và `competitors` được nhập cùng mã nguồn. Pipeline vận hành không dùng chúng.
Script gọi chúng nằm ở FireWatch-Model hoặc repo cũ. `camsim` và `irsim` là module tăng
cường dữ liệu train, không phải công cụ giả lập camera để chạy thử.

**Công cụ (`tools/annotate_video.py`).** Vẽ detection thô lên mọi khung của một video để
xem model bằng mắt, không đi qua voting hay alert.

## Thay đổi so với sơ đồ 05/11

Đối chiếu ngày 2026-11-07. Những phần sơ đồ vẽ đúng với mã hiện tại không liệt kê ở
đây, gồm: luồng sáu bước, ONNX 640 trên CPU, voting 6/10, cooldown 60 s, chờ VLM tối đa
2 s rồi fail-open, console với ba nút, leo thang sau 120 s, và vòng hard negative.

### Đã đổi

| Sơ đồ ghi | Hiện nay | Nguồn |
|---|---|---|
| Huấn luyện: "RTX 4050 · Colab", "Fine-tune YOLO26n" | FireWatch-v2.0 train trên Kaggle (2×T4, 60 epoch) **từ COCO** `yolo26n.pt`, không fine-tune từ model cũ | model card FireWatch-v2.0 ở FireWatch-Model |
| Đánh giá 3 cấp: "Bộ test T1 giữ riêng" | T1 không còn là test mù (clip âm đã được xem qua kết quả model và dùng để chẩn đoán lỗi). Số đo chính thức là R3 ở FireWatch-Model, bảng chính là D-Fire test sạch; R3 là xác nhận sau khám phá | `docs/van_hanh.md` mục 2 |
| Model registry: "models/*.pt → ONNX", "lưu tên mới, không ghi đè" | bảng đăng ký nằm ở FireWatch-Model, danh tính là SHA-256 của `.pt`; repo này ghim model vận hành FireWatch-v2.0 trong `models/README.md` | `models/README.md` |
| Detector: "≈ 26 ms mỗi khung" | số đo R3 của FireWatch-v2.0: p50 30,8 ms, p95 44,0 ms (`benchmark_edge.py`, 4 luồng); lần chạy kiểm 07/11 trên clip mẫu trung bình 38 ms. Điều kiện đo khác nhau, không so trực tiếp | model card; `docs/van_hanh.md` mục 6 |
| Verifier: một nhánh chờ 2 s, fail-open | vẫn đúng khi cờ tắt. Thêm verifier bền vững sau cờ `verifier.ben_vung` (mặc định tắt): trạng thái và schema, hàng chờ và ngân sách nền 10 s độc lập heartbeat (`xac_minh_nen.py`), cầu dao (`cau_dao.py`), khối `verifier` trên `/health`, `reason: "verifier"` trên WebSocket, console hiện `needs_human_check` | `docs/decisions/2026-11-07-verifier-ben-vung.md` |

### Sơ đồ vẽ nhưng FireWatchAI chưa có

| Sơ đồ ghi | Thực tế |
|---|---|
| "chỉ quét vùng `watch_area`" | FireWatchAI chưa có vùng quét: detector xử lý cả khung. Hàm che `watch_area` hiện chỉ có trong khung `ai_service` ở nhánh `backend` |
| Container, "1 tiến trình mỗi camera", MediaMTX cấp RTSP :8554 | FireWatchAI không có Dockerfile hay cấu hình MediaMTX; mỗi lần chạy `python -m firewatch` là một nguồn. Docker và MediaMTX nằm ở `EdgeAI-MatPho/` của nhánh `backend`. FireWatch nhận URL RTSP bất kỳ, nên đọc được luồng MediaMTX |
| Gemini "p50 ≈ 2 s" | số từ một lần đo trên 50 khung val của bộ dữ liệu cũ (README nguồn); chưa đo lại với model và prompt hiện tại |
