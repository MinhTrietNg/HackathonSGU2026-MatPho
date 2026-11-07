# Vận hành FireWatch

Mọi lệnh chạy trong thư mục `FireWatchAI/`. Cài đặt và lệnh cơ bản xem `README.md` của
thư mục này; tài liệu này nói rõ hơn về trọng số, đầu ra, tham số và nguồn live.

## 1. Cài đặt

```bash
uv sync                 # tạo .venv từ uv.lock: torch bản CPU, ultralytics, OpenCV, FastAPI
cp .env.example .env    # chỉ cần khi dùng Gemini thật hoặc webhook; .env không commit
```

Không cần GPU. Chạy lệnh bằng `uv run ...` hoặc `.venv\Scripts\python.exe ...` trên
Windows. Trên PowerShell đặt `$env:PYTHONUTF8=1` để log tiếng Việt in đúng.

## 2. Trọng số

Model vận hành là FireWatch-v2.0. Tên file, SHA-256, cách lấy file và thứ tự chép nằm ở
`models/README.md`.

| File trong `models/` | Dùng khi |
|---|---|
| `firewatch-v2.0.pt` + `firewatch-v2.0_640.onnx` | pipeline (`detector.weights`, `backend: onnx`) |
| `yolo26n.pt` | weights gốc COCO, tự tải khi thiếu `detector.weights`. Không có lớp fire/smoke nên không bao giờ tạo event, chỉ để kiểm khung xương |

- Ghi đè nhanh bằng `run --weights <file>`.
- Với nguồn file, weights gốc vẫn chạy được để kiểm khung xương.
- Với webcam, RTSP và lệnh `serve`, pipeline **từ chối chạy** nếu weights không có lớp
  fire/smoke, vì chạy tiếp nghĩa là không bao giờ báo cháy.
- `--weights` trỏ sai đường dẫn cũng dừng ngay, không âm thầm rơi về weights gốc.
- `detector.require_classes: true` áp quy tắc từ chối cho cả nguồn file.

**Train và đánh giá không ở repo này.**
- FireWatch-v2.0 được train trên Kaggle (2×T4, 60 epoch, imgsz 640, batch 32), từ
  `yolo26n.pt` COCO, trên DataFireWatch-v2.0.
- Số đo chính thức là R3 trong
  [FireWatch-Model](https://github.com/MinhTrietNg/FireWatch-Model): bảng chính là D-Fire
  test sạch, mAP50 0,634. R3 là xác nhận sau khám phá, không phải đấu mù.
- Tập clip T1 của dự án **không phải test mù**: các clip âm đã được xem qua kết quả model
  nhiều lần, và một số được dùng để chẩn đoán lỗi khi làm dữ liệu.
- Vì vậy không có số nào ở repo này dùng được làm độ chính xác của model trên camera thật.

## 3. Mỗi lần chạy sinh ra gì

| Nơi | Nội dung |
|---|---|
| `runs/<video>_<thời gian>/run.log` | mọi heartbeat với timestamp video lẫn giờ thật, mọi chuyển trạng thái track |
| `runs/.../hbNNNNN_<giây>s.jpg` | heartbeat có detection, đã vẽ box và track (vàng CANDIDATE, đỏ CONFIRMED, xám COOLDOWN) |
| `runs/.../summary.json` | số heartbeat, box theo lớp, chuyển trạng thái, danh sách alert, ms trung bình và p95, tốc độ so với thời gian thực |
| `events/<stamp>_<id>.json` + `.jpg` | một alert là một event đúng schema trong `docs/ban_giao_backend.md`, kèm keyframe đã vẽ box |
| `events/<stamp>_<id>_goc.jpg` | keyframe sạch (khi `alerts.save_raw_keyframe: true`), dùng lại làm hard negative |

- Retention: `output.keep_runs` (mặc định 30) chỉ giữ N thư mục `runs/` mới nhất.
- `alerts.keep_days` (mặc định 0, nghĩa là giữ hết) xoá event cũ hơn N ngày lúc khởi
  động.
- Ảnh được ghi bằng helper an toàn với đường dẫn có dấu tiếng Việt. Ghi thất bại thì
  event có `snapshot_path` rỗng và log ERROR, không trỏ tới file không tồn tại.

## 4. Chỉnh tham số

Mọi tham số nằm trong `config.yaml` và được pydantic kiểm: gõ sai tên khoá là lỗi ngay
lúc khởi động. Ghi đè tại chỗ bằng `--set section.khoa=gia_tri`, đặt trước tên lệnh và
dùng nhiều lần được, ví dụ `python -m firewatch --set voting.k_enter=3 run ...`.

| Tham số | Ý nghĩa | Mặc định |
|---|---|---|
| `heartbeat.interval_s` | T giây giữa hai lần detect, theo timestamp video | 1.0 |
| `detector.conf_threshold` | ngưỡng tin cậy giữ box; `conf_by_class` ghi đè riêng từng lớp | 0.25 |
| `detector.imgsz` | cạnh ảnh đưa vào YOLO; đổi thì ONNX được export lại theo kích thước mới | 640 |
| `voting.k_enter` / `window_m` | số phiếu trong cửa sổ để xác nhận; thời gian báo sớm nhất ≈ k × T | 6 / 10 |
| `voting.k_fire` | số heartbeat có box **lửa** để lên CRITICAL | 2 |
| `voting.cooldown_s`, `scene_cooldown_s`, `realert_s` | giây không báo lại cho cùng track, cùng camera; chu kỳ nhắc lại khi còn cháy | 60 / 60 / 60 |
| `vlm.provider` | `gemini` hoặc `mock` (xác minh giả lập, mô tả có tiền tố `[mock]`) | gemini |
| `vlm.grace_s` | alert chờ VLM tối đa chừng này giây rồi phát `UNVERIFIED` | 2 |
| `alerts.escalation_s` | CRITICAL chưa ai trả lời sau chừng này giây thì gửi lại; 0 = tắt | 120 |

Ràng buộc voting: `1 ≤ k_exit ≤ k_enter ≤ window_m` và `k_fire ≤ k_enter`.

Secrets (API key, webhook) chỉ đọc từ `.env` theo mẫu `.env.example`. Thiếu
`GEMINI_API_KEY` thì VLM tự tắt, log lỗi rõ, và event là `UNVERIFIED`.

## 5. Nguồn live

- `--source 0` cho webcam, `--source rtsp://...` cho camera IP.
- Webcam và RTSP được đọc bằng thread riêng, chỉ giữ **khung mới nhất**. CPU chậm hơn fps
  thì khung cũ bị bỏ (có đếm trong log) thay vì xếp hàng làm heartbeat xử lý ảnh càng lúc
  càng cũ.
- Mất khung thì thread mở lại mãi với back-off 2, 4, 8… tới 30 s (`source.max_reconnects:
  0`), có timeout mở và đọc `source.read_timeout_s`.
- Nếu nguồn live vẫn kết thúc, `run` trả exit code 1 để supervisor khởi động lại, và
  `/health` trả 503.

## 6. Kiểm sau khi đổi model (2026-11-07, FireWatch-v1.5 → FireWatch-v2.0)

Máy kiểm: Windows 11, CPU, ultralytics 8.4.198, onnxruntime 1.31.1.

1. **SHA-256.** Cả `firewatch-v2.0.pt` và `firewatch-v2.0_640.onnx` sau khi chép đều trùng
   `SHA256SUMS` của FireWatch-Model.
2. **Tương đương `.pt` và ONNX** trên 50 ảnh val (seed 0); bảng đầy đủ ở
   `models/README.md`.
   - Cùng đầu vào 640×640: lệch IoU tối đa 0,000005, lệch conf tối đa 0,0000015, không
     box nào lệch ghép. **Đạt** ngưỡng < 0,01 / < 0,005.
   - Mỗi backend tự tiền xử lý: lệch IoU tối đa 0,043, lệch conf tối đa 0,056, 1 box không
     khớp. **Không đạt**. Nguyên nhân là letterbox khác nhau giữa hai backend, không phải
     do file ONNX.
3. **Pipeline trên clip dương.**
   - Lệnh: `python -m firewatch --set vlm.provider=mock run --source
     mau-xx-ngoai-chay-001_d1.mp4`. Đây là clip mẫu công khai, có lửa từ 0 đến 10,5 s.
   - Không có `.env`, nên không gọi Gemini thật và không gửi webhook.
   - Kết quả: exit 0, 11 heartbeat, **1 alert CRITICAL** ở giây 5,0 (VERIFIED, do mock),
     suy luận trung bình 38 ms, nhanh gấp 8,2 lần thời gian thực.
   - ONNX đã chép được dùng nguyên, không bị export lại, và SHA không đổi sau lượt chạy.
   - Đây là kiểm khói (smoke test): pipeline chạy đúng với model mới. **Không phải** số đo
     độ chính xác; clip này cũng nằm trong tập T1.

## 7. Chạy như dịch vụ

### Script chạy có kiểm trọng số

```bash
./run.sh serve --source rtsp://<camera>/stream        # Linux, macOS, container
.\run.ps1 serve --source rtsp://<camera>/stream       # Windows PowerShell
```

- Hai script gọi `tools/kiem_trong_so.py` trước: SHA-256 của file `.pt` phải trùng
  bảng trong `models/README.md`, sai hoặc thiếu thì **không chạy** (mã 1). ONNX lệch SHA
  chỉ cảnh báo, vì đó là bản export lại trên máy.
- Mọi tham số chuyển nguyên cho `python -m firewatch`. Trình thông dịch lấy từ
  `FIREWATCH_PYTHON`, rồi `.venv` của thư mục, rồi `python` hệ thống.
- Đặt `FIREWATCH_SOURCE` thì `serve` không kèm `--source` chạy trên nguồn đó.

### Docker

```bash
docker build -t firewatch FireWatchAI
docker run -d --name firewatch --restart unless-stopped -p 8000:8000 \
  --env-file FireWatchAI/.env -e FIREWATCH_SOURCE=rtsp://<camera>/stream \
  -v "$PWD/FireWatchAI/models:/app/models:ro" \
  -v firewatch_events:/app/events -v firewatch_runs:/app/runs \
  firewatch
```

| Mục | Cách làm |
|---|---|
| Lệnh | `run.sh serve --host 0.0.0.0 --port 8000 --exit-on-pipeline-stop`: kiểm SHA rồi chạy `python -m firewatch serve` với `/app/config.yaml` |
| Trọng số | mount `models/` vào `/app/models`. Chép `.pt` rồi ONNX theo `models/README.md`; mount `:ro` được khi ONNX đã có và mới hơn `.pt`, nếu không thì mount ghi được để detector export ONNX |
| Bí mật | `.env` không nằm trong image; truyền bằng `--env-file` hay `env_file` |
| Event và ảnh | volume `/app/events` (JSON, keyframe, `acks.json`; `/snapshots` phục vụ từ đây) |
| Log | `run.log` trong volume `/app/runs`, xoay vòng theo `output.log_toi_da_mb` × `output.log_so_ban`. Log stdout của container xoay bằng tuỳ chọn `logging` của Docker (ví dụ dưới) |
| Healthcheck | `HEALTHCHECK` gọi `GET /health` mỗi 30 s; 503 hay không trả lời 3 lần thì container `unhealthy` |
| Tự khởi động lại | `--exit-on-pipeline-stop`: pipeline lỗi hay nguồn live kết thúc thì `serve` thoát mã 1, và `restart: unless-stopped` khởi động lại cả tiến trình. Docker không tự khởi động lại container chỉ vì `unhealthy`; cờ này là thứ biến "pipeline chết" thành "tiến trình chết" |

### Gắn vào docker-compose của backend

Không sửa nhánh `backend`. Thêm service sau vào `docker-compose.yml` của backend, đường
dẫn tính từ thư mục chứa file compose đó tới `FireWatchAI/` của repo:

```yaml
services:
  firewatch:
    build: ../FireWatchAI
    restart: unless-stopped
    env_file: ../FireWatchAI/.env          # FIREWATCH_WEBHOOK_URL, FIREWATCH_WEBHOOK_TOKEN, GEMINI_API_KEY
    environment:
      FIREWATCH_SOURCE: rtsp://mediamtx:8554/cam01
    volumes:
      - ../FireWatchAI/models:/app/models:ro
      - firewatch_events:/app/events
      - firewatch_runs:/app/runs
    ports:
      - "8000:8000"
    logging:
      driver: json-file
      options: {max-size: "20m", max-file: "5"}

volumes:
  firewatch_events:
  firewatch_runs:
```

- Webhook trỏ vào service backend trong cùng mạng compose, ví dụ
  `FIREWATCH_WEBHOOK_URL=http://backend:<cổng>/<đường dẫn>`.
- Mỗi camera một service (một tiến trình một nguồn), mỗi service một `camera.id`: ghi đè
  bằng `command: ["--set", "camera.id=cam02", "serve", "--host", "0.0.0.0",
  "--exit-on-pipeline-stop"]` và một volume event riêng.

## 8. Chạy thử cờ `verifier.ben_vung` bật (2026-11-07)

Mục đích: xác nhận verifier bền vững và gom sự cố chạy đúng trên pipeline thật, trước
khi quyết mặc định cờ. **Không phải** số đo độ chính xác: các clip thuộc tập T1, VLM là
giả.

**Cách chạy.** Pipeline thật (FireWatch-v2.0, ONNX 640, CPU) với `--realtime`, nhánh
`FireWatch-AI` @ `81966a6`, `camera.context=HAM`, webhook rỗng. `/health` hỏi mỗi 5 s
qua cùng ứng dụng FastAPI của `serve`. Bốn chế độ:

| Chế độ | Cấu hình |
|---|---|
| cờ tắt | `vlm.provider=mock`, `vlm.mock_delay_s=0.5` (đối chứng) |
| nhanh | cờ bật, mock 0,5 s |
| chậm | cờ bật, mock 5 s |
| chết | cờ bật, `vlm.provider=gemini` trỏ `api_url` tới cổng đóng trên localhost: mọi lượt gọi lỗi mạng, không gọi Gemini thật |

Kết quả thô (event, `run.log`, `ket_qua.json` mỗi trường hợp) ở
`E:\Hackathon\_tam_gd1\verifier_thu\`, ngoài repo.

**Clip.**
- Dương: `tr-cn-tret-chay-101_d1.mp4` (170 s, cháy gần suốt clip).
- Âm: `te-vn-ham-bt-031_d1.mp4` (50 s).
- Leo thang: `te-cn-ngoai-chay-134_d1.mp4` (67 s, WARNING ở 18 s rồi CRITICAL ở 24 s), chỉ
  chạy cờ tắt và nhanh.
- Clip dương chọn ban đầu, `te-vn-ham-chay-023_d1.mp4`, không sinh cảnh báo nào với
  FireWatch-v2.0 ở cả bốn chế độ, nên được thay.

### Kết quả

| Clip, chế độ | `created` | `updated` | Voting quyết → `created` | Trạng thái verifier | ERROR trong log |
|---|---|---|---|---|---|
| dương, cờ tắt | 3 (26 s, 86 s, 146 s video) | 0 | 1,04 s | không có | 0 |
| dương, nhanh | 1 | 4 (nhịp 30 s) | 0,53 s | `VERIFIED` ngay trong `created` | 0 |
| dương, chậm | 1 | 5 | 2,07 s | `PENDING` rồi `VERIFIED` sau 3 s (5 s từ lúc quyết) | 0 |
| dương, chết | 1 | 5 | 2,05 s | `PENDING` rồi `VLM_ERROR` (`loi_mang`) | 0 |
| âm, cả 4 chế độ | 0 | 0 | | | 0 |
| leo thang, cờ tắt | 2 (WARNING, CRITICAL) | 0 | 1,03 s; 1,01 s | không có | 0 |
| leo thang, nhanh | 1 (WARNING) | 2 | 0,55 s; lên CRITICAL sau 0,04 s | `VERIFIED`, lượt 2 khi leo thang | 0 |

- **Thời điểm cảnh báo.** `created` đầu tiên có cùng `video_ts_sec` ở mọi chế độ (26,0 s
  clip dương; 18,0 s clip leo thang). Cờ bật không phát muộn hơn cửa sổ 2 s; với VLM
  nhanh còn sớm hơn cờ tắt khoảng 0,5 s, vì bộ điều phối phát ngay khi có kết quả thay vì
  chờ heartbeat kế tiếp.
- **VLM chết.** Lỗi kết nối tới cổng đóng trên Windows mất khoảng 2 s, nên `created` ra
  `PENDING` đúng lúc 2 s và `VLM_ERROR` theo sau trong cùng mili giây. Chỉ có một lượt gọi
  (gom sự cố), nên cầu dao không mở.
- **Gom sự cố.** Clip dương: 3 event của cờ tắt thành 1 event, `updated` đều 30 s một lần,
  `status` giữ `open` vì cháy tới hết clip. Clip leo thang: 2 event thành 1, mức lên
  CRITICAL bằng `updated` ngay (`luot_xac_minh` 2).
- **`/health`.** Luôn trả 200 trong lúc chạy, không lần nào không trả lời. Khối
  `verifier` khớp từng trường hợp: nhanh `answered_ratio_in_window` 1,0 và p50 500 ms;
  chậm 1,0 và p50 5000 ms; chết 0,0 và p50 `null`; cầu dao `closed`, `vlm_off_total` 0.
- **Log.** Không dòng ERROR nào. WARNING gồm dòng báo VLM giả lập lúc khởi động, dòng lỗi
  của mỗi lượt gọi VLM ở chế độ chết, và dòng báo mức tăng của sự cố.

### Chưa kiểm được ở đây

- Kết thúc sự cố (`ended` sau 120 s) và kiểm lại VLM sau 300 s: cần clip dài hơn hoặc
  nguồn lặp; đã có test với đồng hồ giả (`tests/test_su_co.py`).
- Cầu dao mở trên pipeline thật: cần ít nhất 3 lượt gọi lỗi liên tiếp, tức 3 sự cố trong
  thời gian ngắn; đã có test (`tests/test_verifier_cau_dao.py`).
