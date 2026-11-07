"""
Settings and System Utilities Router for Mắt Phố
Phase 5: Notification settings and Test Alarm Trigger (Screen H4)
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from ..core.config import settings
from ..core.security import get_current_user
from ..core.formatters import format_iso_utc
from ..models.user import UserModel
from ..services.fcm_service import get_fcm_service
from ..services.repositories.user_repo import get_user_repo

logger = logging.getLogger("backend.routers.settings")

router = APIRouter(prefix="/settings", tags=["Settings"])


class TestAlertRequest(BaseModel):
    pass


@router.post("/test-alert", summary="Trigger test siren on device (Screen H4)")
def trigger_test_alert(
    payload: Optional[TestAlertRequest] = None,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Sends a test alarm push to the user's registered devices to test siren volume and speaker.
    Screen H4: Thử nghiệm còi báo cháy.
    """
    fcm_svc = get_fcm_service()
    dispatched_count = 0
    now_dt = datetime.now(timezone.utc)
    test_id = f"tst_{int(now_dt.timestamp())}"

    if current_user.fcm_tokens:
        for tok in current_user.fcm_tokens:
            dispatched_count += fcm_svc.send_test_alert_push(tok, test_id)

    return {
        "status": "dispatched",
        "test_id": test_id,
        "tokens_targeted": len(current_user.fcm_tokens or []),
        "dispatched_count": dispatched_count,
        "sent_at": format_iso_utc(now_dt),
    }


@router.get("/system", summary="System Information & Health metadata")
def get_system_info(
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Returns application environment and system metadata."""
    return {
        "project_name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "server_time": format_iso_utc(datetime.now(timezone.utc)),
    }
