import base64
import numpy as np
import pytest
from src.config import AISettings
from src.inference_stub import DetectionResult, MockFireModel
from src.masking import (
    apply_watch_area_mask,
    is_bbox_in_watch_area,
    normalize_watch_area_to_polygon,
)
from src.webhook_client import CloudWebhookClient, encode_frame_to_base64_jpeg


def test_ai_settings_default():
    """Verify default runtime settings for AI service."""
    settings = AISettings()
    assert settings.ai_sampling_fps == 1.0
    assert settings.ai_confidence_threshold == 0.60
    assert settings.alert_cooldown_seconds == 30.0
    assert settings.mediamtx_rtsp_url == "rtsp://mediamtx:8554"
    assert settings.rtsp_url_for("cam_01") == "rtsp://mediamtx:8554/live/cam_01"


def test_detection_result_dataclass():
    """Verify DetectionResult dataclass structure."""
    det = DetectionResult(class_name="fire", confidence=0.95, bbox=[0.1, 0.2, 0.4, 0.5])
    assert det.class_name == "fire"
    assert det.confidence == 0.95
    assert len(det.bbox) == 4


def test_mock_fire_model():
    """Verify MockFireModel stub interface."""
    model = MockFireModel()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    results = model.predict(frame)
    assert isinstance(results, list)
    assert len(results) == 0


def test_watch_area_masking_polygon_and_rectangle():
    """Verify both Polygon list and Rectangle dict watch_area formats mask pixels outside watch_area (Q2)."""
    frame = np.full((100, 100, 3), 255, dtype=np.uint8)

    # 1. Without watch area -> unchanged
    unmasked = apply_watch_area_mask(frame, None)
    assert np.array_equal(unmasked, frame)

    # 2. Polygon covering center box [0.2, 0.2] to [0.8, 0.8]
    poly_area = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
    masked_poly = apply_watch_area_mask(frame, poly_area)
    assert np.all(masked_poly[10, 10] == [0, 0, 0])
    assert np.all(masked_poly[90, 90] == [0, 0, 0])
    assert np.all(masked_poly[50, 50] == [255, 255, 255])

    # 3. Rectangle dict (from App I5 / Cloud Backend) covering [0.2, 0.2] to [0.8, 0.8]
    rect_area = {"left": 0.2, "top": 0.2, "width": 0.6, "height": 0.6}
    assert np.allclose(normalize_watch_area_to_polygon(rect_area), poly_area)
    masked_rect = apply_watch_area_mask(frame, rect_area)
    assert np.all(masked_rect[10, 10] == [0, 0, 0])
    assert np.all(masked_rect[90, 90] == [0, 0, 0])
    assert np.all(masked_rect[50, 50] == [255, 255, 255])


def test_is_bbox_in_watch_area():
    """Verify post-inference BBox overlap check works with both Rectangle dict and Polygon list."""
    rect_area = {"left": 0.2, "top": 0.2, "width": 0.6, "height": 0.6}
    # Inside [20..80, 20..80] on a 100x100 frame
    assert is_bbox_in_watch_area([30, 30, 60, 60], rect_area, 100, 100) is True
    # Outside top-left corner [0..15, 0..15]
    assert is_bbox_in_watch_area([0, 0, 15, 15], rect_area, 100, 100) is False


def test_encode_frame_to_base64_jpeg():
    """Verify JPEG frame encoding to Base64."""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    b64_str = encode_frame_to_base64_jpeg(frame, quality=80)
    assert isinstance(b64_str, str)
    decoded = base64.b64decode(b64_str)
    assert decoded[:2] == b"\xff\xd8"


@pytest.mark.asyncio
async def test_cloud_webhook_client_fire_event(monkeypatch):
    """Verify CloudWebhookClient formats payload and dispatches with X-Internal-Secret."""
    settings = AISettings(
        cloud_backend_url="https://mock.backend.vn",
        internal_api_secret_key="secret_test_key",
    )
    client = CloudWebhookClient(settings)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    captured_request = {}

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def post(self, url, json=None, headers=None):
            captured_request["url"] = url
            captured_request["json"] = json
            captured_request["headers"] = headers

            class MockResponse:
                status_code = 202
                text = "Accepted"

            return MockResponse()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    ok = await client.report_fire_event(
        cam_id="cam_01",
        class_name="fire",
        confidence=0.945,
        bbox=[0.1, 0.2, 0.3, 0.4],
        frame_bgr=frame,
        timestamp=1730000000.0,
    )

    assert ok is True
    assert captured_request["url"] == "https://mock.backend.vn/api/v1/internal/ai/fire-events"
    assert captured_request["headers"]["X-Internal-Secret"] == "secret_test_key"
    payload = captured_request["json"]
    assert payload["cam_id"] == "cam_01"
    assert payload["class_name"] == "fire"
    assert payload["confidence"] == 0.945
    assert payload["bbox"] == [0.1, 0.2, 0.3, 0.4]
    assert payload["image_base64"] is not None
