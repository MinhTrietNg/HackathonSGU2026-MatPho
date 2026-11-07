import pytest
from fastapi.testclient import TestClient
from src.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["service"] == "edge-backend"
    assert "edge_device_id" in data


def test_status_endpoint(client):
    res = client.get("/api/v1/status")
    assert res.status_code == 200
    data = res.json()
    assert "sessions" in data


def test_stream_ticket_auth_hook(client):
    """Test MediaMTX security hook endpoint."""
    res = client.post(
        "/api/v1/auth/stream-ticket",
        json={"path": "live/cam_mock", "query": "ticket=valid_token"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "authorized"


def test_sync_camera_returns_hls_and_rtsp_urls(client):
    """Verify syncing a camera returns HLS playback URL for App and RTSP URL for AI (Q1 & Q4)."""
    res = client.post(
        "/api/v1/edge/cameras",
        json={
            "cam_id": "cam_hls_01",
            "cam_name": "Camera Cổng 1",
            "rtsp_url": "rtsp://mediamtx:8554/live/cam_hls_01",  # triggers anti-loopback rewrite
            "watch_area": {"left": 0.1, "top": 0.2, "width": 0.5, "height": 0.4},
            "is_active": False,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["cam_id"] == "cam_hls_01"
    assert data["hls_stream_url"].endswith("/live/cam_hls_01/index.m3u8")
    assert data["rtsp_output_url"].endswith("/live/cam_hls_01")

    # Verify list cameras returns the synced camera with watch_area and HLS URL
    list_res = client.get("/api/v1/edge/cameras")
    assert list_res.status_code == 200
    cams = list_res.json()["cameras"]
    matched = [c for c in cams if c["cam_id"] == "cam_hls_01"]
    assert len(matched) == 1
    assert matched[0]["watch_area"] == {"left": 0.1, "top": 0.2, "width": 0.5, "height": 0.4}
    assert matched[0]["hls_stream_url"].endswith("/live/cam_hls_01/index.m3u8")

    # Clean up
    del_res = client.delete("/api/v1/edge/cameras/cam_hls_01")
    assert del_res.status_code == 200
