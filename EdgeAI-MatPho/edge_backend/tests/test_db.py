import pytest
from src.db import EdgeDatabase


@pytest.mark.asyncio
async def test_edge_sqlite_wal_cameras_crud_and_dual_watch_area(tmp_path):
    """Verify local_cameras CRUD in SQLite WAL mode with both Polygon and Rectangle watch_area (Q2)."""
    db_file = str(tmp_path / "test_edge.db")
    db = EdgeDatabase(db_path=db_file)
    await db.init_db()

    # 1. Insert camera with Polygon watch_area
    watch_poly = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
    await db.upsert_camera(
        cam_id="cam_01",
        rtsp_url="rtsp://admin:pass@192.168.1.10:554/live",
        cam_name="Camera Cổng Chính",
        watch_area=watch_poly,
        is_active=True,
    )

    cams = await db.list_cameras()
    assert len(cams) == 1
    assert cams[0]["cam_id"] == "cam_01"
    assert cams[0]["watch_area"] == watch_poly

    # 2. Update camera with Rectangle dict watch_area (from App I5 / Cloud Backend)
    watch_rect = {"left": 0.15, "top": 0.25, "width": 0.5, "height": 0.4}
    await db.upsert_camera(
        cam_id="cam_01",
        rtsp_url="rtsp://admin:pass@192.168.1.11:554/live",
        cam_name="Camera Cổng Chính Mới",
        watch_area=watch_rect,
        is_active=False,
    )

    cams_after = await db.list_cameras()
    assert cams_after[0]["watch_area"] == watch_rect
    assert cams_after[0]["is_active"] is False

    # 3. Remove camera
    removed = await db.remove_camera("cam_01")
    assert removed is True
    assert await db.list_cameras() == []


@pytest.mark.asyncio
async def test_edge_sqlite_offline_events_queue(tmp_path):
    """Verify Store-and-Forward offline_events_queue FIFO operations."""
    db_file = str(tmp_path / "test_queue.db")
    db = EdgeDatabase(db_path=db_file)
    await db.init_db()

    id1 = await db.enqueue_offline_event(
        cam_id="cam_01",
        event_type="FIRE_DETECTED",
        payload={"cam_id": "cam_01", "confidence": 0.88, "class_name": "fire"},
    )
    id2 = await db.enqueue_offline_event(
        cam_id="cam_02",
        event_type="FIRE_DETECTED",
        payload={"cam_id": "cam_02", "confidence": 0.92, "class_name": "smoke"},
    )
    assert id2 > id1

    queued = await db.peek_offline_events(limit=10)
    assert len(queued) == 2
    assert queued[0]["cam_id"] == "cam_01"
    assert queued[1]["cam_id"] == "cam_02"

    await db.delete_offline_event(id1)
    remaining = await db.peek_offline_events(limit=10)
    assert len(remaining) == 1
    assert remaining[0]["id"] == id2
