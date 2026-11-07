"""
Firebase Cloud Messaging (FCM) Service for Mắt Phố
Point 12: Standardized 5 FCM Data Message types with High Priority
Overrides phone silence on Flutter clients using loud_when_silent.
"""

import logging
from typing import List, Dict, Optional
import firebase_admin
from firebase_admin import messaging

logger = logging.getLogger("backend.services.fcm_service")


class FCMService:
    """Manages high-priority multicast FCM push notifications for alarms and system events."""

    def send_data_message(
        self,
        fcm_tokens: List[str],
        data: Dict[str, str],
        priority: str = "high",
        title: Optional[str] = None,
        body: Optional[str] = None,
    ) -> int:
        """
        Sends FCM Message (data payload + optional visible notification) to wake up
        background/killed Flutter App and play alarm-stream ringtone (loud_when_silent).
        Configures APNs and Android notification channels for background delivery.
        """
        if not fcm_tokens:
            return 0

        # Ensure all values in data are strings for FCM spec compatibility
        sanitized_data = {str(k): str(v) for k, v in data.items()}
        is_fire = "FIRE" in sanitized_data.get("type", "")

        if is_fire:
            # Android Pure Data Message: Plays loud alarm channel
            sanitized_data["channel_id"] = "fire_alarms"
            notification = messaging.Notification(title=title, body=body) if (title and body) else None
            android_notification = messaging.AndroidNotification(
                title=title,
                body=body,
                sound="default",
                channel_id="fire_alarms",
                priority="max",
            ) if (title and body) else None
            aps_alert = messaging.ApsAlert(title=title, body=body) if (title and body) else None
            aps_sound = "alarm.caf"
        else:
            notification = messaging.Notification(title=title, body=body) if (title and body) else None
            android_notification = messaging.AndroidNotification(
                title=title,
                body=body,
                sound="default",
                channel_id="matpho_general",
            ) if (title and body) else None
            aps_alert = messaging.ApsAlert(title=title, body=body) if (title and body) else None
            aps_sound = "default"

        message = messaging.MulticastMessage(
            data=sanitized_data,
            tokens=fcm_tokens,
            notification=notification,
            android=messaging.AndroidConfig(
                priority="high",
                ttl=3600,
                notification=android_notification,
            ),
            apns=messaging.APNSConfig(
                headers={"apns-priority": "10"},
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=aps_alert,
                        sound=aps_sound,
                        content_available=True,
                    )
                ),
            ),
        )

        try:
            response = messaging.send_each_for_multicast(message)
            logger.info(
                f"Dispatched FCM Data Message (type={sanitized_data.get('type')}) "
                f"to {len(fcm_tokens)} devices: success={response.success_count}, failure={response.failure_count}"
            )
            return response.success_count
        except Exception as e:
            logger.error(f"FCM multicast dispatch failed: {e}")
            return 0

    # 1. FIRE_ALERT (Level 0 / Level 1)
    def send_fire_alert_push(
        self,
        fcm_tokens: List[str],
        alert_id: str,
        escalation_level: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        emergency_token: Optional[str] = None,
    ) -> int:
        """Dispatches critical siren FCM push."""
        if not emergency_token:
            from ..core.security import generate_emergency_token
            emergency_token = generate_emergency_token(alert_id)

        data = {
            "type": "FIRE_ALERT",
            "alert_id": alert_id,
            "escalation_level": str(escalation_level),
            "emergency_token": emergency_token,
            "urgency": "HIGH" if escalation_level > 0 else "NORMAL",
            "loud_when_silent": "true" if escalation_level > 0 else "false",
            "action_call": "tel:114",
            "action_view": f"/alert/{alert_id}?emergency_token={emergency_token}",
        }
        notif_title = title or ("BÁO ĐỘNG CHÁY CẤP 2 (KHẨN CẤP)" if escalation_level > 0 else "CẢNH BÁO CHÁY CẤP 1 (XÁC MINH)")
        notif_body = body or "Phát hiện dấu hiệu lửa/khói tại cơ sở! Nhấn để kiểm tra ngay."
        return self.send_data_message(fcm_tokens, data, title=notif_title, body=notif_body)

    # 2. FIRE_ALERT_UPDATED
    def send_fire_alert_updated_push(
        self,
        fcm_tokens: List[str],
        alert_id: str,
        status: str,
        resolved_by_name: Optional[str] = None,
        title: Optional[str] = None,
        body: Optional[str] = None,
    ) -> int:
        """Notifies members when fire incident is resolved or marked false alarm."""
        data = {
            "type": "FIRE_ALERT_UPDATED",
            "alert_id": alert_id,
            "status": status,
            "resolved_by_name": resolved_by_name or "",
        }
        status_text = "Đã dập tắt / xử lý xong" if status == "RESOLVED" else "Xác nhận báo nhầm"
        notif_title = title or "Cập nhật sự cố cháy"
        notif_body = body or f"Sự cố {alert_id} đã được cập nhật: {status_text} (bởi {resolved_by_name or 'Người dùng'})."
        return self.send_data_message(fcm_tokens, data, title=notif_title, body=notif_body)

    # 3. TEST_ALERT
    def send_test_alert_push(
        self,
        fcm_token: str,
        test_id: str,
        title: Optional[str] = "Thử nghiệm còi báo cháy",
        body: Optional[str] = "Đây là thông báo kiểm tra hệ thống cảnh báo Mắt Phố.",
    ) -> int:
        """Tests speaker and loud siren on physical phone (Screen H4)."""
        data = {
            "type": "TEST_ALERT",
            "test_id": test_id,
        }
        return self.send_data_message([fcm_token], data, title=title, body=body)

    # 4. INVITATION
    def send_invitation_push(
        self,
        fcm_tokens: List[str],
        group_id: str,
        invitation_id: str,
        title: Optional[str] = "Lời mời gia nhập cơ sở",
        body: Optional[str] = "Bạn vừa nhận được một lời mời tham gia nhóm giám sát cơ sở mới.",
    ) -> int:
        """Notifies user of incoming group invitation."""
        data = {
            "type": "INVITATION",
            "group_id": group_id,
            "invitation_id": invitation_id,
        }
        return self.send_data_message(fcm_tokens, data, title=title, body=body)

    # 5. ROLE_CHANGED
    def send_role_changed_push(
        self,
        fcm_tokens: List[str],
        group_id: str,
        title: Optional[str] = "Cập nhật quyền hạn nhóm",
        body: Optional[str] = "Vai trò hoặc phân quyền camera của bạn trong nhóm đã được thay đổi.",
    ) -> int:
        """Notifies member of role or camera permission update."""
        data = {
            "type": "ROLE_CHANGED",
            "group_id": group_id,
        }
        return self.send_data_message(fcm_tokens, data, title=title, body=body)

    # 6. CAMERA_OFFLINE
    def send_camera_offline_push(
        self,
        fcm_tokens: List[str],
        cam_id: str,
        title: Optional[str] = "Cảnh báo Camera mất kết nối",
        body: Optional[str] = None,
    ) -> int:
        """Notifies managers when camera loses signal (Screen I8)."""
        data = {
            "type": "CAMERA_OFFLINE",
            "cam_id": cam_id,
        }
        notif_body = body or f"Camera {cam_id} đã bị mất kết nối tín hiệu mạng."
        return self.send_data_message(fcm_tokens, data, title=title, body=notif_body)


_fcm_service_instance: Optional[FCMService] = None


def get_fcm_service() -> FCMService:
    global _fcm_service_instance
    if _fcm_service_instance is None:
        _fcm_service_instance = FCMService()
    return _fcm_service_instance
