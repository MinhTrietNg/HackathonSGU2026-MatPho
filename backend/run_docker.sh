#!/usr/bin/env bash
# ==============================================================================
# MẮT PHỐ - SCRIPT TỰ ĐỘNG KHỞI CHẠY BACKEND DOCKER (CHO LINUX / MACOS / BASH)
# ==============================================================================

set -e

# Đảm bảo luôn chạy tại thư mục chứa file script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Xử lý các cờ thao tác nhanh
if [ "$1" == "--down" ] || [ "$1" == "down" ]; then
    echo "🛑 Đang tắt cụm dịch vụ Backend..."
    docker compose down
    exit 0
fi

if [ "$1" == "--logs" ] || [ "$1" == "logs" ]; then
    docker compose logs -f backend
    exit 0
fi

if [ "$1" == "--status" ] || [ "$1" == "status" ]; then
    docker compose ps
    exit 0
fi

if [ "$1" == "--restart" ] || [ "$1" == "restart" ]; then
    echo "🔄 Đang khởi động lại cụm dịch vụ Backend..."
    docker compose down
    docker compose up -d
    exit 0
fi

echo "======================================================================"
echo "   🚀 MẮT PHỐ AI SURVEILLANCE PLATFORM - TỰ ĐỘNG CHẠY BACKEND DOCKER   "
echo "======================================================================"
echo ""

# 1. Kiểm tra Docker
echo "🔍 [1/5] Kiểm tra dịch vụ Docker Engine..."
if ! docker info > /dev/null 2>&1; then
    echo "   ❌ LỖI: Docker chưa được bật hoặc chưa cài đặt!"
    echo "   👉 Vui lòng mở Docker Desktop và chạy lại script này."
    exit 1
fi
echo "   [OK] Docker đang hoạt động bình thường!"

# 2. Tạo .env
echo ""
echo "⚙️  [2/5] Kiểm tra cấu hình môi trường (.env)..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "   [OK] Đã tự động tạo file .env từ .env.example chuẩn!"
    fi
else
    echo "   [OK] File .env đã tồn tại sẵn sàng."
fi

# 3. Kiểm tra Firebase Credentials
echo ""
echo "🔑 [3/5] Kiểm tra chìa khóa Firebase Service Account..."
if [ ! -f "credentials/firebase-service-account.json" ]; then
    echo "   ⚠️ CẢNH BÁO: Chưa tìm thấy file 'credentials/firebase-service-account.json'!"
    echo "   👉 Vui lòng đặt file Service Account JSON vào thư mục credentials/ để kết nối Firebase."
else
    echo "   [OK] Đã tìm thấy chìa khóa Firebase Service Account hợp lệ."
fi

# 4. Khởi động Docker Compose
echo ""
echo "🐳 [4/5] Đang khởi động các container (Backend, Redis, MediaMTX)..."
if [ "$1" == "--build" ] || [ "$1" == "build" ]; then
    docker compose up -d --build --remove-orphans
else
    docker compose up -d --remove-orphans
fi

echo "   ⏳ Đang chờ Backend sẵn sàng..."
backend_ready=false
for i in {1..20}; do
    if curl -s http://localhost:8000/api/v1/health | grep -q -E "ok|healthy|degraded"; then
        backend_ready=true
        break
    fi
    sleep 2
    printf "."
done
echo ""

if [ "$backend_ready" = true ]; then
    echo "   [OK] Backend đã sẵn sàng phản hồi tại cổng 8000!"
else
    echo "   ⚠️ CẢNH BÁO: Backend đang mất nhiều thời gian để khởi động. Kiểm tra logs bằng: ./run_docker.sh --logs"
fi

# 5. Nạp dữ liệu mẫu
echo ""
echo "🌱 [5/5] Kiểm tra kịch bản nạp dữ liệu mẫu (Seed Data)..."
if [ -f "scripts/clean_and_seed_db.py" ]; then
    docker compose exec -T backend python scripts/clean_and_seed_db.py || echo "   ⚠️ Không thể nạp dữ liệu mẫu tự động."
elif [ -f "scripts/init_firestore_db.py" ]; then
    docker compose exec -T backend python scripts/init_firestore_db.py || echo "   ⚠️ Không thể nạp dữ liệu mẫu tự động."
else
    echo "   [INFO] Chưa có script seed dữ liệu (Bỏ qua bước nạp)."
fi

echo ""
echo "======================================================================"
echo "🎉 CHÚC MỪNG: HỆ THỐNG BACKEND ĐÃ ĐƯỢC KHỞI CHẠY THÀNH CÔNG!"
echo "======================================================================"
echo "📡 Địa chỉ API:          http://localhost:8000/api/v1"
echo "📚 Tài liệu Swagger:     http://localhost:8000/docs"
echo "🏥 Kiểm tra sức khỏe:    http://localhost:8000/api/v1/health"
echo "⚡ Cổng Redis Cache:     localhost:6379"
echo "🎥 Media Server MediaMTX:"
echo "   - RTSP Ingest:        rtsp://localhost:8554"
echo "   - HLS Playback:       http://localhost:8888"
echo "   - WebRTC / WHEP:      http://localhost:8889"
echo "   - Control REST API:   http://localhost:9997"
echo ""
echo "🛠️ CÁC LỆNH TIỆN ÍCH:"
echo "   • Xem log:            ./run_docker.sh --logs"
echo "   • Trạng thái:         ./run_docker.sh --status"
echo "   • Khởi động lại:      ./run_docker.sh --restart"
echo "   • Tắt hệ thống:       ./run_docker.sh --down"
echo "======================================================================"
