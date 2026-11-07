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
    """Test MediaMTX security hook endpoint (Q4)."""
    res = client.post("/api/v1/auth/stream-ticket", json={"path": "live/cam_mock", "query": "ticket=valid_token"})
    assert res.status_code == 200
    assert res.json()["status"] == "authorized"
