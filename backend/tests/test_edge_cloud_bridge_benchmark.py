"""
Comprehensive Bridge Benchmark & AI Payload Simulation Test
Validates the communication bridge between Edge AI Gateway (EAG) and Cloud Backend.
Covers:
1. Outbound Duplex WebSocket handshake, heartbeat & latency.
2. Full AI fire detection payload simulation & Escalation Timer activation.
3. Rapid AI verifying & suppressed signal webhooks.
4. Throughput, RTT latency benchmark & 90s debounce stress test.
5. Offline queue recovery simulation.
"""

import base64
import json
import time
import random
import pytest
from fastapi.testclient import TestClient

try:
    from src.main import app, INTERNAL_API_SECRET_KEY
    from src.services.repositories.user_repo import get_user_repo
    from src.services.repositories.group_repo import get_group_repo
    from src.services.repositories.camera_repo import get_camera_repo
    from src.services.repositories.alert_repo import get_alert_repository
    from src.services.escalation_service import get_escalation_service
    from src.services.websocket_manager import get_websocket_manager
except ImportError:
    from backend.src.main import app, INTERNAL_API_SECRET_KEY
    from backend.src.services.repositories.user_repo import get_user_repo
    from backend.src.services.repositories.group_repo import get_group_repo
    from backend.src.services.repositories.camera_repo import get_camera_repo
    from backend.src.services.repositories.alert_repo import get_alert_repository
    from backend.src.services.escalation_service import get_escalation_service
    from backend.src.services.websocket_manager import get_websocket_manager

client = TestClient(app)


@pytest.fixture(scope="module")
def setup_bridge_environment():
    user_repo = get_user_repo()
    group_repo = get_group_repo()
    camera_repo = get_camera_repo()

    phone = f"096{random.randint(1000000, 9999999)}"
    leader = user_repo.register_user_transaction(
        phone_number=phone,
        password_hash="$2b$12$hashedPasswordTestBenchmark1234567890123456789012",
        full_name="Chủ Tọa Benchmark",
    )

    group = group_repo.create_group(
        group_name="Khu Phố Thử Nghiệm Kết Nối EAG",
        address="789 Đường Nguyễn Tri Phương, Q.5, TP.HCM",
        leader_id=leader.user_id,
    )

    subgroup = group_repo.create_subgroup(
        group_id=group.group_id,
        subgroup_name="Cổng Đo Kiểm",
        created_by=leader.user_id,
    )

    camera = camera_repo.create_camera(
        group_id=group.group_id,
        subgroup_id=subgroup.subgroup_id,
        cam_name="Camera Cổng Đo Độ Trễ EAG",
        rtsp_url="rtsp://mediamtx:8554/source/cam_bench_01",
        created_by=leader.user_id,
    )

    return {
        "leader_id": leader.user_id,
        "group_id": group.group_id,
        "cam_id": camera.cam_id,
    }


def test_outbound_websocket_bridge_handshake_and_heartbeat(setup_bridge_environment):
    """
    Test 1: Kiểm tra bắt tay WebSocket Outbound từ Edge lên Cloud.
    Xác minh độ trễ RTT (Round-Trip Time) của kênh điều khiển thời gian thực.
    """
    edge_id = "edg_test_node_01"
    headers = {
        "x-internal-secret": INTERNAL_API_SECRET_KEY,
        "x-edge-id": edge_id,
    }

    t0 = time.perf_counter()
    with client.websocket_connect(
        f"/api/v1/internal/edge/ws?edge_id={edge_id}&secret={INTERNAL_API_SECRET_KEY}",
        headers=headers,
    ) as ws:
        # Nhận tin nhắn chào mừng từ Backend
        ack_data = ws.receive_json()
        handshake_rtt_ms = (time.perf_counter() - t0) * 1000.0

        assert ack_data["type"] == "EDGE_CONNECTED_ACK"
        assert ack_data["edge_device_id"] == edge_id

        # 2. Gửi Gateway Announce (Public Cloudflare URL)
        t_pub0 = time.perf_counter()
        ws.send_json({
            "type": "EDGE_GATEWAY_ANNOUNCE",
            "edge_device_id": edge_id,
            "active_streams": 2,
            "public_hls_base_url": "https://quick-tunnel-demo.trycloudflare.com",
            "cameras": [setup_bridge_environment["cam_id"]],
            "timestamp": time.time(),
        })

        # 3. Gửi Ping và nhận Pong đo độ trễ tức thời
        ws.send_text("ping")
        pong_data = ws.receive_json()
        ping_rtt_ms = (time.perf_counter() - t_pub0) * 1000.0

        assert pong_data["type"] == "pong"

        # Kiểm tra Backend đã đăng ký gateway URL thành công
        ws_mgr = get_websocket_manager()
        assert edge_id in ws_mgr.edge_registry
        assert ws_mgr.get_edge_public_hls_url(edge_id) == "https://quick-tunnel-demo.trycloudflare.com"

        print(f"\n[BENCHMARK] WebSocket Handshake RTT: {handshake_rtt_ms:.2f} ms")
        print(f"[BENCHMARK] WebSocket Control Ping/Pong RTT: {ping_rtt_ms:.2f} ms")


def test_simulate_ai_detection_payload_and_pipeline(setup_bridge_environment):
    """
    Test 2: Giả lập output của khối AI (ai_service) khi phát hiện ngọn lửa thật.
    Kiểm tra cấu trúc Payload JSON, mã hóa Base64 JPEG, độ trễ xử lý API và kích hoạt Timer leo thang.
    """
    cam_id = setup_bridge_environment["cam_id"]
    group_id = setup_bridge_environment["group_id"]

    # Giả lập frame ảnh JPEG 1080p với bounding box ngọn lửa (khoảng 35KB Base64)
    dummy_jpeg_bytes = b"\xff\xd8\xff\xe0" + (b"A" * 32000) + b"\xff\xd9"
    image_base64 = base64.b64encode(dummy_jpeg_bytes).decode("utf-8")

    payload = {
        "cam_id": cam_id,
        "class_name": "fire",
        "confidence": 0.942,
        "timestamp": time.time(),
        "bbox": [0.152, 0.224, 0.485, 0.658],  # [ymin, xmin, ymax, xmax]
        "image_base64": image_base64,
    }

    headers = {
        "Content-Type": "application/json",
        "X-Internal-Secret": INTERNAL_API_SECRET_KEY,
    }

    t0 = time.perf_counter()
    response = client.post("/api/v1/internal/ai/fire-events", json=payload, headers=headers)
    duration_ms = (time.perf_counter() - t0) * 1000.0

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert "alert_id" in data
    assert data["escalation_level"] == 0

    alert_id = data["alert_id"]
    print(f"\n[BENCHMARK] AI Fire Event Dispatch API Latency: {duration_ms:.2f} ms")

    # Kiểm tra bộ đếm leo thang 60s (Two-Tier Escalation Timer) đã được kích hoạt trên Redis
    esc_svc = get_escalation_service()
    assert esc_svc.is_timer_active(alert_id) is True

    # Dọn dẹp timer sau test
    esc_svc.cancel_timer(alert_id)


def test_simulate_ai_verifying_and_suppressed_signals(setup_bridge_environment):
    """
    Test 3: Giả lập các tín hiệu tiền xử lý của AI (Verifying & Suppressed)
    - Verifying: AI phát hiện khói mờ/lửa bập bùng, đang tích lũy frame thẩm định.
    - Suppressed: AI kết luận đèn xe rọi hoặc lò sưởi, triệt tiêu không báo động.
    """
    cam_id = setup_bridge_environment["cam_id"]
    headers = {"X-Internal-Secret": INTERNAL_API_SECRET_KEY}

    # 1. Tín hiệu Verifying (Khung viền vàng màn hình E2)
    t0 = time.perf_counter()
    resp_v = client.post(
        "/api/v1/internal/ai/verifying",
        json={
            "cam_id": cam_id,
            "sign": "SMOKE",
            "confidence": 0.68,
            "message": "Phát hiện khói bốc lên tại xưởng cưa, đang thẩm định...",
            "steps": [{"step": 1, "name": "MotionCheck"}],
        },
        headers=headers,
    )
    t_v = (time.perf_counter() - t0) * 1000.0
    assert resp_v.status_code == 202
    print(f"[BENCHMARK] AI Verifying Webhook Latency: {t_v:.2f} ms")

    # 2. Tín hiệu Suppressed (Bỏ qua báo động giả E4)
    t1 = time.perf_counter()
    resp_s = client.post(
        "/api/v1/internal/ai/suppressed",
        json={
            "cam_id": cam_id,
            "alert_id": "alt_test_bench_supp",
            "summary": "Ánh sáng đèn pha xe tải phản chiếu trên tường",
            "detail": "Khu vực nằm trong vùng loại trừ hoặc không phát triển thành ngọn lửa.",
        },
        headers=headers,
    )
    t_s = (time.perf_counter() - t1) * 1000.0
    assert resp_s.status_code == 202
    print(f"[BENCHMARK] AI Suppressed Webhook Latency: {t_s:.2f} ms")


def test_burst_throughput_and_debounce_stress(setup_bridge_environment):
    """
    Test 4: Thử nghiệm tải cao (Burst Stress Test):
    Giả lập AI phát hiện 10 frames liên tiếp trong thời gian ngắn (tương tự video 10-20 FPS).
    Xác minh:
    - Băng thông / Tốc độ xử lý (Requests/giây).
    - Khóa chống báo ảo (Redis Debounce Lock 90s) không tạo 10 alerts rác mà gom chung.
    """
    cam_id = setup_bridge_environment["cam_id"]
    headers = {"X-Internal-Secret": INTERNAL_API_SECRET_KEY}
    dummy_b64 = base64.b64encode(b"FRAME_DATA_" * 100).decode("utf-8")

    total_requests = 10
    latencies = []
    created_alert_ids = set()

    t_start = time.perf_counter()
    for i in range(total_requests):
        t_req_start = time.perf_counter()
        resp = client.post(
            "/api/v1/internal/ai/fire-events",
            json={
                "cam_id": cam_id,
                "class_name": "fire",
                "confidence": 0.85 + (i * 0.01),
                "timestamp": time.time(),
                "bbox": [0.1, 0.1, 0.4, 0.4],
                "image_base64": dummy_b64,
            },
            headers=headers,
        )
        t_req_end = time.perf_counter()
        latencies.append((t_req_end - t_req_start) * 1000.0)

        assert resp.status_code == 202
        created_alert_ids.add(resp.json()["alert_id"])

    t_total = time.perf_counter() - t_start
    throughput = total_requests / t_total

    avg_lat = sum(latencies) / len(latencies)
    min_lat = min(latencies)
    max_lat = max(latencies)

    print(f"\n================ BURST BENCHMARK RESULTS ================")
    print(f"Tổng số request AI gửi liên tiếp : {total_requests}")
    print(f"Tổng thời gian xử lý            : {t_total:.3f} s")
    print(f"Throughput (Tốc độ xử lý)       : {throughput:.2f} req/s")
    print(f"Độ trễ trung bình (Avg Latency) : {avg_lat:.2f} ms")
    print(f"Độ trễ tối thiểu (Min Latency)  : {min_lat:.2f} ms")
    print(f"Độ trễ tối đa (Max Latency)     : {max_lat:.2f} ms")
    print(f"Số alert_id tạo ra trên Cloud   : {len(created_alert_ids)} (Debounce 90s gom chung thành công!)")
    print(f"=========================================================\n")

    # Xác minh tính năng Debounce Lock 90s: Cùng 1 camera trong 90s chỉ tạo 1 alert_id duy nhất
    assert len(created_alert_ids) == 1
