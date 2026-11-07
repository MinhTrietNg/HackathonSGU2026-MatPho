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
                    ai_mode TEXT NOT NULL DEFAULT 'ALWAYS',
                    ai_schedules_json TEXT DEFAULT '[]',
                    updated_at REAL NOT NULL
                );
                """
            )
            # Auto-migration for existing SQLite databases created before Phase 8
            try:
                await db.execute("ALTER TABLE local_cameras ADD COLUMN ai_mode TEXT NOT NULL DEFAULT 'ALWAYS';")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE local_cameras ADD COLUMN ai_schedules_json TEXT DEFAULT '[]';")
            except Exception:
                pass

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
        ai_mode: Optional[str] = None,
        ai_schedules: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        watch_json = json.dumps(watch_area) if watch_area is not None else None
        schedules_json = json.dumps(ai_schedules) if ai_schedules is not None else None
        mode_val = (ai_mode or "ALWAYS").upper()
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO local_cameras (
                    cam_id, cam_name, rtsp_url, watch_area_json, is_active, ai_mode, ai_schedules_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cam_id) DO UPDATE SET
                    cam_name = excluded.cam_name,
                    rtsp_url = excluded.rtsp_url,
                    watch_area_json = COALESCE(excluded.watch_area_json, local_cameras.watch_area_json),
                    is_active = excluded.is_active,
                    ai_mode = CASE WHEN ? IS NOT NULL THEN excluded.ai_mode ELSE local_cameras.ai_mode END,
                    ai_schedules_json = CASE WHEN ? IS NOT NULL THEN excluded.ai_schedules_json ELSE local_cameras.ai_schedules_json END,
                    updated_at = excluded.updated_at;
                """,
                (
                    cam_id,
                    cam_name,
                    rtsp_url,
                    watch_json,
                    1 if is_active else 0,
                    mode_val,
                    schedules_json or "[]",
                    now,
                    ai_mode,
                    schedules_json,
                ),
            )
            await db.commit()

    async def update_camera_ai_config(
        self,
        cam_id: str,
        ai_mode: str,
        ai_schedules: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Update AI mode and rest schedule slots for a camera in local SQLite."""
        mode_val = (ai_mode or "ALWAYS").upper()
        schedules_json = json.dumps(ai_schedules or [])
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE local_cameras
                SET ai_mode = ?, ai_schedules_json = ?, updated_at = ?
                WHERE cam_id = ?
                """,
                (mode_val, schedules_json, now, cam_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def remove_camera(self, cam_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM local_cameras WHERE cam_id = ?", (cam_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def get_camera(self, cam_id: str) -> Optional[Dict[str, Any]]:
        query = (
            "SELECT cam_id, cam_name, rtsp_url, watch_area_json, is_active, "
            "ai_mode, ai_schedules_json, updated_at FROM local_cameras WHERE cam_id = ?"
        )
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (cam_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                watch_area = None
                if row["watch_area_json"]:
                    try:
                        watch_area = json.loads(row["watch_area_json"])
                    except Exception:
                        watch_area = None
                schedules = []
                if row["ai_schedules_json"]:
                    try:
                        schedules = json.loads(row["ai_schedules_json"])
                    except Exception:
                        schedules = []
                return {
                    "cam_id": row["cam_id"],
                    "cam_name": row["cam_name"],
                    "rtsp_url": row["rtsp_url"],
                    "watch_area": watch_area,
                    "is_active": bool(row["is_active"]),
                    "ai_mode": row["ai_mode"] or "ALWAYS",
                    "ai_schedules": schedules if isinstance(schedules, list) else [],
                    "updated_at": row["updated_at"],
                }

    async def list_cameras(self, only_active: bool = False) -> List[Dict[str, Any]]:
        query = (
            "SELECT cam_id, cam_name, rtsp_url, watch_area_json, is_active, "
            "ai_mode, ai_schedules_json, updated_at FROM local_cameras"
        )
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
                    schedules = []
                    if r["ai_schedules_json"]:
                        try:
                            schedules = json.loads(r["ai_schedules_json"])
                        except Exception:
                            schedules = []
                    result.append(
                        {
                            "cam_id": r["cam_id"],
                            "cam_name": r["cam_name"],
                            "rtsp_url": r["rtsp_url"],
                            "watch_area": watch_area,
                            "is_active": bool(r["is_active"]),
                            "ai_mode": r["ai_mode"] or "ALWAYS",
                            "ai_schedules": schedules if isinstance(schedules, list) else [],
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
