# Tồn đọng

Việc đã biết nhưng chưa làm, kèm lý do. Xong việc nào thì xoá dòng đó trong cùng commit.

## Repo này

| Việc | Vì sao chưa làm |
|---|---|
| Detector kiểm SHA-256 của ONNX theo `.pt` thay vì so mtime (`onnx_is_stale`) | `src/firewatch/detector.py` đang khoá. Trong lúc chờ, tránh lỗi bằng thứ tự chép ở `models/README.md` |
| Docstring dòng 3 của `detector.py` còn tên checkpoint cũ | cùng lý do trên; `tests/test_ten_cu.py` đang miễn trừ file này |
| Xoá các section `train`, `finetune`, `datasets`, `audit`, `eval` khỏi `config.yaml` vận hành | các section này phục vụ script train và đánh giá, vốn không nằm ở đây. Đã đổi tên tại chỗ; xoá phải sửa cả model trong `config.py`, nên tách thành quyết định riêng |
| `datafirewatch-v0.4` trong `train` và `finetune` | bộ fine-tune v0.4 không có trong bảng đăng ký của FireWatch-Model; tên mới được đặt theo quy tắc, chưa có dòng đăng ký |
| Vùng quét `watch_area` (sơ đồ 05/11 có vẽ) | chưa có trong FireWatchAI; khung `ai_service` ở nhánh `backend` đã có hàm che |
| `.pt` và ONNX cho box lệch nhau khi mỗi backend tự tiền xử lý (lệch IoU tối đa 0,043; `models/README.md`) | chưa quyết có cần thống nhất letterbox hay không. Pipeline chạy ONNX nên hiện không ảnh hưởng vận hành |
| Verifier bền vững: hàng chờ, ngân sách nền, cầu dao, `/health`, `reason: "verifier"` trên WebSocket | đang làm trên nhánh `FireWatch-AI` theo `docs/decisions/2026-11-07-verifier-ben-vung.md` |

## FireWatch-Model

Bốn tài liệu và script của repo cũ (`Model-Mat-Pho-` @ `afa5a70`) thuộc phần benchmark
nhưng chưa có chỗ ở FireWatch-Model. Không chép sang đây.

| File ở repo cũ | Ưu tiên | Ghi chú |
|---|---|---|
| `docs/dinh_nghia_thiet_bi_bien.md` | **cao** | `benchmark_edge.py` của FireWatch-Model đang trỏ tới file này |
| `docs/giao_thuc_danh_gia*.md` | trung bình | giao thức đánh giá mà các module `eventmetrics`, `claims`, `noninferiority` cài theo |
| `scripts/eval_verifier.py` | trung bình | đánh giá VLM trên tập khung có nhãn |
| `docs/huong_dan_train_cloud.md` | thấp | hướng dẫn train trên Kaggle/Colab |
