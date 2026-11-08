"""
Unit & Integration Tests for Phase 7: Edge HTTPS Gateway & On-Demand Live Streaming
Validates cross-network public HLS routing, Edge registry and On-Demand commands.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

try:
    from src.main import app, INTERNAL_API_SECRET_KEY
    from src.services.websocket_manager import get_websocket_manager
    from src.routers.cameras import build_hls_url
    _CAM_REPO_PATCH_PATH = "src.routers.cameras.get_camera_repo"
except ImportError:
    from backend.src.main import app, INTERNAL_API_SECRET_KEY
    from backend.src.services.websocket_manager import get_websocket_manager
    from backend.src.routers.cameras import build_hls_url
    _CAM_REPO_PATCH_PATH = "backend.src.routers.cameras.get_camera_repo"


@pytest.fixture
def test_client():
    return TestClient(app)


def test_edge_registry_and_public_hls_url():
    ws_mgr = get_websocket_manager()
    edge_id = "edg_test_gateway_01"
    pub_url = "https://alpha-beta.trycloudflare.com"

    # Register edge node
    ws_mgr.register_edge_node(
        edge_id=edge_id,
        public_hls_base_url=pub_url,
        cameras=["cam_gw_01", "cam_gw_02"],
    )

    # Verify lookups
    assert ws_mgr.get_edge_public_hls_url(edge_id) == pub_url
    assert ws_mgr.get_edge_for_camera("cam_gw_01") == edge_id
    assert ws_mgr.get_edge_for_camera("cam_gw_02") == edge_id
    assert ws_mgr.get_edge_for_camera("cam_unknown") is None


def test_build_hls_url_with_and_without_edge_gateway():
    ws_mgr = get_websocket_manager()
    edge_id = "edg_test_tunnel_99"
    pub_url = "https://my-edge-box.trycloudflare.com"

    ws_mgr.register_edge_node(
        edge_id=edge_id,
        public_hls_base_url=pub_url,
        cameras=["cam_tunnel_99"],
    )

    # 1. With registered edge_device_id -> returns public tunnel URL
    url_with_edge = build_hls_url("cam_tunnel_99", edge_device_id=edge_id)
    assert url_with_edge.startswith("https://my-edge-box.trycloudflare.com/")
    assert "cam_tunnel_99/index.m3u8" in url_with_edge

    # 2. Without edge gateway, MEDIAMTX_HOST or request host -> no reachable address:
    #    None (never "http://localhost:8888/..." which the phone cannot open)
    with patch.dict("os.environ", {"MEDIAMTX_HOST": ""}):
        assert build_hls_url("cam_local_only") is None
        assert build_hls_url("cam_local_only", edge_device_id="edg_khong_ton_tai") is None


def test_camera_stream_keepalive_and_stop_endpoints(test_client):
    headers = {"Authorization": "Bearer usr_leader_matpho_01"}

    # Mock camera exists in repo
    mock_cam = MagicMock()
    mock_cam.cam_id = "cam_ondemand_01"
    mock_cam.group_id = "grp_test_ondemand"
    mock_cam.edge_device_id = "edg_test_gateway_01"

    with patch(_CAM_REPO_PATCH_PATH) as mock_cam_repo_fn:
        mock_repo = MagicMock()
        mock_repo.get_camera.return_value = mock_cam
        mock_cam_repo_fn.return_value = mock_repo

        # Keepalive
        res_keep = test_client.post("/api/v1/cameras/cam_ondemand_01/stream/keepalive", headers=headers)
        assert res_keep.status_code == 200
        assert res_keep.json() == {"status": "ok", "cam_id": "cam_ondemand_01"}

        # Stop
        res_stop = test_client.post("/api/v1/cameras/cam_ondemand_01/stream/stop", headers=headers)
        assert res_stop.status_code == 200
        assert res_stop.json() == {"status": "ok", "cam_id": "cam_ondemand_01"}
