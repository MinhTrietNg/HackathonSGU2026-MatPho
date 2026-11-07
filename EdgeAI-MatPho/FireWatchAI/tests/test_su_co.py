"""Gom sự cố (ADR 2026-11-07-gom-su-co): ngân sách mỗi camera và các luật ghép.

Chạy Voting thật trên chuỗi detection giả lập, mỗi giây một heartbeat, qua đúng
``Pipeline._on_track_event`` và lớp gom sự cố, với đồng hồ giả: 10 phút cháy
chạy trong vài giây giờ thật. VLM giả trả lời ngay; worker vẫn là luồng thật
nên sau mỗi heartbeat test chờ bộ điều phối xong (giờ thật, tối đa 2 s).
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from firewatch.acks import Ack, AckStore, EscalationWatcher
from firewatch.alerts import Event, EventStore, gio_iso, sample_event
from firewatch.detector import Detection
from firewatch.pipeline import Pipeline, RunSummary
from firewatch.vlm import GeminiHTTPError, VerificationService, VLMVerifier
from firewatch.voting import VotingEngine

import he_verifier as hv
import kich_ban_verifier as kb

ANH = np.zeros((360, 640, 3), dtype=np.uint8)
HOP = (100.0, 100.0, 220.0, 240.0)
GOC_GIO = 1_794_000_000.0


class VlmDem(VLMVerifier):
    """VLM giả trả lời ngay; đếm số lượt gọi (dùng chung được giữa camera)."""

    name = "dem"

    def __init__(self, loi_o_luot: set[int] | None = None):
        self.so_luot = 0
        self._loi = loi_o_luot or set()
        self._khoa = threading.Lock()

    def verify(self, *a, **k):
        with self._khoa:
            self.so_luot += 1
            n = self.so_luot
        if n in self._loi:
            raise GeminiHTTPError(503, "unavailable")
        return kb.CHAY


def _he(tmp: Path, vlm: VLMVerifier, **su_co) -> SimpleNamespace:
    cfg = kb.cau_hinh(tmp, verifier={"ben_vung": True},
                      vlm={"provider": "mock", "max_workers": 2},
                      su_co=su_co)
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    dh = hv.DongHoGia()
    phat: list[tuple[str, Event, float]] = []
    store.subscribe(lambda e, k: phat.append((k, e, dh.bay_gio())))
    svc = VerificationService(cfg.vlm, vlm)
    p = Pipeline(cfg, "gia_lap")
    s = RunSummary(source="gia_lap", weights="w", out_dir="o")
    gom = p._tao_gom(store, s, svc, dong_ho=dh)
    return SimpleNamespace(cfg=cfg, store=store, dh=dh, phat=phat, svc=svc, p=p,
                           s=s, gom=gom, voting=VotingEngine(cfg.voting))


def _don(h: SimpleNamespace) -> None:
    h.gom.dong()
    h.svc.shutdown()


def _buoc(h: SimpleNamespace, t: int, lop: tuple[str, ...]) -> None:
    """Một heartbeat ở giây ``t`` với các box ``lop`` (rỗng = không thấy cháy)."""
    h.dh.tien_toi(float(t))
    dets = [Detection(c, 0 if c == "fire" else 1, 0.9, HOP) for c in lop]
    frame = SimpleNamespace(image=ANH, wall_time=GOC_GIO + t, video_ts=float(t))
    h.p._apply_acks(h.voting)
    for ev in h.voting.update(t, float(t), dets, frame=frame):
        h.p._on_track_event(ev, h.s, h.svc)
    h.gom.thay_chay([(tr.track_id, tr.box) for tr in h.voting.tracks
                     if tr.latest_vote is not None and tr.latest_vote.seq == t],
                    frame.wall_time, frame.image)
    assert h.gom.cho_xong(2.0), "bộ điều phối chưa xong sau 2 s giờ thật"


def _chay(h, t0: int, t1: int, lop: tuple[str, ...]) -> None:
    for t in range(t0, t1):
        _buoc(h, t, lop)


def _theo_loai(h, loai: str, truoc: float = float("inf")) -> list[tuple[Event, float]]:
    """``loai`` theo ``type`` của payload: ``created`` hay ``updated`` (mọi lần
    gửi lại, cả thông báo ``su_co`` của store)."""
    return [(e, luc) for _, e, luc in h.phat if e.type == loai and luc < truoc]


def _toi_da_moi_phut(lucs: list[float]) -> int:
    return max((sum(1 for x in lucs if t - 60 < x <= t) for t in lucs), default=0)


# ------------------------------------------------------------- ngân sách
def test_chay_10_phut_mot_created_toi_da_20_updated_3_vlm(tmp_path):
    vlm = VlmDem()
    h = _he(tmp_path, vlm)
    try:
        _chay(h, 0, 600, ("fire",))
        tao = _theo_loai(h, "created")
        cap_nhat = _theo_loai(h, "updated", truoc=600)
        assert len(tao) == 1
        eid = tao[0][0].event_id
        assert len(cap_nhat) <= 20, [luc for _, luc in cap_nhat]
        assert _toi_da_moi_phut([luc for _, luc in cap_nhat]) <= 2
        assert vlm.so_luot <= 3
        assert {e.event_id for _, e, _ in h.phat} == {eid}
        dau = tao[0][0]
        assert (dau.status, dau.luot_xac_minh, dau.severity) == ("open", 1,
                                                                 "CRITICAL")
        assert dau.verifier.status == "VERIFIED"
        assert all(e.status == "open" for e, _ in cap_nhat)
        assert (datetime.fromisoformat(cap_nhat[-1][0].last_seen_ts)
                > datetime.fromisoformat(dau.last_seen_ts))
        # hết cháy: đúng một updated ended, sau khoang_cach_s
        _chay(h, 600, 800, ())
        het = [(e, luc) for e, luc in _theo_loai(h, "updated")
               if e.status == "ended"]
        assert len(het) == 1
        assert 599 + 120 <= het[0][1] <= 599 + 121
        assert het[0][0].event_id == eid
        assert h.store.get(eid).status == "ended"
        assert h.store.get(eid).last_seen_ts == gio_iso(GOC_GIO + 599)
        assert vlm.so_luot <= 3
        assert len(_theo_loai(h, "created")) == 1
        assert h.s.alerts[0]["status"] == "ended" and len(h.s.alerts) == 1
    finally:
        _don(h)


def test_10_camera_moi_camera_mot_created_tong_vlm_toi_da_30(tmp_path):
    vlm = VlmDem()
    cams = [_he(tmp_path / f"cam{i}", vlm) for i in range(10)]
    try:
        for t in range(600):
            for h in cams:
                _buoc(h, t, ("fire",))
        for h in cams:
            assert len(_theo_loai(h, "created")) == 1
            assert len(_theo_loai(h, "updated", truoc=600)) <= 20
        assert vlm.so_luot <= 30
    finally:
        for h in cams:
            _don(h)


def test_canh_bao_trong_khoang_cach_vao_cung_su_co_qua_thi_su_co_moi(tmp_path):
    h = _he(tmp_path, VlmDem())
    try:
        _chay(h, 0, 60, ("fire",))
        _chay(h, 60, 160, ())                 # 100 s không thấy: còn mở
        _chay(h, 160, 200, ("fire",))
        tao = _theo_loai(h, "created")
        assert len(tao) == 1 and h.gom.su_co_mo is not None
        assert not [e for e, _ in _theo_loai(h, "updated") if e.status == "ended"]
        _chay(h, 200, 340, ())                # 140 s không thấy: ended ở 319
        het = [luc for e, luc in _theo_loai(h, "updated") if e.status == "ended"]
        assert len(het) == 1 and 319 <= het[0] <= 320
        _chay(h, 340, 400, ("fire",))         # thấy lại: sự cố mới
        tao = _theo_loai(h, "created")
        assert len(tao) == 2 and tao[0][0].event_id != tao[1][0].event_id
        assert tao[1][1] - tao[0][1] >= h.cfg.su_co.khoang_cach_s
        assert tao[1][0].luot_xac_minh == 1
    finally:
        _don(h)


def test_ack_roi_van_nhan_leo_thang_ngay_va_luot_xac_minh_moi(tmp_path):
    vlm = VlmDem()
    h = _he(tmp_path, vlm)
    try:
        _chay(h, 0, 50, ("smoke",))
        (dau, _), = _theo_loai(h, "created")
        assert dau.severity == "WARNING" and vlm.so_luot == 1
        h.p._ack_queue.put(Ack(event_id=dau.event_id, action="confirm",
                               acked_at="2026-11-07T12:00:50+07:00"))
        _chay(h, 50, 100, ("smoke",))
        assert all(t.muted for t in h.voting.tracks), "ack tắt nhắc của sự cố"
        so_truoc = len(h.phat)
        _chay(h, 100, 103, ("fire", "smoke"))
        leo = [(e, luc) for e, luc in _theo_loai(h, "updated")
               if e.severity == "CRITICAL"]
        assert leo, "leo thang phải phát dù đã ack"
        e, luc = leo[0]
        assert e.event_id == dau.event_id and e.luot_xac_minh == 2
        assert luc in (100.0, 101.0, 102.0), "phát ngay, không chờ nhịp"
        assert vlm.so_luot == 2
        assert len(_theo_loai(h, "created")) == 1
        assert len(h.phat) - so_truoc <= 2
        assert not any(t.muted for t in h.voting.tracks), "leo thang gỡ mute"
        assert h.store.get(dau.event_id).frame_ts == GOC_GIO + luc
    finally:
        _don(h)


def test_luot_kiem_lai_loi_khong_xoa_ket_luan_da_co(tmp_path):
    vlm = VlmDem(loi_o_luot={2})
    h = _he(tmp_path, vlm, vlm_kiem_lai_s=60)
    try:
        _chay(h, 0, 120, ("fire",))
        assert vlm.so_luot >= 2
        ev = h.store.get(_theo_loai(h, "created")[0][0].event_id)
        assert ev.verifier.status == "VERIFIED" and ev.verification == "VERIFIED"
        assert ev.luot_xac_minh >= 2
    finally:
        _don(h)


def test_khong_kiem_lai_khi_khong_con_thay_chay(tmp_path):
    vlm = VlmDem()
    h = _he(tmp_path, vlm, vlm_kiem_lai_s=60, khoang_cach_s=300)
    try:
        _chay(h, 0, 20, ("fire",))
        _chay(h, 20, 200, ())
        assert vlm.so_luot == 1
    finally:
        _don(h)


# ------------------------------------------------------------- schema, cờ
def test_truong_su_co_chi_co_khi_bat_co():
    d = sample_event().model_dump()
    assert not {"status", "last_seen_ts", "luot_xac_minh"} & set(d)
    co = sample_event().model_copy(update={"status": "open",
                                           "last_seen_ts": gio_iso(1.0),
                                           "luot_xac_minh": 1})
    assert {"status", "last_seen_ts", "luot_xac_minh"} <= set(co.model_dump())


def test_co_tat_khong_gom_su_co(tmp_path):
    cfg = kb.cau_hinh(tmp_path, vlm={"provider": "mock"})
    p = Pipeline(cfg, "gia_lap")
    assert p._gom is None and cfg.verifier.ben_vung is False


def test_escalation_watcher_theo_doi_su_co_len_critical_qua_updated(tmp_path):
    class _Store:
        def __init__(self):
            self.subs, self.pushed = [], []

        def subscribe(self, fn):
            self.subs.append(fn)

        def renotify(self, event_id, kind="escalated"):
            self.pushed.append(event_id)

    now = [0.0]
    store = _Store()
    w = EscalationWatcher(store, AckStore(tmp_path / "acks.json"), 120,
                          clock=lambda: now[0])
    warn = sample_event().model_copy(update={"severity": "WARNING"})
    store.subs[0](warn, "created")
    now[0] = 130.0
    assert w.tick() == []
    store.subs[0](warn.model_copy(update={"severity": "CRITICAL"}), "su_co")
    now[0] = 250.0
    assert w.tick() == [warn.event_id]
