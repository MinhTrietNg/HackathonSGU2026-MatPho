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

from .relay_rules import bo_su_kien_bi_tu_choi
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

    async def announce_camera_sync(self) -> bool:
        """Immediately announce updated camera list to Cloud Backend."""
        if not self._active_ws:
            return False
        snap = self.get_status_snapshot()
        public_url = self.get_public_hls_url() if self.get_public_hls_url else ""
        try:
            cams = [c["cam_id"] for c in await self.db.list_cameras(only_active=True)]
        except Exception:
            cams = list(snap.keys())
        self._push_gateway_to_redis(public_url, cams)
        try:
            await self._active_ws.send(
                json.dumps({
                    "type": "EDGE_GATEWAY_ANNOUNCE",
                    "edge_device_id": self.edge_id,
                    "active_streams": len(snap),
                    "public_hls_base_url": public_url,
                    "cameras": cams,
                    "timestamp": time.time(),
                })
            )
            return True
        except Exception:
            return False

    async def announce_gateway_url(self, public_hls_url: str) -> bool:
        """Instantly publish newly discovered Cloudflare public tunnel URL to Cloud."""
        if not self._active_ws:
            return False
        snap = self.get_status_snapshot()
        try:
            cams = [c["cam_id"] for c in await self.db.list_cameras(only_active=True)]
        except Exception:
            cams = list(snap.keys())
        self._push_gateway_to_redis(public_hls_url, cams)
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

    def _push_gateway_to_redis(self, public_hls_url: str, cams: list) -> None:
        """Sync public_hls_base_url directly to Upstash Redis & Firestore if configured."""
        if not public_hls_url or public_hls_url.startswith("http://localhost") or public_hls_url.startswith("http://127.0.0.1"):
            return
        clean_url = public_hls_url.rstrip("/")
        redis_url = os.getenv(
            "REDIS_URL",
            "rediss://default:gQAAAAAAAvH2AAIgcDI3Mzg5YjhlYzNhODc0MTJhOWIyNDg2NmIwNmJmMWI0YQ@integral-osprey-193014.upstash.io:6379",
        )
        try:
            import redis
            r = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
            record = {
                "public_hls_base_url": clean_url,
                "cameras": cams,
                "last_seen": time.time(),
            }
            r.setex(f"edge:node:{self.edge_id}", 300, json.dumps(record))
        except Exception:
            pass

    async def flush_offline_events(self) -> int:
        """Drain queued fire events from SQLite and POST them to Cloud Backend."""
        events = await self.db.peek_offline_events(limit=20)
        flushed = 0
        if not events:
            return 0

        headers = {
            "Authorization": f"Bearer {self.secret}",
            "X-Internal-Secret": self.secret,
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            for ev in events:
                try:
                    url = f"{self.cloud_api_url}/api/v1/internal/ai/fire-events"
                    res = await client.post(url, json=ev["payload"], headers=headers)
                    if res.status_code in (200, 201, 202):
                        await self.db.delete_offline_event(ev["id"])
                        flushed += 1
                    elif bo_su_kien_bi_tu_choi(res.status_code):
                        # Cloud rejected this event for good (camera not registered, bad
                        # payload): drop it, or it blocks the whole queue forever and gets
                        # replayed as a stale fire alert every heartbeat.
                        logger.warning(
                            "Dropping offline event %s (cam %s): cloud returned %d",
                            ev["id"], ev.get("cam_id"), res.status_code,
                        )
                        await self.db.delete_offline_event(ev["id"])
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
                # Compatible with both websockets >= 14 (additional_headers) and legacy (< 14, extra_headers)
                ws_headers = {
                    "x-internal-secret": self.secret,
                    "x-edge-id": self.edge_id,
                }
                import inspect
                connect_sig = inspect.signature(websockets.connect)
                header_kwarg = (
                    {"additional_headers": ws_headers}
                    if "additional_headers" in connect_sig.parameters
                    else {"extra_headers": ws_headers}
                )
                async with websockets.connect(
                    full_url,
                    **header_kwarg,
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
        self._push_gateway_to_redis(public_url, cams)
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
