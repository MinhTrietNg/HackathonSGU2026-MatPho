"""
Escalation Background Worker for Mắt Phố (ADR 0011)
Periodically checks active timers and triggers Tier 2 escalation on 60s timeout.
"""

import asyncio
import logging
from ..services.escalation_service import get_escalation_service

logger = logging.getLogger("matpho.escalation_worker")


async def escalation_loop(interval_seconds: float = 2.0):
    """
    Background worker loop that checks expired escalation timers every interval_seconds.
    """
    esc_svc = get_escalation_service()
    logger.info("Started escalation worker background loop")
    while True:
        try:
            await esc_svc.check_and_escalate_expired()
        except asyncio.CancelledError:
            logger.info("Escalation worker cancelled, shutting down")
            break
        except Exception as e:
            logger.error(f"Error in escalation worker: {e}", exc_info=True)
        await asyncio.sleep(interval_seconds)
