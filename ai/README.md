# ai/: FireWatch

Pipeline phát hiện cháy và khói từ camera giám sát khu để xe:

```
nguồn video → heartbeat → detector (YOLO26n) → voting → xác minh VLM → event
```

Mỗi cảnh báo thành một event (JSON + ảnh keyframe), được đẩy qua REST, WebSocket và
webhook cho backend, và hiện trên console người trực (`/console`).

Mọi lệnh dưới đây chạy **trong thư mục `ai/`**: `config.yaml` được tìm từ thư mục hiện
tại trở lên, `.env` được đọc cạnh `config.yaml`. Chạy từ chỗ khác thì thêm
`--config <đường dẫn tới ai/config.yaml>`.

## Cài đặt

```bash
cd ai
uv sync                 # tạo ai/.venv từ uv.lock
cp .env.example .env    # điền GEMINI_API_KEY, webhook nếu dùng; .env không commit
```

Trọng số detector không nằm trong git. Đặt file `.pt` vào `ai/models/` đúng tên ở
`detector.weights` trong `config.yaml`. Thiếu file đó thì detector dùng
`detector.fallback_weights`, nhưng `serve` và nguồn live sẽ từ chối chạy nếu trọng số
không có lớp `fire` / `smoke`.

## Chạy

```bash
# pipeline trên một video, ghi log, ảnh và event vào runs/ và events/
uv run python -m firewatch run --source <video.mp4>

# API + WebSocket + console người trực, pipeline chạy nền trên nguồn
uv run python -m firewatch serve --source <video.mp4> --realtime

# demo không cần mạng: xác minh giả lập, mô tả có tiền tố [mock]
uv run python -m firewatch serve --source <video.mp4> --realtime --set vlm.provider=mock
```

`--source` nhận file video, `0` (webcam) hoặc `rtsp://...`. `--set section.key=value`
ghi đè config tại chỗ, dùng nhiều lần được.

## Test

```bash
uv run pytest -q
```

Trên Windows PowerShell đặt `$env:PYTHONUTF8=1` trước khi chạy để log tiếng Việt in
đúng.

## Tài liệu

- `docs/decisions/`: các quyết định thiết kế (ADR).
- `docs/nguon_goc.md`: mã này nhập từ đâu và đối chiếu hash các module lõi.
- Benchmark detector và dữ liệu đánh giá không nằm ở đây; xem README gốc của repo.
