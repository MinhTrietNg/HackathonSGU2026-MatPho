# FireWatch chạy như dịch vụ: python -m firewatch serve với config.yaml.
# Hướng dẫn build, chạy và gắn vào docker-compose của backend: docs/van_hanh.md mục 7.
#
#   docker build -t firewatch FireWatchAI
#   docker run -d --restart unless-stopped -p 8000:8000 --env-file FireWatchAI/.env \
#     -e FIREWATCH_SOURCE=rtsp://camera/stream \
#     -v "$PWD/FireWatchAI/models:/app/models:ro" -v firewatch_events:/app/events \
#     firewatch
#
# Trọng số không nằm trong image: mount models/ (kiểm SHA-256 lúc khởi động bằng
# tools/kiem_trong_so.py, sai thì container dừng). .env không nằm trong image:
# truyền bằng --env-file / env_file.

FROM python:3.11-slim

ENV PYTHONUTF8=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# OpenCV cần libGL và glib kể cả khi không mở cửa sổ.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Phụ thuộc theo uv.lock. torch và torchvision lấy bản CPU (cùng phiên bản trong
# uv.lock) từ index của PyTorch: bản PyPI trên Linux kéo theo CUDA nhiều GB.
COPY --from=ghcr.io/astral-sh/uv:0.9.27 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-hashes --no-emit-project -o /tmp/req.txt \
    && grep -E '^(torch|torchvision)==' /tmp/req.txt | sed 's/ *;.*//' > /tmp/torch.txt \
    && grep -viE '^(torch|torchvision|nvidia-|cuda-|triton)' /tmp/req.txt > /tmp/req-cpu.txt \
    && pip install --index-url https://download.pytorch.org/whl/cpu -r /tmp/torch.txt \
    && pip install -r /tmp/req-cpu.txt \
    && rm /tmp/req.txt /tmp/torch.txt /tmp/req-cpu.txt

COPY README.md config.yaml run.sh ./
COPY src ./src
COPY tools ./tools
COPY models/README.md ./models/README.md
RUN pip install --no-deps . && mkdir -p /app/events /app/runs

# Thư mục event (JSON + ảnh keyframe, phục vụ /snapshots) và thư mục run.log.
VOLUME ["/app/events", "/app/runs"]
EXPOSE 8000

# /health trả 503 khi pipeline chết hoặc quá lâu không có heartbeat: urlopen ném
# lỗi, lệnh thoát khác 0, container thành unhealthy.
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"

ENV FIREWATCH_PYTHON=python
ENTRYPOINT ["sh", "/app/run.sh"]
# Pipeline chết thì serve thoát mã 1 để restart: unless-stopped khởi động lại.
CMD ["serve", "--host", "0.0.0.0", "--port", "8000", "--exit-on-pipeline-stop"]
