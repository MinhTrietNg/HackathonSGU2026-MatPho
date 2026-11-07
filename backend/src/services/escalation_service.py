"""
Redis-backed Two-Tier Escalation Timer Service for Mắt Phố (ADR 0011)

Level 0 (T=0s): Alert sent only to LEADER & MEMBER_MANAGER.
Level 1 (T=60s Timeout): Automatically escalates to ALL members (MEMBER & NOTIFIER).
Atomic Cancel: Del key immediately when incident is CONFIRMED, RESOLVED, or marked FALSE_ALARM.
"""

import os
import json
import time
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

try:
    import redis
except ImportError:
    redis = None

from .websocket_manager import get_websocket_manager
from .fcm_service import get_fcm_service
from .repositories.user_repo import get_user_repository
from .repositories.group_repo import get_group_repository
from ..core.formatters import format_iso_utc
from ..models.common import UserRole

logger = logging.getLogger("matpho.escalation")


class EscalationService:
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0")
        self._redis = None
        self._in_memory_timers: Dict[str, Dict[str, Any]] = {}
        self._connect_redis()

    def _connect_redis(self):
        if redis:
            try:
                self._redis = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                )
                self._redis.ping()
                logger.info(f"Connected to Redis escalation cache at {self.redis_url}")
            except Exception as e:
                logger.warning(f"Could not connect to Redis ({e}), using in-memory escalation timer fallback")
                self._redis = None
        else:
            self._redis = None

    def start_timer(
        self,
        alert_id: str,
        group_id: str,
        alert_data: Dict[str, Any],
        ttl_seconds: int = 60,
    ) -> bool:
        """
        Starts a 60s countdown timer in Redis (ADR 0011).
        Key: escalation:timer:{alert_id}
        """
        payload = {
            "alert_id": alert_id,
            "group_id": group_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ttl": ttl_seconds,
            "data": alert_data,
        }
        key = f"escalation:timer:{alert_id}"

        if self._redis:
            try:
                self._redis.set(key, json.dumps(payload, default=str), ex=ttl_seconds)
                self._redis.sadd("escalation:active_timers", alert_id)
                logger.info(f"Redis escalation timer started for alert {alert_id} ({ttl_seconds}s)")
                return True
            except Exception as e:
                logger.error(f"Redis set failed for {key}: {e}")

        # In-memory fallback
        self._in_memory_timers[alert_id] = {
            "payload": payload,
            "expire_at": time.time() + ttl_seconds,
        }
        logger.info(f"In-memory escalation timer started for alert {alert_id} ({ttl_seconds}s)")
        return True

    def cancel_timer(self, alert_id: str) -> bool:
        """
        Atomic cancellation of the escalation timer.
        Called on: resolve, mark_false_alarm, call_114, report_real_fire.
        """
        key = f"escalation:timer:{alert_id}"
        cancelled = False

        if self._redis:
            try:
                deleted = self._redis.delete(key)
                self._redis.srem("escalation:active_timers", alert_id)
                if deleted > 0:
                    cancelled = True
                    logger.info(f"Redis escalation timer cancelled for alert {alert_id}")
            except Exception as e:
                logger.error(f"Redis delete failed for {key}: {e}")

        if alert_id in self._in_memory_timers:
            del self._in_memory_timers[alert_id]
            cancelled = True
            logger.info(f"In-memory escalation timer cancelled for alert {alert_id}")

        return cancelled

    def is_timer_active(self, alert_id: str) -> bool:
        key = f"escalation:timer:{alert_id}"
        if self._redis:
            try:
                if bool(self._redis.exists(key)):
                    return True
            except Exception:
                pass

        if alert_id in self._in_memory_timers:
            if time.time() < self._in_memory_timers[alert_id]["expire_at"]:
                return True
            else:
                del self._in_memory_timers[alert_id]
        return False

    def get_remaining_seconds(self, alert_id: str) -> int:
        key = f"escalation:timer:{alert_id}"
        if self._redis:
            try:
                ttl = self._redis.ttl(key)
                if ttl > 0:
                    return ttl
            except Exception:
                pass

        if alert_id in self._in_memory_timers:
            rem = int(self._in_memory_timers[alert_id]["expire_at"] - time.time())
            return max(0, rem)
        return 0

    async def trigger_escalation(self, alert_id: str, group_id: Optional[str] = None) -> bool:
        """
        Escalates alert to Tier 2 (Level 1):
        Broadcasts siren to ALL members via WebSocket and dispatches High Priority FCM.
        """
        from .repositories.alert_repo import get_alert_repository
        alert_repo = get_alert_repository()
        user_repo = get_user_repository()
        group_repo = get_group_repository()

        alert = alert_repo.get_alert(alert_id)
        if not alert:
            return False

        gid = group_id or alert.group_id
        ws = get_websocket_manager()
        fcm = get_fcm_service()

        alert_payload = {
            "alert_id": alert.alert_id,
            "cam_id": alert.cam_id,
            "cam_name": alert.cam_name,
            "location_name": alert.location_name or alert.subgroup_name,
            "sign": alert.sign.value if hasattr(alert.sign, "value") else str(alert.sign),
            "confidence": alert.confidence,
            "still_url": alert.still_url or alert.fire_image_url,
            "summary": alert.summary,
            "detail": alert.detail,
            "verification": alert.verification.value if hasattr(alert.verification, "value") else str(alert.verification),
            "detected_at": format_iso_utc(alert.detected_at) or (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"),
        }

        # 1. Update escalation_level to 1 in Firestore
        try:
            alert_repo.collection.document(alert_id).update({
                "escalation_level": 1,
                "updated_at": datetime.now(timezone.utc),
            })
        except Exception as e:
            logger.warning(f"Failed to update escalation_level in Firestore: {e}")

        # 2. Broadcast Level 1 to entire group
        ws_broadcast = ws.broadcast_fire_alert(
            group_id=gid,
            alert_payload=alert_payload,
            escalation_level=1,
        )

        # 3. Dispatch FCM High Priority to members according to camera_ids
        async def dispatch_fcm():
            members = group_repo.list_members(gid)
            all_tokens = []
            for m in members:
                # Leaders/Managers receive all; Members/Notifiers receive if assigned to this camera
                if m.role in (UserRole.LEADER, UserRole.MEMBER_MANAGER) or m.camera_ids is None or alert.cam_id in m.camera_ids:
                    u = user_repo.get_user_by_id(m.user_id)
                    if u and u.fcm_tokens:
                        all_tokens.extend(u.fcm_tokens)
            if all_tokens:
                await asyncio.to_thread(
                    fcm.send_fire_alert_push,
                    fcm_tokens=all_tokens,
                    alert_id=alert_id,
                    escalation_level=1,
                )

        await asyncio.gather(ws_broadcast, dispatch_fcm(), return_exceptions=True)
        logger.info(f"Escalated alert {alert_id} to Level 1 (Tier 2)")
        return True

    async def check_and_escalate_expired(self):
        """
        Periodic worker check: finds expired timers and escalates them.
        """
        expired_ids: List[str] = []

        # Check in Redis
        if self._redis:
            try:
                active_ids = self._redis.smembers("escalation:active_timers")
                for aid in active_ids:
                    key = f"escalation:timer:{aid}"
                    if not self._redis.exists(key):
                        expired_ids.append(aid)
                        self._redis.srem("escalation:active_timers", aid)
            except Exception as e:
                logger.error(f"Error checking expired Redis timers: {e}")

        # Check in-memory
        now = time.time()
        for aid, item in list(self._in_memory_timers.items()):
            if now >= item["expire_at"]:
                expired_ids.append(aid)
                del self._in_memory_timers[aid]

        for aid in expired_ids:
            try:
                await self.trigger_escalation(aid)
            except Exception as e:
                logger.error(f"Failed to auto-escalate alert {aid}: {e}")


_escalation_service_instance: Optional[EscalationService] = None


def get_escalation_service() -> EscalationService:
    global _escalation_service_instance
    if _escalation_service_instance is None:
        _escalation_service_instance = EscalationService()
    return _escalation_service_instance
