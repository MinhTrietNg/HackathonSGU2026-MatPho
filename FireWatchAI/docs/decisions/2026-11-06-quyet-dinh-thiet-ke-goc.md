# Quyết định thiết kế gốc của FireWatch

- Ngày: 2026-11-06. Đây là ngày của commit nguồn; nội dung được chốt dần trước ngày đó.
- Trạng thái: đã áp dụng.
- Nguồn: README của `Model-Mat-Pho-` @ `afa5a70`, mục 8 "Quyết định thiết kế đã chốt".
  Chép lại với ba chỗ sửa, ghi ở cuối file.

## Quyết định

- **Heartbeat theo timestamp video**, không theo đồng hồ máy. Chạy file nhanh hơn thời
  gian thực mà kết quả vẫn tái lập; `--realtime` chỉ thêm sleep để demo đúng nhịp.
- **Lưới heartbeat cố định** (0, T, 2T…): mất khung hay decoder giật không làm lệch mốc.
- **Voting là logic thuần.**
  - Nhận danh sách box, trả danh sách chuyển trạng thái kèm cờ `alert`, nên test được
    không cần model.
  - Track ghép bằng IoU, có fallback "tâm hộp này nằm trong hộp kia" để theo kịp lửa lan.
    Hộp của track được làm mượt nửa cũ nửa mới.
  - Mức CRITICAL cũng theo k-of-M: cần `k_fire` heartbeat có box lửa, không phải một box
    lẻ.
- **Hai lớp cooldown**: theo track và theo cảnh.
  - Một đám cháy lớn bị detector tách thành nhiều hộp sẽ sinh nhiều track. Cooldown theo
    cảnh giữ đúng một alert cho mỗi camera trong 60 s, nhưng leo thang WARNING → CRITICAL
    vẫn luôn được báo.
  - Track bị cảnh chặn lúc xác nhận **không bị câm vĩnh viễn**: nó giữ cờ chờ và được báo
    (`DEFERRED`) ngay heartbeat đầu tiên sau khi cooldown cảnh hết.
  - Tắt cooldown cảnh bằng `scene_cooldown_s: 0`.
- **Cháy kéo dài được nhắc lại.** Track còn CONFIRMED thì mỗi `voting.realert_s` (mặc định
  60 s) phát thêm một alert `STILL_BURNING`. Nhờ vậy một lần VLM phủ nhận sai hay một lần
  webhook rớt không làm đám cháy thật biến mất khỏi app. Đặt 0 để về đúng một alert.
- **Nguồn live không tự dừng, không dồn khung.**
  - Webcam và RTSP được đọc bằng thread riêng, chỉ giữ **khung mới nhất**. CPU chậm hơn
    fps thì khung cũ bị bỏ (có đếm trong log), thay vì xếp hàng làm heartbeat xử lý ảnh
    càng lúc càng cũ. Timestamp là lúc camera đẩy khung.
  - Thread đó mở lại mãi với back-off 2, 4, 8… 30 s, có timeout mở và đọc.
  - Nếu nguồn live vẫn kết thúc, `run` trả exit code 1 để supervisor khởi động lại, và
    `/health` trả 503.
- **Thời gian báo sớm nhất ≈ k × T** (mặc định 6 s). Clip ngắn hơn, hoặc muốn báo nhanh
  hơn, thì giảm `k_enter`, đổi lại dễ báo giả hơn. Chọn bằng đánh giá, không đoán.
- **VLM không chặn vòng lặp và không trì hoãn alert.**
  - Xác minh chạy trên thread pool (`vlm.max_workers`). Alert chờ tối đa `vlm.grace_s` rồi
    phát `UNVERIFIED`; kết quả VLM về sau được vá vào cùng event (`event_update`).
  - Với CRITICAL, keyframe gửi VLM và ảnh snapshot là vote gần nhất **có box lửa**, không
    phải vote conf cao nhất (thường là khói).
  - Cuối lần chạy, pipeline chờ nốt các xác minh còn dở rồi mới ghi `summary.json`.
- **Gemini qua REST, không qua SDK**: tránh thêm dependency nặng. Đổi provider chỉ cần một
  lớp con `VLMVerifier` trong `vlm.py`.
- **VLM không hạ severity.** Mức WARNING/CRITICAL vẫn theo detector (có lửa hay chỉ khói);
  VLM chỉ quyết `verification`. Lý do: VLM có thể thấy khói mà bỏ lỡ lửa nhỏ, và hạ mức sẽ
  làm chậm ứng cứu. App hiển thị cả hai trường để người trực tự cân nhắc.
- **Chọn backend bằng số đo, không bằng thói quen.**
  - ONNX 640 là mặc định vì nhanh hơn PyTorch ở imgsz 640 trên CPU. Ở imgsz lớn hơn thì
    phải đo lại.
  - ONNX được export một lần thành `models/<tên>_<imgsz>.onnx` và chạy qua chính
    ultralytics và onnxruntime, không viết lại NMS.
  - Số đo tốc độ hiện hành của model vận hành nằm ở FireWatch-Model (R3, `benchmark_edge.py`).
- **Có giao diện tối thiểu cho người trực, không làm app.** Server trả JSON và WebSocket
  cho backend, app và dashboard của đội khác. Riêng trang `/console` (HTML tĩnh, không
  build) để người trực xem cảnh báo và trả lời bằng ba nút. Chỉ người trực được bỏ qua
  một cảnh báo.

## Chỗ sửa so với nguồn

1. Nguồn ghi "**Không UI**: server chỉ trả JSON / WebSocket". Nay đã có console người trực
   (`/console`, `acks.py`, `hitl.py`), nên quyết định được viết lại thành "giao diện tối
   thiểu cho người trực, không làm app".
2. Nguồn trỏ số đo pt/ONNX tới `scripts/benchmark_cpu.py` và `reports/benchmark_cpu.md`
   của repo cũ, đo bằng model cũ. Bản này chỉ giữ kết luận chọn ONNX 640, và trỏ số đo
   hiện hành sang FireWatch-Model.
3. Bỏ cụm "chọn bằng eval ở Phase 4"; việc đánh giá nay nằm ở FireWatch-Model.
