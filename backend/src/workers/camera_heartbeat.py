"""
Camera Heartbeat Background Worker for Mắt Phố
Phase 5: Periodic 5-second camera telemetry broadcast (Points 6 & Q4)
"""

import asyncio
import logging
from ..services.websocket_manager import get_websocket_manager
from ..services.repositories.camera_repo import get_camera_repo

logger = logging.getLogger("backend.workers.camera_heartbeat")


async def camera_heartbeat_loop():
    """Background loop to broadcast camera heartbeats every 5 seconds over WebSocket."""
    ws = get_websocket_manager()
    repo = get_camera_repo()
    logger.info("Camera heartbeat background worker started.")

    while True:
        try:
            await asyncio.sleep(5)
            # Find all active online cameras across all groups
            active_cams = repo.list_all_online_cameras()
            for c in active_cams:
                await ws.broadcast_camera_heartbeat(
                    group_id=c.group_id,
                    cam_id=c.cam_id,
                    status=c.status.value if hasattr(c.status, "value") else str(c.status),
                    ai_status="SCANNING" if c.is_ai_enabled else "STANDBY",
                    fps=25,
                )
        except asyncio.CancelledError:
            logger.info("Camera heartbeat background worker received cancellation.")
            break
        except Exception as e:
            logger.debug(f"Heartbeat loop error: {e}")
