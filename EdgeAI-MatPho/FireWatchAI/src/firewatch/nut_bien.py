"""Chế độ nút biên: nhiều camera trong một tiến trình (dịch vụ ``firewatch-ai``).

``python -m firewatch edge`` (lệnh mặc định của image) đọc cấu hình nút biên từ
biến môi trường (``nut_bien_cau_hinh``), rồi:

- chạy một ``Pipeline`` cho mỗi camera trên ``rtsp://mediamtx:8554/live/{cam_id}``,
  mọi camera dùng chung một model (``DetectorDungChung``);
- mỗi 2 s hỏi ``GET /api/v1/edge/cameras`` của edge_backend: camera có
  ``should_ai_scan_now`` thì chạy (kể cả camera mới), camera đang nghỉ theo lịch
  hoặc bị tắt thì ngắt RTSP ngay; camera không có trong danh sách giữ nguyên.
  giống khung ``ai_service`` mà FireWatchAI đã thay;
- gửi event tới cổng chuyển tiếp ``/api/v1/edge/ai-events`` của edge_backend
  (cloud backend nếu không có edge_backend), kèm ``X-Internal-Secret``;
- phục vụ ``GET /health`` cho HEALTHCHECK của Docker.

Camera không mở được nguồn hoặc mất nguồn thì tự chạy lại, chờ 2 s rồi gấp đôi,
tối đa 30 s. Trọng số không có lớp fire/smoke thì cả tiến trình dừng mã 1.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from collections.abc import Callable, MutableMapping
from typing import Any

from fastapi import FastAPI, Response

from .alerts import EventStore
from .config import Config, env_secret
from .nut_bien_cau_hinh import (CameraBien, CauHinhBien, ap_webhook,
                                bien_bi_bo_qua, camera_tu_edge)
from .pipeline import PipelineHealth

log = logging.getLogger(__name__)

DINH_DANG_LOG_BIEN = "%(asctime)s %(levelname)s [%(threadName)s] %(message)s"
HAN_KET_NOI_S = 120.0
"""Camera chưa có heartbeat nào quá chừng này giây (tính từ lúc bắt đầu chạy)
thì ``/health`` trả 503."""


class DetectorDungChung:
    """Một model cho mọi camera; ``detect`` được tuần tự hoá bằng khoá.

    Parameters
    ----------
    det : Any
        ``Detector`` thật (hoặc đối tượng cùng giao diện: ``detect``,
        ``keep_ids``, ``weights``).
    """

    def __init__(self, det: Any) -> None:
        self._det = det
        self._khoa = threading.Lock()
        self.keep_ids = det.keep_ids
        self.weights = det.weights

    def detect(self, image: Any) -> Any:
        with self._khoa:
            return self._det.detect(image)


class CameraChay:
    """Một camera: chạy ``Pipeline`` trên nguồn của nó, tự chạy lại khi lỗi.

    Parameters
    ----------
    cam : CameraBien
        Camera.
    nguon : str
        URL nguồn (chỉ dùng để hiển thị; ``tao_pipeline`` đã biết nguồn).
    tao_pipeline : Callable[[PipelineHealth, Any], Any]
        Dựng một ``Pipeline`` mới (có ``run()``, ``dung()``) cho mỗi lần chạy;
        tham số thứ hai là sự cố đang mở của lần chạy trước (``su_co_mo`` của
        pipeline vừa dừng, hoặc ``None``) để lần chạy lại giữ nguyên
        ``event_id`` thay vì mở sự cố mới cho cùng đám cháy.
    khi_loi_chet : Callable[[str], None]
        Gọi khi gặp lỗi không thể chạy lại (``SystemExit`` từ pipeline, ví dụ
        trọng số sai): cả tiến trình phải dừng.
    cho_lai_s : tuple[float, float]
        Thời gian chờ đầu tiên và tối đa trước khi chạy lại.
    bay_gio : Callable[[], float]
        Đồng hồ đơn điệu (tiêm được trong test).
    """

    def __init__(self, cam: CameraBien, nguon: str,
                 tao_pipeline: Callable[[PipelineHealth], Any],
                 khi_loi_chet: Callable[[str], None], *,
                 cho_lai_s: tuple[float, float] = (2.0, 30.0),
                 bay_gio: Callable[[], float] = time.monotonic) -> None:
        self.cam = cam
        self.nguon = nguon
        self._tao = tao_pipeline
        self._khi_loi_chet = khi_loi_chet
        self._cho_dau, self._cho_toi_da = cho_lai_s
        self._bay_gio = bay_gio
        self._dung = threading.Event()
        self._khoa = threading.Lock()
        self._pipe: Any = None
        self.health: PipelineHealth | None = None
        self.bat_dau_luc: float | None = None
        self.so_lan_chay_lai = 0
        self.loi_cuoi: str | None = None
        self.da_co_heartbeat = False
        """Đã từng nhận heartbeat ở một lần chạy nào đó."""
        self.su_co_mo: Any = None
        """Sự cố đang mở do lần chạy gần nhất để lại (``Pipeline.su_co_mo``)."""
        self._thread = threading.Thread(target=self._vong,
                                        name=f"cam-{cam.cam_id}", daemon=True)

    def start(self) -> None:
        self.bat_dau_luc = self._bay_gio()
        self._thread.start()

    def stop(self, timeout_s: float = 15.0) -> None:
        """Ngắt camera: dừng pipeline đang chạy và không chạy lại."""
        self._dung.set()
        with self._khoa:
            pipe = self._pipe
        if pipe is not None:
            pipe.dung()
        if self._thread.is_alive():
            self._thread.join(timeout_s)

    @property
    def dang_chay(self) -> bool:
        return self._thread.is_alive()

    def _vong(self) -> None:
        cho = self._cho_dau
        while not self._dung.is_set():
            health = PipelineHealth()
            pipe = self._tao(health, self.su_co_mo)
            with self._khoa:
                self.health, self._pipe = health, pipe
            if self._dung.is_set():
                break
            try:
                pipe.run()
                if self._dung.is_set():
                    break
                self.loi_cuoi = "nguồn kết thúc"
            except SystemExit as exc:
                msg = f"camera {self.cam.cam_id}: {exc}"
                self.loi_cuoi = msg
                self._khi_loi_chet(msg)
                break
            except Exception as exc:  # noqa: BLE001 - chạy lại, không dừng tiến trình
                self.loi_cuoi = f"{type(exc).__name__}: {exc}"
            finally:
                self.su_co_mo = getattr(pipe, "su_co_mo", None)
            if self._dung.is_set():
                break
            if health.heartbeats > 0:
                self.da_co_heartbeat = True
                cho = self._cho_dau
            self.so_lan_chay_lai += 1
            log.warning("camera %s (%s): %s; chạy lại sau %.0f s", self.cam.cam_id,
                        self.nguon, self.loi_cuoi, cho)
            if self._dung.wait(cho):
                break
            cho = min(cho * 2, self._cho_toi_da)

    def trang_thai(self) -> dict[str, Any]:
        """Trạng thái cho ``/health``; ``ok`` cho biết camera có làm 503 không.

        ``ok``: heartbeat đều. ``connecting``: lần chạy hiện tại chưa có
        heartbeat (đang mở nguồn hoặc chờ chạy lại). ``stale``: có heartbeat
        nhưng đã quá lâu. Camera chưa từng có heartbeat được chờ
        ``HAN_KET_NOI_S`` kể từ lúc bắt đầu (MediaMTX có thể chưa phát luồng);
        sau đó, hoặc khi đã từng chạy rồi mất, ``connecting`` là hỏng.
        """
        with self._khoa:
            health = self.health
        snap = health.snapshot() if health is not None else None
        tuoi = (self._bay_gio() - self.bat_dau_luc
                if self.bat_dau_luc is not None else 0.0)
        tung_chay = self.da_co_heartbeat or bool(snap and snap["heartbeats"])
        if snap is not None and snap["status"] == "ok":
            state, ok = "ok", True
        elif snap is not None and snap["status"] == "stale":
            state, ok = "stale", False
        else:
            state = "connecting"
            ok = not tung_chay and tuoi <= HAN_KET_NOI_S
        return {"state": state, "ok": ok, "pipeline": snap,
                "restarts": self.so_lan_chay_lai, "last_error": self.loi_cuoi}


class GiamSatBien:
    """Giữ tập camera đang chạy khớp với cấu hình và lịch quét của edge_backend.

    Parameters
    ----------
    cameras_ban_dau : tuple[CameraBien, ...]
        Camera khai trong ``AI_CAMERA_STREAMS`` / ``AI_CAMERA_IDS``, chạy ngay.
    tao_camera : Callable[[CameraBien], CameraChay]
        Dựng worker cho một camera (chưa ``start``).
    lay_camera_edge : Callable[[], dict[str, bool]] or None
        Đọc ``cam_id -> có quét`` từ edge_backend; ``None`` thì không đồng bộ.
    nhip_s : float
        Khoảng giữa hai lần đồng bộ.
    """

    def __init__(self, cameras_ban_dau: tuple[CameraBien, ...],
                 tao_camera: Callable[[CameraBien], CameraChay],
                 lay_camera_edge: Callable[[], dict[str, bool]] | None,
                 nhip_s: float = 2.0) -> None:
        self._ban_dau = cameras_ban_dau
        self._context = {c.cam_id: c for c in cameras_ban_dau}
        self._tao = tao_camera
        self._lay = lay_camera_edge
        self._nhip = nhip_s
        self._khoa = threading.Lock()
        self._dang_chay: dict[str, CameraChay] = {}
        self._tam_dung: set[str] = set()
        self._dung = threading.Event()
        self.loi_chet: str | None = None
        self.dong_bo_luc: float | None = None
        self.loi_dong_bo: str | None = None
        self._thread: threading.Thread | None = None

    # ---------------------------------------------------------------- vòng
    def bat_dau(self) -> None:
        for cam in self._ban_dau:
            self._bat(cam.cam_id)
        if self._lay is not None:
            self._thread = threading.Thread(target=self._vong, name="dong-bo-edge",
                                            daemon=True)
            self._thread.start()

    def _vong(self) -> None:
        while not self._dung.is_set():
            self.dong_bo_mot_lan()
            if self._dung.wait(self._nhip):
                break

    def dong_bo_mot_lan(self) -> None:
        """Một lần đồng bộ với edge_backend; lỗi mạng thì giữ nguyên tập camera."""
        try:
            muon = self._lay() if self._lay is not None else {}
        except Exception as exc:  # noqa: BLE001
            if self.loi_dong_bo is None:
                log.warning("chưa đọc được danh sách camera của edge_backend: %s",
                            exc)
            self.loi_dong_bo = f"{type(exc).__name__}: {exc}"
            return
        if self.loi_dong_bo is not None:
            log.info("đã đọc được danh sách camera của edge_backend")
        self.loi_dong_bo = None
        self.dong_bo_luc = time.time()
        for cam_id, quet in muon.items():
            if quet:
                self._bat(cam_id)
            else:
                self._tat(cam_id)

    def _bat(self, cam_id: str) -> None:
        with self._khoa:
            if self._dung.is_set() or cam_id in self._dang_chay:
                return
            worker = self._tao(self._context.get(cam_id, CameraBien(cam_id)))
            self._dang_chay[cam_id] = worker
            self._tam_dung.discard(cam_id)
        worker.start()
        log.info("camera %s: nối RTSP vào FireWatch (%s)", cam_id, worker.nguon)

    def _tat(self, cam_id: str) -> None:
        with self._khoa:
            worker = self._dang_chay.pop(cam_id, None)
            self._tam_dung.add(cam_id)
        if worker is not None:
            log.info("camera %s: ngắt RTSP (tắt hoặc đang trong giờ nghỉ theo lịch)",
                     cam_id)
            worker.stop()

    def bao_loi_chet(self, msg: str) -> None:
        log.error("lỗi không chạy lại được, dừng tiến trình: %s", msg)
        self.loi_chet = msg

    def dung_het(self) -> None:
        self._dung.set()
        with self._khoa:
            workers = list(self._dang_chay.values())
            self._dang_chay.clear()
        for w in workers:
            w.stop()
        if self._thread is not None:
            self._thread.join(5)

    # -------------------------------------------------------------- health
    def camera_dang_chay(self) -> list[str]:
        with self._khoa:
            return sorted(self._dang_chay)

    def trang_thai(self) -> tuple[int, dict[str, Any]]:
        """(mã HTTP, thân) cho ``/health``: 503 khi có camera đang chạy mà hỏng."""
        with self._khoa:
            workers = dict(self._dang_chay)
            tam_dung = sorted(self._tam_dung)
        cams = {cid: w.trang_thai() for cid, w in sorted(workers.items())}
        hong = [cid for cid, t in cams.items() if not t["ok"]]
        ok = not hong and self.loi_chet is None
        body = {"status": "ok" if ok else "degraded", "mode": "nut_bien",
                "cameras": cams, "paused": tam_dung, "unhealthy": hong,
                "edge_sync": {"last_ok_unix": self.dong_bo_luc,
                              "error": self.loi_dong_bo},
                "fatal": self.loi_chet}
        return (200 if ok else 503), body


def doc_camera_edge(url: str, timeout_s: float = 3.0) -> dict[str, bool]:
    """``GET`` danh sách camera của edge_backend (``camera_tu_edge``)."""
    with urllib.request.urlopen(url, timeout=timeout_s) as resp:
        return camera_tu_edge(json.loads(resp.read() or b"{}"))


def cau_hinh_camera(cfg: Config, cam: CameraBien) -> Config:
    """Bản config của một camera: ``camera.id`` = ``cam_id``; event và log
    nằm trong thư mục con theo ``cam_id`` để các camera không ghi đè nhau."""
    c = cfg.model_copy(deep=True)
    c.camera.id = cam.cam_id
    if cam.context:
        c.camera.context = cam.context
    c.alerts.events_dir = cfg.alerts.events_dir / cam.cam_id
    c.output.dir = cfg.output.dir / cam.cam_id
    return c


def tao_app(gs: GiamSatBien) -> FastAPI:
    """Ứng dụng FastAPI nhỏ: ``/health`` và ``/``."""
    app = FastAPI(title="FireWatch (nút biên)")

    @app.get("/health")
    def health(response: Response) -> dict[str, Any]:
        code, body = gs.trang_thai()
        response.status_code = code
        return body

    @app.get("/")
    def index() -> dict[str, Any]:
        return {"service": "firewatch", "mode": "nut_bien",
                "cameras": gs.camera_dang_chay()}

    return app


def _dat_dinh_dang_log() -> None:
    from . import pipeline

    pipeline.DINH_DANG_LOG = DINH_DANG_LOG_BIEN
    for h in logging.getLogger().handlers:
        h.setFormatter(logging.Formatter(DINH_DANG_LOG_BIEN, datefmt="%H:%M:%S"))


def chay_nut_bien(cfg: Config, cfgb: CauHinhBien, *, host: str | None,
                  port: int | None, env: MutableMapping[str, str]) -> int:
    """Chạy chế độ nút biên tới khi nhận tín hiệu dừng.

    Parameters
    ----------
    cfg : Config
        Config đã áp ``GHI_DE_MAC_DINH`` và ``--set``.
    cfgb : CauHinhBien
        Cấu hình nút biên từ biến môi trường.
    host, port : str or None, int or None
        Địa chỉ của ``/health``; ``None`` thì lấy ``server`` trong config.
    env : MutableMapping[str, str]
        Môi trường (thường là ``os.environ``); đích webhook được điền vào đây.

    Returns
    -------
    int
        0 khi dừng bình thường, 1 khi có lỗi không chạy lại được.
    """
    import uvicorn

    from .detector import Detector
    from .pipeline import Pipeline

    _dat_dinh_dang_log()
    bo_qua = bien_bi_bo_qua(env)
    if bo_qua:
        log.info("bỏ qua %s: nhịp, ngưỡng, cooldown và trọng số lấy từ config.yaml "
                 "và models/README.md", ", ".join(bo_qua))
    url, co_token = ap_webhook(cfgb, cfg.alerts.webhook_url_env,
                               cfg.alerts.webhook_token_env, env)
    log.info("nút biên: %d camera khai sẵn, đồng bộ %s, webhook %s (%s token)",
             len(cfgb.cameras), cfgb.camera_url or "tắt", url or "không có",
             "có" if co_token else "không")
    if not env_secret(cfg.vlm.api_key_env) and cfg.vlm.provider != "mock":
        log.warning("không có %s: VLM tắt, event cần người xác thực",
                    cfg.vlm.api_key_env)

    det = Detector(cfg.detector, cfg)
    if det.keep_ids is None:
        log.error("trọng số %s không có lớp %s: không chạy (xem models/README.md)",
                  det.weights.name, cfg.detector.classes)
        return 1
    dung_chung = DetectorDungChung(det)
    stores: dict[str, EventStore] = {}
    gs_hop: dict[str, Any] = {}

    def khi_loi_chet(msg: str) -> None:
        gs_hop["gs"].bao_loi_chet(msg)
        if "server" in gs_hop:
            gs_hop["server"].should_exit = True

    def tao_camera(cam: CameraBien) -> CameraChay:
        c = cau_hinh_camera(cfg, cam)
        if cam.cam_id not in stores:
            stores[cam.cam_id] = EventStore(c.alerts, c.camera, c)
        store = stores[cam.cam_id]
        nguon = cfgb.nguon(cam.cam_id)

        def tao_pipeline(health: PipelineHealth, su_co_truoc: Any) -> Pipeline:
            return Pipeline(c, nguon, store=store, strict=True, health=health,
                            detector=dung_chung, su_co_truoc=su_co_truoc)

        return CameraChay(cam, nguon, tao_pipeline, khi_loi_chet)

    lay = ((lambda: doc_camera_edge(cfgb.camera_url)) if cfgb.camera_url
           else None)
    gs = GiamSatBien(cfgb.cameras, tao_camera, lay, cfgb.nhip_dong_bo_s)
    gs_hop["gs"] = gs
    server = uvicorn.Server(uvicorn.Config(
        tao_app(gs), host=host or cfg.server.host, port=port or cfg.server.port,
        log_level="warning"))
    gs_hop["server"] = server
    gs.bat_dau()
    try:
        server.run()
    finally:
        gs.dung_het()
    return 1 if gs.loi_chet else 0
