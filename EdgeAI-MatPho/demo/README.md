# Video demo: luồng luôn có hình, cháy khi bấm

Thư mục này chứa video cho chế độ demo của cụm Edge. Video không nằm trong git, mỗi máy
tự tạo. Thư mục vẫn được mount vào MediaMTX (`/demo`) nên phải tồn tại.

## Cách hoạt động

- `mediamtx/mediamtx.demo.yml` bật `alwaysAvailable` cho các path demo bên dưới. Khi không
  có ai phát, MediaMTX tự phát lặp file `<ten>_thuong.mp4` (cảnh bình thường), nên camera
  trên app không bao giờ mất hình, kể cả khi khởi động lại.
- `run_eag_ai.bat chay <ten>` phát `<ten>_chay.mp4` **một lần** vào cùng path. Hết clip,
  MediaMTX tự quay về cảnh thường. edge-backend đang đọc luồng không bị ngắt khi đổi nguồn.

| `<ten>`       | Path MediaMTX       | Link RTSP khi thêm camera trong app        |
|---------------|---------------------|--------------------------------------------|
| `cam_gara`    | `mock/cam_gara`     | `rtsp://mediamtx:8554/mock/cam_gara`       |
| `cam_xe_dien` | `mock/cam_xe_dien`  | `rtsp://mediamtx:8554/mock/cam_xe_dien`    |
| `cam_nha_xe`  | `mock/cam_nha_xe`   | `rtsp://mediamtx:8554/mock/cam_nha_xe`     |
| `cam_bai_xe`  | `mock/cam_bai_xe`   | `rtsp://mediamtx:8554/mock/cam_bai_xe`     |
| `fire_demo`   | `mock/fire_demo`    | `rtsp://mediamtx:8554/mock/fire_demo`      |
| `cam_01`      | `source/cam_01`     | `rtsp://127.0.0.1:8554/source/cam_01`      |

`cam_01` dùng chung video với `fire_demo`, nên cần cặp file `fire_demo_*` (lệnh
`chay cam_01` đọc `cam_01_chay.mp4`: chép `fire_demo_chay.mp4` sang tên đó).

## Bật chế độ demo

1. Đặt đủ cặp file `<ten>_thuong.mp4` và `<ten>_chay.mp4` cho mọi path trong
   `mediamtx.demo.yml` vào thư mục này. Thiếu một file `_thuong` thì MediaMTX không khởi động.
2. Thêm vào `EdgeAI-MatPho/.env`: `MEDIAMTX_CONFIG=./mediamtx/mediamtx.demo.yml`
3. Chạy lại cụm Edge: `run_eag_ai.bat`

Bỏ dòng ở bước 2 là về cấu hình thường.

## Định dạng bắt buộc

Clip cháy được phát bằng `-c copy` thay cho cảnh thường, nên mọi file phải cùng định dạng:
H.264 Main, 1280x720, 25 fps, GOP 25 khung (1 s), không B-frame, không tiếng.

```
ffmpeg -i vao.mp4 -an \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25,format=yuv420p" \
  -c:v libx264 -profile:v main -g 25 -keyint_min 25 -sc_threshold 0 -bf 0 \
  -movflags +faststart <ten>_chay.mp4
```

Cảnh thường lấy khung đầu của clip cháy (chưa có lửa) giữ 10 giây: trích khung đầu ra
`dau.png` rồi `ffmpeg -loop 1 -i dau.png -t 10` với cùng `-vf` và tham số mã hoá như trên.
