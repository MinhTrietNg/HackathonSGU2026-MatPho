"""Báo động cháy chờ ảnh pha 2 bằng tín hiệu, không chặn event loop.

Repo, WebSocket, FCM và Redis đều là bản giả: test không chạm Firestore thật.
"""

import asyncio
import time
from types import SimpleNamespace

import pytest

from src.models.fire_alert import AIFireEventPayload, AISnapshotUploadPayload
from src.routers import internal_ai as ia

URL_ANH = "https://storage.example/anh.jpg"
TAI_ANH_S = 0.3  # thời gian giả lập tải ảnh lên Storage (chặn, chạy trong thread)


class _Ws:
    def __init__(self) -> None:
        self.bao_dong: list[tuple[float, dict]] = []

    async def broadcast_fire_alert(self, group_id, alert_payload, escalation_level):
        self.bao_dong.append((time.monotonic(), alert_payload))

    async def broadcast_alert_snapshot_ready(self, **_):
        return None


def _ban_ghi(alert_id: str = "alt_1") -> SimpleNamespace:
    return SimpleNamespace(
        alert_id=alert_id, event_id="ev_1", group_id="grp_1", cam_name="Cam",
        location_name="Kho", subgroup_name=None, status="OPEN",
        verification="UNVERIFIED", sign="FIRE", still_url=None, fire_image_url=None,
        summary="", detail="", detected_at=None, model_dump=lambda: {},
    )


@pytest.fixture
def gia(monkeypatch):
    ws = _Ws()

    def tai_anh(**_):
        time.sleep(TAI_ANH_S)  # I/O chặn như Storage thật
        return SimpleNamespace(still_url=URL_ANH, fire_image_url=None,
                               group_id="grp_1", alert_id="alt_1")

    repo_canh_bao = SimpleNamespace(
        upsert_fire_incident_signal=lambda p: (_ban_ghi(), True, {}),
        attach_incident_snapshot=tai_anh,
    )
    camera = SimpleNamespace(ai_mode="ALWAYS", is_ai_enabled=True, ai_schedules=[])
    esc = SimpleNamespace(is_timer_active=lambda _id: False,
                          start_timer=lambda **_: None,
                          cancel_timer=lambda _id: None, _redis=None)
    monkeypatch.setattr(ia, "get_alert_repository", lambda: repo_canh_bao)
    monkeypatch.setattr(ia, "get_camera_repository",
                        lambda: SimpleNamespace(get_camera=lambda _c: camera))
    monkeypatch.setattr(ia, "get_group_repository",
                        lambda: SimpleNamespace(list_members=lambda _g: []))
    monkeypatch.setattr(ia, "get_user_repository", lambda: SimpleNamespace())
    monkeypatch.setattr(ia, "get_websocket_manager", lambda: ws)
    monkeypatch.setattr(ia, "get_fcm_service", lambda: SimpleNamespace())
    monkeypatch.setattr(ia, "get_escalation_service", lambda: esc)
    monkeypatch.setattr(ia, "should_ai_scan_now", lambda *_: True)
    ia._anh_san_sang.clear()
    ia._anh_url.clear()
    return ws


def _su_kien() -> AIFireEventPayload:
    return AIFireEventPayload(event_id="ev_1", cam_id="cam_1", severity="CRITICAL")


async def _cho_nen() -> None:
    while ia._tac_vu_nen:
        await asyncio.gather(*list(ia._tac_vu_nen))


def test_bao_dong_phat_ngay_khi_anh_toi_va_kem_url(gia):
    async def chay():
        await ia.receive_ai_fire_events(_su_kien(), authorized=True)
        # Event loop phải chạy tiếp trong lúc ảnh đang tải (trước đây đứng ~4 s).
        nhip = 0

        async def dem() -> None:
            nonlocal nhip
            while True:
                await asyncio.sleep(0.02)
                nhip += 1

        dem_task = asyncio.create_task(dem())
        await ia.upload_ai_snapshot(
            "ev_1",
            AISnapshotUploadPayload(event_id="ev_1", cam_id="cam_1",
                                    snapshot_base64="AAAA"),
            authorized=True,
        )
        anh_xong = time.monotonic()
        dem_task.cancel()
        await _cho_nen()
        return nhip, anh_xong

    nhip, anh_xong = asyncio.run(chay())
    assert nhip >= 5, "event loop bị chặn trong lúc tải ảnh"
    assert len(gia.bao_dong) == 1
    luc, payload = gia.bao_dong[0]
    assert payload["still_url"] == URL_ANH
    # Báo động ra ngay sau khi ảnh xong, không đợi hết hạn chờ.
    assert luc - anh_xong < 0.2


def test_khong_co_anh_thi_van_bao_dong_khi_het_han(gia, monkeypatch):
    monkeypatch.setattr(ia, "CHO_ANH_BAO_CAO_S", 0.2)

    async def chay():
        bat_dau = time.monotonic()
        await ia.receive_ai_fire_events(_su_kien(), authorized=True)
        await _cho_nen()
        return bat_dau

    bat_dau = asyncio.run(chay())
    assert len(gia.bao_dong) == 1
    luc, payload = gia.bao_dong[0]
    assert payload["still_url"] is None
    assert 0.15 <= luc - bat_dau < 1.0
