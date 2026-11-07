# Tồn đọng

Việc đã biết nhưng chưa làm, kèm lý do. Xong việc nào thì xoá dòng đó trong cùng commit.

## Repo này

| Việc | Vì sao chưa làm |
|---|---|
| Detector kiểm SHA-256 của ONNX theo `.pt` thay vì so mtime (`onnx_is_stale`) | `src/firewatch/detector.py` đang khoá. Trong lúc chờ, tránh lỗi bằng thứ tự chép ở `models/README.md`; `run.sh` / `run.ps1` kiểm SHA-256 trước khi chạy, ONNX lệch chỉ cảnh báo |
| Docstring dòng 3 của `detector.py` còn tên checkpoint cũ | cùng lý do trên; `tests/test_ten_cu.py` đang miễn trừ file này |
| Xoá các section `train`, `finetune`, `datasets`, `audit`, `eval` khỏi `config.yaml` vận hành | các section này phục vụ script train và đánh giá, vốn không nằm ở đây. Đã đổi tên tại chỗ; xoá phải sửa cả model trong `config.py`, nên tách thành quyết định riêng |
| `datafirewatch-v0.4` trong `train` và `finetune` | bộ fine-tune v0.4 không có trong bảng đăng ký của FireWatch-Model; tên mới được đặt theo quy tắc, chưa có dòng đăng ký |
| Vùng quét `watch_area` (sơ đồ 05/11 có vẽ) | FireWatch chưa có; edge_backend có trả `watch_area` cho mỗi camera. Khung `ai_service` cũ có `masking.py` nhưng cũng không gọi tới, nên chạy thay nó không mất gì. Chưa quyết che trước detector hay lọc box sau, việc nào cũng đổi điểm vận hành |
| Chạy thử cả cụm `EdgeAI-MatPho` bằng `docker compose` (MediaMTX, edge_backend thật, RTSP) với FireWatchAI ở chỗ `ai_service` | Docker Desktop tắt lúc làm; đã thử trên máy với edge_backend giả và model Pydantic thật của backend (`docs/van_hanh.md` mục 11) |
| Chế độ nút biên: mỗi `run.log` nhận log của mọi camera (handler gắn vào logger gốc), có `[cam-<cam_id>]` để lọc | tách log theo camera phải sửa cách `pipeline.py` gắn handler; dung lượng vẫn bị chặn bởi xoay vòng |
| `fire_type` ở cấp ngoài của payload (backend có trường này, FireWatch chỉ gửi `vlm.fire_type`) | chỉ có nghĩa với camera NGOAI; backend chỉ đọc lúc `created`, khi VLM thường chưa trả lời |
| Căn letterbox của `detector.py` theo tiền xử lý của ultralytics, để `.pt` và ONNX cho cùng box (hiện lệch IoU tối đa 0,043; `models/README.md`) | `detector.py` đang khoá. Pipeline chỉ chạy ONNX nên hiện không ảnh hưởng vận hành |
| Tách đường ảnh khỏi webhook khi nhiều camera | `webhook.gui_anh` nhúng ảnh gốc (JPEG ≤ 200 KB, base64) vào từng payload, đủ cho một vài camera. Nhiều camera thì nên đẩy ảnh qua đường riêng và chỉ gửi đường dẫn; việc này đổi hợp đồng với backend nên phải thống nhất hai bên trước |
| `updated` dạng timeline mỗi 30 s (gửi kèm lịch sử các lần cập nhật) | ADR gom sự cố chọn mỗi `updated` chỉ mang trạng thái hiện tại; backend tự ghép dòng thời gian từ chuỗi `updated` cùng `event_id` nếu cần |
| Giữ trạng thái sự cố qua lần khởi động lại | trạng thái nằm trong bộ nhớ; khởi động lại thì cảnh báo kế tiếp mở sự cố mới (ADR gom sự cố, mục hạn chế) |

## Chọn ngưỡng vận hành (bài FA ở FireWatch-Model) phải xét clip này

`te-vn-ham-chay-023_d1.mp4`: ngọn lửa nhỏ trong hầm xe cháy khoảng 45 s mà
FireWatch-v2.0 không cảnh báo; FireWatch-v1.5 cũng vậy. Số liệu ở `docs/van_hanh.md`
mục 9.

- Ở ngưỡng 0,25 chỉ 2 trên 98 heartbeat có box, xa mức 6/10 của voting.
- Hạ riêng ngưỡng không cứu được: ở 0,10 FireWatch-v2.0 chỉ có 5 heartbeat liền nhau có
  box, và voting tách chúng thành 3 track. Bài chọn ngưỡng phải xét cùng lúc
  `conf_threshold`, `conf_by_class`, `heartbeat.interval_s`, `k_enter`/`window_m` và việc
  ghép track, mỗi phương án đo kèm báo động giả trên clip âm.
- Clip này là ca bỏ sót bắt buộc phải báo cáo trong bài đó, kể cả khi phương án được
  chọn vẫn không bắt được nó.

Chưa làm vì phiên 2026-11-08 giữ nguyên model, ngưỡng và k-of-M theo yêu cầu.

## FireWatch-Model

Bốn tài liệu và script của repo cũ (`Model-Mat-Pho-` @ `afa5a70`) thuộc phần benchmark
nhưng chưa có chỗ ở FireWatch-Model. Không chép sang đây.

| File ở repo cũ | Ưu tiên | Ghi chú |
|---|---|---|
| `docs/dinh_nghia_thiet_bi_bien.md` | **cao** | `benchmark_edge.py` của FireWatch-Model đang trỏ tới file này |
| `docs/giao_thuc_danh_gia*.md` | trung bình | giao thức đánh giá mà các module `eventmetrics`, `claims`, `noninferiority` cài theo |
| `scripts/eval_verifier.py` | trung bình | đánh giá VLM trên tập khung có nhãn |
| `docs/huong_dan_train_cloud.md` | thấp | hướng dẫn train trên Kaggle/Colab |
