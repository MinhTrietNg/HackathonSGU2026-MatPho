import os
import sqlite3
import pytest
from src.db import (
    clear_sent_events,
    delete_camera,
    enqueue_offline_event,
    get_camera,
    get_pending_offline_events,
    get_queue_stats,
    init_db,
    init_db_sync,
    list_active_cameras,
    list_active_cameras_sync,
    mark_event_failed,
    mark_event_sent,
    update_camera_status,
    update_camera_watch_area,
    upsert_camera,
)


@pytest.fixture
def test_db_path(tmp_path):
    return str(tmp_path / "test_edge.db")


def test_init_db_sync(test_db_path):
    """Verify synchronous DB initialization and WAL journal mode."""
    init_db_sync(test_db_path)
    assert os.path.exists(test_db_path)

    # Check WAL mode
    with sqlite3.connect(test_db_path) as conn:
        cursor = conn.execute("PRAGMA journal_mode;")
        row = cursor.fetchone()
        assert row[0].lower() == "wal"


@pytest.mark.asyncio
async def test_crud_camera_lifecycle(test_db_path):
    """Verify full CRUD lifecycle for local_cameras table."""
    await init_db(test_db_path)

    # 1. Upsert
    watch_area = [[0.1, 0.1], [0.8, 0.1], [0.8, 0.8], [0.1, 0.8]]
    await upsert_camera(
        cam_id="cam_01",
        cam_name="Cổng chính",
        rtsp_url="rtsp://192.168.1.10:554/live",
        is_active=True,
        codec="h264",
        watch_area=watch_area,
        db_path=test_db_path,
    )

    # 2. Get camera
    cam = await get_camera("cam_01", db_path=test_db_path)
    assert cam is not None
    assert cam["cam_name"] == "Cổng chính"
    assert cam["is_active"] == 1
    assert "0.8" in cam["watch_area"]

    # 3. List active
    active = await list_active_cameras(db_path=test_db_path)
    assert len(active) == 1
    assert active[0]["cam_id"] == "cam_01"

    # Test sync helper (cold boot)
    active_sync = list_active_cameras_sync(db_path=test_db_path)
    assert len(active_sync) == 1
    assert active_sync[0]["cam_id"] == "cam_01"

    # 4. Update status & watch_area
    await update_camera_status("cam_01", "ONLINE", db_path=test_db_path)
    cam_updated = await get_camera("cam_01", db_path=test_db_path)
    assert cam_updated["status"] == "ONLINE"

    new_area = [[0.2, 0.2], [0.7, 0.7]]
    await update_camera_watch_area("cam_01", new_area, db_path=test_db_path)
    cam_area = await get_camera("cam_01", db_path=test_db_path)
    assert "0.7" in cam_area["watch_area"]

    # 5. Delete camera
    deleted = await delete_camera("cam_01", db_path=test_db_path)
    assert deleted is True

    cam_gone = await get_camera("cam_01", db_path=test_db_path)
    assert cam_gone is None


@pytest.mark.asyncio
async def test_offline_events_queue_resilience(test_db_path):
    """Verify Sơ đồ 6: Offline events buffering, FIFO retrieval, retry and cleanup."""
    await init_db(test_db_path)

    # 1. Enqueue 3 events while offline
    p1 = {"confidence": 0.92, "bbox": [0.1, 0.2, 0.4, 0.5]}
    p2 = {"confidence": 0.85, "bbox": [0.2, 0.3, 0.5, 0.6]}
    p3 = {"confidence": 0.78, "bbox": [0.3, 0.4, 0.6, 0.7]}

    await enqueue_offline_event("evt_01", "cam_01", "fire", p1, db_path=test_db_path)
    await enqueue_offline_event("evt_02", "cam_01", "fire", p2, db_path=test_db_path)
    await enqueue_offline_event("evt_03", "cam_02", "smoke", p3, db_path=test_db_path)

    # 2. Retrieve pending events in FIFO order
    pending = await get_pending_offline_events(limit=10, db_path=test_db_path)
    assert len(pending) == 3
    assert pending[0]["event_id"] == "evt_01"
    assert pending[1]["event_id"] == "evt_02"
    assert pending[2]["event_id"] == "evt_03"
    assert pending[0]["payload"]["confidence"] == 0.92

    # 3. Mark evt_01 as sent successfully
    ok = await mark_event_sent("evt_01", db_path=test_db_path)
    assert ok is True

    # 4. Mark evt_02 as failed with retry increment
    await mark_event_failed("evt_02", error_message="HTTP 503 Service Unavailable", max_retries=3, db_path=test_db_path)
    pending_after_retry = await get_pending_offline_events(limit=10, db_path=test_db_path)
    assert len(pending_after_retry) == 2  # evt_02 and evt_03 still pending
    assert pending_after_retry[0]["event_id"] == "evt_02"
    assert pending_after_retry[0]["retry_count"] == 1

    # 5. Check queue stats
    stats = await get_queue_stats(db_path=test_db_path)
    assert stats["SENT"] == 1
    assert stats["PENDING"] == 2

    # 6. Reclaim disk space by clearing sent events
    cleared = await clear_sent_events(db_path=test_db_path)
    assert cleared == 1

    stats_after_clear = await get_queue_stats(db_path=test_db_path)
    assert stats_after_clear["SENT"] == 0
    assert stats_after_clear["PENDING"] == 2
