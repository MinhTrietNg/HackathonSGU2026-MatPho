# ==============================================================================
# Edge Backend Dockerfile (EdgeAI-MatPho - Master Spec v4.0)
# Python 3.11 with FFmpeg/libav and OpenCV headless
# ==============================================================================

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install FFmpeg and system dependencies needed for PyAV and networking
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libavfilter-dev \
    pkg-config \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create data directory for SQLite database
RUN mkdir -p /app/data

# Copy application source code
COPY src/ /app/src/

# Default entrypoint runs FastAPI + Background WebSocket sync
CMD ["python", "-m", "src.main"]
