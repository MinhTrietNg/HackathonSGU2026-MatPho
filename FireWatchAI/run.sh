#!/bin/sh
# Chạy FireWatch sau khi kiểm SHA-256 trọng số theo models/README.md.
# Sai hoặc thiếu file .pt thì dừng, không chạy. Mọi tham số chuyển nguyên cho
# "python -m firewatch", ví dụ:
#   ./run.sh serve --source rtsp://camera/stream
#   ./run.sh --set vlm.provider=mock run --source clip.mp4
# Đặt FIREWATCH_SOURCE thì "serve" không kèm --source sẽ chạy trên nguồn đó
# (cách container nhận URL camera).
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
