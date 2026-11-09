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

# Keepalive: a pong must arrive within PING_TIMEOUT_S of each ping.
PING_INTERVAL_S = 20
PING_TIMEOUT_S = 20
# Stream restarts allowed to run at the same time while commands are handled.
COMMAND_RESTART_SLOTS = 4
# Commands that stop or restart a stream session and so take a restart slot.
RESTARTING_ACTIONS = frozenset({"SYNC_CAMERA", "ADD_CAMERA", "UPDATE_CAMERA", "REMOVE_CAMERA"})
# Quiet time after the last camera change before the camera list is announced.
ANNOUNCE_QUIET_S = 1.0
# Minimum age before an unchanged gateway record is written to Redis again.
REDIS_REFRESH_S = 60.0


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
        # Commands run off the receive loop (see _dispatch): one lock per camera keeps
        # their order, and a small pool bounds how many stream restarts run at once.
        self._cam_locks: Dict[str, asyncio.Lock] = {}
        self._restart_slots = asyncio.Semaphore(COMMAND_RESTART_SLOTS)
        self._tasks: set = set()
        self._announce_task: Optional[asyncio.Task] = None
        self._redis_client: Optional[Any] = None
        self._redis_last: tuple = ("", (), 0.0)

    def stop(self) -> None:
        self._stop = True

    def schedule_camera_announce(self) -> None:
        """Announce the camera list once a burst of camera changes has settled.

        A reconnect brings one SYNC_CAMERA per camera; announcing after each of them
        sent the full list dozens of times in a row.
        """
        if self._announce_task is not None and not self._announce_task.done():
            self._announce_task.cancel()
        self._announce_task = asyncio.create_task(self._announce_after_quiet())

    async def _announce_after_quiet(self) -> None:
        try:
            await asyncio.sleep(ANNOUNCE_QUIET_S)
        except asyncio.CancelledError:
            return
        await self.announce_camera_sync()

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
        await asyncio.to_thread(self._push_gateway_to_redis, public_url, cams)
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
        await asyncio.to_thread(self._push_gateway_to_redis, public_hls_url, cams)
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
        """Sync public_hls_base_url directly to Upstash Redis & Firestore if configured.

        Blocking network I/O (about 0.4 s per call to Upstash): call it through
        asyncio.to_thread, never on the event loop, or keepalive pongs stall and the
        Cloud link drops.
        """
        if not public_hls_url or public_hls_url.startswith("http://localhost") or public_hls_url.startswith("http://127.0.0.1"):
            return
        clean_url = public_hls_url.rstrip("/")
        now = time.time()
        last_url, last_cams, last_at = self._redis_last
        # The key lives 300 s; rewriting an unchanged record more often only adds load.
        if (clean_url, tuple(cams)) == (last_url, last_cams) and now - last_at < REDIS_REFRESH_S:
            return
        redis_url = os.getenv(
            "REDIS_URL",
            "rediss://default:gQAAAAAAAvH2AAIgcDI3Mzg5YjhlYzNhODc0MTJhOWIyNDg2NmIwNmJmMWI0YQ@integral-osprey-193014.upstash.io:6379",
        )
        try:
            import redis
            if self._redis_client is None:
                self._redis_client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=3,
                )
            record = {
                "public_hls_base_url": clean_url,
                "cameras": cams,
                "last_seen": now,
            }
            self._redis_client.setex(f"edge:node:{self.edge_id}", 300, json.dumps(record))
            self._redis_last = (clean_url, tuple(cams), now)
        except Exception:
            self._redis_client = None

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
                    ping_interval=PING_INTERVAL_S,
                    ping_timeout=PING_TIMEOUT_S,
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

                            self._spawn(self._dispatch(ws, payload))
                    finally:
                        self._active_ws = None
                        hb_task.cancel()
                logger.warning("Cloud WS closed by peer, reconnecting")
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    "Cloud WS unreachable (%s). Retrying in %.1fs...", exc, backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _dispatch(self, ws, payload: Dict[str, Any]) -> None:
        """Run one Cloud command without holding up the receive loop.

        Handling commands inline stopped the loop from reading frames: a reconnect
        brings one SYNC_CAMERA per camera, each restart took up to seconds, the
        keepalive pong waited behind them and the link dropped every ~37 s before the
        sync could finish. Tasks are created in arrival order and asyncio.Lock is
        FIFO, so commands for the same camera still run in order.
        """
        action = payload.get("action") or payload.get("type")
        cam_id = payload.get("cam_id")
        lock = self._cam_locks.setdefault(cam_id, asyncio.Lock()) if cam_id else None
        try:
            if lock is not None:
                await lock.acquire()
            try:
                if action in RESTARTING_ACTIONS:
                    async with self._restart_slots:
                        reply = await self.on_command(payload)
                else:
                    reply = await self.on_command(payload)
            finally:
                if lock is not None:
                    lock.release()
            if reply:
                await ws.send(json.dumps(reply, ensure_ascii=False))
        except Exception as exc:
            logger.warning("Cloud command %s (cam %s) failed: %s", action, cam_id, exc)

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
        await asyncio.to_thread(self._push_gateway_to_redis, public_url, cams)
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
