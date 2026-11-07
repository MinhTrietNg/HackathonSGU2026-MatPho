"""Cấu hình nút biên (EdgeAI-MatPho) đọc từ biến môi trường.

Khi FireWatchAI chạy làm dịch vụ ``firewatch-ai`` của ``EdgeAI-MatPho``,
docker-compose của nút biên truyền cấu hình qua biến môi trường: ``.env`` của nút
biên và khối ``environment`` của dịch vụ. Module này dịch các biến đó sang
danh sách camera, nguồn RTSP và đích webhook, theo đúng giao diện của khung
``ai_service`` cũ.

Tham số nhận diện (ngưỡng, nhịp heartbeat, voting, cooldown) vẫn lấy từ
``config.yaml``. Các biến tương ứng của khung cũ bị bỏ qua có chủ ý và được ghi
log (``BIEN_BO_QUA``), để không đổi điểm vận hành đã kiểm.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

DUONG_RELAY = "/api/v1/edge/ai-events"
"""Cổng chuyển tiếp của edge_backend: đổi ``camera_id`` sang ``cam_id``, gửi tín
hiệu lên cloud, tải ảnh pha 2, xếp hàng offline khi mất mạng."""
DUONG_CLOUD = "/api/v1/internal/ai/fire-events"
DUONG_CAMERA = "/api/v1/edge/cameras"
CONTEXT_HOP_LE = ("HAM", "TRET", "NGOAI")
BIEN_BO_QUA = ("AI_TARGET_FPS", "AI_SAMPLING_FPS", "AI_CONFIDENCE_THRESHOLD",
               "AI_ALERT_COOLDOWN_S", "ALERT_COOLDOWN_SECONDS",
               "AI_MODEL_WEIGHTS_PATH")
"""Biến của khung ``ai_service`` cũ mà FireWatch không dùng: nhịp, ngưỡng và
cooldown nằm trong ``config.yaml``; trọng số kiểm SHA-256 theo
``models/README.md``."""
GHI_DE_MAC_DINH = ("webhook.gui_anh=true", "alerts.webhook_timeout_s=10")
"""Ghi đè config mặc định của chế độ nút biên; ``--set`` của người chạy đứng sau
nên vẫn thắng. Cổng chuyển tiếp chỉ tải ảnh khi payload có ``snapshot_base64``,
và có thể chờ cloud tới 4 s trước khi trả lời."""


@dataclass(frozen=True)
class CameraBien:
    """Một camera của nút biên.

    Attributes
    ----------
    cam_id : str
        Mã camera của backend; dùng làm ``camera.id`` của FireWatch.
    context : str or None
        HAM, TRET hoặc NGOAI nếu khai trong ``AI_CAMERA_STREAMS``; ``None`` thì
        dùng ``camera.context`` của ``config.yaml``.
    """

    cam_id: str
    context: str | None = None


@dataclass(frozen=True)
class CauHinhBien:
    """Cấu hình nút biên đã dịch từ biến môi trường."""

    rtsp_goc: str
    mau_duong: str
    cameras: tuple[CameraBien, ...]
    edge_url: str | None
    cloud_url: str | None
    bi_mat: str | None
    nhip_dong_bo_s: float = 2.0

    def nguon(self, cam_id: str) -> str:
        """URL RTSP của camera, ví dụ ``rtsp://mediamtx:8554/live/cam_01``."""
        return f"{self.rtsp_goc}/{self.mau_duong.format(cam_id=cam_id)}"

    @property
    def webhook_url(self) -> str | None:
        """Cổng chuyển tiếp của edge_backend nếu có, ngược lại cloud backend."""
        if self.edge_url:
            return self.edge_url + DUONG_RELAY
        if self.cloud_url:
            return self.cloud_url + DUONG_CLOUD
        return None

    @property
    def camera_url(self) -> str | None:
        """Danh sách camera kèm cờ quét của edge_backend."""
        return self.edge_url + DUONG_CAMERA if self.edge_url else None


def _gia_tri(env: Mapping[str, str], *ten: str) -> str | None:
    for t in ten:
        v = (env.get(t) or "").strip()
        if v:
            return v
    return None


def _camera_tu_env(env: Mapping[str, str]) -> tuple[CameraBien, ...]:
    """``AI_CAMERA_STREAMS`` (JSON) trước, rồi ``AI_CAMERA_IDS`` (phân cách phẩy)."""
    tho = _gia_tri(env, "AI_CAMERA_STREAMS")
    if tho:
        try:
            muc = json.loads(tho)
        except json.JSONDecodeError as exc:
            log.warning("AI_CAMERA_STREAMS không phải JSON (%s), dùng AI_CAMERA_IDS",
                        exc)
            muc = None
        if isinstance(muc, list):
            cams: list[CameraBien] = []
            for m in muc:
                if not isinstance(m, dict) or not str(m.get("cam_id", "")).strip():
                    continue
                ctx = m.get("context")
                if ctx is not None and str(ctx).upper() not in CONTEXT_HOP_LE:
                    log.warning("camera %s: context %r không hợp lệ, dùng config.yaml",
                                m["cam_id"], ctx)
                    ctx = None
                cams.append(CameraBien(str(m["cam_id"]).strip(),
                                       str(ctx).upper() if ctx else None))
            return tuple(_bo_trung(cams))
    ids = _gia_tri(env, "AI_CAMERA_IDS")
    if ids:
        return tuple(_bo_trung(CameraBien(c.strip()) for c in ids.split(",")
                               if c.strip()))
    return ()


def _bo_trung(cams: Any) -> list[CameraBien]:
    gap: set[str] = set()
    ra: list[CameraBien] = []
    for c in cams:
        if c.cam_id not in gap:
            gap.add(c.cam_id)
            ra.append(c)
    return ra


def doc_moi_truong(env: Mapping[str, str]) -> CauHinhBien | None:
    """Dịch biến môi trường của nút biên.

    Parameters
    ----------
    env : Mapping[str, str]
        Thường là ``os.environ``.

    Returns
    -------
    CauHinhBien or None
        ``None`` khi môi trường không có dấu hiệu nút biên: không có camera
        (``AI_CAMERA_STREAMS``, ``AI_CAMERA_IDS``) và không có
        ``EDGE_BACKEND_URL`` / ``EDGE_BACKEND_API_URL``.
    """
    cameras = _camera_tu_env(env)
    edge = _gia_tri(env, "EDGE_BACKEND_URL", "EDGE_BACKEND_API_URL")
    if not cameras and not edge:
        return None
    cloud = _gia_tri(env, "CLOUD_BACKEND_URL", "CLOUD_BACKEND_API_URL")
    nhip = _gia_tri(env, "FIREWATCH_EDGE_SYNC_S")
    return CauHinhBien(
        rtsp_goc=(_gia_tri(env, "MEDIAMTX_RTSP_URL")
                  or "rtsp://mediamtx:8554").rstrip("/"),
        mau_duong=_gia_tri(env, "STREAM_PATH_TEMPLATE") or "live/{cam_id}",
        cameras=cameras,
        edge_url=edge.rstrip("/") if edge else None,
        cloud_url=cloud.rstrip("/") if cloud else None,
        bi_mat=_gia_tri(env, "INTERNAL_API_SECRET_KEY"),
        nhip_dong_bo_s=max(0.5, float(nhip)) if nhip else 2.0,
    )


def camera_tu_edge(body: Any) -> dict[str, bool]:
    """Đọc ``GET /api/v1/edge/cameras`` của edge_backend.

    Parameters
    ----------
    body : Any
        JSON trả về, dạng ``{"cameras": [{"cam_id", "is_active",
        "should_ai_scan_now", ...}]}``.

    Returns
    -------
    dict[str, bool]
        ``cam_id`` -> có quét bây giờ không: ``is_active`` và
        ``should_ai_scan_now`` (thiếu trường thì coi là ``True``, như khung cũ).
    """
    cams = body.get("cameras") if isinstance(body, dict) else None
    if not isinstance(cams, list):
        return {}
    ra: dict[str, bool] = {}
    for c in cams:
        if not isinstance(c, dict) or not c.get("cam_id"):
            continue
        ra[str(c["cam_id"])] = (bool(c.get("is_active", True))
                                and bool(c.get("should_ai_scan_now", True)))
    return ra


def bien_bi_bo_qua(env: Mapping[str, str]) -> list[str]:
    """Các biến của khung cũ đang được đặt mà FireWatch không dùng."""
    return [t for t in BIEN_BO_QUA if _gia_tri(env, t)]


def ap_webhook(cfgb: CauHinhBien, ten_url: str, ten_token: str,
               env: MutableMapping[str, str]) -> tuple[str | None, bool]:
    """Điền đích webhook vào ``env`` nếu người chạy chưa tự đặt.

    Parameters
    ----------
    cfgb : CauHinhBien
        Cấu hình nút biên.
    ten_url, ten_token : str
        ``alerts.webhook_url_env`` và ``alerts.webhook_token_env``.
    env : MutableMapping[str, str]
        Thường là ``os.environ``; được sửa tại chỗ.

    Returns
    -------
    tuple[str or None, bool]
        URL webhook có hiệu lực, và có token hay không.
    """
    if not _gia_tri(env, ten_url) and cfgb.webhook_url:
        env[ten_url] = cfgb.webhook_url
    if not _gia_tri(env, ten_token) and cfgb.bi_mat:
        env[ten_token] = cfgb.bi_mat
    return _gia_tri(env, ten_url), bool(_gia_tri(env, ten_token))
