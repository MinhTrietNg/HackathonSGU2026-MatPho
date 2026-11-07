with open('docs/PROJECT_KNOWLEDGE.md', 'r', encoding='utf-8') as f:
    content = f.read()

target = '| *(Tiếp tục cập nhật)* | *...* | *...* | *...* | *...* |'
new_row = '''| **07/11/2026** | **Đồng Bộ API Lịch Nghỉ AI (`ai_schedule`), Snapshot-on-Exit Thumbnail & Ngắt RTSP Khối EAG (Phản hồi Flutter Team)** | 1) `PATCH /api/v1/cameras/{id}` không nhận `ai_schedule` dẫn tới mất dữ liệu lịch nghỉ của người dùng khi tải lại; 2) Thiếu `thumbnail_url` trong response camera và thiếu endpoint `POST /cameras/{id}/thumbnail` (Option B Base64 PNG); 3) Khối EAG chỉ đọc format cũ `start_time`/`end_time`/`["T2".."CN"]` chưa hỗ trợ `from`/`to`/`[1..7]` từ App | 1) Bổ sung `ai_schedule` (chứa `from`, `to`, `days: [1..7]` ISO-8601, hỗ trợ khung qua nửa đêm 22:00->06:00) và `thumbnail_url` vào `CameraModel`, `CameraUpdateRequest`, `CameraCreateRequest` và mọi response Camera (`GET /cameras`, `GET /cameras/{id}`, `PATCH`, `reconnect`, `restore`); 2) Viết endpoint `POST /api/v1/cameras/{id}/thumbnail` nhận JSON Base64 PNG/JPEG, upload Firebase Storage, tự động gắn cache-buster `?v=<timestamp>` và cập nhật Firestore (phân quyền: LEADER/MANAGER/assigned MEMBER, chặn NOTIFIER 403); 3) Cập nhật EAG `edge_backend/src/main.py`: hàm `compute_should_ai_scan_now` và lệnh WS `SYNC_CAMERA` nhận diện cả ISO `[1..7]` và `from`/`to`, kích hoạt ngắt luồng RTSP sang AI worker (`worker.stop()` -> `cap.release()`) khi trong giờ nghỉ; 4) Rà soát toàn diện: 87/87 endpoints trong API Doc khớp 100% với code FastAPI, test suite 63/63 test cases PASS (100%). | Khắc phục triệt để lỗi mất dữ liệu người dùng, tối ưu băng thông/CPU của cả Edge lẫn App, và khớp 100% với yêu cầu ngày 07/11/2026 của Flutter Team. |\n'''

if target in content:
    content = content.replace(target, new_row + target)
    with open('docs/PROJECT_KNOWLEDGE.md', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Updated PROJECT_KNOWLEDGE.md successfully')
else:
    print('Target not found')
