# Mắt Phố

Mắt Phố phát hiện sớm cháy và khói xe tại khu để xe (hầm giữ xe chung cư, nhà xe trong
nhà, sân để xe trước nhà) từ camera an ninh sẵn có. Hệ thống nhận diện lửa và khói trên
từng khung hình, chỉ báo động khi dấu hiệu lặp lại đủ lâu, nhờ mô hình thị giác–ngôn
ngữ xác minh thêm, rồi gửi cảnh báo kèm ảnh tới ứng dụng và người trực. Chỉ người trực
mới được bỏ qua một cảnh báo.

## Các khối

| Khối | Vai trò | Mã nguồn |
|---|---|---|
| `ai/` | pipeline phát hiện, xác minh, phát cảnh báo, console người trực | [ai/](ai/) (ở đây) |
| `backend/` | API, xác thực, lưu và phân phối cảnh báo | [nhánh `backend`](https://github.com/MinhTrietNg/HackathonSGU2026-MatPho/tree/backend) |
| `app/` | ứng dụng nhận và hiển thị cảnh báo | (chưa có link) |

Mỗi khối có README riêng hướng dẫn cài đặt và chạy.

## Benchmark và dữ liệu

[FireWatch-Model](https://github.com/MinhTrietNg/FireWatch-Model): benchmark R3, khoá
trước khi chạy.

## Lịch sử

[Model-Mat-Pho-](https://github.com/MinhTrietNg/Model-Mat-Pho-): lưu trữ, không cập
nhật.
