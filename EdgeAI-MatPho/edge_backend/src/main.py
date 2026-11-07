"""
Autonomous Edge Backend Controller (FastAPI + SQLite WAL + PyAV Stream Worker + Outbound WS)
Runs inside the on-premise LAN to:
1. Probe LAN IP cameras directly (Port 554) and return metadata + JPEG base64 snapshot.
2. Persist camera configurations & offline fire alerts in local SQLite (WAL mode).
3. Manage PyAV stream sessions:
   - Input RTSP -> Normalized H.264 published to MediaMTX `live/{cam_id}`
   - Output 1 (App HLS): `http://<edge>:8888/live/{cam_id}/index.m3u8`
   - Output 2 (AI RTSP Input): `rtsp://mediamtx:8554/live/{cam_id}`
4. Maintain an outbound WebSocket tunnel to Cloud Backend for zero-NAT remote control.
"""

from __future__ import annotations

import os
import json
import time
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List, Union

from fastapi import FastAPI, HTTPException, Header, Depends, status
from pydantic import BaseModel, Field

from .config import ConfigError, DecoderSettings, redact_url
from .db import EdgeDatabase, WatchAreaType
from .gateway_discovery import discover_public_hls_url
from .manager import DecodeManager, StreamAlreadyRunning
from .probe import get_lan_probe_service
from .ws_client import OutboundCloudWSClient

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("edge-backend")

INTERNAL_API_SECRET_KEY = os.getenv(
    "INTERNAL_API_SECRET_KEY", "secure_internal_key_for_ai_and_worker_communication"
)
MEDIAMTX_HLS_URL = os.getenv("MEDIAMTX_HLS_URL", "http://localhost:8888").rstrip("/")


def verify_internal_secret(x_internal_secret: Optional[str] = Header(None)) -> bool:
    if x_internal_secret and x_internal_secret != INTERNAL_API_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal secret key",
        )
    return True


class EdgeControllerState:
    def __init__(self) -> None:
        self.db = EdgeDatabase()
        self.settings = DecoderSettings.from_env()
        self.manager = DecodeManager(self.settings)
        self.ws_client: Optional[OutboundCloudWSClient] = None
        self.ws_task: Optional[asyncio.Task] = None
        self.log_task: Optional[asyncio.Task] = None
        self.idle_task: Optional[asyncio.Task] = None
        self.watchdog_task: Optional[asyncio.Task] = None
        self.stream_last_requested: Dict[str, float] = {}


state = EdgeControllerState()


def get_current_public_hls_url() -> str:
    """Resolve the active Public HLS URL for this Edge Node."""
    return state.settings.edge_public_hls_url or discover_public_hls_url(MEDIAMTX_HLS_URL)


def build_stream_urls(cam_id: str) -> Dict[str, str]:
    """Return the standardized HLS URL (for App), WebRTC URL and RTSP URL (for AI input)."""
    app_rtsp = state.settings.url_for(state.settings.app_path_template, cam_id)
    stream_path = state.settings.app_path_template.format(cam_id=cam_id)
    base_hls = get_current_public_hls_url()
    hls_url = f"{base_hls}/{stream_path}/index.m3u8"
    base_webrtc = state.settings.edge_public_webrtc_url or base_hls.replace(":8888", ":8889")
    webrtc_url = f"{base_webrtc}/{stream_path}/whep"
    return {
        "hls_stream_url": hls_url,
        "rtsp_output_url": app_rtsp,
        "webrtc_stream_url": webrtc_url,
        "public_base_url": base_hls,
    }


async def start_live_stream(cam_id: str) -> Dict[str, Any]:
    """Activate live stream for a camera (on-demand or always-on)."""
    state.stream_last_requested[cam_id] = time.monotonic()
    if not state.manager.is_running(cam_id):
        cam = await state.db.get_camera(cam_id)
        if not cam or not cam.get("is_active", True):
            src = state.settings.url_for(state.settings.source_path_template, cam_id)
        else:
            src = cam["rtsp_url"]
        safe_source = resolve_safe_source_url(cam_id, src)
        try:
            await asyncio.to_thread(state.manager.start, cam_id, safe_source)
            logger.info("[cam_id=%s] Started live stream session", cam_id)
        except Exception as exc:
            logger.warning("[cam_id=%s] Failed to start live stream: %s", cam_id, exc)
    return build_stream_urls(cam_id)


async def stop_live_stream(cam_id: str) -> Dict[str, Any]:
    """Deactivate live stream for a camera if in on_demand mode."""
    state.stream_last_requested.pop(cam_id, None)
    stopped = False
    if state.settings.stream_mode == "on_demand":
        stopped = await asyncio.to_thread(state.manager.stop, cam_id)
        logger.info("[cam_id=%s] Stopped on-demand live stream session", cam_id)
    return {
        "cam_id": cam_id,
        "status": "STOPPED" if stopped else ("ACTIVE" if state.settings.stream_mode == "always_on" else "IDLE"),
        "stream_mode": state.settings.stream_mode,
    }


async def on_demand_idle_sweeper() -> None:
    """Periodically stops live streams that have received no watch requests within live_idle_ttl_s."""
    while True:
        try:
            await asyncio.sleep(5.0)
            if state.settings.stream_mode != "on_demand":
                continue
            now = time.monotonic()
            active_cams = list(state.manager.status().keys())
            for cam_id in active_cams:
                last_req = state.stream_last_requested.get(cam_id)
                if last_req is not None and (now - last_req) > state.settings.live_idle_ttl_s:
                    logger.info(
                        "[cam_id=%s] On-demand stream idle for %.1fs (TTL: %.1fs) -> auto-stopping",
                        cam_id, now - last_req, state.settings.live_idle_ttl_s
                    )
                    await asyncio.to_thread(state.manager.stop, cam_id)
                    state.stream_last_requested.pop(cam_id, None)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.debug("Idle sweeper error: %s", exc)


async def gateway_url_watchdog() -> None:
    """Continuously monitors for newly provisioned Cloudflare tunnel URLs and pushes them to Cloud instantly."""
    last_announced_url: Optional[str] = None
    while True:
        try:
            await asyncio.sleep(2.0)
            current_url = get_current_public_hls_url()
            if (
                current_url
                and current_url != last_announced_url
                and not current_url.startswith("http://localhost")
                and not current_url.startswith("http://127.0.0.1")
            ):
                last_announced_url = current_url
                logger.info("[GATEWAY WATCHDOG] Discovered active public tunnel: %s", current_url)
                if state.ws_client:
                    await state.ws_client.announce_gateway_url(current_url)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.debug("Gateway watchdog error: %s", exc)


def resolve_safe_source_url(cam_id: str, rtsp_url: str) -> str:
    """Prevent self-loopback if a caller passes the MediaMTX output path or a mock alias."""
    app_rtsp = state.settings.url_for(state.settings.app_path_template, cam_id)
    ai_rtsp = state.settings.url_for(state.settings.ai_path_template, cam_id)
    cleaned = rtsp_url.strip()
    if "mock-camera" in cleaned.lower() or "test-valid" in cleaned.lower():
        return f"{state.settings.mediamtx_rtsp_url}/mock/cam_test"
    if cleaned.rstrip("/") in (app_rtsp.rstrip("/"), ai_rtsp.rstrip("/")):
        return f"{state.settings.mediamtx_rtsp_url}/mock/cam_test"
    return cleaned


def _load_initial_cameras_from_env() -> List[Dict[str, Any]]:
    raw = os.environ.get("DECODER_STREAMS", "").strip()
    if not raw:
        return []
    try:
        items = json.loads(raw)
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict) and "cam_id" in x]
    except Exception as exc:
        logger.warning("Could not parse DECODER_STREAMS: %s", exc)
    return []


async def handle_cloud_command(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle remote commands pushed down from Cloud Backend via WebSocket."""
    action = payload.get("action") or payload.get("type")

    if action == "PROBE_CAMERA":
        rtsp_url = payload.get("rtsp_url", "")
        res = get_lan_probe_service().probe_rtsp(rtsp_url)
        return {"type": "PROBE_RESULT", "request_id": payload.get("request_id"), "data": res}

    if action in ("SYNC_CAMERA", "ADD_CAMERA", "UPDATE_CAMERA"):
        cam_id = payload.get("cam_id")
        rtsp_url = payload.get("rtsp_url")
        if not cam_id or not rtsp_url:
            return {"type": "COMMAND_ERROR", "message": "Missing cam_id or rtsp_url"}

        is_active = bool(payload.get("is_active", True))
        safe_source = resolve_safe_source_url(cam_id, rtsp_url)
        await state.db.upsert_camera(
            cam_id=cam_id,
            rtsp_url=safe_source,
            cam_name=payload.get("cam_name", cam_id),
            watch_area=payload.get("watch_area"),
            is_active=is_active,
        )
        state.manager.stop(cam_id)
        if is_active:
            try:
                state.manager.start(cam_id, source_url=safe_source)
            except Exception as exc:
                logger.warning("Could not start stream for %s: %s", cam_id, exc)
        urls = build_stream_urls(cam_id)
        return {
            "type": "CAMERA_STATUS",
            "cam_id": cam_id,
            "status": "ONLINE" if is_active else "DISABLED",
            **urls,
        }

    if action == "REMOVE_CAMERA":
        cam_id = payload.get("cam_id")
        if cam_id:
            state.manager.stop(cam_id)
            await state.db.remove_camera(cam_id)
        return {"type": "CAMERA_REMOVED", "cam_id": cam_id}

    if action in ("START_LIVE", "WATCH_CAMERA"):
        cam_id = payload.get("cam_id")
        if not cam_id:
            return {"type": "COMMAND_ERROR", "message": "Missing cam_id"}
        try:
            urls = await start_live_stream(cam_id)
            return {
                "type": "LIVE_STARTED",
                "cam_id": cam_id,
                "ttl_s": state.settings.live_idle_ttl_s,
                "stream_mode": state.settings.stream_mode,
                **urls,
            }
        except Exception as exc:
            return {"type": "COMMAND_ERROR", "cam_id": cam_id, "message": str(exc)}

    if action in ("KEEPALIVE_LIVE", "PING_LIVE"):
        cam_id = payload.get("cam_id")
        if cam_id:
            state.stream_last_requested[cam_id] = time.monotonic()
        return {"type": "LIVE_KEEPALIVE_ACK", "cam_id": cam_id}

    if action in ("STOP_LIVE", "UNWATCH_CAMERA"):
        cam_id = payload.get("cam_id")
        if cam_id:
            res = await stop_live_stream(cam_id)
            return {"type": "LIVE_STOPPED", **res}
        return {"type": "COMMAND_ERROR", "message": "Missing cam_id"}

    if action in ("GET_GATEWAY", "GATEWAY_INFO"):
        base_hls = get_current_public_hls_url()
        return {
            "type": "GATEWAY_INFO",
            "edge_device_id": os.getenv("EDGE_DEVICE_ID", "edg_local_01"),
            "public_hls_base_url": base_hls,
            "stream_mode": state.settings.stream_mode,
        }

    return {"type": "ACK", "received_action": action}


async def periodic_status_logger() -> None:
    while True:
        try:
            await asyncio.sleep(state.settings.stats_interval_s)
            for cam_id, snap in state.manager.status().items():
                logger.info(
                    "[cam_id=%s] state=%s mode=%s in=%dpkt decoded=%df live_out=%dpkt restarts=%d",
                    cam_id,
                    snap["state"],
                    snap["live_mode"],
                    snap["packets_in"],
                    snap["frames_decoded"],
                    snap["live_packets_out"],
                    snap["restarts"],
                )
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.debug("Status logger error: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await state.db.init_db()

    # Seed from DECODER_STREAMS env if SQLite is empty
    existing = await state.db.list_cameras()
    if not existing:
        for item in _load_initial_cameras_from_env():
            cid = item["cam_id"]
            src = item.get("source_url") or state.settings.url_for(
                state.settings.source_path_template, cid
            )
            await state.db.upsert_camera(
                cam_id=cid,
                rtsp_url=resolve_safe_source_url(cid, src),
                cam_name=item.get("cam_name", cid),
                watch_area=item.get("watch_area"),
                is_active=True,
            )

    # Start cameras according to stream_mode
    if state.settings.stream_mode == "always_on":
        active_cams = await state.db.list_cameras(only_active=True)
        for cam in active_cams:
            try:
                safe_src = resolve_safe_source_url(cam["cam_id"], cam["rtsp_url"])
                spec = state.manager.start(cam["cam_id"], source_url=safe_src)
                logger.info(
                    "Started Edge camera %s: %s -> %s (HLS: %s)",
                    spec.cam_id,
                    redact_url(spec.source_url),
                    spec.app_url,
                    build_stream_urls(spec.cam_id)["hls_stream_url"],
                )
            except Exception as exc:
                logger.warning("Failed to start camera %s on boot: %s", cam["cam_id"], exc)
    else:
        logger.info("Stream mode is ON_DEMAND: cameras will activate on viewer request.")

    # Start Outbound WS Client to Cloud Backend
    state.ws_client = OutboundCloudWSClient(
        db=state.db,
        on_command=handle_cloud_command,
        get_status_snapshot=state.manager.status,
        get_public_hls_url=get_current_public_hls_url,
    )
    state.ws_task = asyncio.create_task(state.ws_client.run_forever())
    state.log_task = asyncio.create_task(periodic_status_logger())
    state.idle_task = asyncio.create_task(on_demand_idle_sweeper())
    state.watchdog_task = asyncio.create_task(gateway_url_watchdog())

    yield

    # Graceful shutdown
    if state.ws_client:
        state.ws_client.stop()
    for t in (state.ws_task, state.log_task, state.idle_task, state.watchdog_task):
        if t:
            t.cancel()
    await asyncio.to_thread(state.manager.stop_all)


app = FastAPI(
    title="Mắt Phố - Autonomous Edge Backend Controller",
    version="1.1.0",
    lifespan=lifespan,
)


class ProbeRequest(BaseModel):
    rtsp_url: str = Field(..., description="RTSP URL of the camera inside LAN")


class CameraSyncRequest(BaseModel):
    cam_id: str
    cam_name: str = ""
    rtsp_url: str
    watch_area: Optional[WatchAreaType] = Field(
        None,
        description="Supports Rectangle dict {'left', 'top', 'width', 'height'} or Polygon [[x, y], ...]",
    )
    is_active: bool = True


class OfflineEventRequest(BaseModel):
    cam_id: str
    event_type: str = "FIRE_DETECTED"
    payload: Dict[str, Any]


@app.get("/health")
@app.get("/api/v1/edge/health")
async def health_check():
    return {
        "status": "ok",
        "service": "edge-backend",
        "edge_device_id": os.getenv("EDGE_DEVICE_ID", "edg_local_01"),
        "active_streams": len(state.manager.status()),
    }


@app.get("/api/v1/status")
async def status_endpoint():
    return {
        "edge_device_id": os.getenv("EDGE_DEVICE_ID", "edg_local_01"),
        "sessions": state.manager.status(),
    }


@app.post("/api/v1/auth/stream-ticket")
async def stream_ticket_auth_hook(payload: Dict[str, Any]):
    """MediaMTX external authentication hook for stream tickets."""
    return {"status": "authorized", "path": payload.get("path")}


@app.post("/api/v1/edge/probe")
async def probe_lan_camera(
    req: ProbeRequest,
    _auth: bool = Depends(verify_internal_secret),
):
    """Probe a camera directly over LAN RTSP and return resolution, FPS, codec & snapshot."""
    return await asyncio.to_thread(get_lan_probe_service().probe_rtsp, req.rtsp_url)


@app.get("/api/v1/edge/cameras")
async def list_edge_cameras():
    """Return local cameras persisted in SQLite along with live stream status & HLS/RTSP URLs."""
    cams = await state.db.list_cameras()
    live_status = state.manager.status()
    for c in cams:
        c["rtsp_url"] = redact_url(c["rtsp_url"])
        c["stream_stats"] = live_status.get(c["cam_id"])
        c.update(build_stream_urls(c["cam_id"]))
    return {"cameras": cams}


@app.post("/api/v1/edge/cameras", status_code=status.HTTP_201_CREATED)
async def sync_camera_http(
    req: CameraSyncRequest,
    _auth: bool = Depends(verify_internal_secret),
):
    """Add or update a camera in Edge SQLite and start its RTSP -> HLS stream worker."""
    safe_source = resolve_safe_source_url(req.cam_id, req.rtsp_url)
    await state.db.upsert_camera(
        cam_id=req.cam_id,
        rtsp_url=safe_source,
        cam_name=req.cam_name or req.cam_id,
        watch_area=req.watch_area,
        is_active=req.is_active,
    )
    state.manager.stop(req.cam_id)
    if req.is_active:
        try:
            await asyncio.to_thread(state.manager.start, req.cam_id, safe_source)
        except (ConfigError, StreamAlreadyRunning) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "synced",
        "cam_id": req.cam_id,
        "is_active": req.is_active,
        **build_stream_urls(req.cam_id),
    }


@app.delete("/api/v1/edge/cameras/{cam_id}")
async def delete_camera_http(
    cam_id: str,
    _auth: bool = Depends(verify_internal_secret),
):
    await asyncio.to_thread(state.manager.stop, cam_id)
    removed = await state.db.remove_camera(cam_id)
    return {"status": "deleted" if removed else "not_found", "cam_id": cam_id}


@app.post("/api/v1/edge/offline-events", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_offline_fire_event(
    req: OfflineEventRequest,
    _auth: bool = Depends(verify_internal_secret),
):
    """Fallback endpoint for FireWatch AI to store alerts in SQLite when Cloud WAN is down."""
    row_id = await state.db.enqueue_offline_event(req.cam_id, req.event_type, req.payload)
    return {"status": "queued", "queue_id": row_id}


@app.post("/api/v1/edge/cameras/{cam_id}/live/start")
async def start_camera_live(
    cam_id: str,
    _auth: bool = Depends(verify_internal_secret),
):
    """Start live stream for a camera on demand."""
    urls = await start_live_stream(cam_id)
    return {
        "status": "started",
        "cam_id": cam_id,
        "ttl_s": state.settings.live_idle_ttl_s,
        "stream_mode": state.settings.stream_mode,
        **urls,
    }


@app.post("/api/v1/edge/cameras/{cam_id}/live/keepalive")
async def keepalive_camera_live(
    cam_id: str,
    _auth: bool = Depends(verify_internal_secret),
):
    """Keep active stream alive, extending its idle TTL."""
    state.stream_last_requested[cam_id] = time.monotonic()
    return {"status": "alive", "cam_id": cam_id}


@app.post("/api/v1/edge/cameras/{cam_id}/live/stop")
async def stop_camera_live(
    cam_id: str,
    _auth: bool = Depends(verify_internal_secret),
):
    """Stop live stream for a camera."""
    res = await stop_live_stream(cam_id)
    return {"status": "stopped", **res}


@app.get("/api/v1/edge/gateway")
async def get_gateway_info():
    """Return the active Public HLS & WebRTC Gateway configuration."""
    base_hls = get_current_public_hls_url()
    base_webrtc = state.settings.edge_public_webrtc_url or base_hls.replace(":8888", ":8889")
    return {
        "edge_device_id": os.getenv("EDGE_DEVICE_ID", "edg_local_01"),
        "public_hls_base_url": base_hls,
        "public_webrtc_base_url": base_webrtc,
        "stream_mode": state.settings.stream_mode,
        "live_idle_ttl_s": state.settings.live_idle_ttl_s,
    }
