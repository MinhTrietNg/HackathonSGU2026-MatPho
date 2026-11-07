#!/bin/sh
# Chạy FireWatch sau khi kiểm SHA-256 trọng số theo models/README.md.
# Sai hoặc thiếu file .pt thì dừng, không chạy. Mọi tham số chuyển nguyên cho
# "python -m firewatch", ví dụ:
#   ./run.sh serve --source rtsp://camera/stream
#   ./run.sh --set vlm.provider=mock run --source clip.mp4
# Đặt FIREWATCH_SOURCE thì "serve" không kèm --source sẽ chạy trên nguồn đó
# (cách container nhận URL camera). Image chạy "edge" (chế độ nút biên); xem
# docs/van_hanh.md mục 11.
set -eu
cd "$(dirname "$0")"

# Trình thông dịch: FIREWATCH_PYTHON nếu đặt, rồi .venv của thư mục này, rồi python3.
if [ -n "${FIREWATCH_PYTHON:-}" ]; then
    PY=$FIREWATCH_PYTHON
elif [ -x .venv/bin/python ]; then
    PY=.venv/bin/python
elif [ -x .venv/Scripts/python.exe ]; then
    PY=.venv/Scripts/python.exe
else
    PY=python3
fi
export PYTHONUTF8=1

# Trọng số gắn từ ngoài: docker-compose của EdgeAI-MatPho gắn ai_service/weights
# vào /app/weights, chỉ đọc. Chép .pt rồi mới chép .onnx sang models/ (ghi được),
# để ONNX mới hơn .pt và detector không phải export lại. Thư mục không có thì bỏ
# qua; file cùng tên trong models/ bị ghi đè bằng bản gắn ngoài.
W=${FIREWATCH_WEIGHTS_DIR:-/app/weights}
if [ -d "$W" ]; then
    for f in "$W"/*.pt; do
        if [ -f "$f" ]; then cp "$f" models/; echo "chép $f -> models/"; fi
    done
    for f in "$W"/*.onnx; do
        if [ -f "$f" ]; then
            cp "$f" models/ && touch "models/$(basename "$f")"
            echo "chép $f -> models/"
        fi
    done
fi

"$PY" tools/kiem_trong_so.py

case " $* " in
    *" serve "*)
        case " $* " in
            *" --source "*) ;;
            *) if [ -n "${FIREWATCH_SOURCE:-}" ]; then
                   set -- "$@" --source "$FIREWATCH_SOURCE"
               fi ;;
        esac ;;
esac

exec "$PY" -m firewatch "$@"
