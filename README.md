# Mắt Phố

Mắt Phố phát hiện sớm cháy và khói xe tại khu để xe (hầm giữ xe chung cư, nhà xe trong
nhà, sân để xe trước nhà) từ camera an ninh sẵn có. Hệ thống nhận diện lửa và khói trên
từng khung hình, chỉ báo động khi dấu hiệu lặp lại đủ lâu, nhờ mô hình thị giác–ngôn
ngữ xác minh thêm, rồi gửi cảnh báo kèm ảnh tới ứng dụng và người trực. Chỉ người trực
mới được bỏ qua một cảnh báo.

## Bản đồ dự án

Mọi khối đều nằm trên `main`; nhánh riêng của từng khối dùng để làm tính năng rồi merge.

| Khối | Nhánh làm việc | Thư mục | Vai trò |
|---|---|---|---|
| Backend | [`backend`](https://github.com/MinhTrietNg/HackathonSGU2026-MatPho/tree/backend) | `backend/` | API, xác thực, lưu và phân phối cảnh báo |
| Nút biên | [`backend`](https://github.com/MinhTrietNg/HackathonSGU2026-MatPho/tree/backend) | `EdgeAI-MatPho/` | docker-compose chạy MediaMTX, `edge_backend` và FireWatch tại nơi đặt camera |
| FireWatch | `FireWatch-AI` | [EdgeAI-MatPho/FireWatchAI/](EdgeAI-MatPho/FireWatchAI/) | phát hiện lửa/khói, voting, xác minh VLM, phát event qua `edge_backend` hoặc webhook; là dịch vụ `firewatch-ai` của nút biên |
| Ứng dụng | [`frontend`](https://github.com/MinhTrietNg/HackathonSGU2026-MatPho/tree/frontend) | `frontend/` | ứng dụng Flutter nhận và hiển thị cảnh báo, xem camera |

FireWatch gửi event cho backend theo hợp đồng ở
[EdgeAI-MatPho/FireWatchAI/docs/ban_giao_backend.md](EdgeAI-MatPho/FireWatchAI/docs/ban_giao_backend.md),
mẫu thật ở
[EdgeAI-MatPho/FireWatchAI/docs/mau_event.json](EdgeAI-MatPho/FireWatchAI/docs/mau_event.json).
Cách chạy FireWatch ở [EdgeAI-MatPho/FireWatchAI/README.md](EdgeAI-MatPho/FireWatchAI/README.md).

## Repo liên quan

- [FireWatch-Model](https://github.com/MinhTrietNg/FireWatch-Model): benchmark R3, đăng
  ký trọng số (SHA-256) và dữ liệu; khoá trước khi chạy. Trọng số FireWatch-v2.0 mà
  FireWatch dùng lấy từ đây.
- [Model-Mat-Pho-](https://github.com/MinhTrietNg/Model-Mat-Pho-): repo cũ, chỉ lưu trữ,
  không cập nhật.

## Thành viên
- Nguyễn Minh Triết
- Phi Công Tài
- Nguyễn Hoàng Khả
- Nguyễn Ngọc Thu Ngân
- Vũ Đình Phi
