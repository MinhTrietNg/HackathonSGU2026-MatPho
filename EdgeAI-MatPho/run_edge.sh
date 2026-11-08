#!/usr/bin/env bash
# ==============================================================================
# Mắt Phố - POSIX Shell Launcher for EdgeAI-MatPho Docker Stack
# Compatible with Linux, macOS, WSL, and On-Premise Edge Mini PCs
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

write_header() {
    echo -e "\n${CYAN}======================================================================${NC}"
    echo -e "  ${YELLOW}$1${NC}"
    echo -e "${CYAN}======================================================================${NC}"
}

assert_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo -e "${RED}[LỖI] Docker chưa được cài đặt trên hệ thống!${NC}"
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        echo -e "${RED}[LỖI] Docker daemon chưa chạy. Vui lòng bật Docker service rồi thử lại!${NC}"
        exit 1
    fi
}

# IP LAN của máy này để Cloud trả cho điện thoại địa chỉ HLS mở được (không tunnel).
# Ưu tiên EDGE_LAN_IP / EDGE_PUBLIC_HLS_URL đã đặt sẵn trong môi trường hoặc .env.
detect_lan_ip() {
    if [ -n "${EDGE_LAN_IP:-}" ] || [ -n "${EDGE_PUBLIC_HLS_URL:-}" ]; then
        return
    fi
    if [ -f ".env" ] && grep -Eq '^(EDGE_LAN_IP|EDGE_PUBLIC_HLS_URL)=.+$' .env; then
        return
    fi
    local ip=""
    if command -v hostname >/dev/null 2>&1 && hostname -I >/dev/null 2>&1; then
        ip="$(hostname -I | awk '{print $1}')"
    elif command -v ipconfig >/dev/null 2>&1 && ipconfig getifaddr en0 >/dev/null 2>&1; then
        ip="$(ipconfig getifaddr en0)"
    elif command -v ipconfig.exe >/dev/null 2>&1; then
        ip="$(ipconfig.exe | tr -d '
' | grep -m1 'IPv4' | sed 's/.*: *//')"
    fi
    if [ -n "$ip" ]; then
        export EDGE_LAN_IP="$ip"
        echo -e "${GREEN}[OK] IP LAN cho luồng HLS: ${ip} (ghi đè bằng EDGE_LAN_IP hoặc EDGE_PUBLIC_HLS_URL)${NC}"
    else
        echo -e "${YELLOW}[CẢNH BÁO] Không dò được IP LAN; đặt EDGE_LAN_IP trong .env nếu xem camera trong LAN.${NC}"
    fi
}

ensure_env() {
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            echo -e "${GREEN}[OK] Đã tự động tạo file .env từ .env.example.${NC}"
        fi
    fi
}

show_endpoints() {
    local with_mock="${1:-false}"
    write_header "THÔNG TIN CỔNG DỊCH VỤ KHỐI EDGE (EdgeAI-MatPho)"
    echo -e "  * RTSP Media Server  : ${GREEN}rtsp://localhost:8554/live/cam_01${NC}"
    echo -e "  * HLS Mobile Stream  : ${GREEN}http://localhost:8888/live/cam_01/index.m3u8${NC}"
    echo -e "  * WebRTC WHEP Stream : ${GREEN}http://localhost:8889/live/cam_01${NC}"
    echo -e "  * Edge Controller API: ${CYAN}http://localhost:8090/docs${NC}"
    echo -e "  * Health Check API   : ${CYAN}http://localhost:8090/api/v1/edge/health${NC}"
    echo -e "  * MediaMTX Control   : http://localhost:9997/v3/config/paths/list"
    if [ "$with_mock" = "true" ]; then
        echo -e "  * Camera Giả Lập OSD : ${YELLOW}rtsp://localhost:8554/mock/cam_test (ĐANG PHÁT LUỒNG)${NC}"
    fi
    echo -e "${CYAN}----------------------------------------------------------------------${NC}"
}

cmd_up() {
    local with_mock="${1:-false}"
    local with_gateway="${2:-false}"
    assert_docker
    ensure_env
    detect_lan_ip
    local profiles=()
    if [ "$with_mock" = "true" ]; then profiles+=("--profile" "mock"); fi
    if [ "$with_gateway" = "true" ]; then profiles+=("--profile" "gateway"); fi

    if [ "$with_gateway" = "true" ]; then
        write_header "KHỞI CHẠY KHỐI EDGE KÈM HTTPS GATEWAY (CLOUDFLARE TUNNEL)"
    elif [ "$with_mock" = "true" ]; then
        write_header "KHỞI CHẠY KHỐI EDGE KÈM CAMERA GIẢ LẬP (--profile mock)"
    else
        write_header "KHỞI CHẠY KHỐI EDGE TIÊU CHUẨN (3 CONTAINERS)"
    fi

    if [ ${#profiles[@]} -gt 0 ]; then
        docker compose "${profiles[@]}" up -d --build
    else
        docker compose up -d --build
    fi
    echo -e "${GREEN}[OK] Đã khởi chạy thành công!${NC}"
    show_endpoints "$with_mock"
}

cmd_down() {
    assert_docker
    write_header "DỪNG TOÀN BỘ CỤM EDGE"
    docker compose --profile mock --profile gateway down
    echo -e "${GREEN}[OK] Đã dừng toàn bộ containers.${NC}"
}

cmd_restart() {
    assert_docker
    cmd_down
    cmd_up false false
}

cmd_logs() {
    assert_docker
    write_header "XEM LOGS TRỰC TIẾP (Ctrl+C để thoát)"
    docker compose --profile mock --profile gateway logs -f --tail 100
}

cmd_status() {
    assert_docker
    write_header "TRẠNG THÁI CONTAINERS KHỐI EDGE"
    docker compose --profile mock --profile gateway ps
    echo ""
    echo -e "${CYAN}Kiểm tra phản hồi Healthcheck Edge Backend (:8090)...${NC}"
    curl -s http://localhost:8090/api/v1/edge/health || echo -e "${YELLOW}Chưa phản hồi (Container đang khởi động)${NC}"
    echo ""
    echo -e "${CYAN}Kiểm tra Edge Gateway Discovery (:8090)...${NC}"
    curl -s http://localhost:8090/api/v1/edge/gateway || echo -e "${YELLOW}Chưa có phản hồi gateway${NC}"
    echo ""
}

cmd_clean() {
    assert_docker
    write_header "DỌN DẸP SẠCH CỤM EDGE (XÓA VOLUMES DỮ LIỆU SQLITE)"
    read -p "Bạn có chắc chắn muốn xóa toàn bộ containers và volumes SQLite? (y/N): " -r confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        docker compose --profile mock --profile gateway down -v --remove-orphans
        echo -e "${GREEN}[OK] Đã xóa sạch containers và volume.${NC}"
    else
        echo "Đã hủy thao tác."
    fi
}

cmd_menu() {
    while true; do
        write_header "MENU QUẢN LÝ DOCKER KHỐI EDGEAI-MATPHO"
        echo "  1. Khởi chạy cụm Edge tiêu chuẩn       (docker compose up -d --build)"
        echo "  2. Khởi chạy KÈM Camera Giả Lập        (docker compose --profile mock up -d)"
        echo "  3. Khởi chạy KÈM HTTPS Gateway Tunnel  (docker compose --profile gateway up -d)"
        echo "  4. Xem Logs thời gian thực             (docker compose logs -f)"
        echo "  5. Kiểm tra trạng thái & Sức khỏe      (docker compose ps & healthcheck)"
        echo "  6. Khởi động lại cụm Edge              (docker compose restart)"
        echo "  7. Dừng cụm Edge                       (docker compose down)"
        echo "  8. Dọn dẹp sạch (Xóa Containers & Vol) (docker compose down -v)"
        echo "  0. Thoát"
        echo -e "${CYAN}----------------------------------------------------------------------${NC}"
        read -p "Nhập lựa chọn của bạn [0-8]: " -r choice
        case "$choice" in
            1) cmd_up false false; break ;;
            2) cmd_up true false; break ;;
            3) cmd_up true true; break ;;
            4) cmd_logs; break ;;
            5) cmd_status; break ;;
            6) cmd_restart; break ;;
            7) cmd_down; break ;;
            8) cmd_clean; break ;;
            0) exit 0 ;;
            *) echo -e "${YELLOW}Lựa chọn không hợp lệ!${NC}" ;;
        esac
    done
}

ACTION="${1:-}"
case "$ACTION" in
    up|start)              cmd_up false false ;;
    up-mock|mock)          cmd_up true false ;;
    up-gateway|gateway)    cmd_up true true ;;
    down|stop)             cmd_down ;;
    restart)               cmd_restart ;;
    logs)                  cmd_logs ;;
    status|ps)             cmd_status ;;
    clean)                 cmd_clean ;;
    *)                     cmd_menu ;;
esac
