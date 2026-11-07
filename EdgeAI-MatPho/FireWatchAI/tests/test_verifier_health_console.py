"""Verifier bền vững: ``/health`` (kịch bản 11), ``reason: "verifier"`` trên
WebSocket và console người trực.

Kịch bản 11: ``GET /health`` trả đủ khối ``verifier`` (cầu dao, hàng chờ, tỉ lệ
kịp, p50 / p95 cửa sổ 10 phút, số lần VLM_OFF) và vẫn đủ trường cũ; cờ tắt thì
không có khối này. Đồng hồ giả, VLM giả như các test verifier khác.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from firewatch.alerts import EventStore, VerifierInfo, event_to_dict, sample_event
from firewatch.pipeline import Pipeline, PipelineHealth, RunSummary
from firewatch.server import CONSOLE_HTML, create_app, ws_payload
from firewatch.vlm import GeminiHTTPError, VerificationService

import he_verifier as hv
import kich_ban_verifier as kb

TRUONG_CU = {"status", "pipeline", "vlm_provider"}
TRUONG_PIPELINE_CU = {"status", "heartbeats", "alerts", "last_heartbeat_age_s",
                      "uptime_s", "source_live", "error"}
TRUONG_VERIFIER = {"breaker", "breaker_opens", "queued", "window_s",
                   "requests_in_window", "answered_ratio_in_window",
                   "latency_p50_ms", "latency_p95_ms", "vlm_off_total"}
DONG_CAN_NGUOI = "Xác minh tự động không khả dụng, cần người xác thực"


def _health(h) -> PipelineHealth:
    health = PipelineHealth()
    health.beat()
    health.verifier_stats = h.dp.thong_ke
    return health


def _so_verified(h) -> int:
    return sum(1 for e in h.store.all() if e.verifier.status == "VERIFIED")


# ------------------------------------------------------------- kịch bản 11
def test_kich_ban_11_health_du_truong_moi_va_giu_truong_cu(he):
    h = he(max_workers=2)
    client = TestClient(create_app(h.cfg, h.store, _health(h)))
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == TRUONG_CU | {"verifier"}
    assert set(body["pipeline"]) == TRUONG_PIPELINE_CU
    assert body["status"] == "ok" and body["vlm_provider"] == "mock"
    assert body["verifier"] == {
        "breaker": "closed", "breaker_opens": 0, "queued": 0, "window_s": 600,
        "requests_in_window": 0, "answered_ratio_in_window": None,
        "latency_p50_ms": None, "latency_p95_ms": None, "vlm_off_total": 0}
    # A, B đang gọi (2 worker, thứ tự lượt gọi không chắc), C chờ trong hàng
    h.gui(ts=0.0, track=0)
    h.gui(ts=0.0, track=1)
    hv.cho(lambda: len(h.vlm.luot) == 2)
    c = h.gui(ts=0.0, track=2)
    assert client.get("/health").json()["verifier"]["queued"] == 1
    # một lượt trả lời ở 3 s, lượt kia ở 7 s; C được gọi khi có worker rảnh rồi
    # quá ngân sách ở 10 s
    h.dh.tien_toi(3.0)
    h.vlm.luot[0].tra(kb.CHAY)
    hv.cho(lambda: _so_verified(h) == 1)
    hv.cho(lambda: len(h.vlm.luot) == 3)
    h.dh.tien_toi(7.0)
    h.vlm.luot[1].tra(kb.CHAY)
    hv.cho(lambda: _so_verified(h) == 2)
    h.dh.tien_toi(10.0)
    assert h.store.get(c).verifier.status == "VLM_TIMEOUT"
    h.vlm.luot[2].tra(kb.CHAY)               # kết quả muộn, bỏ
    hv.cho(lambda: h.vlm.luot[2].da_xong.is_set())
    v = client.get("/health").json()["verifier"]
    assert set(v) == TRUONG_VERIFIER
    assert (v["requests_in_window"], v["answered_ratio_in_window"]) == (3, 0.667)
    assert (v["latency_p50_ms"], v["latency_p95_ms"]) == (3000, 3000)
    assert (v["breaker"], v["queued"], v["vlm_off_total"]) == ("closed", 0, 0)
    assert sorted(e.verifier.latency_ms for e in h.store.all()
                  if e.verifier.status == "VERIFIED") == [3000, 7000]
    # hai lỗi nữa (cùng C quá ngân sách là 3 thất bại): cầu dao mở, G nhận VLM_OFF
    for i in (3, 4):
        eid = h.gui(ts=10.0, track=i)
        hv.cho(lambda i=i: len(h.vlm.luot) > i)
        h.vlm.luot[i].nem(GeminiHTTPError(503, "unavailable"))
        hv.cho(lambda eid=eid: h.store.get(eid) is not None)
    hv.cho(lambda: h.dp.cau_dao.trang_thai == "mo")
    g = h.gui(ts=10.0, track=5)
    assert h.store.get(g).verifier.status == "VLM_OFF"
    v = client.get("/health").json()["verifier"]
    assert (v["breaker"], v["breaker_opens"], v["vlm_off_total"]) == ("open", 1, 1)
    assert (v["requests_in_window"], v["answered_ratio_in_window"]) == (6, 0.333)
    h.dh.tien_toi(70.0)
    assert client.get("/health").json()["verifier"]["breaker"] == "half_open"
    # cửa sổ 10 phút trượt: kết quả cũ rơi khỏi thống kê, bộ đếm tổng giữ nguyên
    h.dh.tien_toi(611.0)
    v = client.get("/health").json()["verifier"]
    assert (v["requests_in_window"], v["answered_ratio_in_window"]) == (0, None)
    assert (v["latency_p50_ms"], v["latency_p95_ms"]) == (None, None)
    assert (v["breaker_opens"], v["vlm_off_total"]) == (1, 1)


def test_health_vlm_tat_dem_vlm_off_va_cau_dao_dong(he):
    h = he(vlm="tat")
    client = TestClient(create_app(h.cfg, h.store, _health(h)))
    h.gui(ts=1.0)
    v = client.get("/health").json()["verifier"]
    assert (v["breaker"], v["vlm_off_total"], v["requests_in_window"],
            v["answered_ratio_in_window"]) == ("closed", 1, 1, 0.0)


def test_health_co_tat_khong_co_khoi_verifier(tmp_path):
    cfg = kb.cau_hinh(tmp_path, vlm={"provider": "mock"})
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    health = PipelineHealth()
    health.beat()
    body = TestClient(create_app(cfg, store, health)).get("/health").json()
    assert set(body) == TRUONG_CU
    assert set(body["pipeline"]) == TRUONG_PIPELINE_CU
    khong_pipeline = TestClient(create_app(cfg, store)).get("/health").json()
    assert set(khong_pipeline) == TRUONG_CU and khong_pipeline["pipeline"] is None


def test_tao_dieu_phoi_gan_verifier_stats_vao_health(tmp_path):
    cfg = kb.cau_hinh(tmp_path, verifier={"ben_vung": True},
                      vlm={"provider": "mock"})
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    svc = VerificationService(cfg.vlm, None)
    health = PipelineHealth()
    p = Pipeline(cfg, "kich_ban", health=health)
    dp = p._tao_dieu_phoi(store, RunSummary(source="k", weights="w", out_dir="o"),
                          svc, dong_ho=hv.DongHoGia())
    try:
        assert health.verifier_stats == dp.thong_ke
        assert health.verifier_stats()["breaker"] == "closed"
    finally:
        dp.dong()
        svc.shutdown()


# ------------------------------------------------------------- WebSocket
def test_ws_payload_reason_verifier_chi_khi_updated_co_object_verifier():
    ev = sample_event()
    assert ws_payload(ev, "created") == {"type": "event", "event": event_to_dict(ev)}
    assert "reason" not in ws_payload(ev, "updated")        # cờ tắt: như trước
    assert ws_payload(ev, "escalated")["reason"] == "escalation"
    co = ev.model_copy(update={"verifier": VerifierInfo.tao("PENDING",
                                                            reason="cho_vlm")})
    assert ws_payload(co, "updated") == {"type": "event_update", "reason": "verifier",
                                         "event": event_to_dict(co)}
    assert "reason" not in ws_payload(co, "created")
    assert ws_payload(co, "escalated")["reason"] == "escalation"
    assert ws_payload(co, "created")["event"]["verifier"]["status"] == "PENDING"
    assert ws_payload(co, "su_co")["reason"] == "su_co"
    assert ws_payload(co, "su_co")["type"] == "event_update"


# ------------------------------------------------------------- console
def test_console_hien_co_needs_human_check_va_giu_ba_nut():
    html = CONSOLE_HTML.read_text(encoding="utf-8")
    assert "needs_human_check" in html and DONG_CAN_NGUOI in html
    for nut in ("Xác nhận sự cố", "Bỏ qua — lửa có kiểm soát", "Theo dõi"):
        assert nut in html
    assert 'msg.reason === "escalation"' in html       # leo thang không đổi
