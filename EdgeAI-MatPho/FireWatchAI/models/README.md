# models/: trọng số detector

Trọng số không nằm trong git (`*.pt`, `*.onnx` bị ignore). Thư mục này chỉ commit file
README này. Danh tính của model là **SHA-256 của file `.pt`**, không phải tên file.

## Model vận hành

| Mục | Giá trị |
|---|---|
| Model | FireWatch-v2.0 (YOLO26n, 2 lớp: 0 = fire, 1 = smoke) |
| File `.pt` | `firewatch-v2.0.pt`, SHA-256 `58def3d0c45c7faca9c1f93207be174d99cb736341e55b3d5b3f354461108ea6` |
| File ONNX 640 | `firewatch-v2.0_640.onnx`, SHA-256 `9d2e93b24ccfd51b013c797696e37cd27873d564acc2ddd2f07dec0097792854` |
| Khai trong config | `detector.weights: models/firewatch-v2.0.pt`, `detector.backend: onnx`, `imgsz: 640` |
| Nguồn đăng ký | [FireWatch-Model](https://github.com/MinhTrietNg/FireWatch-Model) @ `6652f9a`, file `models/SHA256SUMS` và bảng trong `models/README.md` |
| Vai trò trong R3 | cặp chính (model card `reports/model_cards/firewatch-v2.0.md` của FireWatch-Model) |

Bảng đối chiếu tên file cũ sang tên mới nằm ở `CHANGELOG.md` của FireWatch-Model.

## Lấy file và kiểm

Chép theo đúng thứ tự: **`.pt` trước, ONNX sau**.

```bash
cd EdgeAI-MatPho/FireWatchAI
cp <FireWatch-Model>/models/firewatch-v2.0.pt models/
cp <FireWatch-Model>/models/firewatch-v2.0_640.onnx models/
touch models/firewatch-v2.0_640.onnx      # bảo đảm ONNX mới hơn .pt
sha256sum models/firewatch-v2.0.pt models/firewatch-v2.0_640.onnx
```

Hai dòng SHA phải trùng bảng trên, cũng là các dòng tương ứng trong `SHA256SUMS` của
FireWatch-Model.

Vì sao phải theo thứ tự: với `backend: onnx`, detector dùng `models/<tên>_640.onnx` nếu
file đó tồn tại và **mtime không cũ hơn** file `.pt`. Ngược lại, nó tự export ONNX mới
từ `.pt` và ghi đè. Nhiều lệnh chép giữ nguyên mtime gốc, và trong FireWatch-Model hai
file có mtime gần như bằng nhau, nên phải chạm lại ONNX sau khi chép.

ONNX lệch SHA chỉ có nghĩa là file đã được export lại trên máy này. Model vẫn là
FireWatch-v2.0 nếu SHA của `.pt` đúng. Khi đó kết quả có thể khác chút ít so với bản ONNX
đã đăng ký.

## Kiểm tương đương `.pt` và ONNX (2026-11-07)

Cách kiểm: 50 ảnh lấy ngẫu nhiên từ `val.txt` của DataFireWatch-v2.0 (`random.Random(0)`).
Dùng `conf` 0,25, `imgsz` 640, CPU, ultralytics 8.4.198, onnxruntime 1.31.1. Mỗi box của
`.pt` được ghép với box ONNX cùng lớp có IoU cao nhất.

| Đầu vào | Box `.pt` | Không khớp | 1 − IoU lớn nhất | Lệch conf lớn nhất |
|---|---|---|---|---|
| Cùng một ảnh đã letterbox sẵn 640×640 | 36 | 0 | 0,000005 | 0,0000015 |
| Ảnh gốc, mỗi backend tự tiền xử lý | 35 | 1 | 0,043 | 0,056 |

Ngưỡng đặt trước: lệch IoU < 0,01 và lệch conf < 0,005.
- Dòng 1 **đạt**: file ONNX là bản export đúng của `.pt`.
- Dòng 2 **không đạt**: ultralytics letterbox ảnh cho `.pt` theo khung chữ nhật nhỏ nhất,
  còn ONNX tĩnh luôn nhận khung vuông 640. Hai backend vì vậy cho box và conf khác nhau
  chút ít trên cùng một ảnh.
- Pipeline chạy `backend: onnx`. Số đo nào làm bằng `.pt` thì không thay thế trực tiếp
  cho hành vi của pipeline.

## Tồn đọng

- Detector nên kiểm SHA-256 của ONNX theo `.pt` thay vì so mtime. Chưa làm vì
  `src/firewatch/detector.py` đang khoá.
