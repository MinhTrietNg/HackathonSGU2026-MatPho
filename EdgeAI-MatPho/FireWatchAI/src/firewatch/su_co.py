"""Gom sự cố (ADR 2026-11-07-gom-su-co); chỉ chạy khi cờ ``verifier.ben_vung`` bật.

Một sự cố là một ``event_id`` trên một camera. Cảnh báo đầu tiên của Voting mở
sự cố và phát ``created`` (qua lượt xác minh 1 của
:class:`~firewatch.xac_minh_nen.DieuPhoiXacMinh`, đúng mốc 2 s / 10 s như
trước). Cảnh báo sau, khi sự cố còn mở, không tạo ``event_id`` mới:

* mức tăng (``ESCALATED`` hay bất kỳ cảnh báo nào có mức cao hơn): ``updated``
  ngay với mức mới và keyframe mới, mở lượt xác minh mới;
* ``STILL_BURNING``, ``RECONFIRMED``, ``CONFIRMED`` của track khác, và mỗi
  heartbeat còn thấy cháy: gom lại, ``updated`` nhiều nhất mỗi
  ``su_co.nhip_cap_nhat_s``;
* ``DEFERRED`` không đổi mức: bỏ.

Kết quả xác minh làm đổi ``verifier.status`` thì ``updated`` ngay; không đổi thì
gom vào nhịp. Lượt kiểm lại (mỗi ``su_co.vlm_kiem_lai_s`` khi còn thấy cháy)
chỉ ghi kết quả khi VLM trả lời được: lượt kiểm lại lỗi không xoá kết luận đã
có. Quá ``su_co.khoang_cach_s`` không thấy cháy thì ``updated`` với
``status: ended``; thấy lại sau đó là sự cố mới.

Mọi mốc thời gian do đồng hồ tiêm được (:class:`~firewatch.xac_minh_nen.DongHo`)
gọi, không do vòng heartbeat. Mọi chuyển trạng thái đi qua một khoá; bộ điều
phối gọi vào lớp này khi đang giữ khoá của nó, nên lớp này không bao giờ gọi bộ
điều phối khi đang giữ khoá của mình.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

from .alerts import EventStore, VerifierInfo, gio_iso
from .config import Config
from .detector import Detection
from .vlm import VerificationService, VerifyOutcome, VerifyRequest
from .voting import Box, Severity, iou, union
from .xac_minh_nen import DieuPhoiXacMinh, DongHo, DongHoThat, MucXacMinh, VeHen

log = logging.getLogger(__name__)

NHO_SU_CO = 256
"""Số sự cố gần nhất được nhớ (để ack áp lên track của sự cố)."""


@dataclass(eq=False)
class SuCo:
    """Trạng thái của một sự cố (một ``event_id``)."""

    event_id: str
    severity: Severity
    kind: str
    """Loại cảnh báo Voting đã mở sự cố (ghi vào summary)."""
    track_dau: int
    ts: float
    """Giây video của cảnh báo mở sự cố."""
    started_at: datetime
    detections: list[Detection]
    image: Any
    box: Box
    """Box của lần thấy gần nhất; track mới chồng lên box này là còn thấy cháy."""
    thay_cuoi: float
    """Lần thấy cháy gần nhất, theo đồng hồ của lớp gom."""
    last_seen_unix: float
    t_luot: float
    """Lúc mở lượt xác minh hiện tại, theo đồng hồ của lớp gom."""
    req: VerifyRequest
    """Yêu cầu xác minh dựng từ khung thấy cháy gần nhất (cho lượt kiểm lại)."""
    tracks: set[int] = field(default_factory=set)
    luot: int = 1
    da_tao: bool = False
    da_ket_thuc: bool = False
    phat_cuoi: float | None = None
    """Lần phát gần nhất (``created`` hay ``updated``)."""
    ban: bool = False
    """Có thay đổi chưa phát (chờ nhịp)."""
    cho_phat: dict[str, Any] = field(default_factory=dict)
    """Trường đổi đang chờ nhịp (kết quả xác minh không đổi trạng thái)."""
    verifier: VerifierInfo | None = None
    record: dict | None = None
    ve_nhip: VeHen | None = None
    ve_ket_thuc: VeHen | None = None
    ve_kiem_lai: VeHen | None = None


class GomSuCo:
    """Gom cảnh báo của một camera thành sự cố; sở hữu bộ điều phối xác minh.

    Parameters
    ----------
    cfg : Config
        Lấy khối ``su_co``, ``camera`` và cấu hình của bộ điều phối.
    store : EventStore
        Nơi phát ``created`` / ``updated``.
    service : VerificationService
        Gọi VLM qua bộ điều phối.
    summary : RunSummary, optional
        Mỗi sự cố một bản ghi trong ``summary.alerts``.
    health : PipelineHealth, optional
        ``alerts`` tăng một mỗi sự cố.
    dong_ho : DongHo, optional
        Mặc định :class:`DongHoThat` (đóng cùng lớp gom).
    """

    def __init__(self, cfg: Config, store: EventStore, service: VerificationService,
                 *, summary: Any = None, health: Any = None,
                 dong_ho: DongHo | None = None):
        self._cfg = cfg.su_co
        self._ctx = cfg.camera.context
        self._store, self._summary, self._health = store, summary, health
        self._dong_ho_rieng = dong_ho is None
        self._dong_ho: DongHo = dong_ho if dong_ho is not None else DongHoThat()
        self._khoa = threading.RLock()
        self._mo: SuCo | None = None
        """Sự cố đang mở của camera (nhiều nhất một)."""
        self._tat_ca: OrderedDict[str, SuCo] = OrderedDict()
        self.dieu_phoi = DieuPhoiXacMinh(cfg, service, phat_tao=self._ket_qua,
                                         phat_cap_nhat=self._ket_qua,
                                         dong_ho=self._dong_ho)

    # ------------------------------------------------------------ bên ngoài
    def canh_bao(self, *, kind: str, track_id: int, severity: Severity, ts: float,
                 detections: list[Detection], image: np.ndarray, wall_time: float,
                 box: Box, req: VerifyRequest) -> str:
        """Nhận một cảnh báo của Voting (``ev.alert``); trả ``event_id`` sự cố."""
        viec: list[tuple[str, VerifyRequest, int]] = []
        with self._khoa:
            now = self._dong_ho.bay_gio()
            sc = self._mo
            if sc is None:
                sc = self._mo_su_co(kind, track_id, severity, ts, detections, image,
                                    wall_time, box, req, now)
                viec.append((sc.event_id, req, 1))
            else:
                # Không cập nhật lần thấy cuối ở đây: STILL_BURNING có thể bắn ở
                # heartbeat không có detection. "Còn thấy" chỉ do thay_chay.
                sc.tracks.add(track_id)
                if severity.rank > sc.severity.rank:
                    viec += self._tang_muc(sc, severity, detections, image,
                                           wall_time, req, now, kind)
                elif kind != "DEFERRED":
                    log.info("sự cố %s: %s của track#%d gom vào nhịp cập nhật",
                             sc.event_id[:8], kind, track_id)
                    self._danh_dau(sc)
            eid = sc.event_id
        for event_id, r, luot in viec:
            self.dieu_phoi.gui(event_id, r, None, luot=luot)
        return eid

    def thay_chay(self, thay: list[tuple[int, Box]], wall_time: float,
                  image: np.ndarray | None) -> None:
        """Một heartbeat: các track vừa có phiếu, ``(track_id, box)``.

        Track thuộc sự cố, hoặc chồng box sự cố quá ``su_co.iou_ghep``, là còn
        thấy cháy: ``last_seen_ts`` đổi và gom vào nhịp cập nhật.
        """
        with self._khoa:
            sc = self._mo
            if sc is None or not thay:
                return
            khop = [(t, b) for t, b in thay
                    if t in sc.tracks or iou(b, sc.box) > self._cfg.iou_ghep]
            if not khop:
                return
            box = khop[0][1]
            for _, b in khop[1:]:
                box = union(box, b)
            sc.tracks.update(t for t, _ in khop)
            req = (VerifyRequest(image, box, self._ctx, sc.severity.value, sc.ts)
                   if image is not None else sc.req)
            self._ghi_thay(sc, self._dong_ho.bay_gio(), wall_time, req, box)
            if sc.da_tao:
                self._danh_dau(sc)

    def track_cua(self, event_id: str) -> set[int]:
        """Các track của sự cố (để ack tắt nhắc lại của cả sự cố)."""
        with self._khoa:
            sc = self._tat_ca.get(event_id)
            return set(sc.tracks) if sc is not None else set()

    @property
    def su_co_mo(self) -> SuCo | None:
        with self._khoa:
            return self._mo

    def cho_xong(self, timeout_s: float) -> bool:
        """Chờ (giờ thật) các lượt xác minh đang dở có trạng thái cuối."""
        return self.dieu_phoi.cho_xong(timeout_s)

    def dong(self) -> None:
        """Dừng bộ điều phối và đồng hồ riêng; sự cố còn mở giữ nguyên."""
        self.dieu_phoi.dong()
        with self._khoa:
            for sc in self._tat_ca.values():
                self._huy_ve(sc)
        if self._dong_ho_rieng:
            self._dong_ho.dong()

    # ------------------------------------------------------------ mở, thấy
    def _mo_su_co(self, kind: str, track_id: int, severity: Severity, ts: float,
                  detections: list[Detection], image: np.ndarray, wall_time: float,
                  box: Box, req: VerifyRequest, now: float) -> SuCo:
        sc = SuCo(event_id=str(uuid.uuid4()), severity=severity, kind=kind,
                  track_dau=track_id, ts=ts,
                  started_at=datetime.fromtimestamp(wall_time).astimezone(),
                  detections=list(detections), image=image, box=box, thay_cuoi=now,
                  last_seen_unix=wall_time, t_luot=now, req=req, tracks={track_id})
        self._mo = sc
        self._tat_ca[sc.event_id] = sc
        while len(self._tat_ca) > NHO_SU_CO:
            self._tat_ca.popitem(last=False)
        log.info("SỰ CỐ mới %s: %s %s track#%d video %.1fs", sc.event_id[:8],
                 kind, severity.value, track_id, ts)
        sc.ve_ket_thuc = self._dong_ho.hen(now + self._cfg.khoang_cach_s,
                                           lambda: self._kiem_ket_thuc(sc))
        sc.ve_kiem_lai = self._dong_ho.hen(now + self._cfg.vlm_kiem_lai_s,
                                           lambda: self._kiem_lai(sc))
        return sc

    @staticmethod
    def _ghi_thay(sc: SuCo, now: float, wall_time: float, req: VerifyRequest,
                  box: Box) -> None:
        sc.thay_cuoi, sc.last_seen_unix = now, wall_time
        sc.req, sc.box = req, box

    def _tang_muc(self, sc: SuCo, severity: Severity, detections: list[Detection],
                  image: np.ndarray, wall_time: float, req: VerifyRequest, now: float,
                  kind: str) -> list[tuple[str, VerifyRequest, int]]:
        """Mức tăng: ``updated`` ngay và lượt xác minh mới (nếu đã ``created``)."""
        cu, sc.severity = sc.severity, severity
        log.warning("sự cố %s: mức %s -> %s (%s)", sc.event_id[:8], cu.value,
                    severity.value, kind)
        if not sc.da_tao:
            # created chưa phát: created sẽ mang mức và keyframe mới.
            sc.detections, sc.image = list(detections), image
            return []
        sc.luot += 1
        sc.t_luot = now
        self._phat_ngay(sc, {"severity": severity.value}, anh=image,
                        detections=detections, wall_time=wall_time,
                        ly_do=f"mức tăng, lượt {sc.luot}")
        self._hen_kiem_lai(sc, now + self._cfg.vlm_kiem_lai_s)
        return [(sc.event_id, req, sc.luot)]

    # --------------------------------------------------------------- phát
    def _truong_su_co(self, sc: SuCo) -> dict[str, Any]:
        return {"status": "ended" if sc.da_ket_thuc else "open",
                "last_seen_ts": gio_iso(sc.last_seen_unix),
                "luot_xac_minh": sc.luot}

    def _danh_dau(self, sc: SuCo) -> None:
        """Có thay đổi thường: phát ở nhịp kế tiếp (ngay nếu đã đủ nhịp)."""
        sc.ban = True
        if sc.ve_nhip is not None or not sc.da_tao or sc.da_ket_thuc:
            return
        now = self._dong_ho.bay_gio()
        den = (sc.phat_cuoi if sc.phat_cuoi is not None else now) \
            + self._cfg.nhip_cap_nhat_s
        if den <= now:
            self._phat_nhip(sc)
        else:
            sc.ve_nhip = self._dong_ho.hen(den, lambda: self._het_nhip(sc))

    def _het_nhip(self, sc: SuCo) -> None:
        with self._khoa:
            sc.ve_nhip = None
            if sc.ban and not sc.da_ket_thuc:
                self._phat_nhip(sc)

    def _phat_nhip(self, sc: SuCo) -> None:
        self._phat(sc, {}, ly_do="nhịp cập nhật")

    def _phat_ngay(self, sc: SuCo, thay: dict[str, Any], *, ly_do: str,
                   anh: np.ndarray | None = None,
                   detections: list[Detection] | None = None,
                   wall_time: float | None = None) -> None:
        if sc.ve_nhip is not None:
            sc.ve_nhip.huy()
            sc.ve_nhip = None
        self._phat(sc, thay, ly_do=ly_do, anh=anh, detections=detections,
                   wall_time=wall_time)

    def _phat(self, sc: SuCo, thay: dict[str, Any], *, ly_do: str,
              anh: np.ndarray | None = None,
              detections: list[Detection] | None = None,
              wall_time: float | None = None) -> None:
        """Một ``updated``: trường chờ nhịp + ``thay`` + trường sự cố."""
        moi = {**sc.cho_phat, **thay, **self._truong_su_co(sc)}
        luc = (datetime.fromtimestamp(wall_time).astimezone()
               if wall_time is not None else None)
        ev = self._store.cap_nhat_su_co(sc.event_id, moi, anh=anh,
                                        detections=detections, luc=luc, ly_do=ly_do)
        sc.cho_phat.clear()
        sc.ban = False
        sc.phat_cuoi = self._dong_ho.bay_gio()
        if ev is not None and sc.record is not None:
            sc.record.update({"severity": ev.severity, "verification": ev.verification,
                              "status": ev.status, "luot_xac_minh": ev.luot_xac_minh,
                              "updated": True,
                              "so_updated": sc.record.get("so_updated", 0) + 1})
            if ev.verifier is not None:
                sc.record["verifier_status"] = ev.verifier.status

    # ------------------------------------------------------------ xác minh
    def _ket_qua(self, m: MucXacMinh, outcome: VerifyOutcome,
                 info: VerifierInfo) -> None:
        """Callback của bộ điều phối (đang giữ khoá của nó) cho một lượt."""
        with self._khoa:
            sc = self._tat_ca.get(m.event_id)
            if sc is None:
                return
            if m.luot != sc.luot:
                log.info("sự cố %s: bỏ kết quả lượt %d (đang ở lượt %d)",
                         sc.event_id[:8], m.luot, sc.luot)
                return
            if not sc.da_tao:
                self._tao(sc, outcome, info)
                return
            if m.luot >= 2 and outcome.result is None:
                # Lượt sau chờ hay lỗi không xoá kết luận đã có.
                if info.status != "PENDING":
                    log.info("sự cố %s: lượt %d %s, giữ kết luận trước",
                             sc.event_id[:8], m.luot, info.status)
                return
            thay = {"verification": outcome.verification, "vlm": outcome.result,
                    "verifier": info}
            doi = sc.verifier is None or info.status != sc.verifier.status
            sc.verifier = info
            if doi:
                self._phat_ngay(sc, thay, ly_do=f"xác minh lượt {m.luot}")
            else:
                sc.cho_phat.update(thay)
                self._danh_dau(sc)

    def _tao(self, sc: SuCo, outcome: VerifyOutcome, info: VerifierInfo) -> None:
        ev = self._store.create(
            severity=sc.severity.value, verification=outcome.verification,
            video_ts=sc.ts, detections=sc.detections, image=sc.image,
            vlm=outcome.result, started_at=sc.started_at, verifier=info,
            event_id=sc.event_id, su_co=self._truong_su_co(sc))
        sc.da_tao, sc.verifier = True, info
        sc.phat_cuoi = self._dong_ho.bay_gio()
        sc.image = None                    # keyframe đã ghi đĩa, không giữ RAM
        sc.record = {"event_id": ev.event_id, "kind": sc.kind,
                     "severity": ev.severity, "verification": ev.verification,
                     "video_ts_sec": ev.video_ts_sec, "track_id": sc.track_dau,
                     "vlm_latency_s": round(outcome.latency_s, 2),
                     "vlm_attempts": outcome.attempts, "vlm_error": outcome.error,
                     "updated": False, "verifier_status": info.status,
                     "status": ev.status, "luot_xac_minh": ev.luot_xac_minh,
                     "so_updated": 0}
        if self._summary is not None:
            self._summary.alerts.append(sc.record)
        if self._health is not None:
            self._health.alerts += 1
        if sc.da_ket_thuc:
            self._phat_ngay(sc, {}, ly_do="kết thúc trước khi created")
        elif sc.ban:
            self._danh_dau(sc)

    # --------------------------------------------------------- kết thúc, kiểm lại
    def _kiem_ket_thuc(self, sc: SuCo) -> None:
        with self._khoa:
            sc.ve_ket_thuc = None
            if sc.da_ket_thuc:
                return
            now = self._dong_ho.bay_gio()
            den = sc.thay_cuoi + self._cfg.khoang_cach_s
            if now < den:
                sc.ve_ket_thuc = self._dong_ho.hen(den, lambda: self._kiem_ket_thuc(sc))
                return
            sc.da_ket_thuc = True
            if self._mo is sc:
                self._mo = None
            if sc.ve_kiem_lai is not None:
                sc.ve_kiem_lai.huy()
                sc.ve_kiem_lai = None
            log.info("SỰ CỐ kết thúc %s: %.0fs không thấy cháy", sc.event_id[:8],
                     now - sc.thay_cuoi)
            if sc.da_tao:
                self._phat_ngay(sc, {}, ly_do="kết thúc")

    def _hen_kiem_lai(self, sc: SuCo, luc: float) -> None:
        if sc.ve_kiem_lai is not None:
            sc.ve_kiem_lai.huy()
        sc.ve_kiem_lai = self._dong_ho.hen(luc, lambda: self._kiem_lai(sc))

    def _kiem_lai(self, sc: SuCo) -> None:
        viec: tuple[str, VerifyRequest, int] | None = None
        with self._khoa:
            sc.ve_kiem_lai = None
            if sc.da_ket_thuc:
                return
            now = self._dong_ho.bay_gio()
            den = sc.t_luot + self._cfg.vlm_kiem_lai_s
            if now < den:
                self._hen_kiem_lai(sc, den)
                return
            if not sc.da_tao or now - sc.thay_cuoi > self._cfg.nhip_cap_nhat_s:
                # Không còn thấy cháy gần đây: không có gì mới để xác minh.
                self._hen_kiem_lai(sc, now + self._cfg.vlm_kiem_lai_s)
                return
            sc.luot += 1
            sc.t_luot = now
            log.info("sự cố %s: kiểm lại VLM, lượt %d", sc.event_id[:8], sc.luot)
            req = sc.req
            req = VerifyRequest(req.frame, req.box, req.context, sc.severity.value,
                                req.video_ts, req.first_frame)
            viec = (sc.event_id, req, sc.luot)
            self._danh_dau(sc)              # luot_xac_minh mới đi theo nhịp
            self._hen_kiem_lai(sc, now + self._cfg.vlm_kiem_lai_s)
        self.dieu_phoi.gui(viec[0], viec[1], None, luot=viec[2])

    @staticmethod
    def _huy_ve(sc: SuCo) -> None:
        for ten in ("ve_nhip", "ve_ket_thuc", "ve_kiem_lai"):
            ve = getattr(sc, ten)
            if ve is not None:
                ve.huy()
                setattr(sc, ten, None)
