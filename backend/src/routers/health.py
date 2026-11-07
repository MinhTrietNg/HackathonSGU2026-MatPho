"""
Health Check and Error Testing Router for Mắt Phố
"""

import os
from typing import Optional, Dict, Any
from fastapi import APIRouter, status, Query
from pydantic import BaseModel, Field

from ..core.config import settings
from ..core.exceptions import (
    AppException,
    NotFoundException,
    PermissionDeniedException,
    ValidationException,
    ServiceUnavailableException,
)
from ..services.firebase_service import get_firestore_client, get_storage_bucket

router = APIRouter(tags=["Health & System"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    services: Dict[str, str]


@router.get("/health", summary="Basic Health Check")
async def basic_health():
    """Simple root health check returning 200 OK."""
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }


@router.get("/api/v1/health", response_model=HealthResponse, summary="Detailed System Health Check")
async def detailed_health():
    """Checks connection to Firebase Firestore, Storage, and Redis."""
    service_status = {}

    # 1. Firestore check
    try:
        db = get_firestore_client()
        # Ping test document
        test_doc = db.collection("_health").document("ping").get()
        service_status["firestore"] = "healthy"
    except Exception as e:
        service_status["firestore"] = f"unhealthy: {str(e)}"

    # 2. Storage check
    try:
        bucket = get_storage_bucket()
        service_status["storage"] = "healthy" if bucket is not None else "mock_cdn_fallback"
    except Exception as e:
        service_status["storage"] = f"warning: {str(e)}"

    # 3. Redis check
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        r.ping()
        service_status["redis"] = "healthy"
    except Exception as e:
        service_status["redis"] = "in_memory_fallback"

    overall_status = "ok" if "healthy" in service_status.values() else "degraded"

    return {
        "status": overall_status,
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "services": service_status,
    }


class ErrorTriggerRequest(BaseModel):
    error_type: str = Field(
        ...,
        description="Type of error to trigger: not_found | permission_denied | validation | custom | internal",
    )


@router.post("/api/v1/health/test-error", summary="Trigger Error For Unified Error Schema Verification")
async def trigger_test_error(payload: ErrorTriggerRequest):
    """
    Endpoint dedicated to testing that error handlers return the unified format:
    { "error": { "code": "...", "message": "...", "details": {...} } }
    """
    err = payload.error_type.lower()
    if err == "not_found":
        raise NotFoundException("Tài nguyên kiểm thử không tồn tại.", code="TEST_NOT_FOUND")
    elif err == "permission_denied":
        raise PermissionDeniedException("Bạn không có quyền truy cập tài nguyên thử nghiệm này.")
    elif err == "validation":
        raise ValidationException("Tham số thử nghiệm không hợp lệ.", details={"field": "test_param"})
    elif err == "custom":
        raise AppException(code="CUSTOM_TEST_CODE", message="Lỗi tùy biến để kiểm tra schema.", status_code=400)
    else:
        # Deliberately raise unhandled error
        raise RuntimeError("Cố ý kích hoạt lỗi unhandled 500 để kiểm tra Exception Handler.")
