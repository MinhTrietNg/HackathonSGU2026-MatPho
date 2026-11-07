# FireWatchAI/: FireWatch

Pipeline phát hiện cháy và khói từ camera giám sát khu để xe:

```
nguồn video → heartbeat → detector (YOLO26n) → voting → xác minh VLM → event
```

Mỗi cảnh báo thành một event (JSON + ảnh keyframe), được đẩy qua REST, WebSocket và
webhook cho backend, và hiện trên console người trực (`/console`). Model vận hành là
FireWatch-v2.0 (YOLO26n, `.pt` SHA-256 `58def3d0…`).

## Chạy trong 5 lệnh

```bash
cd FireWatchAI
uv sync                                  # tạo .venv từ uv.lock
cp .env.example .env                     # điền GEMINI_API_KEY, webhook nếu dùng
cp <FireWatch-Model>/models/firewatch-v2.0.pt <FireWatch-Model>/models/firewatch-v2.0_640.onnx models/ && touch models/firewatch-v2.0_640.onnx
./run.sh serve --source <video.mp4> --realtime --set vlm.provider=mock
```

Mở `http://localhost:8000/console`. Lệnh cuối kiểm SHA-256 trọng số trước khi chạy
(`.pt` sai thì dừng), rồi chạy API, WebSocket và console với pipeline chạy nền.
`vlm.provider=mock` là xác minh giả lập, không cần mạng; bỏ đi để dùng Gemini thật.
Trên Windows dùng `.\run.ps1` thay `./run.sh` và đặt `$env:PYTHONUTF8=1`.

`--source` nhận file video, `0` (webcam) hoặc `rtsp://...`. Chạy một video không cần
server: `./run.sh run --source <video.mp4>`, kết quả vào `runs/` và `events/`. Chạy như
dịch vụ (Docker, tự khởi động lại, gắn vào docker-compose của backend): `docs/van_hanh.md`
mục 7.

## Cấu hình

`config.yaml` là file cấu hình duy nhất, mọi tham số có chú thích tại chỗ.
`--set section.key=value` ghi đè khi chạy, dùng nhiều lần được. Bí mật chỉ nằm trong
`.env`: `GEMINI_API_KEY`, `FIREWATCH_WEBHOOK_URL`, `FIREWATCH_WEBHOOK_TOKEN`.

| Muốn | Tham số |
|---|---|
| nhạy hơn hoặc ít báo giả hơn | `detector.conf_threshold`, `voting.k_enter` / `voting.window_m` |
| lấy mẫu dày hơn | `heartbeat.interval_s` |
| bớt nhắc lại | `voting.cooldown_s`, `voting.realert_s` |
| gửi ảnh gốc trong webhook | `webhook.gui_anh` |
| camera và bối cảnh | `camera.id`, `camera.context` (HAM, TRET, NGOAI) |

Chạy từ thư mục khác thì thêm `--config <đường dẫn tới config.yaml>`.

## Cờ `verifier.ben_vung`

Bật trong `config.yaml` từ 2026-11-08. Cờ bật thì:

- mỗi event có object `verifier` (`status`, `needs_human_check`, `latency_ms`, `reason`);
  `created` không chờ VLM quá 2 s (`PENDING`), kết quả về sau thành `updated`, chậm nhất
  10 s (`VLM_TIMEOUT`);
- cầu dao ngừng gọi VLM 60 s sau 3 lần lỗi liền (`VLM_OFF`); VLM không bao giờ hạ mức
  hay gỡ cảnh báo;
- một đám cháy trên một camera là một event: `created` một lần, `updated` tối đa mỗi
  30 s, lên mức hoặc đổi trạng thái xác minh thì báo ngay, 120 s không thấy lửa thì
  `status: ended`;
- `/health` có khối `verifier`; console hiện "cần người xác thực" khi
  `needs_human_check`.

`--set verifier.ben_vung=false` trả về đúng hành vi cũ (mỗi cảnh báo một event, không có
trường mới). Lý do bật và số liệu: `docs/van_hanh.md` mục 8 và 10. Thiết kế:
`docs/decisions/2026-11-07-verifier-ben-vung.md` và `2026-11-07-gom-su-co.md`.

## Hợp đồng với backend

`docs/ban_giao_backend.md` là hợp đồng: trường của event, REST, WebSocket, webhook,
object `verifier` và sự cố. `docs/mau_event.json` là một payload webhook thật đủ mọi
trường. Event chỉ được thêm trường; không đổi tên, kiểu hay xoá trường đã có.

## Test

```bash
uv run pytest -q
```

## Tài liệu

- `docs/van_hanh.md`: trọng số, đầu ra, tham số, nguồn live, chạy như dịch vụ, kết quả
  chạy thử và kiểm chấp nhận, bỏ sót đã biết.
- `docs/kien_truc.md`: các khối và luồng dữ liệu.
- `docs/decisions/`: các quyết định thiết kế (ADR).
- `docs/nguon_goc.md`: mã này nhập từ đâu và đối chiếu hash các module lõi.
- `models/README.md`: model vận hành, SHA-256, cách lấy file.
- `tools/annotate_video.py`: vẽ detection lên mọi khung của một video để xem bằng mắt.

## Tồn đọng

`docs/ton_dong.md` liệt kê việc đã biết nhưng chưa làm, kèm lý do. Đáng chú ý nhất:
clip `te-vn-ham-chay-023` (lửa nhỏ trong hầm) không được cảnh báo, và việc chọn ngưỡng
vận hành ở FireWatch-Model phải xét clip này.
