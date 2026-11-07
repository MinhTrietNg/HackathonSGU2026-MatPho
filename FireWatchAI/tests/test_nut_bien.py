"""Chế độ nút biên (FireWatchAI thay ``EdgeAI-MatPho/ai_service``).

Biến môi trường trong test lấy đúng giá trị của ``EdgeAI-MatPho/docker-compose.yml``
(dịch vụ ``firewatch-ai``) và ``.env.example`` của nút biên. Pipeline là đồ giả:
không cần trọng số, không mở RTSP.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from firewatch import __main__ as cli
from firewatch import nut_bien as nb
from firewatch.config import Config
from firewatch.nut_bien_cau_hinh import (CameraBien, ap_webhook, bien_bi_bo_qua,
                                         camera_tu_edge, doc_moi_truong)

CFG = str(Path(__file__).resolve().parents[1] / "config.yaml")
COMPOSE_ENV = {
    # khối environment của firewatch-ai
    "EDGE_DEVICE_ID": "edg_local_01",
    "MEDIAMTX_RTSP_URL": "rtsp://mediamtx:8554",
    "STREAM_PATH_TEMPLATE": "live/{cam_id}",
    "CLOUD_BACKEND_API_URL": "http://host.docker.internal:8000",
    "EDGE_BACKEND_API_URL": "http://edge-backend:8090",
    "INTERNAL_API_SECRET_KEY": "secure_internal_key_for_ai_and_worker_communication",
    "AI_CAMERA_STREAMS": '[{"cam_id": "cam_01"}]',
    "AI_TARGET_FPS": "3.0",
    "LOG_LEVEL": "INFO",
    # thêm từ .env.example (env_file)
    "AI_CAMERA_IDS": "cam_01",
    "AI_CONFIDENCE_THRESHOLD": "0.50",
    "AI_ALERT_COOLDOWN_S": "15.0",
    "AI_MODEL_WEIGHTS_PATH": "/app/weights/trong_so.pt",   # .env.example: đường khác
}


# ------------------------------------------------------------- môi trường
def test_doc_dung_moi_truong_cua_compose():
    c = doc_moi_truong(COMPOSE_ENV)
    assert c is not None
    assert c.cameras == (CameraBien("cam_01"),)
    assert c.nguon("cam_01") == "rtsp://mediamtx:8554/live/cam_01"
    assert c.webhook_url == "http://edge-backend:8090/api/v1/edge/ai-events"
    assert c.camera_url == "http://edge-backend:8090/api/v1/edge/cameras"
    assert c.bi_mat == COMPOSE_ENV["INTERNAL_API_SECRET_KEY"]
    assert bien_bi_bo_qua(COMPOSE_ENV) == [
        "AI_TARGET_FPS", "AI_CONFIDENCE_THRESHOLD", "AI_ALERT_COOLDOWN_S",
        "AI_MODEL_WEIGHTS_PATH"]


def test_khong_phai_nut_bien():
    assert doc_moi_truong({}) is None
    assert doc_moi_truong({"FIREWATCH_SOURCE": "rtsp://cam/1"}) is None
    assert doc_moi_truong({"AI_CAMERA_STREAMS": "  "}) is None


def test_khong_co_edge_thi_gui_thang_cloud():
    c = doc_moi_truong({"AI_CAMERA_IDS": "cam_01, cam_02,cam_01",
                        "CLOUD_BACKEND_URL": "https://api.vi.du/"})
    assert [x.cam_id for x in c.cameras] == ["cam_01", "cam_02"]
    assert c.webhook_url == "https://api.vi.du/api/v1/internal/ai/fire-events"
    assert c.camera_url is None
    assert c.nguon("cam_02") == "rtsp://mediamtx:8554/live/cam_02"


def test_camera_streams_hong_thi_dung_camera_ids():
    c = doc_moi_truong({"AI_CAMERA_STREAMS": "[{cam_id: x}", "AI_CAMERA_IDS": "c9"})
    assert c.cameras == (CameraBien("c9"),)


def test_camera_streams_co_context():
    c = doc_moi_truong({"AI_CAMERA_STREAMS":
                        '[{"cam_id": "a", "context": "ngoai"}, {"cam_id": "b", '
                        '"context": "BEP"}, {"x": 1}, {"cam_id": "a"}]'})
    assert c.cameras == (CameraBien("a", "NGOAI"), CameraBien("b", None))


def test_camera_tu_edge():
    body = {"cameras": [
        {"cam_id": "cam_01", "is_active": True, "should_ai_scan_now": True},
        {"cam_id": "cam_02", "is_active": True, "should_ai_scan_now": False},
        {"cam_id": "cam_03", "is_active": False, "should_ai_scan_now": True},
        {"cam_id": "cam_04"}, {"is_active": True}, "rac"]}
    assert camera_tu_edge(body) == {"cam_01": True, "cam_02": False,
                                    "cam_03": False, "cam_04": True}
    assert camera_tu_edge([]) == {} and camera_tu_edge({"cameras": None}) == {}


def test_ap_webhook_khong_de_cau_hinh_tay():
    c = doc_moi_truong(COMPOSE_ENV)
    env: dict[str, str] = {}
    url, co_token = ap_webhook(c, "W_URL", "W_TOKEN", env)
    assert url == c.webhook_url and co_token
    assert env["W_TOKEN"] == COMPOSE_ENV["INTERNAL_API_SECRET_KEY"]
    env = {"W_URL": "http://tu-dat/hook", "W_TOKEN": "rieng"}
    assert ap_webhook(c, "W_URL", "W_TOKEN", env) == ("http://tu-dat/hook", True)
    assert env["W_TOKEN"] == "rieng"


def test_cau_hinh_camera_tach_thu_muc(tmp_path):
    cfg = Config(root=tmp_path)
    c = nb.cau_hinh_camera(cfg, CameraBien("cam_02", "TRET"))
    assert (c.camera.id, c.camera.context) == ("cam_02", "TRET")
    assert c.resolve(c.alerts.events_dir) == tmp_path / "events" / "cam_02"
    assert c.resolve(c.output.dir) == tmp_path / "runs" / "cam_02"
    assert (cfg.camera.id, cfg.alerts.events_dir) == ("cam01", Path("events"))


# --------------------------------------------------------------- detector
def test_detector_dung_chung_tuan_tu():
    class Det:
        keep_ids, weights = [0, 1], Path("x.pt")

        def __init__(self) -> None:
            self.trong, self.max_trong = 0, 0

        def detect(self, image):
            self.trong += 1
            self.max_trong = max(self.max_trong, self.trong)
            time.sleep(0.002)
            self.trong -= 1
            return image

    det = Det()
    dc = nb.DetectorDungChung(det)
    ts = [threading.Thread(target=lambda: [dc.detect(1) for _ in range(10)])
          for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert det.max_trong == 1 and dc.keep_ids == [0, 1]


# ------------------------------------------------------------- một camera
class PipelineGia:
    """``hanh_vi``: ``chay`` (heartbeat tới khi dung), ``loi``, ``chet``."""

    def __init__(self, health, hanh_vi: str) -> None:
        self.health = health
        self.hanh_vi = hanh_vi
        self._dung = threading.Event()

    def run(self):
        if self.hanh_vi == "loi":
            raise RuntimeError("không mở được nguồn live")
        if self.hanh_vi == "chet":
            raise SystemExit("trọng số không có lớp fire/smoke")
        while not self._dung.wait(0.002):
            self.health.beat()

    def dung(self) -> None:
        self._dung.set()


def _cho(dk, han_s: float = 5.0) -> bool:
    het = time.monotonic() + han_s
    while time.monotonic() < het:
        if dk():
            return True
        time.sleep(0.005)
    return dk()


def _camera(kich_ban: list[str], chet: list[str] | None = None,
            bay_gio=time.monotonic) -> nb.CameraChay:
    it = iter(kich_ban)
    return nb.CameraChay(
        CameraBien("cam_01"), "rtsp://mediamtx:8554/live/cam_01",
        lambda h: PipelineGia(h, next(it, "chay")),
        (chet.append if chet is not None else lambda m: None),
        cho_lai_s=(0.005, 0.02), bay_gio=bay_gio)


def test_camera_chay_lai_khi_loi_roi_dung_duoc():
    w = _camera(["loi", "loi"])
    w.start()
    assert _cho(lambda: w.trang_thai()["state"] == "ok")
    assert w.so_lan_chay_lai == 2 and "không mở được" in w.loi_cuoi
    t0 = time.monotonic()
    w.stop()
    assert not w.dang_chay and time.monotonic() - t0 < 1


def test_camera_loi_chet_bao_len_va_khong_chay_lai():
    chet: list[str] = []
    w = _camera(["chet"], chet)
    w.start()
    assert _cho(lambda: not w.dang_chay)
    assert len(chet) == 1 and "fire/smoke" in chet[0] and w.so_lan_chay_lai == 0


def test_health_camera_cho_ket_noi_co_han():
    gio = [100.0]
    w = _camera([], bay_gio=lambda: gio[0])
    w.bat_dau_luc = 100.0
    assert w.trang_thai() | {"pipeline": None} == {
        "state": "connecting", "ok": True, "pipeline": None, "restarts": 0,
        "last_error": None}
    gio[0] = 100.0 + nb.HAN_KET_NOI_S + 1
    assert w.trang_thai()["ok"] is False
    gio[0] = 101.0
    w.da_co_heartbeat = True          # đã từng chạy rồi mất nguồn: hỏng ngay
    assert w.trang_thai()["ok"] is False


# ---------------------------------------------------------------- giám sát
class CameraGia:
    def __init__(self, cam: CameraBien) -> None:
        self.cam, self.nguon = cam, f"rtsp://x/{cam.cam_id}"
        self.chay, self.da_dung, self.ok = False, False, True

    def start(self) -> None:
        self.chay = True

    def stop(self) -> None:
        self.chay, self.da_dung = False, True

    def trang_thai(self) -> dict:
        return {"state": "ok" if self.ok else "stale", "ok": self.ok}


def _giam_sat(muon):
    tao: dict[str, CameraGia] = {}

    def tao_camera(cam: CameraBien) -> CameraGia:
        tao[cam.cam_id] = CameraGia(cam)
        return tao[cam.cam_id]

    gs = nb.GiamSatBien((CameraBien("cam_01", "NGOAI"), CameraBien("cam_09")),
                        tao_camera, lambda: muon(), nhip_s=60)
    return gs, tao


def test_giam_sat_theo_lich_quet_cua_edge():
    hien: dict = {"cam_01": True, "cam_02": True}
    gs, tao = _giam_sat(lambda: hien)
    gs.bat_dau()
    try:
        assert _cho(lambda: "cam_02" in tao)       # vòng đồng bộ đầu tiên
        assert gs.camera_dang_chay() == ["cam_01", "cam_02", "cam_09"]
        assert tao["cam_01"].cam.context == "NGOAI"
        hien.update(cam_01=False)                  # vào giờ nghỉ: ngắt ngay
        gs.dong_bo_mot_lan()
        assert tao["cam_01"].da_dung and gs.camera_dang_chay() == ["cam_02",
                                                                    "cam_09"]
        code, body = gs.trang_thai()
        assert code == 200 and body["paused"] == ["cam_01"]
        hien.update(cam_01=True)                   # hết giờ nghỉ: nối lại
        gs.dong_bo_mot_lan()
        assert tao["cam_01"].chay and "cam_01" in gs.camera_dang_chay()
    finally:
        gs.dung_het()
    assert all(not c.chay for c in tao.values())


def test_giam_sat_mat_edge_thi_giu_nguyen_va_bao_loi():
    def hong():
        raise OSError("connection refused")

    gs, tao = _giam_sat(hong)
    gs.bat_dau()
    try:
        assert _cho(lambda: gs.loi_dong_bo is not None)
        assert gs.camera_dang_chay() == ["cam_01", "cam_09"]
        code, body = gs.trang_thai()
        assert code == 200 and "refused" in body["edge_sync"]["error"]
        tao["cam_09"].ok = False
        code, body = gs.trang_thai()
        assert code == 503 and body["unhealthy"] == ["cam_09"]
        tao["cam_09"].ok = True
        gs.bao_loi_chet("trọng số sai")
        assert gs.trang_thai()[0] == 503
    finally:
        gs.dung_het()


def test_health_http():
    from fastapi.testclient import TestClient

    gs, tao = _giam_sat(lambda: {})
    gs.bat_dau()
    try:
        cl = TestClient(nb.tao_app(gs))
        r = cl.get("/health")
        assert r.status_code == 200 and r.json()["mode"] == "nut_bien"
        tao["cam_01"].ok = False
        assert cl.get("/health").status_code == 503
        assert cl.get("/").json()["cameras"] == ["cam_01", "cam_09"]
    finally:
        gs.dung_het()


# -------------------------------------------------------------------- CLI
@pytest.fixture
def moi_truong(monkeypatch):
    for k in list(COMPOSE_ENV) + ["FIREWATCH_SOURCE", "EDGE_BACKEND_URL",
                                  "CLOUD_BACKEND_URL"]:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def test_cli_edge_khong_co_gi_de_chay(moi_truong):
    assert cli.main(["--config", CFG, "edge"]) == 2


def test_cli_edge_lui_ve_serve_khi_chi_co_firewatch_source(moi_truong):
    goi: dict = {}
    moi_truong.setenv("FIREWATCH_SOURCE", "rtsp://cam/1")
    import firewatch.server as server

    moi_truong.setattr(server, "serve", lambda cfg, **k: goi.update(k) or 0)
    assert cli.main(["--config", CFG, "edge", "--port", "8001"]) == 0
    assert goi["source"] == "rtsp://cam/1" and goi["exit_on_pipeline_stop"]
    assert goi["port"] == 8001


def test_cli_edge_nut_bien_ghi_de_mac_dinh_va_set_van_thang(moi_truong):
    goi: dict = {}
    for k, v in COMPOSE_ENV.items():
        moi_truong.setenv(k, v)
    moi_truong.setattr(nb, "chay_nut_bien",
                       lambda cfg, cfgb, **k: goi.update(cfg=cfg, cfgb=cfgb) or 0)
    assert cli.main(["--config", CFG, "edge"]) == 0
    assert goi["cfg"].webhook.gui_anh is True
    assert goi["cfg"].alerts.webhook_timeout_s == 10
    assert goi["cfgb"].cameras == (CameraBien("cam_01"),)
    assert cli.main(["--config", CFG, "--set", "webhook.gui_anh=false",
                     "edge"]) == 0
    assert goi["cfg"].webhook.gui_anh is False
