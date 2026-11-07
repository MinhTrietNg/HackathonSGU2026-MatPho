"""
Outbound WebSocket Client to Cloud Backend (`/api/v1/internal/edge/ws`)
Allows Edge Node behind NAT/Firewall (Zero Port-Forwarding) to:
1. Maintain a persistent full-duplex WebSocket tunnel to Cloud Backend.
2. Receive real-time commands (`SYNC_CAMERA`, `REMOVE_CAMERA`, `PROBE_CAMERA`, `RESTART_STREAM`).
3. Flush queued offline fire alerts from SQLite (`offline_events_queue`) once WAN reconnects.
4. Send periodic `EDGE_HEARTBEAT` & `CAMERA_STATUS` frames.
"""

import os
import json
import time
import asyncio
import logging
import httpx
import websockets
from typing import Callable, Awaitable, Dict, Any, Optional

from .db import EdgeDatabase

logger = logging.getLogger("edge-backend.ws_client")


class OutboundCloudWSClient:
    def __init__(
        self,
        db: EdgeDatabase,
        on_command: Callable[[Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]],
        get_status_snapshot: Callable[[], Dict[str, Any]],
        get_public_hls_url: Optional[Callable[[], str]] = None,
    ):
        self.db = db
        self.on_command = on_command
        self.get_status_snapshot = get_status_snapshot
        self.get_public_hls_url = get_public_hls_url
        self.edge_id = os.getenv("EDGE_DEVICE_ID", "edg_local_01")
        self.secret = os.getenv(
            "INTERNAL_API_SECRET_KEY", "secure_internal_key_for_ai_and_worker_communication"
        )
        self.cloud_ws_url = os.getenv(
            "CLOUD_BACKEND_WS_URL", "ws://localhost:8000/api/v1/internal/edge/ws"
        )
        self.cloud_api_url = os.getenv(
            "CLOUD_BACKEND_API_URL", "http://localhost:8000"
        ).rstrip("/")
        self._stop = False
        self._active_ws: Optional[Any] = None

    def stop(self) -> None:
        self._stop = True

    async def announce_gateway_url(self, public_hls_url: str) -> bool:
        """Instantly publish newly discovered Cloudflare public tunnel URL to Cloud."""
        if not self._active_ws:
            return False
        snap = self.get_status_snapshot()
        try:
            cams = [c["cam_id"] for c in await self.db.list_cameras(only_active=True)]
        except Exception:
            cams = list(snap.keys())
        try:
            await self._active_ws.send(
                json.dumps({
                    "type": "EDGE_GATEWAY_ANNOUNCE",
                    "edge_device_id": self.edge_id,
                    "active_streams": len(snap),
                    "public_hls_base_url": public_hls_url,
                    "cameras": cams,
                    "timestamp": time.time(),
                })
            )
            logger.info("[GATEWAY WATCHDOG] Pushed public tunnel URL to Cloud: %s", public_hls_url)
            return True
        except Exception as exc:
            logger.debug("Failed to push gateway announcement: %s", exc)
            return False

    async def flush_offline_events(self) -> int:
        """Drain queued fire events from SQLite and POST them to Cloud Backend."""
        events = await self.db.peek_offline_events(limit=20)
        flushed = 0
        if not events:
            return 0

        headers = {"X-Internal-Secret": self.secret}
        async with httpx.AsyncClient(timeout=8.0) as client:
            for ev in events:
                try:
                    url = f"{self.cloud_api_url}/api/v1/internal/ai/fire-events"
                    res = await client.post(url, json=ev["payload"], headers=headers)
                    if res.status_code in (200, 201, 202):
                        await self.db.delete_offline_event(ev["id"])
                        flushed += 1
                    else:
                        break
                except Exception as exc:
                    logger.debug("Offline event flush paused: %s", exc)
                    break
        if flushed > 0:
            logger.info("Flushed %d offline fire events to Cloud Backend.", flushed)
        return flushed

    async def run_forever(self) -> None:
        backoff = 2.0
        while not self._stop:
            sep = "&" if "?" in self.cloud_ws_url else "?"
            full_url = f"{self.cloud_ws_url}{sep}edge_id={self.edge_id}&secret={self.secret}"
            try:
                async with websockets.connect(
                    full_url,
                    extra_headers={
                        "x-internal-secret": self.secret,
                        "x-edge-id": self.edge_id,
                    },
                    ping_interval=15,
                    ping_timeout=10,
                ) as ws:
                    self._active_ws = ws
                    logger.info("Connected Outbound WebSocket to Cloud: %s", self.cloud_ws_url)
                    backoff = 2.0

                    await self._send_heartbeat(ws)
                    await self.flush_offline_events()

                    hb_task = asyncio.create_task(self._heartbeat_loop(ws))
                    try:
                        async for message in ws:
                            if message == "pong":
                                continue
                            try:
                                payload = json.loads(message)
                            except Exception:
                                continue

                            msg_type = payload.get("type") or payload.get("action")
                            if msg_type == "EDGE_CONNECTED_ACK":
                                logger.info(
                                    "Cloud acknowledged Edge Node %s",
                                    payload.get("edge_device_id"),
                                )
                                continue

                            reply = await self.on_command(payload)
                            if reply:
                                await ws.send(json.dumps(reply, ensure_ascii=False))
                    finally:
                        self._active_ws = None
                        hb_task.cancel()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug(
                    "Cloud WS unreachable (%s). Retrying in %.1fs...", exc, backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)

    async def _heartbeat_loop(self, ws) -> None:
        while not self._stop:
            await asyncio.sleep(10.0)
            await self._send_heartbeat(ws)
            await self.flush_offline_events()

    async def _send_heartbeat(self, ws) -> None:
        snap = self.get_status_snapshot()
        public_url = self.get_public_hls_url() if self.get_public_hls_url else ""
        try:
            cams = [c["cam_id"] for c in await self.db.list_cameras(only_active=True)]
        except Exception:
            cams = list(snap.keys())
        await ws.send(
            json.dumps(
                {
                    "type": "EDGE_HEARTBEAT",
                    "edge_device_id": self.edge_id,
                    "active_streams": len(snap),
                    "public_hls_base_url": public_url,
                    "cameras": cams,
                    "timestamp": time.time(),
                }
            )
        )
