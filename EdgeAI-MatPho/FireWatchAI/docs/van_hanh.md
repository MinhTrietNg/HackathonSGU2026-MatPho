# Vận hành FireWatch

Mọi lệnh chạy trong thư mục `EdgeAI-MatPho/FireWatchAI/`. Cài đặt và lệnh cơ bản xem
`README.md` của thư mục này; tài liệu này nói rõ hơn về trọng số, đầu ra, tham số và nguồn live.

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
cd EdgeAI-MatPho
docker build -t firewatch FireWatchAI
docker run -d --name firewatch --restart unless-stopped -p 8000:8000 \
  --env-file FireWatchAI/.env -e FIREWATCH_SOURCE=rtsp://<camera>/stream \
  -v "$PWD/FireWatchAI/models:/app/models:ro" \
  -v firewatch_events:/app/events -v firewatch_runs:/app/runs \
  firewatch
```

| Mục | Cách làm |
|---|---|
| Lệnh | `run.sh edge --host 0.0.0.0 --port 8000`: kiểm SHA rồi chạy `python -m firewatch edge` với `/app/config.yaml`. Không có biến của nút biên (mục 11) thì `edge` chạy `serve --exit-on-pipeline-stop` trên `FIREWATCH_SOURCE` |
| Trọng số | mount `models/` vào `/app/models`. Chép `.pt` rồi ONNX theo `models/README.md`; mount `:ro` được khi ONNX đã có và mới hơn `.pt`, nếu không thì mount ghi được để detector export ONNX |
| Bí mật | `.env` không nằm trong image; truyền bằng `--env-file` hay `env_file` |
| Event và ảnh | volume `/app/events` (JSON, keyframe, `acks.json`; `/snapshots` phục vụ từ đây) |
| Log | `run.log` trong volume `/app/runs`, xoay vòng theo `output.log_toi_da_mb` × `output.log_so_ban`. Log stdout của container xoay bằng tuỳ chọn `logging` của Docker (ví dụ dưới) |
| Healthcheck | `HEALTHCHECK` gọi `GET /health` mỗi 30 s; 503 hay không trả lời 3 lần thì container `unhealthy` |
| Tự khởi động lại | `--exit-on-pipeline-stop`: pipeline lỗi hay nguồn live kết thúc thì `serve` thoát mã 1, và `restart: unless-stopped` khởi động lại cả tiến trình. Docker không tự khởi động lại container chỉ vì `unhealthy`; cờ này là thứ biến "pipeline chết" thành "tiến trình chết" |

### Gắn vào docker-compose của backend

Với nút biên `EdgeAI-MatPho`, làm theo mục 11: FireWatchAI đã là dịch vụ
`firewatch-ai` của compose đó, mọi camera trong một container. Cách dưới đây chạy một
nguồn mỗi service trong một compose khác.

Không sửa nhánh `backend`. Thêm service sau vào `docker-compose.yml` của backend, đường
dẫn tính từ thư mục chứa file compose đó tới `EdgeAI-MatPho/FireWatchAI/` của repo:

```yaml
services:
  firewatch:
    build: ../EdgeAI-MatPho/FireWatchAI
    restart: unless-stopped
    env_file: ../EdgeAI-MatPho/FireWatchAI/.env   # FIREWATCH_WEBHOOK_URL, FIREWATCH_WEBHOOK_TOKEN, GEMINI_API_KEY
    environment:
      FIREWATCH_SOURCE: rtsp://mediamtx:8554/cam01
    volumes:
      - ../EdgeAI-MatPho/FireWatchAI/models:/app/models:ro
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
  FireWatch-v2.0 ở cả bốn chế độ, nên được thay. Phân tích bỏ sót này ở mục 9.

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

## 9. Bỏ sót đã biết

### `te-vn-ham-chay-023_d1.mp4` (đo 2026-11-08)

Camera hầm xe, 98 s, 1280×720, 30 fps; clip thuộc `vn_test` và T1 dev của
`Model-Mat-Pho-`. Nhãn tự động (`tu_dong_v1.0`) ghi cháy từ 0 đến 52 s. Nhìn các khung
ở 5, 20 và 35 s thấy một ngọn lửa nhỏ giữa hàng xe máy; khoảng 45 s có người phun bình
chữa cháy. Pipeline với FireWatch-v2.0 không sinh cảnh báo nào (mục 8).

**Cách đo.** Một script ngoài repo gọi đúng lớp `Detector` và `HeartbeatSampler` của
pipeline: ONNX 640, CPU, `detector.conf_threshold` 0,10, không voting. Chạy trên mọi
khung (2940) và trên khung heartbeat (98, mỗi 1 s video). Sau đó cho `VotingEngine` với
cấu hình hiện hành (6/10, `iou_match` 0,3) chạy lại trên phát hiện của heartbeat, ở
ngưỡng vận hành 0,25 và ở 0,10. Hai lần chạy cho kết quả giống hệt. So sánh với
FireWatch-v1.5 (`firewatch-v1.5_640.onnx` của FireWatch-Model, `.pt` SHA-256
`3e5e527e…`).

| Đại lượng | FireWatch-v2.0 | FireWatch-v1.5 |
|---|---|---|
| Khung có box lửa/khói ≥ 0,10 (trên 2940) | 114 | 68 |
| trong đó trước 40 s | 3 | 0 |
| Khung có box ≥ 0,25 | 61, đều trong 45–50 s | 37, đều trong 40–50 s |
| conf lớn nhất, lửa | 0,47 (46,5 s) | 0,70 (46,4 s) |
| conf lớn nhất, khói | 0,44 (48,9 s) | 0,47 (44,9 s) |
| Heartbeat có box ≥ 0,10 (trên 98) | 5 (45–49 s) | 3 (45–47 s) |
| Heartbeat có box ≥ 0,25 | 2 (46 s, 49 s) | 1 (45 s) |
| Phiếu nhiều nhất của một track, ngưỡng 0,25 | 2/10 | 1/10 |
| Phiếu nhiều nhất của một track, ngưỡng 0,10 | 4/10 | 2/10 |

**Vì sao voting không đủ 6/10.** Đã xác nhận từ số liệu trên:
- Trong 40 s đầu, detector gần như im lặng ở cả hai model dù lửa có trong khung:
  FireWatch-v2.0 có 3 khung trên 1200 có box ≥ 0,10, FireWatch-v1.5 không có khung nào.
- Phát hiện chỉ dồn vào 45–50 s, lúc bình chữa cháy phun và lửa bùng lên. Lấy mẫu 1 s chỉ
  gặp 2 heartbeat có box ≥ 0,25, nên mỗi cửa sổ 10 heartbeat có tối đa 2 phiếu, cần 6.
- Hạ ngưỡng xuống 0,10 cũng không đủ. FireWatch-v2.0 có 5 heartbeat liền nhau có box,
  nhưng box nhảy chỗ: khói ở x 483–701 px lúc 45 s, lửa ở x 776–850 px từ 46 s. Voting
  tách thành 3 track, track nhiều nhất 4 phiếu. Kể cả không tách track, 5 vẫn nhỏ hơn 6.
- Bỏ sót không phải hồi quy riêng của FireWatch-v2.0: FireWatch-v1.5 cũng không báo, dù
  conf lửa lớn nhất của nó cao hơn.

Giả thuyết, chưa kiểm: lửa quá nhỏ so với khung khi về 640 px, bị cột và xe che một phần,
ánh sáng yếu. Box lửa FireWatch-v2.0 bắt được ở 45–50 s có trung vị 69×28 px trên khung
1280×720, tức khoảng 34×14 px ở đầu vào 640; ngọn lửa trước đó nhìn bằng mắt còn nhỏ hơn.
Video là bản đăng lại, có chữ và logo chèn.

**Hệ quả.** Một ngọn lửa nhỏ cháy khoảng 45 s trong hầm xe không được báo. Phiên này không
đổi ngưỡng và không đổi k-of-M. Việc chọn ngưỡng vận hành phải xét clip này, ghi ở
`docs/ton_dong.md`.

## 10. Kiểm chấp nhận (2026-11-08)

Mục đích: xác nhận `serve` chạy liền 30 phút không lỗi, không phình bộ nhớ, `/health`
luôn trả lời, với cờ `verifier.ben_vung` bật (cấu hình ghi đè, trước khi đổi mặc định).

**Cách chạy.** `main` @ `ceb0d60`, `./run.sh` (kiểm SHA-256 trọng số: cả hai `OK`) rồi
`serve --realtime --exit-on-pipeline-stop` trên clip âm `te-vn-ham-bt-031_d1.mp4` (50 s)
với `source.loop=true`, tức khoảng 36 vòng clip. Ghi đè: `verifier.ben_vung=true`,
`vlm.provider=mock`, `vlm.mock_delay_s=5`, webhook rỗng, `output.save_frames=false`.
Máy Windows 11, CPU 16 luồng, FireWatch-v2.0 ONNX 640 trên CPU. Một script ngoài repo
hỏi `/health` mỗi 10 s và đo working set lớn nhất trong các tiến trình Python con. Kết
quả thô ở `E:\Hackathon\_tam_gd1\chap_nhan_3e\lan1_30phut\`, ngoài repo.

| Tiêu chí | Ngưỡng đạt | Kết quả |
|---|---|---|
| Dòng ERROR hoặc Traceback trong log | 0 | 0 |
| RAM phút 30 so với phút 1 | tăng ≤ 20 % | 532,8 MB → 518,7 MB (−2,6 %); dao động 510,9–535,4 MB |
| `/health` không trả lời | 0 | 0 trên 167 lần hỏi, lần nào cũng 200 và `status: ok` |
| Tiến trình tự thoát giữa chừng | không | không |

**Kết luận: đạt ở lần chạy đầu.**

Số khác:
- 1793 heartbeat trong 1799 s chạy, tức pipeline theo kịp thời gian thực suốt 30 phút;
  `last_heartbeat_age_s` cuối là 0,2 s.
- 0 cảnh báo, đúng với clip âm.
- WARNING duy nhất là dòng báo VLM giả lập lúc khởi động.
- Khối `verifier` cuối: cầu dao `closed`, 0 lần mở, hàng chờ 0, `vlm_off_total` 0.

Giới hạn của lần đo:
- Clip âm không sinh cảnh báo nên hàng chờ xác minh, cầu dao và gom sự cố không có việc
  để làm (`requests_in_window` 0). Lần đo này kiểm độ bền của vòng heartbeat, server và
  bộ nhớ khi cờ bật; đường có cảnh báo đã chạy thử ở mục 8.
- Khoảng phút 2–5 có một lệnh tìm kiếm khác chạy trên một luồng CPU. `/health` vẫn trả
  200 và heartbeat không bị trễ trong lúc đó.

## 11. Chạy trong nút biên `EdgeAI-MatPho`

FireWatchAI nằm ở `EdgeAI-MatPho/FireWatchAI/` và là dịch vụ `firewatch-ai` của
`EdgeAI-MatPho/docker-compose.yml`. Từ 2026-11-08 nó thay khung `ai_service` cũ, vốn chỉ
đọc RTSP và gửi webhook quanh một model trống. `edge_backend` và backend không phải sửa
gì.

**Các bước.**
1. Chép `firewatch-v2.0.pt` rồi `firewatch-v2.0_640.onnx` vào
   `EdgeAI-MatPho/FireWatchAI/models/` theo `models/README.md` (không vào git). Compose
   gắn thư mục này vào `/app/weights` ở chế độ chỉ đọc; `run.sh` chép sang `/app/models`
   rồi kiểm SHA-256, sai hoặc thiếu thì container dừng mã 1 với thông báo rõ.
2. Điền `GEMINI_API_KEY=<key>` trong `EdgeAI-MatPho/.env` (dòng có sẵn trong
   `.env.example`). Không có key thì VLM tắt và mọi event ra `VLM_OFF`, cần người xác
   thực.
3. `cd EdgeAI-MatPho && ./run_edge.sh up` (hoặc `docker compose up -d --build`).

**Biến môi trường được dùng** (đúng như khung `ai_service` cũ):

| Biến | Dùng để |
|---|---|
| `AI_CAMERA_STREAMS` (JSON) hoặc `AI_CAMERA_IDS` | camera chạy ngay khi khởi động; `cam_id` thành `camera.id` của event. Mỗi mục có thể thêm `"context": "HAM"`, `"TRET"` hoặc `"NGOAI"`, mặc định lấy `camera.context` của `config.yaml` |
| `MEDIAMTX_RTSP_URL`, `STREAM_PATH_TEMPLATE` | nguồn mỗi camera: `rtsp://mediamtx:8554/live/{cam_id}` |
| `EDGE_BACKEND_API_URL` | mỗi 2 s đọc `GET /api/v1/edge/cameras`: camera có `should_ai_scan_now` thì nối (kể cả camera mới thêm), camera tắt hoặc đang trong giờ nghỉ theo lịch thì ngắt RTSP ngay; camera không có trong danh sách giữ nguyên. Event gửi tới `POST /api/v1/edge/ai-events` |
| `CLOUD_BACKEND_API_URL` | đích event khi không có `EDGE_BACKEND_API_URL` (`/api/v1/internal/ai/fire-events`) |
| `INTERNAL_API_SECRET_KEY` | gửi trong `Authorization: Bearer` và `X-Internal-Secret` |
| `GEMINI_API_KEY` | VLM thật |

`FIREWATCH_WEBHOOK_URL` và `FIREWATCH_WEBHOOK_TOKEN`, nếu đặt, thắng các giá trị suy ra ở
trên. `AI_TARGET_FPS`, `AI_SAMPLING_FPS`, `AI_CONFIDENCE_THRESHOLD`, `AI_ALERT_COOLDOWN_S`,
`ALERT_COOLDOWN_SECONDS` và `AI_MODEL_WEIGHTS_PATH` bị **bỏ qua**, có ghi một dòng log
lúc khởi động. Nhịp heartbeat, ngưỡng, voting và cooldown lấy từ `config.yaml`, nên điểm
vận hành giữ đúng như đã kiểm ở mục 6, 8 và 10. `watch_area` của camera cũng chưa được
dùng; khung cũ cũng không dùng (tồn đọng).

**Đường đi của một cảnh báo.** FireWatch gửi `POST /api/v1/edge/ai-events` tới
edge_backend. Edge_backend đổi `camera_id` sang `cam_id`, tách `snapshot_base64` và chuyển
tín hiệu lên `POST /api/v1/internal/ai/fire-events` của cloud trong vòng 4 s. Mất WAN thì
nó xếp event vào hàng SQLite. Ảnh được tải riêng một lần mỗi `event_id` (pha 2). Lệnh
`edge` tự bật `webhook.gui_anh` để pha 2 có ảnh, và đặt timeout webhook 10 s; `--set`
vẫn ghi đè được.

**Camera phải có ở backend.** FireWatch báo cháy theo `cam_id` của camera trên edge;
backend chỉ nhận event của camera đã tạo trong app (id dạng `cam_<hex>`), camera lạ trả
404 `CAMERA_NOT_FOUND` và app không hú. edge-backend nhận danh sách camera của backend
qua `CLOUD_BACKEND_WS_URL`, nên biến này và `CLOUD_BACKEND_API_URL` phải trỏ cùng backend
(local: `host.docker.internal:8000`). Thử bằng clip cháy: phát vào
`rtsp://<máy edge>:8554/source/<tên>`, tạo camera trong app với đúng URL đó, đợi edge
nhận `SYNC_CAMERA` rồi kiểm `GET :8090/api/v1/edge/cameras` có `cam_<hex>`. Phát vào
`source/cam_01` mà không tạo camera thì FireWatch vẫn phát hiện, nhưng event bị từ chối
(edge ghi log `Backend rejected fire event … HTTP 404`). Đã chạy thử 2026-11-08 trên
cụm Docker với backend giả: luồng mở lúc 02:33:30, `CONFIRMED 6/10 CRITICAL` lúc
02:33:37, event và ảnh pha 2 tới backend với HTTP 202.

**Trong container.**
- Mọi camera dùng chung một model (gọi tuần tự có khoá). Event nằm ở `/app/events/<cam_id>/`,
  `run.log` ở `/app/runs/<cam_id>/`, mỗi dòng log có `[cam-<cam_id>]`.
- Camera không mở được nguồn (MediaMTX chưa phát luồng) hoặc mất nguồn thì tự chạy lại:
  chờ 2 s, gấp đôi, tối đa 30 s. Sự cố đang mở được giữ qua lần chạy lại: chưa quá
  `su_co.khoang_cach_s` (120 s) kể từ lần thấy cháy cuối thì cảnh báo kế tiếp là
  `updated` cùng `event_id`, không phải `created` mới (log `SỰ CỐ … tiếp tục sau khi
  chạy lại`).
- `GET /health` trên cổng 8000 trong container: 200 khi mọi camera đang chạy có heartbeat
  đều, 503 khi có camera `stale`, camera đã từng chạy rồi mất nguồn, hoặc camera chưa có
  heartbeat nào sau 120 s. Thân trả về liệt kê từng camera, camera đang nghỉ theo lịch
  (`paused`) và lần đồng bộ edge_backend gần nhất.
- Không chạy bộ nhắc lại của console (`alerts.escalation_s`): backend tự leo thang.

**Đã kiểm (2026-11-08, trên máy, không Docker).** Chạy `run.sh edge` với trọng số thật;
hai "camera" là file phát lặp theo thời gian thực: clip có cháy và clip âm. Edge_backend
giả làm đúng các bước của `relay_ai_fire_event`. Cloud giả kiểm payload bằng
`AIFireEventPayload` và `AISnapshotUploadPayload` thật của `backend/`.

| Kiểm | Kết quả |
|---|---|
| `created` qua edge tới cloud | 202, `cam_id` đúng, `last_seen_ts` dạng ISO |
| Ảnh pha 2 | 202, một lần, 91 KB |
| `updated` | 202, đều 30 s một lần |
| Camera vào giờ nghỉ rồi hết | ngắt ở lần đồng bộ kế tiếp (nhịp 2 s), pipeline dừng trong cùng giây; nối lại ở lần đồng bộ kế tiếp |
| `/health` | 200 suốt 110 s |
| Dòng ERROR | 0 |

**Chưa kiểm:** build image và chạy cả cụm `docker compose` thật (MediaMTX, edge_backend,
RTSP), vì Docker Desktop đang tắt; edge_backend thật cần `aiosqlite`, `av`,
`pydantic-settings`, không có trong `.venv` của FireWatchAI.
