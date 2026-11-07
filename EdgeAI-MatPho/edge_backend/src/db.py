"""
Edge Local SQLite Database Manager (Autonomous Offline-First Storage)
Uses SQLite in WAL (Write-Ahead Logging) mode for high-concurrency read/write on Edge Mini PC.
Stores:
1. `local_cameras`: Camera configurations synced from Cloud (cam_id, rtsp_url, watch_area, is_active)
   - `watch_area` supports both Rectangle dict `{"left": 0.1, "top": 0.2, "width": 0.5, "height": 0.4}`
     and Polygon list `[[x1, y1], [x2, y2], ...]`.
2. `offline_events_queue`: Fire events queued when WAN/Cloud is unreachable (Store-and-Forward)
"""

import os
import json
import time
import logging
import aiosqlite
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger("edge-backend.db")

DEFAULT_DB_PATH = os.getenv(
    "EDGE_SQLITE_PATH",
    str(Path(__file__).resolve().parents[1] / "data" / "edge_local.db")
)

WatchAreaType = Union[Dict[str, float], List[List[float]]]


class EdgeDatabase:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    async def init_db(self) -> None:
        """Initialize tables and enable SQLite WAL mode."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS local_cameras (
                    cam_id TEXT PRIMARY KEY,
                    cam_name TEXT NOT NULL DEFAULT '',
                    rtsp_url TEXT NOT NULL,
                    watch_area_json TEXT DEFAULT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    updated_at REAL NOT NULL
                );
                """
            )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS offline_events_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cam_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            await db.commit()
        logger.info("Edge SQLite WAL initialized at %s", self.db_path)

    async def upsert_camera(
        self,
        cam_id: str,
        rtsp_url: str,
        cam_name: str = "",
        watch_area: Optional[WatchAreaType] = None,
        is_active: bool = True,
    ) -> None:
        watch_json = json.dumps(watch_area) if watch_area is not None else None
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO local_cameras (cam_id, cam_name, rtsp_url, watch_area_json, is_active, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cam_id) DO UPDATE SET
                    cam_name = excluded.cam_name,
                    rtsp_url = excluded.rtsp_url,
                    watch_area_json = COALESCE(excluded.watch_area_json, local_cameras.watch_area_json),
                    is_active = excluded.is_active,
                    updated_at = excluded.updated_at;
                """,
                (cam_id, cam_name, rtsp_url, watch_json, 1 if is_active else 0, now),
            )
            await db.commit()

    async def remove_camera(self, cam_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM local_cameras WHERE cam_id = ?", (cam_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def list_cameras(self, only_active: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT cam_id, cam_name, rtsp_url, watch_area_json, is_active, updated_at FROM local_cameras"
        if only_active:
            query += " WHERE is_active = 1"
        query += " ORDER BY cam_id ASC"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                result = []
                for r in rows:
                    watch_area = None
                    if r["watch_area_json"]:
                        try:
                            watch_area = json.loads(r["watch_area_json"])
                        except Exception:
                            watch_area = None
                    result.append(
                        {
                            "cam_id": r["cam_id"],
                            "cam_name": r["cam_name"],
                            "rtsp_url": r["rtsp_url"],
                            "watch_area": watch_area,
                            "is_active": bool(r["is_active"]),
                            "updated_at": r["updated_at"],
                        }
                    )
                return result

    async def enqueue_offline_event(
        self, cam_id: str, event_type: str, payload: Dict[str, Any]
    ) -> int:
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO offline_events_queue (cam_id, event_type, payload_json, created_at, retry_count)
                VALUES (?, ?, ?, ?, 0)
                """,
                (cam_id, event_type, json.dumps(payload), now),
            )
            await db.commit()
            return cursor.lastrowid or 0

    async def peek_offline_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, cam_id, event_type, payload_json, created_at, retry_count "
                "FROM offline_events_queue ORDER BY id ASC LIMIT ?",
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "id": r["id"],
                        "cam_id": r["cam_id"],
                        "event_type": r["event_type"],
                        "payload": json.loads(r["payload_json"]),
                        "created_at": r["created_at"],
                        "retry_count": r["retry_count"],
                    }
                    for r in rows
                ]

    async def delete_offline_event(self, event_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM offline_events_queue WHERE id = ?", (event_id,))
            await db.commit()
