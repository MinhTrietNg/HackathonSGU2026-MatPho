"""
Phase 5 Test Suite: WebSocket Realtime Hub, Two-Tier Isolation & FCM Push Infrastructure
"""

import time
import json
import base64
import pytest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient

from src.main import app
from src.services.repositories.user_repo import get_user_repo
from src.services.repositories.group_repo import get_group_repo
from src.services.repositories.camera_repo import get_camera_repo
from src.services.websocket_manager import get_websocket_manager
from src.services.fcm_service import get_fcm_service
from src.models.common import UserRole


def _register_user(client, phone: str, name: str) -> dict:
    req = client.post(
        "/api/v1/auth/register/request-otp",
        json={"phone_number": phone, "full_name": name, "password": "Password123@"},
    )
    assert req.status_code == 200
    ch_id = req.json()["challenge_id"]
    ver = client.post(
        "/api/v1/auth/verify-otp",
        json={"challenge_id": ch_id, "code": "123456"},
    )
    assert ver.status_code == 200
    data = ver.json()
    token = data["custom_token"]
    user_id = data["user"]["user_id"]
    return {
        "user_id": user_id,
        "token": token,
        "phone": phone,
        "name": name,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def test_websocket_unauthorized_rejection(client):
    """Test connecting to WebSocket without token or invalid token is rejected."""
    with pytest.raises(Exception):
        with client.websocket_connect("/ws") as ws:
            pass


def test_websocket_connection_and_handshake(client):
    """Test connecting with valid token receives CONNECTED event and joins rooms."""
    ts = int(time.time() * 1000) % 10000000
    leader = _register_user(client, f"091{ts:07d}", "Trưởng Ban WS Handshake")

    # 1. Create a group
    res_grp = client.post(
        "/api/v1/groups",
        json={"name": "Khu Phố Realtime", "address": "Hai Bà Trưng", "my_nickname": "Trưởng Ban"},
        headers=leader["headers"],
    )
    group_id = res_grp.json()["group_id"]

    # 2. Connect to WebSocket
    with client.websocket_connect(f"/ws?token={leader['user_id']}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "CONNECTED"
        assert msg["user_id"] == leader["user_id"]
        assert f"group_{group_id}" in msg["rooms"]
        assert f"group_{group_id}_leaders" in msg["rooms"]


def test_websocket_custom_token_jwt_connection(client):
    """Test connecting with Firebase Custom Token format (eyJ...) via query and header."""
    ts = int(time.time() * 1000) % 10000000
    user = _register_user(client, f"092{ts:07d}", "User JWT WS")
    user_id = user["user_id"]

    header_b64 = base64.urlsafe_b64encode(b'{"alg":"RS256","typ":"JWT"}').decode("utf-8").rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps({"uid": user_id, "sub": user_id}).encode("utf-8")).decode("utf-8").rstrip("=")
    fake_jwt = f"{header_b64}.{payload_b64}.fake_sig"

    # 1. Connect via query param
    with client.websocket_connect(f"/api/v1/ws?token={fake_jwt}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "CONNECTED"
        assert msg["user_id"] == user_id

    # 2. Connect via Authorization header
    with client.websocket_connect("/ws", headers={"Authorization": f"Bearer {fake_jwt}"}) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "CONNECTED"
        assert msg["user_id"] == user_id


def test_websocket_ping_pong_and_ack(client):
    """Test WebSocket ping/pong and client acknowledgement."""
    ts = int(time.time() * 1000) % 10000000
    user = _register_user(client, f"093{ts:07d}", "Ping Pong User")

    with client.websocket_connect(f"/ws?token={user['user_id']}") as ws:
        # Handshake
        handshake = ws.receive_json()
        assert handshake["type"] == "CONNECTED"

        # Client sends plain text ping
        ws.send_text("ping")
        resp = ws.receive_json()
        assert resp["type"] == "pong"
        assert "timestamp" in resp

        # Client sends json ping
        ws.send_json({"type": "ping"})
        resp2 = ws.receive_json()
        assert resp2["type"] == "pong"

        # Client sends ack
        ws.send_json({"type": "ack", "alert_id": "alt_test_123"})
        resp3 = ws.receive_json()
        assert resp3["type"] == "ack_ok"
        assert resp3["alert_id"] == "alt_test_123"


def test_websocket_two_tier_broadcasting(client):
    """
    Test Two-Tier Isolation over WebSocket:
    - Tier 0 broadcast -> ONLY Leader/Manager receives it.
    - Tier 1 broadcast -> ALL members receive it.
    """
    ts = int(time.time() * 1000) % 10000000
    leader = _register_user(client, f"094{ts:07d}", "Leader Tier")
    member = _register_user(client, f"095{ts:07d}", "Member Tier")

    # 1. Leader creates group
    res_grp = client.post(
        "/api/v1/groups",
        json={"name": "Khu Phố Hai Tầng", "address": "Đống Đa", "my_nickname": "Trưởng Nhóm"},
        headers=leader["headers"],
    )
    group_id = res_grp.json()["group_id"]

    # 2. Invite member and accept
    inv = client.post(
        f"/api/v1/groups/{group_id}/invitations",
        json={"phone_number": member["phone"], "role": "MEMBER", "nickname": "Thành Viên 1"},
        headers=leader["headers"],
    ).json()
    client.post(f"/api/v1/invitations/{inv['invitation_id']}/accept", headers=member["headers"])

    ws_manager = get_websocket_manager()

    with client.websocket_connect(f"/ws?token={leader['user_id']}") as ws_leader:
        with client.websocket_connect(f"/ws?token={member['user_id']}") as ws_member:
            # Drain handshakes
            h_leader = ws_leader.receive_json()
            h_member = ws_member.receive_json()
            assert f"group_{group_id}_leaders" in h_leader["rooms"]
            assert f"group_{group_id}_leaders" not in h_member["rooms"]

            # Broadcast Tier 0 (Level 0: Leaders only)
            import asyncio
            asyncio.run(ws_manager.broadcast_fire_alert(
                group_id=group_id,
                alert_payload={"alert_id": "alt_001", "cam_id": "cam_01", "confidence": 0.9},
                escalation_level=0,
            ))

            # Leader receives Tier 0
            leader_msg = ws_leader.receive_json()
            assert leader_msg["type"] == "FIRE_ALERT"
            assert leader_msg["escalation_level"] == 0

            # Member does NOT receive Tier 0 (verify channel is clean with ping)
            ws_member.send_text("ping")
            pong = ws_member.receive_json()
            assert pong["type"] == "pong"

            # Broadcast Tier 1 (Level 1: Entire Group)
            asyncio.run(ws_manager.broadcast_fire_alert(
                group_id=group_id,
                alert_payload={"alert_id": "alt_001", "cam_id": "cam_01", "confidence": 0.95},
                escalation_level=1,
            ))

            # Both Leader and Member receive Tier 1
            l_t1 = ws_leader.receive_json()
            m_t1 = ws_member.receive_json()
            assert l_t1["type"] == "FIRE_ALERT"
            assert l_t1["escalation_level"] == 1
            assert m_t1["type"] == "FIRE_ALERT"
            assert m_t1["escalation_level"] == 1


def test_fcm_data_message_standard_payloads():
    """Verify FCM Service constructs and formats all 5 standard data message types."""
    fcm = get_fcm_service()

    with patch("firebase_admin.messaging.send_each_for_multicast") as mock_send:
        mock_resp = MagicMock()
        mock_resp.success_count = 2
        mock_resp.failure_count = 0
        mock_send.return_value = mock_resp

        # 1. FIRE_ALERT Tier 0 & 1
        res1 = fcm.send_fire_alert_push(["tok_1", "tok_2"], "alt_123", escalation_level=0)
        assert res1 == 2
        args1, _ = mock_send.call_args
        msg1 = args1[0]
        assert msg1.data["type"] == "FIRE_ALERT"
        assert msg1.data["alert_id"] == "alt_123"
        assert msg1.data["escalation_level"] == "0"
        assert msg1.android.priority == "high"
        assert msg1.apns.payload.aps.content_available is True

        # 2. FIRE_ALERT_UPDATED
        res2 = fcm.send_fire_alert_updated_push(["tok_1"], "alt_123", "RESOLVED", "Bảo vệ A")
        assert res2 == 2
        args2, _ = mock_send.call_args
        msg2 = args2[0]
        assert msg2.data["type"] == "FIRE_ALERT_UPDATED"
        assert msg2.data["status"] == "RESOLVED"
        assert msg2.data["resolved_by_name"] == "Bảo vệ A"

        # 3. TEST_ALERT
        res3 = fcm.send_test_alert_push("tok_1", "test_abc")
        assert res3 == 2
        args3, _ = mock_send.call_args
        assert args3[0].data["type"] == "TEST_ALERT"

        # 4. INVITATION
        res4 = fcm.send_invitation_push(["tok_1"], "grp_xyz", "inv_123")
        assert res4 == 2
        args4, _ = mock_send.call_args
        assert args4[0].data["type"] == "INVITATION"

        # 5. CAMERA_OFFLINE
        res5 = fcm.send_camera_offline_push(["tok_1"], "cam_456")
        assert res5 == 2
        args5, _ = mock_send.call_args
        assert args5[0].data["type"] == "CAMERA_OFFLINE"


def test_fcm_token_registration_and_settings(client):
    """Test device FCM token registration, loud_when_silent setting and test-alert endpoint."""
    ts = int(time.time() * 1000) % 10000000
    user = _register_user(client, f"096{ts:07d}", "Device FCM User")
    token_headers = user["headers"]
    user_id = user["user_id"]

    # 1. Register FCM Device Token
    r1 = client.post(
        "/api/v1/users/me/fcm-tokens",
        json={"fcm_token": "fcm_device_token_phone_15_pro"},
        headers=token_headers,
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "success"

    repo = get_user_repo()
    u = repo.get_user_by_id(user_id)
    assert "fcm_device_token_phone_15_pro" in u.fcm_tokens

    # 2. Update loud_when_silent setting
    r2 = client.patch(
        "/api/v1/users/me/settings",
        json={"loud_when_silent": True},
        headers=token_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["loud_when_silent"] is True

    # 3. Trigger Test Alert (Screen H4)
    with patch("src.services.fcm_service.FCMService.send_test_alert_push") as mock_push:
        mock_push.return_value = 1
        r3 = client.post(
            "/api/v1/settings/test-alert",
            json={},
            headers=token_headers,
        )
        assert r3.status_code == 200
        assert r3.json()["status"] == "dispatched"
        assert "sent_at" in r3.json()
        mock_push.assert_called_once()
        args, _ = mock_push.call_args
        assert args[0] == "fcm_device_token_phone_15_pro"


def test_edge_websocket_channel(client):
    """Test dedicated internal WebSocket channel for On-Premise Edge nodes."""
    secret = "secure_internal_key_for_ai_and_worker_communication"

    # 1. Invalid secret is rejected
    with pytest.raises(Exception):
        with client.websocket_connect("/internal/edge/ws?secret=wrong_key") as ws:
            pass

    # 2. Valid secret connects and gets ack
    with client.websocket_connect(f"/internal/edge/ws?edge_id=edg_lan_01&secret={secret}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "EDGE_CONNECTED_ACK"
        assert msg["edge_device_id"] == "edg_lan_01"

        # Edge sends camera heartbeat
        ws.send_json({"type": "CAMERA_STATUS", "cam_id": "cam_edge_01", "status": "ONLINE", "fps": 25})

        # Ping
        ws.send_text("ping")
        pong = ws.receive_json()
        assert pong["type"] == "pong"
