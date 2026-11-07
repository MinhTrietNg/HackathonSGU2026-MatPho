"""Kịch bản phát cảnh báo dùng chung cho test verifier bền vững.

Chỉ dùng API có từ trước cờ ``verifier.ben_vung``, để cùng một kịch bản chạy
được trên code cũ (sinh snapshot) và code mới (so với snapshot khi cờ tắt).
Không phải file test (pytest không thu thập), được ``test_verifier_ben_vung.py``
import.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from firewatch.alerts import EventStore, VLMResult
from firewatch.config import Config
from firewatch.detector import Detection
from firewatch.pipeline import Pipeline, RunSummary, _PendingAlert
from firewatch.vlm import VerifyOutcome
from firewatch.voting import Severity

SNAPSHOT = Path(__file__).parent / "snapshots" / "verifier_co_tat.json"
BAT_DAU = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone(timedelta(hours=7)))
DET = Detection("fire", 0, 0.9, (10.0, 20.0, 60.0, 80.0))
CHAY = VLMResult(is_fire=True, is_smoke=True, confidence=0.9,
                 description_vi="Lửa và khói bốc lên từ yên xe.",
                 fire_type="UNCONTROLLED")
KHONG_CHAY = VLMResult(is_fire=False, is_smoke=False, confidence=0.8,
                       description_vi="Không thấy lửa hay khói.",
                       fire_type="UNCONTROLLED")


def cau_hinh(tmp: Path, **muc: dict[str, Any]) -> Config:
    """Config tối thiểu cho kịch bản; ``muc`` ghi đè từng section.

    Webhook trỏ vào biến môi trường không tồn tại, nên không gửi gì ra ngoài.
    """
    raw: dict[str, Any] = {
        "camera": {"id": "cam01", "context": "HAM"},
        "alerts": {"events_dir": str(tmp / "events"),
                   "webhook_url_env": "FIREWATCH_TEST_KHONG_CO_WEBHOOK"},
    }
    for k, v in muc.items():
        raw[k] = {**raw.get(k, {}), **v}
    return Config(**raw, root=tmp)


def xong(outcome: VerifyOutcome) -> Future:
    """Future đã có kết quả."""
    f: Future = Future()
    f.set_result(outcome)
    return f


class BoGhi:
    """Ghi lại thông báo của store (theo thứ tự) và log của ``firewatch``."""

    def __init__(self, store: EventStore):
        self.thong_bao: list[tuple[str, dict]] = []
        self.dong_log: list[str] = []
        store.subscribe(lambda e, k: self.thong_bao.append(
            (k, e.model_dump(mode="json"))))
        self._h = logging.Handler(logging.INFO)
        self._h.emit = lambda r: self.dong_log.append(
            f"{r.name} {r.levelname} {r.getMessage()}")

    def __enter__(self) -> "BoGhi":
        lg = logging.getLogger("firewatch")
        self._muc_cu = lg.level
        lg.setLevel(logging.INFO)
        lg.addHandler(self._h)
        return self

    def __exit__(self, *exc: object) -> None:
        lg = logging.getLogger("firewatch")
        lg.removeHandler(self._h)
        lg.setLevel(self._muc_cu)


def them_canh_bao(p: Pipeline, fut: Future, *, ts: float, track: int,
                  han_s: float, severity: Severity = Severity.CRITICAL) -> None:
    """Đưa một cảnh báo vào hàng chờ của pipeline như ``_on_track_event``.

    ``han_s`` là thời gian còn lại của cửa sổ đồng bộ (âm = đã hết).
    """
    p._pending.append(_PendingAlert(
        future=fut, deadline_wall=time.time() + han_s, kind="NEW", track_id=track,
        severity=severity, ts=ts, detections=[DET], image=None,
        started_at=BAT_DAU))


def gui_nen(p: Pipeline, req: Any, *, ts: float, track: int,
            severity: Severity = Severity.CRITICAL) -> str:
    """Giao một cảnh báo cho bộ điều phối nền như ``_on_track_event`` (cờ bật).

    Trả ``event_id`` đã cấp.
    """
    return p._gui_nen(req, _PendingAlert(
        future=None, deadline_wall=0.0, kind="NEW", track_id=track,
        severity=severity, ts=ts, detections=[DET], image=None, started_at=BAT_DAU))


def chay_kich_ban(tmp: Path, **muc: dict[str, Any]) -> dict[str, Any]:
    """Chạy sáu cảnh báo qua ``_flush_pending`` và trả mọi thứ quan sát được.

    A: VLM trả lời trong cửa sổ (VERIFIED). B: quá cửa sổ, kết quả VERIFIED về
    sau. C: REJECTED trong cửa sổ, mức WARNING. D: VLM lỗi trong cửa sổ. E: quá
    cửa sổ, kết quả REJECTED về sau. F: nguồn kết thúc khi VLM chưa xong.

    Returns
    -------
    dict
        ``thong_bao`` (kind, event), ``tom_tat`` (summary.alerts), ``dia``
        (JSON trên đĩa theo thứ tự tạo), ``log``; event_id đã chuẩn hoá thành
        E1, E2... theo thứ tự tạo, độ trễ đo theo giờ thật thay bằng ``<so>``.
    """
    cfg = cau_hinh(tmp, **muc)
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    p = Pipeline(cfg, "kich_ban")
    s = RunSummary(source="kich_ban", weights="w", out_dir="out")
    with BoGhi(store) as ghi:
        them_canh_bao(p, xong(VerifyOutcome("VERIFIED", CHAY, 1.0, 1)),
                      ts=10.0, track=1, han_s=10.0)
        p._flush_pending(store, s)
        fb: Future = Future()
        them_canh_bao(p, fb, ts=20.0, track=2, han_s=-0.5)
        p._flush_pending(store, s)
        fb.set_result(VerifyOutcome("VERIFIED", CHAY, 4.0, 1))
        p._flush_pending(store, s)
        them_canh_bao(p, xong(VerifyOutcome("SUPPRESSED", KHONG_CHAY, 1.2, 1)),
                      ts=30.0, track=3, han_s=10.0, severity=Severity.WARNING)
        p._flush_pending(store, s)
        them_canh_bao(p, xong(VerifyOutcome("UNVERIFIED", None, 3.0, 2,
                                            "GeminiHTTPError: HTTP 429")),
                      ts=40.0, track=4, han_s=10.0)
        p._flush_pending(store, s)
        fe: Future = Future()
        them_canh_bao(p, fe, ts=50.0, track=5, han_s=-0.5)
        p._flush_pending(store, s)
        fe.set_result(VerifyOutcome("SUPPRESSED", KHONG_CHAY, 5.0, 1))
        p._flush_pending(store, s)
        ff: Future = Future()
        them_canh_bao(p, ff, ts=60.0, track=6, han_s=10.0)
        p._flush_pending(store, s, final=True)
    dia = [store._paths[e.event_id].read_text(encoding="utf-8")
           for e in sorted(store.all(), key=lambda e: e.video_ts_sec)]
    return chuan_hoa({"thong_bao": ghi.thong_bao, "tom_tat": s.alerts, "dia": dia,
                      "log": ghi.dong_log}, [e.event_id for e in sorted(
                          store.all(), key=lambda e: e.video_ts_sec)])


def chuan_hoa(x: Any, ids: list[str]) -> Any:
    """Thay event_id (đầy đủ và 8 ký tự đầu) bằng E1, E2..., bỏ độ trễ giờ thật."""
    if isinstance(x, dict):
        return {k: ("<so>" if k == "vlm_latency_s" else chuan_hoa(v, ids))
                for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [chuan_hoa(v, ids) for v in x]
    if isinstance(x, str):
        for i, eid in enumerate(ids, start=1):
            x = x.replace(eid, f"E{i}").replace(eid[:8], f"E{i}")
        return x
    return x


def sinh_snapshot(tmp: Path) -> dict[str, Any]:
    """Snapshot hành vi cờ tắt, với ``notify_suppressed`` bật và tắt."""
    return {"notify_suppressed_true": chay_kich_ban(tmp / "a"),
            "notify_suppressed_false": chay_kich_ban(
                tmp / "b", alerts={"notify_suppressed": False})}


def ghi_snapshot(tmp: Path) -> None:
    """Ghi snapshot từ code hiện tại (chỉ chạy một lần, trên code trước cờ)."""
    SNAPSHOT.parent.mkdir(exist_ok=True)
    SNAPSHOT.write_text(json.dumps(sinh_snapshot(tmp), ensure_ascii=False,
                                   indent=1) + "\n", encoding="utf-8", newline="\n")
