"""Local SQLite Persistence with WAL mode for Zero-Corruption on Power Outages.

Manages both:
1. `local_cameras`: Autonomous local camera configuration cache.
2. `offline_events_queue`: Offline event resilience buffer (Sơ đồ 6 Master Spec)
   when Internet WAN connection is lost.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any

import aiosqlite

logger = logging.getLogger("edge.db")

DEFAULT_DB_PATH = os.getenv("SQLITE_DB_PATH", "/app/data/edge.db")

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS local_cameras (
    cam_id TEXT PRIMARY KEY,
    cam_name TEXT NOT NULL,
    rtsp_url TEXT NOT NULL,
    codec TEXT DEFAULT 'h264',
    watch_area TEXT,
    is_active INTEGER DEFAULT 1,
    status TEXT DEFAULT 'CONNECTING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS offline_events_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    cam_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    retry_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'PENDING',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_retry_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_offline_events_status ON offline_events_queue(status, id);
"""


def _ensure_dir(db_path: str) -> None:
    directory = os.path.dirname(db_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def init_db_sync(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialize SQLite tables and WAL mode synchronously (used during cold boot)."""
    _ensure_dir(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    logger.info("SQLite initialized in WAL mode at %s", db_path)


async def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialize SQLite tables and WAL mode asynchronously."""
    _ensure_dir(db_path)
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript(SCHEMA_SQL)
        await conn.commit()
    logger.info("SQLite initialized (async) in WAL mode at %s", db_path)


# ------------------------------------------------------------------------------
# 1. LOCAL CAMERAS OPERATIONS
# ------------------------------------------------------------------------------

async def upsert_camera(
    cam_id: str,
    cam_name: str,
    rtsp_url: str,
    is_active: bool = True,
    codec: str = "h264",
    watch_area: list[Any] | str | None = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Insert or update a camera in local SQLite."""
    watch_area_str = (
        json.dumps(watch_area) if isinstance(watch_area, (list, dict)) else watch_area
    )
    sql = """
    INSERT INTO local_cameras (cam_id, cam_name, rtsp_url, codec, watch_area, is_active, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(cam_id) DO UPDATE SET
        cam_name=excluded.cam_name,
        rtsp_url=excluded.rtsp_url,
        codec=excluded.codec,
        watch_area=coalesce(excluded.watch_area, local_cameras.watch_area),
        is_active=excluded.is_active,
        updated_at=CURRENT_TIMESTAMP;
    """
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            sql,
            (cam_id, cam_name, rtsp_url, codec, watch_area_str, 1 if is_active else 0),
        )
        await conn.commit()
    logger.info("[cam_id=%s] upserted into local SQLite", cam_id)


async def delete_camera(cam_id: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Remove a camera from local SQLite."""
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute("DELETE FROM local_cameras WHERE cam_id = ?", (cam_id,))
        await conn.commit()
        return cursor.rowcount > 0


async def get_camera(cam_id: str, db_path: str = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    """Fetch one camera by cam_id."""
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM local_cameras WHERE cam_id = ?", (cam_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def list_active_cameras(db_path: str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    """Fetch all active cameras."""
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM local_cameras WHERE is_active = 1") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


def list_active_cameras_sync(db_path: str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    """Synchronous helper to list active cameras during cold boot."""
    _ensure_dir(db_path)
    if not os.path.exists(db_path):
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM local_cameras WHERE is_active = 1")
        return [dict(r) for r in cursor.fetchall()]


async def update_camera_status(cam_id: str, status: str, db_path: str = DEFAULT_DB_PATH) -> None:
    """Update camera connection/running status in SQLite."""
    sql = "UPDATE local_cameras SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE cam_id = ?"
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(sql, (status, cam_id))
        await conn.commit()


async def update_camera_watch_area(
    cam_id: str, watch_area: list[Any] | str, db_path: str = DEFAULT_DB_PATH
) -> None:
    """Update the AI watch_area polygon in SQLite without interrupting video stream."""
    watch_area_str = (
        json.dumps(watch_area) if isinstance(watch_area, (list, dict)) else watch_area
    )
    sql = "UPDATE local_cameras SET watch_area = ?, updated_at = CURRENT_TIMESTAMP WHERE cam_id = ?"
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(sql, (watch_area_str, cam_id))
        await conn.commit()


# ------------------------------------------------------------------------------
# 2. OFFLINE EVENTS QUEUE OPERATIONS (Sơ đồ 6: Offline Resilience)
# ------------------------------------------------------------------------------

async def enqueue_offline_event(
    event_id: str,
    cam_id: str,
    event_type: str,
    payload: dict[str, Any] | str,
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    """Enqueue an event into offline queue when WAN Internet connection is down."""
    payload_str = json.dumps(payload) if isinstance(payload, dict) else payload
    sql = """
    INSERT INTO offline_events_queue (event_id, cam_id, event_type, payload, status)
    VALUES (?, ?, ?, ?, 'PENDING')
    ON CONFLICT(event_id) DO UPDATE SET
        payload=excluded.payload,
        status='PENDING',
        last_retry_at=CURRENT_TIMESTAMP;
    """
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute(sql, (event_id, cam_id, event_type, payload_str))
        await conn.commit()
        logger.info("[event_id=%s] enqueued into offline_events_queue (cam_id=%s)", event_id, cam_id)
        return cursor.lastrowid or 0


async def get_pending_offline_events(
    limit: int = 50, db_path: str = DEFAULT_DB_PATH
) -> list[dict[str, Any]]:
    """Retrieve pending offline events in FIFO order for resynchronization."""
    sql = """
    SELECT id, event_id, cam_id, event_type, payload, retry_count, status, created_at
    FROM offline_events_queue
    WHERE status = 'PENDING'
    ORDER BY id ASC
    LIMIT ?
    """
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(sql, (limit,)) as cursor:
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["payload"] = json.loads(item["payload"])
                except Exception:
                    pass
                results.append(item)
            return results


async def mark_event_sent(event_id: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Mark an offline event as successfully pushed to Cloud Backend."""
    sql = """
    UPDATE offline_events_queue
    SET status = 'SENT', last_retry_at = CURRENT_TIMESTAMP
    WHERE event_id = ?
    """
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute(sql, (event_id,))
        await conn.commit()
        return cursor.rowcount > 0


async def mark_event_failed(
    event_id: str, error_message: str = "", max_retries: int = 5, db_path: str = DEFAULT_DB_PATH
) -> None:
    """Increment retry count and mark failed if exceeding maximum retries."""
    sql = """
    UPDATE offline_events_queue
    SET retry_count = retry_count + 1,
        error_message = ?,
        status = CASE WHEN retry_count + 1 >= ? THEN 'FAILED' ELSE 'PENDING' END,
        last_retry_at = CURRENT_TIMESTAMP
    WHERE event_id = ?
    """
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(sql, (error_message, max_retries, event_id))
        await conn.commit()


async def clear_sent_events(db_path: str = DEFAULT_DB_PATH) -> int:
    """Purge all successfully synchronized events to reclaim disk space."""
    sql = "DELETE FROM offline_events_queue WHERE status = 'SENT'"
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute(sql)
        await conn.commit()
        return cursor.rowcount


async def get_queue_stats(db_path: str = DEFAULT_DB_PATH) -> dict[str, int]:
    """Return count summary of offline queue."""
    sql = "SELECT status, count(*) as count FROM offline_events_queue GROUP BY status"
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute(sql) as cursor:
            rows = await cursor.fetchall()
            stats = {"PENDING": 0, "SENT": 0, "FAILED": 0}
            for status, count in rows:
                stats[status] = count
            return stats
