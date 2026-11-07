"""Minimal FastAPI app: list events, stream new ones over WebSocket.

``python -m firewatch serve`` runs this server; with ``--source`` it also
runs the pipeline in a background thread so events stream live. The Flutter
app / React dashboard consume this API; ``GET /console`` is a single static
page for the operator (ack buttons) so the human-in-the-loop flow can be run
without the dashboard. Acks are a separate API (``/events/{id}/ack``) and do
not change the event schema.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any

from fastapi import (FastAPI, HTTPException, Query, Request, Response, WebSocket,
                     WebSocketDisconnect)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .acks import Ack, AckAction, AckStore, EscalationWatcher
from .alerts import Event, EventStore, event_to_dict, sample_event
from .hitl import export_hard_negative
from .config import Config
from .pipeline import PipelineHealth

log = logging.getLogger(__name__)
CONSOLE_HTML = Path(__file__).resolve().parent / "static" / "console.html"


class AckIn(BaseModel):
    """Body of ``POST /events/{id}/ack``."""

    action: AckAction
    note: str = Field("", max_length=500)


def ws_payload(event: Event, kind: str) -> dict[str, Any]:
    """Message ``WS /ws`` cho một thông báo của store.

    ``created`` → ``type: event``; còn lại → ``type: event_update`` với
    ``reason: "escalation"`` khi gửi lại CRITICAL chưa ai trả lời, và
    ``reason: "verifier"`` khi object ``verifier`` đổi trạng thái và
    ``reason: "su_co"`` khi sự cố cập nhật (nhịp, mức tăng, kết thúc), cả hai
    chỉ khi cờ ``verifier.ben_vung`` bật. Cập nhật VLM khi cờ tắt không có
    ``reason``, như trước.
    """
    msg_type = "event" if kind == "created" else "event_update"
    payload: dict[str, Any] = {"type": msg_type, "event": event_to_dict(event)}
    if kind == "escalated":
        payload["reason"] = "escalation"
    elif kind == "updated" and event.verifier is not None:
        payload["reason"] = "verifier"
    elif kind == "su_co":
        payload["reason"] = "su_co"
    return payload


class Broadcaster:
    """Fan out events from the pipeline thread to WebSocket clients."""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self._queues: set[asyncio.Queue] = set()

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def publish_threadsafe(self, event: Event, kind: str = "created") -> None:
        self.publish_payload_threadsafe(ws_payload(event, kind))

    def publish_ack_threadsafe(self, ack: Ack) -> None:
        self.publish_payload_threadsafe({"type": "ack", "ack": ack.model_dump()})

    def publish_payload_threadsafe(self, payload: dict[str, Any]) -> None:
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(self._publish, payload)

    def _publish(self, payload: dict[str, Any]) -> None:
        for q in list(self._queues):
            q.put_nowait(payload)

    def register(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues.add(q)
        return q

    def unregister(self, q: asyncio.Queue) -> None:
        self._queues.discard(q)


def create_app(cfg: Config, store: EventStore,
               health: PipelineHealth | None = None,
               acks: AckStore | None = None) -> FastAPI:
    app = FastAPI(title="FireWatch v3", version=__version__)
    broadcaster = Broadcaster()
    store.subscribe(broadcaster.publish_threadsafe)
    acks = acks or AckStore(store.dir / "acks.json")
    acks.subscribe(broadcaster.publish_ack_threadsafe)
    hitl_dir = cfg.resolve(cfg.alerts.hitl_negatives_dir)

    def _export_dismissed(ack: Ack) -> None:
        event = store.get(ack.event_id)
        if event is not None:
            export_hard_negative(event, ack, cfg.root, hitl_dir)

    acks.subscribe(_export_dismissed)
    app.state.store, app.state.broadcaster = store, broadcaster
    app.state.acks = acks
    app.state.health = health
    app.add_middleware(CORSMiddleware, allow_origins=cfg.server.cors_origins,
                       allow_methods=["*"], allow_headers=["*"])
    app.mount("/snapshots", StaticFiles(directory=str(store.dir)), name="snapshots")
    vlm_provider = cfg.vlm.provider if cfg.vlm.enabled else "disabled"

    @app.on_event("startup")
    async def _startup() -> None:
        broadcaster.attach(asyncio.get_running_loop())

    @app.get("/")
    def index() -> dict[str, Any]:
        return {"service": "firewatch", "version": __version__,
                "camera_id": cfg.camera.id, "context": cfg.camera.context,
                "vlm_provider": vlm_provider,
                "vlm_is_mock": vlm_provider == "mock",
                "events": len(store), "endpoints": [
                    "/events", "/events/{id}", "/events/{id}/ack", "/acks", "/ws",
                    "/webhook-test", "/snapshots/<file>", "/health", "/console"]}

    @app.get("/health")
    def health_route(response: Response) -> dict[str, Any]:
        """200 khi pipeline còn sống (hoặc server chỉ phục vụ event cũ);
        503 khi pipeline chết, lỗi, hay quá lâu không có heartbeat.

        Cờ ``verifier.ben_vung`` bật thì có thêm khối ``verifier`` (cầu dao,
        hàng chờ, tỉ lệ kịp và p50 / p95 trong 10 phút, số lần VLM_OFF); các
        trường cũ giữ nguyên.
        """
        if health is None:
            return {"status": "ok", "pipeline": None, "vlm_provider": vlm_provider}
        snap = health.snapshot()
        if snap["status"] in ("dead", "stale"):
            response.status_code = 503
        body = {"status": "ok" if snap["status"] == "ok" else snap["status"],
                "pipeline": snap, "vlm_provider": vlm_provider}
        if health.verifier_stats is not None:
            body["verifier"] = health.verifier_stats()
        return body

    @app.get("/events", response_model=list[Event])
    def list_events(limit: int = Query(50, ge=0, description="0 = tất cả"),
                    ) -> list[Event]:
        return store.all(limit=limit)

    @app.get("/events/{event_id}", response_model=Event)
    def get_event(event_id: str) -> Event:
        ev = store.get(event_id)
        if ev is None:
            raise HTTPException(status_code=404, detail="không có event này")
        return ev

    @app.post("/events/{event_id}/ack", response_model=Ack)
    def ack_event(event_id: str, body: AckIn) -> Ack:
        """Người trực trả lời một event: confirm | dismiss_controlled | watch."""
        if store.get(event_id) is None:
            raise HTTPException(status_code=404, detail="không có event này")
        return acks.set(event_id, body.action, body.note)

    @app.get("/events/{event_id}/ack")
    def get_ack(event_id: str) -> dict[str, Any]:
        if store.get(event_id) is None:
            raise HTTPException(status_code=404, detail="không có event này")
        ack = acks.get(event_id)
        return {"event_id": event_id, "ack": ack.model_dump() if ack else None}

    @app.get("/acks")
    def list_acks() -> dict[str, Any]:
        return {k: v.model_dump() for k, v in acks.all().items()}

    @app.get("/console", include_in_schema=False)
    def console() -> FileResponse:
        return FileResponse(CONSOLE_HTML, media_type="text/html")

    @app.post("/webhook-test")
    async def webhook_test(request: Request) -> dict[str, Any]:
        """Backend gọi để thử kết nối; trả lại body và một event mẫu đúng schema."""
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = None
        return {"ok": True, "received": body,
                "sample_event": event_to_dict(sample_event())}

    @app.websocket("/ws")
    async def ws_events(ws: WebSocket) -> None:
        await ws.accept()
        q = broadcaster.register()
        try:
            await ws.send_json({"type": "hello", "events_so_far": len(store)})
            while True:
                await ws.send_json(await q.get())
        except WebSocketDisconnect:
            pass
        finally:
            broadcaster.unregister(q)

    return app


def serve(cfg: Config, *, source: str | None, realtime: bool, host: str | None,
          port: int | None) -> None:
    """Run uvicorn; optionally run the pipeline on ``source`` in a thread."""
    import uvicorn

    from .pipeline import Pipeline

    store = EventStore(cfg.alerts, cfg.camera, cfg)
    acks = AckStore(store.dir / "acks.json")
    health = PipelineHealth() if source else None
    app = create_app(cfg, store, health, acks)
    EscalationWatcher(store, acks, cfg.alerts.escalation_s).start()
    if source:
        pipe = Pipeline(cfg, source, realtime=realtime or None, store=store,
                        strict=True, health=health, acks=acks)

        def _run() -> None:
            try:
                pipe.run()
            except BaseException as exc:  # noqa: BLE001 - ghi vào /health
                log.exception("pipeline dừng vì lỗi: %s", exc)
                if health is not None and not health.error:
                    health.error = f"{type(exc).__name__}: {exc}"
                    health.finished = True

        threading.Thread(target=_run, name="pipeline", daemon=True).start()
        log.info("pipeline chạy nền trên %s", source)
    uvicorn.run(app, host=host or cfg.server.host, port=port or cfg.server.port,
                log_level="info")
