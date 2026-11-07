"""Outbound WebSocket Client connecting EdgeAI-MatPho to Cloud Backend.

Maintains a persistent, bi-directional command channel without requiring any
incoming ports opened on the customer router (Zero Inbound Ports).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx
import websockets

from .backoff import ExponentialBackoff
from .config import DecoderSettings, redact_url
from .db import delete_camera, upsert_camera
from .manager import DecodeManager, StreamAlreadyRunning
from .probe import get_probe_service

logger = logging.getLogger("edge.ws_client")


class EdgeWebSocketClient:
    """Manages the outbound WebSocket lifecycle, commands and heartbeats."""

    def __init__(self, settings: DecoderSettings, manager: DecodeManager) -> None:
        self.settings = settings
        self.manager = manager
        self.probe_service = get_probe_service()
        self._stop_event = asyncio.Event()
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._backoff = ExponentialBackoff(initial=2.0, maximum=30.0)

    async def start(self) -> None:
        """Run the persistent connection loop until stopped."""
        logger.info(
            "Starting Edge Outbound WebSocket client to %s (edge_id=%s)",
            self.settings.cloud_backend_ws_url,
            self.settings.edge_device_id,
        )
        while not self._stop_event.is_set():
            try:
                await self._connect_and_run()
                self._backoff.reset()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                delay = self._backoff.next_delay()
                logger.warning(
                    "WebSocket disconnected (%s). Reconnecting in %.1fs...",
                    exc,
                    delay,
                )
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass

    def stop(self) -> None:
        """Signal the WebSocket loop to terminate."""
        self._stop_event.set()
        if self._ws is not None:
            asyncio.create_task(self._ws.close())

    async def send_message(self, message: dict[str, Any]) -> bool:
        """Send a JSON payload to the Cloud Backend."""
        if self._ws is None:
            return False
        is_closed = getattr(self._ws, "closed", False)
        if self._ws is None or is_closed:
            return False
        try:
            await self._ws.send(json.dumps(message, ensure_ascii=False))
            return True
        except Exception as exc:
            logger.warning("Failed to send WebSocket message: %s", exc)
            return False

    async def _connect_and_run(self) -> None:
        ws_url = (
            f"{self.settings.cloud_backend_ws_url}"
            f"?edge_id={self.settings.edge_device_id}"
            f"&secret={self.settings.internal_api_secret_key}"
        )
        headers = {
            "X-Edge-ID": self.settings.edge_device_id,
            "X-Internal-Secret": self.settings.internal_api_secret_key,
        }

        connect_kwargs: dict[str, Any] = {
            "ping_interval": 20,
            "ping_timeout": 10,
        }
        import inspect
        sig = inspect.signature(websockets.connect)
        if "additional_headers" in sig.parameters:
            connect_kwargs["additional_headers"] = headers
        elif "extra_headers" in sig.parameters:
            connect_kwargs["extra_headers"] = headers

        async with websockets.connect(ws_url, **connect_kwargs) as ws:
            self._ws = ws
            logger.info("Connected successfully to Cloud Backend WebSocket!")

            # 1. Send Handshake
            await self.send_message(
                {
                    "type": "EDGE_CONNECTED",
                    "edge_device_id": self.settings.edge_device_id,
                    "timestamp": time.time(),
                }
            )

            # 2. Concurrently run Receive Loop & Heartbeat Loop
            receive_task = asyncio.create_task(self._receive_loop(ws))
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            done, pending = await asyncio.wait(
                [receive_task, heartbeat_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

    async def _receive_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        async for raw_msg in ws:
            try:
                data = json.loads(raw_msg)
                await self._handle_command(data)
            except json.JSONDecodeError:
                logger.warning("Received non-JSON message: %s", raw_msg[:100])
            except Exception as exc:
                logger.exception("Error processing command from Cloud: %s", exc)

    async def _handle_command(self, data: dict[str, Any]) -> None:
        action = data.get("action") or data.get("type")
        logger.info("Received action from Cloud: %s", action)

        if action == "SYNC_CAMERA":
            await self._on_sync_camera(data)
        elif action == "DELETE_CAMERA":
            await self._on_delete_camera(data)
        elif action == "PROBE_CAMERA":
            await self._on_probe_camera(data)
        elif action == "RESTART_STREAM":
            await self._on_restart_stream(data)
        else:
            logger.debug("Unhandled action from Cloud: %s", data)

    async def _on_sync_camera(self, data: dict[str, Any]) -> None:
        cam_id = data.get("cam_id")
        cam_name = data.get("cam_name", cam_id)
        rtsp_url = data.get("rtsp_url")
        watch_area = data.get("watch_area")
        is_active = data.get("is_active", True)

        if not cam_id or not rtsp_url:
            logger.warning("SYNC_CAMERA missing cam_id or rtsp_url")
            return

        logger.info("[cam_id=%s] SYNC_CAMERA: %s", cam_id, redact_url(rtsp_url))

        # 1. Upsert into local SQLite WAL
        await upsert_camera(
            cam_id=cam_id,
            cam_name=cam_name,
            rtsp_url=rtsp_url,
            is_active=is_active,
            watch_area=watch_area,
            db_path=self.settings.sqlite_db_path,
        )

        # 2. Notify MediaMTX Control API (Standardized to live/{cam_id})
        await self._register_mediamtx_path(cam_id, rtsp_url)

        # 3. Start or update decode session
        if is_active:
            try:
                self.manager.stop(cam_id)
            except Exception:
                pass
            try:
                self.manager.start(cam_id, rtsp_url)
            except StreamAlreadyRunning:
                pass

        # 4. Respond with status
        await self.send_message(
            {
                "type": "CAMERA_STATUS",
                "cam_id": cam_id,
                "status": "ONLINE" if is_active else "DISABLED",
                "timestamp": time.time(),
            }
        )

    async def _on_delete_camera(self, data: dict[str, Any]) -> None:
        cam_id = data.get("cam_id")
        if not cam_id:
            return

        logger.info("[cam_id=%s] DELETE_CAMERA", cam_id)
        self.manager.stop(cam_id)
        await delete_camera(cam_id, db_path=self.settings.sqlite_db_path)
        await self._remove_mediamtx_path(cam_id)

        await self.send_message(
            {
                "type": "CAMERA_DELETED",
                "cam_id": cam_id,
                "timestamp": time.time(),
            }
        )

    async def _on_probe_camera(self, data: dict[str, Any]) -> None:
        probe_token = data.get("probe_token", "")
        rtsp_url = data.get("rtsp_url", "")

        logger.info("[probe_token=%s] PROBE_CAMERA for %s", probe_token, redact_url(rtsp_url))

        # Run OpenCV probe in worker thread pool so we don't block asyncio event loop
        result = await asyncio.to_thread(self.probe_service.probe_rtsp, rtsp_url)

        if result.get("is_accessible"):
            await self.send_message(
                {
                    "type": "PROBE_SUCCESS",
                    "probe_token": probe_token,
                    "device_name": result.get("device_name"),
                    "resolution": result.get("resolution"),
                    "fps": result.get("fps"),
                    "preview_snapshot_base64": result.get("preview_snapshot_base64"),
                    "timestamp": time.time(),
                }
            )
        else:
            await self.send_message(
                {
                    "type": "PROBE_FAILED",
                    "probe_token": probe_token,
                    "error_code": result.get("error_code", "CAMERA_NOT_REACHABLE"),
                    "message": result.get("message", "Probe failed"),
                    "device_name": result.get("device_name"),
                    "timestamp": time.time(),
                }
            )

    async def _on_restart_stream(self, data: dict[str, Any]) -> None:
        cam_id = data.get("cam_id")
        if not cam_id:
            return
        logger.info("[cam_id=%s] RESTART_STREAM", cam_id)
        self.manager.stop(cam_id)
        self.manager.start(cam_id)

    async def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(self.settings.stats_interval_s)
            status_map = self.manager.status()
            await self.send_message(
                {
                    "type": "EDGE_HEARTBEAT",
                    "edge_device_id": self.settings.edge_device_id,
                    "active_streams": len(status_map),
                    "streams": status_map,
                    "timestamp": time.time(),
                }
            )

    async def _register_mediamtx_path(self, cam_id: str, rtsp_source: str) -> None:
        """Call MediaMTX Control REST API (:9997) to register path (live/{cam_id})."""
        url = f"{self.settings.mediamtx_api_url}/v3/config/paths/add/live/{cam_id}"
        payload = {"source": "publisher"}
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code in (200, 201):
                    logger.debug("MediaMTX registered path live/%s", cam_id)
        except Exception as exc:
            logger.debug("MediaMTX add path warning: %s", exc)

    async def _remove_mediamtx_path(self, cam_id: str) -> None:
        """Call MediaMTX Control REST API (:9997) to delete path (live/{cam_id})."""
        url = f"{self.settings.mediamtx_api_url}/v3/config/paths/delete/live/{cam_id}"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.delete(url)
        except Exception as exc:
            logger.debug("MediaMTX delete path warning: %s", exc)
