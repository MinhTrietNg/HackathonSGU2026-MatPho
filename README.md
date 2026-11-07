# Mắt Phố

Mắt Phố phát hiện sớm cháy và khói xe tại khu để xe (hầm giữ xe chung cư, nhà xe trong
nhà, sân để xe trước nhà) từ camera an ninh sẵn có. Hệ thống nhận diện lửa và khói trên
từng khung hình, chỉ báo động khi dấu hiệu lặp lại đủ lâu, nhờ mô hình thị giác–ngôn
ngữ xác minh thêm, rồi gửi cảnh báo kèm ảnh tới ứng dụng và người trực. Chỉ người trực
mới được bỏ qua một cảnh báo.

## Bản đồ dự án

Mỗi khối sống trên một nhánh riêng của repo này.

| Khối | Nhánh | Thư mục | Vai trò |
|---|---|---|---|
| FireWatch | `main` (tính năng mới làm trên `FireWatch-AI`) | [FireWatchAI/](FireWatchAI/) | phát hiện lửa/khói, voting, xác minh VLM, phát event qua WebSocket và webhook, console người trực |
| Backend và nút biên | [`backend`](https://github.com/MinhTrietNg/HackathonSGU2026-MatPho/tree/backend) | `backend/`, `EdgeAI-MatPho/` | API, xác thực, lưu và phân phối cảnh báo; nút biên gồm MediaMTX, `edge_backend` và khung `ai_service` |
| Ứng dụng | [`frontend`](https://github.com/MinhTrietNg/HackathonSGU2026-MatPho/tree/frontend) | `frontend/` | ứng dụng Flutter nhận và hiển thị cảnh báo, xem camera |

FireWatch gửi event cho backend theo hợp đồng ở
[FireWatchAI/docs/ban_giao_backend.md](FireWatchAI/docs/ban_giao_backend.md), mẫu thật ở
[FireWatchAI/docs/mau_event.json](FireWatchAI/docs/mau_event.json). Cách chạy FireWatch
ở [FireWatchAI/README.md](FireWatchAI/README.md).

## Repo liên quan

- [FireWatch-Model](https://github.com/MinhTrietNg/FireWatch-Model): benchmark R3, đăng
  ký trọng số (SHA-256) và dữ liệu; khoá trước khi chạy. Trọng số FireWatch-v2.0 mà
  FireWatch dùng lấy từ đây.
- [Model-Mat-Pho-](https://github.com/MinhTrietNg/Model-Mat-Pho-): repo cũ, chỉ lưu trữ,
  không cập nhật.
