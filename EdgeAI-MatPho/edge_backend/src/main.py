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
import uuid
import base64
import asyncio
import logging
import httpx
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List, Union

from fastapi import FastAPI, HTTPException, Header, Depends, status
from pydantic import BaseModel, Field

from .config import ConfigError, DecoderSettings, redact_url
from .db import EdgeDatabase, WatchAreaType
from .gateway_discovery import discover_public_hls_url
from .relay_rules import la_dia_chi_noi_bo, match_cam_id
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
CLOUD_BACKEND_API_URL = os.getenv(
    "CLOUD_BACKEND_API_URL", "http://localhost:8000"
).rstrip("/")


def verify_internal_secret(
    x_internal_secret: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
) -> bool:
    token = None
    if x_internal_secret:
        token = x_internal_secret
    elif authorization:
        parts = authorization.split(" ", 1)
        token = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else parts[0]

    if token is not None and token != INTERNAL_API_SECRET_KEY:
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
        self.uploaded_snapshot_events: set[str] = set()
        self.ws_task: Optional[asyncio.Task] = None
        self.log_task: Optional[asyncio.Task] = None
        self.idle_task: Optional[asyncio.Task] = None
        self.watchdog_task: Optional[asyncio.Task] = None
        self.stream_last_requested: Dict[str, float] = {}


state = EdgeControllerState()

VN_TZ = timezone(timedelta(hours=7))
WEEKDAY_TO_VN: Dict[int, str] = {
    0: "T2",
    1: "T3",
    2: "T4",
    3: "T5",
    4: "T6",
    5: "T7",
    6: "CN",
}


def compute_should_ai_scan_now(
    ai_mode: Any,
    schedules: Optional[List[Dict[str, Any]]] = None,
    now_vn: Optional[datetime] = None,
) -> bool:
    """
    Evaluate whether FireWatch AI should currently connect and scan the camera's RTSP stream.
      - ALWAYS / True -> True (connect RTSP)
      - OFF / False   -> False (disconnect RTSP from AI immediately to save CPU/GPU)
      - SCHEDULE      -> False if current Asia/Ho_Chi_Minh time falls in any rest slot, else True
    Supports both legacy {start_time, end_time, days: ["T2".."CN"]} and frontend {from, to, days: [1..7]}.
    """
    if isinstance(ai_mode, bool):
        if not ai_mode:
            return False
        mode = "SCHEDULE" if schedules else "ALWAYS"
    else:
        mode = str(ai_mode or "ALWAYS").upper()

    if mode in ("OFF", "FALSE", "DISABLED"):
        return False
    if mode == "SCHEDULE" and schedules:
        now = now_vn or datetime.now(VN_TZ)
        if now.tzinfo is None:
            now = now.replace(tzinfo=VN_TZ)
        else:
            now = now.astimezone(VN_TZ)

        curr_iso_day = now.isoweekday()  # 1 = Monday ... 7 = Sunday
        prev_iso_day = 7 if curr_iso_day == 1 else curr_iso_day - 1
        curr_vn_day = WEEKDAY_TO_VN[now.weekday()]
        prev_vn_day = WEEKDAY_TO_VN[(now.weekday() - 1) % 7]
        curr_hm = now.strftime("%H:%M")

        for slot in schedules:
            if not isinstance(slot, dict):
                continue
            start = slot.get("from") or slot.get("start_time") or ""
            end = slot.get("to") or slot.get("end_time") or ""
            days = slot.get("days") or []
            if not start or not end or not days:
                continue

            # Check matching days for current and previous day (for overnight slots)
            match_curr = (
                curr_iso_day in days
                or str(curr_iso_day) in days
                or curr_vn_day in days
            )
            match_prev = (
                prev_iso_day in days
                or str(prev_iso_day) in days
                or prev_vn_day in days
            )

            if start <= end:
                if match_curr and start <= curr_hm < end:
                    return False
            else:
                # Overnight slot: e.g. 22:00 -> 06:00
                if (match_curr and curr_hm >= start) or (match_prev and curr_hm < end):
                    return False
    return True


def get_current_public_hls_url() -> str:
    """
    Resolve the HLS base URL the phone can reach, announced to the Cloud Backend:
    EDGE_PUBLIC_HLS_URL -> Cloudflare tunnel URL from tunnel.log -> http://<EDGE_LAN_IP>:8888
    (LAN demo without tunnel; the launchers fill EDGE_LAN_IP) -> MEDIAMTX_HLS_URL.
    A localhost address is still returned last so local tools keep working; the cloud
    ignores it and reports "no reachable stream" to the app instead of a broken URL.
    """
    url = state.settings.edge_public_hls_url or discover_public_hls_url(MEDIAMTX_HLS_URL)
    if la_dia_chi_noi_bo(url):
        lan_ip = os.getenv("EDGE_LAN_IP", "").strip()
        if lan_ip:
            port = os.getenv("MEDIAMTX_HLS_PORT", "8888").strip() or "8888"
            return f"http://{lan_ip}:{port}"
    return url


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
    sess = state.manager.get_session(cam_id)
    if sess is None or not sess.alive:
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
    else:
        from .stats import SessionState
        if sess.stats.state == SessionState.BACKOFF:
            sess.wake_up()
            logger.info("[cam_id=%s] Woke up session from BACKOFF for live view", cam_id)
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
    """Prevent self-loopback if a caller passes the MediaMTX output path or a mock alias, and normalize localhost:8554."""
    app_rtsp = state.settings.url_for(state.settings.app_path_template, cam_id)
    ai_rtsp = state.settings.url_for(state.settings.ai_path_template, cam_id)
    cleaned = rtsp_url.strip()
    if ":8554/" in cleaned:
        for local_alias in ("rtsp://127.0.0.1:8554/", "rtsp://localhost:8554/", "rtsp://0.0.0.0:8554/", "rtsp://10.0.2.2:8554/"):
            if cleaned.lower().startswith(local_alias):
                cleaned = f"{state.settings.mediamtx_rtsp_url}/" + cleaned[len(local_alias):]
                break
    if "mock-camera" in cleaned.lower() or "test-valid" in cleaned.lower() or "mock-cam" in cleaned.lower():
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
        is_ai_enabled = payload.get("is_ai_enabled")
        ai_schedule = payload.get("ai_schedule") or payload.get("schedules") or payload.get("ai_schedules") or []
        ai_mode = payload.get("ai_mode")
        if ai_mode is None:
            if is_ai_enabled is False:
                ai_mode = "OFF"
            elif len(ai_schedule) > 0:
                ai_mode = "SCHEDULE"
            else:
                ai_mode = "ALWAYS"

        safe_source = resolve_safe_source_url(cam_id, rtsp_url)
        await state.db.upsert_camera(
            cam_id=cam_id,
            rtsp_url=safe_source,
            cam_name=payload.get("cam_name", cam_id),
            watch_area=payload.get("watch_area"),
            is_active=is_active,
            ai_mode=ai_mode,
            ai_schedules=ai_schedule,
        )
        if is_active:
            try:
                await asyncio.to_thread(state.manager.restart, cam_id, safe_source)
                logger.info("[cam_id=%s] Restarted stream session with source: %s", cam_id, safe_source)
            except Exception as exc:
                logger.warning("Could not start stream for %s: %s", cam_id, exc)
        else:
            await asyncio.to_thread(state.manager.stop, cam_id)

        if state.ws_client:
            asyncio.create_task(state.ws_client.announce_camera_sync())
        urls = build_stream_urls(cam_id)
        return {
            "type": "CAMERA_STATUS",
            "cam_id": cam_id,
            "status": "ONLINE" if is_active else "DISABLED",
            **urls,
        }

    if action == "SET_CAMERA_AI_CONFIG":
        cam_id = payload.get("cam_id")
        if not cam_id:
            return {"type": "COMMAND_ERROR", "message": "Missing cam_id"}
        ai_mode = (payload.get("ai_mode") or "ALWAYS").upper()
        schedules = payload.get("schedules") or []
        updated = await state.db.update_camera_ai_config(
            cam_id=cam_id,
            ai_mode=ai_mode,
            ai_schedules=schedules,
        )
        if not updated:
            # If camera wasn't in local SQLite yet, create a placeholder entry so AI config is persisted
            fallback_src = state.settings.url_for(state.settings.source_path_template, cam_id)
            await state.db.upsert_camera(
                cam_id=cam_id,
                rtsp_url=resolve_safe_source_url(cam_id, fallback_src),
                cam_name=payload.get("cam_name", cam_id),
                is_active=True,
                ai_mode=ai_mode,
                ai_schedules=schedules,
            )
        should_scan = compute_should_ai_scan_now(ai_mode, schedules)
        stream_action = "CONNECT_AI_RTSP" if should_scan else "DISCONNECT_AI_RTSP"
        logger.info(
            "[cam_id=%s] Applied SET_CAMERA_AI_CONFIG: ai_mode=%s should_ai_scan_now=%s (%s)",
            cam_id,
            ai_mode,
            should_scan,
            stream_action,
        )
        return {
            "type": "CAMERA_AI_CONFIG_ACK",
            "cam_id": cam_id,
            "ai_mode": ai_mode,
            "should_ai_scan_now": should_scan,
            "stream_action": stream_action,
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


async def sync_cameras_from_cloud() -> int:
    """Fetch registered cameras from Cloud Backend and synchronize them into local SQLite."""
    url = f"{CLOUD_BACKEND_API_URL}/api/v1/internal/edge/cameras?edge_device_id={os.getenv('EDGE_DEVICE_ID', 'edg_local_01')}"
    headers = {
        "x-internal-secret": INTERNAL_API_SECRET_KEY,
        "Authorization": f"Bearer {INTERNAL_API_SECRET_KEY}",
    }
    synced = 0
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                cameras = data.get("cameras", [])
                for c in cameras:
                    cid = c.get("cam_id")
                    raw_rtsp = c.get("rtsp_url")
                    if not cid or not raw_rtsp:
                        continue
                    safe_src = resolve_safe_source_url(cid, raw_rtsp)
                    is_active = bool(c.get("is_active", True))
                    await state.db.upsert_camera(
                        cam_id=cid,
                        rtsp_url=safe_src,
                        cam_name=c.get("cam_name", cid),
                        watch_area=c.get("watch_area"),
                        is_active=is_active,
                        ai_mode=c.get("ai_mode", "ALWAYS"),
                        ai_schedules=c.get("ai_schedules", []),
                    )
                    synced += 1
                logger.info("Auto-synced %d cameras from Cloud Backend into Edge DB", synced)
    except Exception as exc:
        logger.debug("Cloud Backend cameras sync unavailable: %s", exc)
    return synced


@asynccontextmanager
async def lifespan(app: FastAPI):
    await state.db.init_db()

    # 1. Pull latest cameras from Cloud Backend
    await sync_cameras_from_cloud()

    # 2. Seed from DECODER_STREAMS env if SQLite is still empty
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


class EdgeAIConfigRequest(BaseModel):
    ai_mode: str = Field(..., description="ALWAYS | SCHEDULE | OFF")
    schedules: Optional[List[Dict[str, Any]]] = Field(default_factory=list)


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
    """Return local cameras persisted in SQLite along with live stream status, AI scan flag & HLS/RTSP URLs."""
    cams = await state.db.list_cameras()
    live_status = state.manager.status()
    for c in cams:
        c["rtsp_url"] = redact_url(c["rtsp_url"])
        c["stream_stats"] = live_status.get(c["cam_id"])
        ai_mode = c.get("ai_mode", "ALWAYS")
        ai_schedules = c.get("ai_schedules", [])
        c["should_ai_scan_now"] = bool(c.get("is_active", True)) and compute_should_ai_scan_now(
            ai_mode, ai_schedules
        )
        c.update(build_stream_urls(c["cam_id"]))
    return {"cameras": cams}


@app.put("/api/v1/edge/cameras/{cam_id}/ai-config")
async def update_edge_camera_ai_config_http(
    cam_id: str,
    req: EdgeAIConfigRequest,
    _auth: bool = Depends(verify_internal_secret),
):
    """Directly update AI mode & rest schedule for a camera on the Edge Node."""
    ai_mode = (req.ai_mode or "ALWAYS").upper()
    schedules = req.schedules or []
    updated = await state.db.update_camera_ai_config(cam_id, ai_mode, schedules)
    if not updated:
        fallback_src = state.settings.url_for(state.settings.source_path_template, cam_id)
        await state.db.upsert_camera(
            cam_id=cam_id,
            rtsp_url=resolve_safe_source_url(cam_id, fallback_src),
            cam_name=cam_id,
            is_active=True,
            ai_mode=ai_mode,
            ai_schedules=schedules,
        )
    should_scan = compute_should_ai_scan_now(ai_mode, schedules)
    return {
        "status": "updated",
        "cam_id": cam_id,
        "ai_mode": ai_mode,
        "schedules": schedules,
        "should_ai_scan_now": should_scan,
        "stream_action": "CONNECT_AI_RTSP" if should_scan else "DISCONNECT_AI_RTSP",
    }


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


async def resolve_edge_cam_id(raw_camera_id: Optional[str]) -> str:
    """Map the FireWatch camera identifier to a registered cam_id (see match_cam_id)."""
    cams = await state.db.list_cameras()
    resolved = match_cam_id(raw_camera_id, cams)
    if raw_camera_id and resolved == raw_camera_id and not any(c.get("cam_id") == resolved for c in cams):
        logger.warning("Fire event for unregistered camera id %r: forwarded unchanged", raw_camera_id)
    return resolved


@app.post("/api/v1/edge/ai-events", status_code=status.HTTP_202_ACCEPTED)
@app.post("/api/v1/internal/ai/fire-events", status_code=status.HTTP_202_ACCEPTED)
async def relay_ai_fire_event(
    payload: Dict[str, Any],
    _auth: bool = Depends(verify_internal_secret),
):
    """
    Two-Phase EAG Fire Event Relay:
    1. Maps AI raw camera_id -> registered cam_id and injects 'cam_id' to payload.
    2. Phase 1 (Fast Signal < 30ms): Strips snapshot_base64, forwards lightweight JSON (~0.6KB)
       immediately to Cloud Backend to trigger sirens & Redis escalation timer without waiting for image upload.
       If Cloud WAN is unreachable, enqueues to SQLite offline_events_queue.
    3. Phase 2 (Single Snapshot History): Launches background task to upload the single clean JPEG
       snapshot to Cloud Storage endpoint '/api/v1/internal/ai/fire-events/{event_id}/snapshot'.
       Once uploaded, marks event_id in uploaded_snapshot_events so subsequent updates do not duplicate upload.
    """
    raw_cam_id = payload.get("camera_id") or payload.get("cam_id") or "cam_unknown"
    resolved_cam_id = await resolve_edge_cam_id(raw_cam_id)
    payload["cam_id"] = resolved_cam_id
    if not payload.get("camera_id"):
        payload["camera_id"] = raw_cam_id

    event_id = payload.get("event_id") or f"evt_{uuid.uuid4().hex[:12]}"
    payload["event_id"] = event_id

    # Extract snapshot
    snapshot_b64 = payload.pop("snapshot_base64", None) or payload.pop("image_base64", None)
    if not snapshot_b64 and payload.get("snapshot_path"):
        snap_path = payload.get("snapshot_path")
        if os.path.exists(snap_path):
            try:
                with open(snap_path, "rb") as f:
                    snapshot_b64 = base64.b64encode(f.read()).decode("utf-8")
            except Exception as exc:
                logger.warning("Failed to read snapshot file %s: %s", snap_path, exc)

    # 1. Phase 1: Fast Signal Forwarding
    cloud_url = f"{CLOUD_BACKEND_API_URL}/api/v1/internal/ai/fire-events"
    headers = {
        "Authorization": f"Bearer {INTERNAL_API_SECRET_KEY}",
        "X-Internal-Secret": INTERNAL_API_SECRET_KEY,
    }

    forward_success = False
    cloud_response_data = {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(cloud_url, json=payload, headers=headers)
            if resp.status_code in (200, 201, 202):
                forward_success = True
                try:
                    val = resp.json()
                    cloud_response_data = await val if asyncio.iscoroutine(val) else val
                except Exception:
                    cloud_response_data = {}
            else:
                logger.warning("Cloud backend returned %d on fast signal forward", resp.status_code)
    except Exception as exc:
        logger.warning("Cloud backend unreachable for fast signal (%s). Storing to local SQLite queue...", exc)

    if not forward_success:
        queue_id = await state.db.enqueue_offline_event(resolved_cam_id, "FIRE_SIGNAL", payload)
        logger.info("Enqueued fire signal offline: queue_id=%d, event_id=%s", queue_id, event_id)

    # 2. Phase 2: Background Snapshot Upload (Single Image per incident)
    if snapshot_b64 and event_id not in state.uploaded_snapshot_events:
        boxes_data = payload.get("boxes", [])
        fw = payload.get("frame_w", 1920)
        fh = payload.get("frame_h", 1080)
        f_ts = payload.get("frame_ts") or payload.get("last_seen_ts")

        async def _upload_snapshot_task():
            try:
                snap_upload_url = f"{CLOUD_BACKEND_API_URL}/api/v1/internal/ai/fire-events/{event_id}/snapshot"
                snap_body = {
                    "event_id": event_id,
                    "cam_id": resolved_cam_id,
                    "camera_id": raw_cam_id,
                    "frame_ts": f_ts,
                    "frame_w": fw,
                    "frame_h": fh,
                    "boxes": boxes_data,
                    "snapshot_base64": snapshot_b64,
                }
                async with httpx.AsyncClient(timeout=15.0) as cl:
                    res = await cl.post(snap_upload_url, json=snap_body, headers=headers)
                    if res.status_code in (200, 201, 202):
                        state.uploaded_snapshot_events.add(event_id)
                        logger.info("Phase 2 snapshot uploaded successfully for %s", event_id)
                    else:
                        logger.warning("Phase 2 snapshot upload returned %d for %s", res.status_code, event_id)
            except Exception as e:
                logger.warning("Phase 2 snapshot upload failed for %s: %s", event_id, e)

        asyncio.create_task(_upload_snapshot_task())

    return {
        "status": "accepted",
        "cam_id": resolved_cam_id,
        "event_id": event_id,
        "relay_signal": "forwarded" if forward_success else "queued_offline",
        "cloud_response": cloud_response_data,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("EDGE_BACKEND_PORT", "8090"))
    logger.info("Starting Edge Backend on 0.0.0.0:%d...", port)
    uvicorn.run("src.main:app", host="0.0.0.0", port=port, log_level="info")
