"""Verifier bền vững (ADR 2026-11-07): trạng thái, schema, Config, kịch bản 1, 2, 9, 10.

Kịch bản 1: cờ tắt thì event và log y hệt hành vi trước cờ (so với snapshot ghi
từ code trước khi có cờ). Kịch bản 2: VLM trả lời trong 1 s thì ``created`` mang
VERIFIED, không có ``updated``. Kịch bản 9: VLM trả REJECTED thì mức cảnh báo
không đổi, cảnh báo không bị gỡ, ``verification`` là SUPPRESSED. Kịch bản 10:
không có ``updated`` nào phát trước ``created`` của cùng ``event_id``.
"""

from __future__ import annotations

import json
import random
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from firewatch.alerts import (CAN_NGUOI_XAC_THUC, VERIFICATION_CUA, Event, EventStore,
                              VerifierInfo, sample_event)
from firewatch.config import Config, load_config
from firewatch.pipeline import Pipeline, RunSummary
from firewatch.vlm import (GeminiHTTPError, MockVerifier, VerificationService,
                           VerifyOutcome, VerifyRequest, VLMVerifier, ma_loi,
                           trang_thai_verifier)

import kich_ban_verifier as kb

ROOT = Path(__file__).resolve().parents[1]
ANH = np.zeros((120, 160, 3), dtype=np.uint8)
HOP = (10.0, 20.0, 60.0, 80.0)


# ------------------------------------------------------------ trạng thái, schema
def test_anh_xa_trang_thai_sang_verification_dung_adr():
    assert VERIFICATION_CUA == {
        "PENDING": "UNVERIFIED", "VERIFIED": "VERIFIED", "REJECTED": "SUPPRESSED",
        "VLM_TIMEOUT": "UNVERIFIED", "VLM_ERROR": "UNVERIFIED",
        "VLM_OFF": "UNVERIFIED"}
    assert CAN_NGUOI_XAC_THUC == {"VLM_TIMEOUT", "VLM_ERROR", "VLM_OFF"}
    for st in VERIFICATION_CUA:
        v = VerifierInfo.tao(st)
        assert v.needs_human_check is (st in CAN_NGUOI_XAC_THUC)
        assert v.verification == VERIFICATION_CUA[st]


def test_verifier_info_tu_choi_ma_la_va_co_can_nguoi_sai():
    with pytest.raises(ValidationError):
        VerifierInfo.tao("VLM_ERROR", reason="HTTP 500: <html>...")
    with pytest.raises(ValidationError):
        VerifierInfo(status="VLM_TIMEOUT", needs_human_check=False)
    assert VerifierInfo.tao("VERIFIED", latency_s=1.2346).latency_ms == 1235


def test_event_khong_co_verifier_thi_json_giu_dung_khoa_cu():
    keys = {"event_id", "camera_id", "context", "severity", "verification",
            "started_at", "video_ts_sec", "boxes", "vlm", "snapshot_path"}
    ev = sample_event()
    assert set(ev.model_dump()) == keys
    assert set(json.loads(ev.model_dump_json())) == keys


def test_event_co_verifier_chi_them_mot_object_va_phai_khop_verification():
    ev = sample_event().model_copy(update={"verification": "UNVERIFIED"})
    d = ev.model_dump() | {"verifier": VerifierInfo.tao(
        "PENDING", reason="cho_vlm").model_dump()}
    ev2 = Event(**d)
    assert set(json.loads(ev2.model_dump_json())) - set(ev.model_dump()) == {"verifier"}
    assert ev2.verifier.status == "PENDING" and ev2.verifier.reason == "cho_vlm"
    with pytest.raises(ValidationError):
        Event(**{**d, "verification": "VERIFIED"})


def test_trang_thai_tu_ket_qua_vlm():
    v = trang_thai_verifier(VerifyOutcome("VERIFIED", kb.CHAY, 1.5, 1))
    assert (v.status, v.latency_ms, v.reason, v.needs_human_check) == (
        "VERIFIED", 1500, None, False)
    assert trang_thai_verifier(
        VerifyOutcome("SUPPRESSED", kb.KHONG_CHAY, 2.0, 1)).status == "REJECTED"
    tat = trang_thai_verifier(VerifyOutcome("UNVERIFIED", None, 0.0, 0,
                                            "vlm disabled", "vlm_tat"))
    assert (tat.status, tat.reason, tat.needs_human_check) == (
        "VLM_OFF", "vlm_tat", True)
    loi = trang_thai_verifier(VerifyOutcome("UNVERIFIED", None, 3.0, 2,
                                            "GeminiHTTPError: HTTP 429", "http_429"))
    assert (loi.status, loi.reason, loi.latency_ms, loi.needs_human_check) == (
        "VLM_ERROR", "http_429", None, True)


@pytest.mark.parametrize("exc, ma", [
    (GeminiHTTPError(429, "quota"), "http_429"),
    (GeminiHTTPError(403, "forbidden"), "http_4xx"),
    (GeminiHTTPError(503, "unavailable"), "http_5xx"),
    (ValueError("Gemini không trả nội dung"), "loi_phan_tich"),
    (TimeoutError("timed out"), "loi_mang"),
    (OSError("connection reset"), "loi_mang"),
])
def test_ma_loi_khong_chua_chuoi_loi_tho(exc, ma):
    assert ma_loi(exc) == ma


def test_service_ghi_ma_loi_khi_vlm_hong(tmp_path):
    class Hong(VLMVerifier):
        name = "hong"

        def verify(self, *a, **k):
            raise GeminiHTTPError(500, "<html>lỗi máy chủ</html>")

    cfg = kb.cau_hinh(tmp_path, vlm={"retries": 0})
    svc = VerificationService(cfg.vlm, Hong())
    out = svc.submit(VerifyRequest(ANH, HOP, "HAM", "CRITICAL", 1.0)).result(5)
    svc.shutdown()
    assert out.reason == "http_5xx" and "<html>" not in trang_thai_verifier(
        out).model_dump_json()


# ------------------------------------------------------------------- Config
def test_config_thieu_khoi_verifier_thi_co_tat():
    assert Config().verifier.ben_vung is False
    cfg = load_config(ROOT / "config.yaml")
    assert cfg.verifier.ben_vung is False
    assert (cfg.verifier.ngan_sach_s, cfg.verifier.hang_cho_toi_da,
            cfg.verifier.cau_dao.loi_lien_tiep, cfg.verifier.cau_dao.mo_s) == (
        10, 8, 3, 60)


def test_config_tu_choi_ngan_sach_khong_lon_hon_cua_so_va_khoa_go_sai():
    with pytest.raises(ValidationError):
        Config(verifier={"ben_vung": True, "ngan_sach_s": 2}, vlm={"grace_s": 2})
    Config(verifier={"ben_vung": False, "ngan_sach_s": 2}, vlm={"grace_s": 2})
    with pytest.raises(ValidationError):
        Config(verifier={"ben_vung_": True})
    with pytest.raises(ValidationError):
        load_config(ROOT / "config.yaml", overrides=["verifier.cau_dao.mo=5"])


# ------------------------------------------------------------- kịch bản 1
def test_kich_ban_1_co_tat_y_het_snapshot(tmp_path):
    """Cờ tắt (thiếu khối hoặc ``ben_vung: false``): thông báo, summary, JSON trên
    đĩa và log trùng snapshot ghi từ code trước khi có cờ."""
    goc = json.loads(kb.SNAPSHOT.read_text(encoding="utf-8"))
    assert kb.sinh_snapshot(tmp_path / "thieu_khoi") == goc
    tat = kb.chay_kich_ban(tmp_path / "tat", verifier={"ben_vung": False})
    assert tat == goc["notify_suppressed_true"]
    for _, ev in tat["thong_bao"]:
        assert "verifier" not in ev


# ------------------------------------------------------- kịch bản 2, 9, 10
def _chay_voi_service(tmp: Path, verifier: VLMVerifier, n: int, *, grace_s: float,
                      notify_suppressed: bool = True, max_workers: int = 2,
                      han_cho_s: float = 10.0, hang_cho_toi_da: int = 8):
    """Chạy ``n`` cảnh báo thật qua bộ điều phối nền với cờ bật, đồng hồ thật.

    Không có vòng heartbeat: ``created`` / ``updated`` do luồng hẹn giờ và
    worker của bộ điều phối phát. Trả (store, danh sách (kind, event) theo thứ
    tự phát).
    """
    cfg = kb.cau_hinh(tmp, verifier={"ben_vung": True,
                                     "hang_cho_toi_da": hang_cho_toi_da},
                      vlm={"grace_s": grace_s, "provider": "mock",
                           "max_workers": max_workers},
                      alerts={"notify_suppressed": notify_suppressed})
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    phat: list[tuple[str, Event]] = []
    khoa = threading.Lock()

    def ghi(e: Event, k: str) -> None:
        with khoa:
            phat.append((k, e))

    store.subscribe(ghi)
    svc = VerificationService(cfg.vlm, verifier)
    p = Pipeline(cfg, "kich_ban")
    s = RunSummary(source="kich_ban", weights="w", out_dir="out")
    dp = p._tao_dieu_phoi(store, s, svc)
    for i in range(n):
        kb.gui_nen(p, VerifyRequest(ANH, HOP, "HAM", "CRITICAL", float(i)),
                   ts=float(i), track=i)
    xong = dp.cho_xong(han_cho_s)
    dp.dong()
    svc.shutdown()
    assert xong, "còn cảnh báo chưa có trạng thái cuối sau hạn kiểm"
    return store, phat


def test_kich_ban_2_vlm_tra_loi_trong_1s_thi_created_mang_verified(tmp_path):
    store, phat = _chay_voi_service(tmp_path, MockVerifier(delay_s=1.0), 1,
                                    grace_s=2.0)
    time.sleep(0.2)
    assert [k for k, _ in phat] == ["created"]
    ev = phat[0][1]
    assert ev.verification == "VERIFIED" and ev.severity == "CRITICAL"
    assert ev.verifier.status == "VERIFIED"
    assert ev.verifier.needs_human_check is False and ev.verifier.reason is None
    assert 1000 <= ev.verifier.latency_ms < 2000
    tren_dia = json.loads(store._paths[ev.event_id].read_text(encoding="utf-8"))
    assert tren_dia["verifier"]["status"] == "VERIFIED"


@pytest.mark.parametrize("delay_s, grace_s, kinds", [
    (0.2, 2.0, ["created"]),                 # REJECTED trong cửa sổ đồng bộ
    (0.8, 0.3, ["created", "updated"]),      # REJECTED về sau, qua updated
])
def test_kich_ban_9_rejected_khong_ha_muc_khong_go_canh_bao(tmp_path, delay_s,
                                                           grace_s, kinds):
    vlm = MockVerifier(delay_s=delay_s, is_fire=False, is_smoke=False)
    store, phat = _chay_voi_service(tmp_path, vlm, 1, grace_s=grace_s,
                                    notify_suppressed=False)
    assert [k for k, _ in phat] == kinds, "cảnh báo phải được đẩy dù SUPPRESSED"
    for _, ev in phat:
        assert ev.severity == "CRITICAL"
    cuoi = phat[-1][1]
    assert cuoi.verification == "SUPPRESSED" and cuoi.verifier.status == "REJECTED"
    assert cuoi.verifier.needs_human_check is False
    con = store.get(cuoi.event_id)
    assert con is not None and con.severity == "CRITICAL"
    assert len(store) == 1
    tren_dia = json.loads(store._paths[cuoi.event_id].read_text(encoding="utf-8"))
    assert tren_dia["severity"] == "CRITICAL"
    assert tren_dia["verification"] == "SUPPRESSED"
    assert tren_dia["verifier"]["status"] == "REJECTED"
    if kinds == ["created", "updated"]:
        dau = phat[0][1]
        assert dau.verifier.status == "PENDING" and dau.verifier.reason == "cho_vlm"
        assert dau.verification == "UNVERIFIED"


class _TreNgauNhien(VLMVerifier):
    """VLM giả với độ trễ khác nhau mỗi lượt, quanh cửa sổ đồng bộ."""

    name = "tre_ngau_nhien"

    def __init__(self, tre: list[float]):
        self._tre = list(tre)
        self._khoa = threading.Lock()

    def verify(self, *a, **k):
        with self._khoa:
            t = self._tre.pop(0)
        time.sleep(t)
        return kb.CHAY


def test_kich_ban_10_khong_co_updated_truoc_created(tmp_path):
    rng = random.Random(0)
    tre = [rng.uniform(0.0, 0.6) for _ in range(16)]
    # hàng đủ chứa cả 16 mục: kịch bản này kiểm thứ tự, không kiểm hàng đầy
    store, phat = _chay_voi_service(tmp_path, _TreNgauNhien(tre), 16, grace_s=0.25,
                                    max_workers=4, hang_cho_toi_da=16)
    da_tao: set[str] = set()
    so_updated: dict[str, int] = {}
    for kind, ev in phat:
        if kind == "created":
            assert ev.event_id not in da_tao, "created phát hai lần"
            da_tao.add(ev.event_id)
        else:
            assert kind == "updated"
            assert ev.event_id in da_tao, f"updated của {ev.event_id} trước created"
            so_updated[ev.event_id] = so_updated.get(ev.event_id, 0) + 1
    assert len(da_tao) == 16 and all(n == 1 for n in so_updated.values())
    # kịch bản phải đi qua cả hai nhánh: có event được vá, có event không
    assert 0 < len(so_updated) < 16
    for ev in store.all():
        assert ev.verifier.status == "VERIFIED" and ev.severity == "CRITICAL"
