from src.probe import CameraProbeService, parse_rtsp_host_and_vendor


def test_parse_rtsp_host_and_vendor():
    host, vendor = parse_rtsp_host_and_vendor("rtsp://admin:123@192.168.1.10:554/Streaming/Channels/101")
    assert host == "192.168.1.10"
    assert "Hikvision" in vendor

    host2, vendor2 = parse_rtsp_host_and_vendor("rtsp://admin:123@192.168.1.20:554/cam/realmonitor")
    assert "Dahua" in vendor2

    host3, vendor3 = parse_rtsp_host_and_vendor("rtsp://192.168.1.30:554/imou_live")
    assert "Imou" in vendor3


def test_probe_invalid_url_format():
    svc = CameraProbeService()
    res = svc.probe_rtsp("http://not-an-rtsp-url.com")
    assert res["is_accessible"] is False
    assert res["error_code"] == "CAMERA_NOT_REACHABLE"


def test_probe_mock_success():
    svc = CameraProbeService()
    res = svc.probe_rtsp("rtsp://mock-camera.lan:554/live")
    assert res["is_accessible"] is True
    assert res["resolution"] == "1920x1080"
    assert res["fps"] == 25
    assert "preview_snapshot_base64" in res


def test_probe_mock_auth_fail():
    svc = CameraProbeService()
    res = svc.probe_rtsp("rtsp://auth-fail.lan:554/live")
    assert res["is_accessible"] is False
    assert res["error_code"] == "CAMERA_AUTH_FAILED"
