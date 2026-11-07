"""
Phase 1 Test Suite: Foundation, Error Schema, BaaS Connections & Formatters
"""

import pytest
from src.core.formatters import normalize_phone_e164, format_iso_utc, current_utc_iso
from src.models.common import generate_semantic_id, UserRole, CameraStatus, AlertStatus
from src.services.repositories.base_repo import BaseFirestoreRepository


def test_basic_health_check(client):
    """Verify root /health endpoint returns 200 OK."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_detailed_health_check(client):
    """Verify /api/v1/health returns detailed infrastructure status."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ok", "degraded")
    assert "services" in data
    assert "firestore" in data["services"]
    assert "redis" in data["services"]


def test_unified_error_format_not_found(client):
    """Verify custom NotFoundException returns unified error schema with 404."""
    res = client.post("/api/v1/health/test-error", json={"error_type": "not_found"})
    assert res.status_code == 404
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "TEST_NOT_FOUND"
    assert "message" in data["error"]
    assert isinstance(data["error"]["details"], dict)


def test_unified_error_format_permission_denied(client):
    """Verify PermissionDeniedException returns unified error schema with 403."""
    res = client.post("/api/v1/health/test-error", json={"error_type": "permission_denied"})
    assert res.status_code == 403
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "PERMISSION_DENIED"


def test_unified_error_format_validation_custom(client):
    """Verify custom ValidationException returns 422 with field details."""
    res = client.post("/api/v1/health/test-error", json={"error_type": "validation"})
    assert res.status_code == 422
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "field" in data["error"]["details"]


def test_pydantic_validation_error_handler(client):
    """Verify unhandled Pydantic validation errors conform to unified error schema."""
    # Sending missing required field 'error_type'
    res = client.post("/api/v1/health/test-error", json={})
    assert res.status_code == 422
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "validation_errors" in data["error"]["details"]
    assert len(data["error"]["details"]["validation_errors"]) > 0


def test_unhandled_500_error_handler(client):
    """Verify uncaught exceptions are caught by global 500 handler."""
    res = client.post("/api/v1/health/test-error", json={"error_type": "internal"})
    assert res.status_code == 500
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"


def test_e164_phone_normalization():
    """Verify phone normalization handles various Vietnamese formats."""
    assert normalize_phone_e164("0912345678") == "+84912345678"
    assert normalize_phone_e164("84912345678") == "+84912345678"
    assert normalize_phone_e164("+84912345678") == "+84912345678"
    assert normalize_phone_e164("091 234 5678") == "+84912345678"
    assert normalize_phone_e164("098-765-4321") == "+84987654321"


def test_semantic_id_generation():
    """Verify semantic IDs are uniquely generated with correct prefixes."""
    uid = generate_semantic_id("usr")
    assert uid.startswith("usr_")
    assert len(uid) == 16

    gid = generate_semantic_id("grp")
    assert gid.startswith("grp_")

    cid = generate_semantic_id("cam")
    assert cid.startswith("cam_")

    aid = generate_semantic_id("alt")
    assert aid.startswith("alt_")


def test_base_repository_instantiation():
    """Verify BaseFirestoreRepository initializes and connects to client."""
    repo = BaseFirestoreRepository()
    assert repo.db is not None
