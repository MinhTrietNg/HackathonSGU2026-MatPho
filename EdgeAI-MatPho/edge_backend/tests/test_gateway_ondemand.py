"""
Unit tests for Edge Gateway Discovery and On-Demand Streaming Controller
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.gateway_discovery import (
    extract_tunnel_url_from_text,
    extract_tunnel_url_from_file,
    discover_public_hls_url,
)
from src.main import app, handle_cloud_command, state


@pytest.fixture
def test_client():
    return TestClient(app)


def test_extract_tunnel_url_from_text():
    sample_log = """
    2026-11-07T10:00:00Z INF +--------------------------------------------------------------------------------------------+
    2026-11-07T10:00:00Z INF |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
    2026-11-07T10:00:00Z INF |  https://alpha-beta-gamma.trycloudflare.com                                                |
    2026-11-07T10:00:00Z INF +--------------------------------------------------------------------------------------------+
    """
    url = extract_tunnel_url_from_text(sample_log)
    assert url == "https://alpha-beta-gamma.trycloudflare.com"

    assert extract_tunnel_url_from_text("") is None
    assert extract_tunnel_url_from_text("no tunnel here") is None


def test_extract_tunnel_url_from_file(tmp_path):
    log_file = tmp_path / "tunnel.log"
    log_file.write_text("Connected to https://my-edge-node-01.trycloudflare.com ready", encoding="utf-8")

    url = extract_tunnel_url_from_file(log_file)
    assert url == "https://my-edge-node-01.trycloudflare.com"

    missing = extract_tunnel_url_from_file(tmp_path / "nonexistent.log")
    assert missing is None


def test_discover_public_hls_url(tmp_path):
    # 1. Environment override takes precedence
    with patch.dict(os.environ, {"EDGE_PUBLIC_HLS_URL": "https://stream.matpho.vn"}):
        res = discover_public_hls_url()
        assert res == "https://stream.matpho.vn"

    # 2. Candidate log file
    log_file = tmp_path / "test_tunnel.log"
    log_file.write_text("Tunnel online at https://box-01.trycloudflare.com", encoding="utf-8")
    with patch.dict(os.environ, {"EDGE_PUBLIC_HLS_URL": ""}):
        res = discover_public_hls_url(fallback_url="http://localhost:8888", candidate_log_paths=[str(log_file)])
        assert res == "https://box-01.trycloudflare.com"

    # 3. Fallback when no env and no file
    with patch.dict(os.environ, {"EDGE_PUBLIC_HLS_URL": ""}):
        res = discover_public_hls_url(fallback_url="http://192.168.1.50:8888", candidate_log_paths=[])
        assert res == "http://192.168.1.50:8888"


@pytest.mark.asyncio
async def test_handle_cloud_command_gateway_and_ondemand():
    # 1. GET_GATEWAY command
    gw_res = await handle_cloud_command({"action": "GET_GATEWAY"})
    assert gw_res["type"] == "GATEWAY_INFO"
    assert "public_hls_base_url" in gw_res

    # 2. START_LIVE command
    start_res = await handle_cloud_command({"action": "START_LIVE", "cam_id": "cam_test_gw"})
    assert start_res["type"] == "LIVE_STARTED"
    assert start_res["cam_id"] == "cam_test_gw"
    assert "hls_stream_url" in start_res
    assert "webrtc_stream_url" in start_res

    # 3. KEEPALIVE_LIVE command
    keep_res = await handle_cloud_command({"action": "KEEPALIVE_LIVE", "cam_id": "cam_test_gw"})
    assert keep_res["type"] == "LIVE_KEEPALIVE_ACK"

    # 4. STOP_LIVE command
    stop_res = await handle_cloud_command({"action": "STOP_LIVE", "cam_id": "cam_test_gw"})
    assert stop_res["type"] == "LIVE_STOPPED"


def test_gateway_rest_api_endpoints(test_client):
    headers = {"X-Internal-Secret": "secure_internal_key_for_ai_and_worker_communication"}

    # 1. GET /api/v1/edge/gateway
    res = test_client.get("/api/v1/edge/gateway")
    assert res.status_code == 200
    data = res.json()
    assert "public_hls_base_url" in data
    assert "stream_mode" in data

    # 2. POST /api/v1/edge/cameras/{cam_id}/live/start
    res_start = test_client.post("/api/v1/edge/cameras/cam_rest_01/live/start", headers=headers)
    assert res_start.status_code == 200
    assert res_start.json()["status"] == "started"
    assert "hls_stream_url" in res_start.json()

    # 3. POST /api/v1/edge/cameras/{cam_id}/live/keepalive
    res_keep = test_client.post("/api/v1/edge/cameras/cam_rest_01/live/keepalive", headers=headers)
    assert res_keep.status_code == 200
    assert res_keep.json()["status"] == "alive"

    # 4. POST /api/v1/edge/cameras/{cam_id}/live/stop
    res_stop = test_client.post("/api/v1/edge/cameras/cam_rest_01/live/stop", headers=headers)
    assert res_stop.status_code == 200
    assert res_stop.json()["status"] in ("ACTIVE", "STOPPED")

    # 5. In on_demand mode:
    from dataclasses import replace
    new_settings = replace(state.settings, stream_mode="on_demand")
    with patch.object(state, "settings", new_settings):
        res_stop2 = test_client.post("/api/v1/edge/cameras/cam_rest_01/live/stop", headers=headers)
        assert res_stop2.status_code == 200
        assert res_stop2.json()["status"] == "STOPPED"
