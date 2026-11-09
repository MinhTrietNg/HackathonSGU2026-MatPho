"""Cloud link stays responsive while a reconnect re-syncs every camera."""

import asyncio
from types import SimpleNamespace

import aiosqlite
import pytest

import src.main as edge_main
from src import ws_client as wsc
from src.db import EdgeDatabase
from src.main import handle_cloud_command, state


class _FakeWs:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, data: str) -> None:
        self.sent.append(data)


def _client(on_command) -> wsc.OutboundCloudWSClient:
    return wsc.OutboundCloudWSClient(
        db=None, on_command=on_command, get_status_snapshot=lambda: {}
    )


@pytest.mark.asyncio
async def test_dispatch_returns_at_once_and_keeps_order_per_camera():
    done: list[str] = []

    async def on_command(payload):
        await asyncio.sleep(payload["delay"])
        done.append(payload["tag"])
        return {"type": "ACK", "tag": payload["tag"]}

    client = _client(on_command)
    ws = _FakeWs()
    commands = [
        {"action": "SYNC_CAMERA", "cam_id": "cam_a", "delay": 0.05, "tag": "a1"},
        {"action": "SYNC_CAMERA", "cam_id": "cam_a", "delay": 0.0, "tag": "a2"},
        {"action": "SYNC_CAMERA", "cam_id": "cam_b", "delay": 0.0, "tag": "b1"},
    ]
    for payload in commands:
        client._spawn(client._dispatch(ws, payload))
    # Nothing ran yet: spawning never waits for a command to finish.
    assert done == []

    await asyncio.gather(*list(client._tasks))
    assert done.index("a1") < done.index("a2")
    assert done.index("b1") < done.index("a1")
    assert len(ws.sent) == 3


@pytest.mark.asyncio
async def test_failing_command_is_contained():
    async def on_command(payload):
        raise RuntimeError("boom")

    client = _client(on_command)
    client._spawn(client._dispatch(_FakeWs(), {"action": "SYNC_CAMERA", "cam_id": "c"}))
    await asyncio.gather(*list(client._tasks))


@pytest.mark.asyncio
async def test_camera_announces_are_coalesced(monkeypatch):
    monkeypatch.setattr(wsc, "ANNOUNCE_QUIET_S", 0.05)
    client = _client(None)
    calls = 0

    async def announce() -> bool:
        nonlocal calls
        calls += 1
        return True

    client.announce_camera_sync = announce
    for _ in range(20):
        client.schedule_camera_announce()
    await asyncio.sleep(0.2)
    assert calls == 1


class _FakeManager:
    def __init__(self, source_url: str) -> None:
        self.session = SimpleNamespace(
            alive=True, spec=SimpleNamespace(source_url=source_url)
        )
        self.restarts: list[tuple[str, str]] = []

    def get_session(self, cam_id):
        return self.session

    def restart(self, cam_id, source_url=None):
        self.restarts.append((cam_id, source_url))

    def stop(self, cam_id):
        return True


@pytest.mark.asyncio
async def test_sync_camera_restarts_only_when_source_changes(tmp_path, monkeypatch):
    db = EdgeDatabase(db_path=str(tmp_path / "edge.db"))
    await db.init_db()
    manager = _FakeManager("rtsp://10.0.0.5:554/stream1")
    monkeypatch.setattr(state, "db", db)
    monkeypatch.setattr(state, "manager", manager)
    monkeypatch.setattr(state, "ws_client", None)

    sync = {"action": "SYNC_CAMERA", "cam_id": "cam_x", "is_active": True}
    await handle_cloud_command({**sync, "rtsp_url": "rtsp://10.0.0.5:554/stream1"})
    assert manager.restarts == []

    await handle_cloud_command({**sync, "rtsp_url": "rtsp://10.0.0.6:554/stream1"})
    assert manager.restarts == [("cam_x", "rtsp://10.0.0.6:554/stream1")]


@pytest.mark.asyncio
async def test_sync_complete_prunes_cameras_deleted_on_cloud(tmp_path, monkeypatch):
    db =EdgeDatabase(db_path=str(tmp_path / "edge.db"))
    await db.init_db()
    for cam_id in ("cam_keep", "cam_gone", "cam_seed", "cam_new"):
        await db.upsert_camera(
            cam_id=cam_id, rtsp_url="rtsp://10.0.0.5/s", cam_name=cam_id, is_active=True
        )
    # Everything but cam_new was last changed long ago.
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "UPDATE local_cameras SET updated_at = 0 WHERE cam_id != 'cam_new'"
        )
        await conn.commit()
    stopped: list[str] = []
    manager = _FakeManager("rtsp://10.0.0.5/s")
    manager.stop = lambda cam_id: stopped.append(cam_id) or True
    monkeypatch.setattr(state, "db", db)
    monkeypatch.setattr(state, "manager", manager)
    monkeypatch.setattr(state, "ws_client", None)
    monkeypatch.setenv(
        "DECODER_STREAMS", '[{"cam_id": "cam_seed", "source_url": "rtsp://x/y"}]'
    )

    # An empty list (failed Cloud query) must never wipe the edge.
    assert await edge_main.prune_cameras_missing_from_cloud([]) == []

    reply = await handle_cloud_command(
        {"action": "SYNC_COMPLETE", "cam_ids": ["cam_keep"]}
    )
    assert reply["removed"] == ["cam_gone"]
    assert stopped == ["cam_gone"]
    left = {c["cam_id"] for c in await db.list_cameras()}
    assert left == {"cam_keep", "cam_seed", "cam_new"}
