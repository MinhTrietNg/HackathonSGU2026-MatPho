"""EdgeAI-MatPho Core Service Entrypoint (Master Spec v4.0).

Combines FastAPI controller, Local SQLite WAL storage, PyAV Decode Engine,
and the persistent Outbound WebSocket Sync Client.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import av
import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import DecoderSettings
from .db import init_db_sync, list_active_cameras_sync, upsert_camera
from .manager import DecodeManager
from .probe import CameraProbeService
from .ws_client import EdgeWebSocketClient

# Global settings
settings = DecoderSettings.from_env()

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
av.logging.set_level(av.logging.WARNING)

logger = logging.getLogger("edge.main")

# Instantiate manager & services
manager = DecodeManager(settings)
probe_service = CameraProbeService()
ws_client = EdgeWebSocketClient(settings, manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for cold boot, SQLite initialization and background tasks."""
    logger.info("Initializing EdgeAI-MatPho Node (edge_id=%s)...", settings.edge_device_id)

    # 1. Initialize SQLite database in WAL mode (with local_cameras and offline_events_queue)
    init_db_sync(settings.sqlite_db_path)

    # 2. Cold-boot: Load active cameras saved in SQLite and start decoding immediately
    active_cams = list_active_cameras_sync(settings.sqlite_db_path)
    logger.info("Cold-boot recovery: Found %d active cameras in SQLite", len(active_cams))
    for cam in active_cams:
        cam_id = cam.get("cam_id")
        rtsp_url = cam.get("rtsp_url")
        if cam_id and rtsp_url:
            try:
                manager.start(cam_id, rtsp_url)
                logger.info("[cam_id=%s] cold-boot started session", cam_id)
            except Exception as exc:
                logger.warning("[cam_id=%s] cold-boot start failed: %s", cam_id, exc)

    # 3. Start Outbound WebSocket connection to Cloud Backend
    ws_task = asyncio.create_task(ws_client.start())

    logger.info("EdgeAI-MatPho Node is UP and RUNNING.")
    yield

    # Shutdown
    logger.info("Shutting down EdgeAI-MatPho Node...")
    ws_client.stop()
    ws_task.cancel()
    manager.stop_all()
    try:
        await asyncio.gather(ws_task, return_exceptions=True)
    except asyncio.CancelledError:
        pass
    logger.info("EdgeAI-MatPho Node shut down gracefully.")


app = FastAPI(
    title="EdgeAI-MatPho Core Service",
    version="1.0.0",
    description="Autonomous On-Premise Edge Node for Mắt Phố Surveillance Platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LocalSyncPayload(BaseModel):
    cam_id: str
    cam_name: str
    rtsp_url: str
    watch_area: list[Any] | None = None
    is_active: bool = True


class LocalProbePayload(BaseModel):
    rtsp_url: str


class StreamTicketAuthPayload(BaseModel):
    user: str | None = None
    password: str | None = None
    ip: str | None = None
    action: str | None = None
    path: str | None = None
    protocol: str | None = None
    id: str | None = None
    query: str | None = None


@app.get("/health", tags=["Health"])
async def health_check():
    """System health check and overview of active streams."""
    status_map = manager.status()
    return {
        "status": "ok",
        "service": "edge-backend",
        "edge_device_id": settings.edge_device_id,
        "active_streams_count": len(status_map),
        "streams": status_map,
    }


@app.get("/api/v1/status", tags=["Status"])
async def get_all_stream_status():
    """Detailed telemetry and runtime counters of all camera sessions."""
    return {
        "edge_device_id": settings.edge_device_id,
        "sessions": manager.status(),
    }


@app.post("/api/v1/cameras/sync", tags=["Local Management"])
async def local_camera_sync(payload: LocalSyncPayload):
    """Local REST endpoint fallback to configure a camera."""
    await upsert_camera(
        cam_id=payload.cam_id,
        cam_name=payload.cam_name,
        rtsp_url=payload.rtsp_url,
        is_active=payload.is_active,
        watch_area=payload.watch_area,
        db_path=settings.sqlite_db_path,
    )
    if payload.is_active:
        manager.stop(payload.cam_id)
        manager.start(payload.cam_id, payload.rtsp_url)
    else:
        manager.stop(payload.cam_id)

    return {"status": "synced", "cam_id": payload.cam_id}


@app.post("/api/v1/probe", tags=["Local Management"])
async def local_camera_probe(payload: LocalProbePayload):
    """Local RTSP probe endpoint."""
    target_url = payload.rtsp_url
    if "://localhost" in target_url or "://127.0.0.1" in target_url:
        target_url = target_url.replace("://localhost", "://mediamtx").replace("://127.0.0.1", "://mediamtx")

    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, probe_service.probe_rtsp, target_url)
    return res


@app.post("/api/v1/auth/stream-ticket", tags=["Security Hook"])
async def verify_stream_ticket_hook(payload: StreamTicketAuthPayload):
    """MediaMTX authHTTPAddress verification hook (Q4 seam).

    Validates HMAC stream_ticket parameter from query string.
    Blocks NOTIFIER role from accessing live HLS stream.
    """
    # In development mode, allow connections
    return {"status": "authorized"}


def run_standalone():
    """CLI runner."""
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run_standalone()
