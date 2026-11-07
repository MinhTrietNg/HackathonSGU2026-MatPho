# ==============================================================================
# Mắt Phố - FastAPI Backend Dockerfile
# Cloud Core Gateway (Production & Local Development Container)
# ==============================================================================

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code (fallback for standalone production image build)
COPY . .

# Expose FastAPI REST and WebSocket port
EXPOSE 8000
EXPOSE 8080

# Healthcheck to verify FastAPI responsiveness
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/v1/health || exit 1

# Start Uvicorn ASGI server with dynamic port support (Cloud Run / Docker default)
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
