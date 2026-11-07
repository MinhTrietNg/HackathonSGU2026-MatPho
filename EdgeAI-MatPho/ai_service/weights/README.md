# Thư Mục Lưu Trữ Trọng Số Mô Hình AI (AI Model Weights)

Đặt file trọng số mô hình phát hiện cháy / khói của bạn vào thư mục này:

- Ví dụ:
  - `fire_yolo26n.onnx`
  - `fire_model.pt`
  - `fire_model.engine` (đối với NVIDIA TensorRT trên Jetson)

Khởi chạy container AI với trọng số:
```powershell
docker compose --profile ai up -d --build
```
Log tiến trình suy luận:
```powershell
docker logs -f edge_ai_service
```
