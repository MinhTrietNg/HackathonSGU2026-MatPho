"""
Alert Repository & Incident Aggregation Engine for Mắt Phố (Phase 6)
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from .base_repo import BaseRepository
from .camera_repo import get_camera_repository
from .user_repo import get_user_repository
from ...models.fire_alert import (
    FireAlertModel,
    StepTimelineModel,
    TimelineSnapshotModel,
)
from ...models.audit_log import AuditLogModel
from ...models.common import (
    AlertStatus,
    AlertVerification,
    SignType,
    AuditAction,
    generate_semantic_id,
)
from ...core.exceptions import NotFoundException
from ...core.formatters import current_utc_iso, format_iso_utc
from ..storage_service import get_storage_service


class AlertRepository(BaseRepository):
    COLLECTION_NAME = "fire_alerts"

    def __init__(self):
        super().__init__()
        self._camera_repo = None
        self._user_repo = None
        self._storage_service = None

    @property
    def camera_repo(self):
        if self._camera_repo is None:
            self._camera_repo = get_camera_repository()
        return self._camera_repo

    @property
    def user_repo(self):
        if self._user_repo is None:
            self._user_repo = get_user_repository()
        return self._user_repo

    @property
    def storage(self):
        if self._storage_service is None:
            self._storage_service = get_storage_service()
        return self._storage_service

    # =========================================================================
    # AUDIT LOGS
    # =========================================================================

    def create_audit_log(
        self,
        group_id: str,
        actor_id: str,
        action: AuditAction,
        target_entity: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditLogModel:
        log_id = generate_semantic_id("log")
        data = {
            "log_id": log_id,
            "group_id": group_id,
            "actor_id": actor_id,
            "action": action.value if hasattr(action, "value") else str(action),
            "target_entity": target_entity,
            "details": details or {},
            "created_at": datetime.now(timezone.utc),
        }
        firestore_payload = dict(data)
        firestore_payload["created_at"] = firestore.SERVER_TIMESTAMP
        self.db.collection("audit_logs").document(log_id).set(firestore_payload)
        if group_id and group_id != "system":
            try:
                self.set_document(f"groups/{group_id}/audit_logs", log_id, data)
            except Exception:
                pass
        return AuditLogModel(**data)

    def list_audit_logs_by_group(self, group_id: str, limit: int = 50) -> List[AuditLogModel]:
        try:
            stream = (
                self.db.collection("audit_logs")
                .where(filter=FieldFilter("group_id", "==", group_id))
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            logs = []
            for doc in stream:
                d = doc.to_dict()
                logs.append(AuditLogModel(**d))
            return logs
        except Exception:
            # Fallback in-memory
            stream = self.db.collection("audit_logs").where(filter=FieldFilter("group_id", "==", group_id)).stream()
            logs = [AuditLogModel(**d) for doc in stream for d in [doc.to_dict()]]
            logs.sort(key=lambda x: str(x.created_at) if x.created_at else "", reverse=True)
            return logs[:limit]

    def list_audit_logs_by_target(self, target_entity: str, limit: int = 50) -> List[AuditLogModel]:
        try:
            stream = (
                self.db.collection("audit_logs")
                .where(filter=FieldFilter("target_entity", "==", target_entity))
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            logs = []
            for doc in stream:
                d = doc.to_dict()
                logs.append(AuditLogModel(**d))
            return logs
        except Exception:
            # Fallback in-memory
            stream = self.db.collection("audit_logs").where(filter=FieldFilter("target_entity", "==", target_entity)).stream()
            logs = [AuditLogModel(**d) for doc in stream for d in [doc.to_dict()]]
            logs.sort(key=lambda x: str(x.created_at) if x.created_at else "", reverse=True)
            return logs[:limit]

    # =========================================================================
    # FIRE ALERTS & INCIDENT AGGREGATION ENGINE (90s Debounce)
    # =========================================================================

    def save_fire_incident(
        self,
        cam_id: str,
        class_name: str,
        confidence: float,
        bbox: List[float],
        image_data: Optional[str] = None,
    ) -> FireAlertModel:
        """
        AI Webhook ingestion with 90-second incident debouncing:
        1. Look up camera info.
        2. Check for active incident on this camera created in the last 90s.
        3. If found: append snapshot to timeline_snapshots (up to 60) and update steps.
        4. If not found: upload initial snapshot and create new fire_alerts document.
        """
        cam = self.camera_repo.get_camera(cam_id) if cam_id else None
        if not cam:
            raise NotFoundException(f"Không tìm thấy camera tương ứng ({cam_id}).", code="CAMERA_NOT_FOUND")

        group_id = cam.group_id
        subgroup_id = cam.subgroup_id
        subgroup_name = cam.subgroup_name

        now = datetime.now(timezone.utc)
        debounce_cutoff = now - timedelta(seconds=90)

        existing_alert_doc = None
        # Try ordered stream with fallback
        try:
            ordered_stream = (
                self.collection
                .where(filter=FieldFilter("cam_id", "==", cam_id))
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(10)
                .stream()
            )
            for doc in ordered_stream:
                d = doc.to_dict()
                if d.get("status") not in (AlertStatus.NEW.value, AlertStatus.CONFIRMED.value):
                    continue
                c_at = d.get("created_at")
                if not c_at:
                    continue
                if isinstance(c_at, str):
                    try:
                        c_at = datetime.fromisoformat(c_at.replace("Z", "+00:00"))
                    except Exception:
                        continue
                if c_at >= debounce_cutoff:
                    existing_alert_doc = doc
                    break
        except Exception:
            fallback_stream = self.collection.where(filter=FieldFilter("cam_id", "==", cam_id)).stream()
            for doc in fallback_stream:
                d = doc.to_dict()
                if d.get("status") not in (AlertStatus.NEW.value, AlertStatus.CONFIRMED.value):
                    continue
                c_at = d.get("created_at")
                if not c_at:
                    continue
                if isinstance(c_at, str):
                    try:
                        c_at = datetime.fromisoformat(c_at.replace("Z", "+00:00"))
                    except Exception:
                        continue
                if c_at >= debounce_cutoff:
                    existing_alert_doc = doc
                    break

        if existing_alert_doc:
            # Aggregate into existing incident
            alert_id = existing_alert_doc.id
            alert_dict = existing_alert_doc.to_dict()

            timeline_snapshots = alert_dict.get("timeline_snapshots", [])
            if len(timeline_snapshots) < 60 and image_data:
                snap_id = f"snap_{int(now.timestamp())}"
                _, download_url = self.storage.upload_fire_snapshot(
                    group_id=group_id,
                    cam_id=cam_id,
                    alert_id=alert_id,
                    image_data=image_data,
                    filename=f"timeline/{snap_id}.jpg",
                )
                new_snapshot = {
                    "snapshot_id": snap_id,
                    "image_url": download_url,
                    "confidence": confidence,
                    "timestamp": current_utc_iso(),
                    "bbox": bbox,
                }
                timeline_snapshots.append(new_snapshot)

                self.collection.document(alert_id).update({
                    "timeline_snapshots": timeline_snapshots,
                    "confidence": max(alert_dict.get("confidence", 0.0), confidence),
                    "updated_at": datetime.now(timezone.utc),
                })
                alert_dict["timeline_snapshots"] = timeline_snapshots
                alert_dict["confidence"] = max(alert_dict.get("confidence", 0.0), confidence)

            return self._parse_alert(alert_dict)

        # Create New Incident
        alert_id = generate_semantic_id("alt")
        fire_image_url = ""
        if image_data:
            _, fire_image_url = self.storage.upload_fire_snapshot(
                group_id=group_id,
                cam_id=cam_id,
                alert_id=alert_id,
                image_data=image_data,
                filename="initial_detected.jpg",
            )
        else:
            fire_image_url = f"https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/fire_alerts%2F{group_id}%2F{cam_id}%2F{alert_id}%2Finitial_detected.jpg?alt=media"

        steps = [
            StepTimelineModel(kind="DETECTED", at=current_utc_iso(), label="Camera phát hiện dấu hiệu ngọn lửa"),
            StepTimelineModel(kind="IMAGE_SENT", at=current_utc_iso(), label="FireWatch gửi snapshot về FastAPI Gateway"),
            StepTimelineModel(kind="AI_VERIFIED", at=current_utc_iso(), label=f"Mô hình ONNX & VotingEngine xác nhận độ tin cậy {int(confidence*100)}%"),
            StepTimelineModel(kind="ALERT_TRIGGERED", at=current_utc_iso(), label="Kích hoạt còi hú cấp 1 tới Leader & Member Manager"),
        ]

        initial_snapshot = TimelineSnapshotModel(
            snapshot_id=f"snap_{int(now.timestamp())}",
            image_url=fire_image_url,
            confidence=confidence,
            timestamp=current_utc_iso(),
            bbox=bbox,
        )

        alert_data = {
            "alert_id": alert_id,
            "group_id": group_id,
            "subgroup_id": subgroup_id,
            "subgroup_name": subgroup_name,
            "location_name": subgroup_name,
            "cam_id": cam_id,
            "cam_name": cam.cam_name,
            "summary": f"Phát hiện dấu hiệu {class_name} tại {subgroup_name}",
            "detail": f"Mô hình YOLO26n ONNX phát hiện {class_name} với độ tin cậy {confidence:.2f}.",
            "call_script": f"Cháy tại {subgroup_name}, cơ sở {cam.cam_name}",
            "sign": SignType.BOTH.value if class_name == "both" else (SignType.SMOKE.value if class_name == "smoke" else SignType.FIRE.value),
            "check_count": 2,
            "fire_image_url": fire_image_url,
            "still_url": fire_image_url,
            "confidence": confidence,
            "status": AlertStatus.NEW.value,
            "verification": AlertVerification.VERIFIED.value,
            "steps": [s.model_dump() for s in steps],
            "timeline_snapshots": [initial_snapshot.model_dump()],
            "called_114_at": None,
            "escalation_level": 0,
            "next_escalation_at": None,
            "resolved_by": None,
            "resolved_at": None,
            "resolution_note": None,
            "detected_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        firestore_payload = dict(alert_data)
        firestore_payload["detected_at"] = firestore.SERVER_TIMESTAMP
        firestore_payload["created_at"] = firestore.SERVER_TIMESTAMP
        firestore_payload["updated_at"] = firestore.SERVER_TIMESTAMP
        self.collection.document(alert_id).set(firestore_payload)

        self.create_audit_log(
            group_id=group_id,
            actor_id="system_ai_firewatch",
            action=AuditAction.ALERT_TRIGGERED,
            target_entity=f"alert:{alert_id}",
            details={"cam_id": cam_id, "confidence": confidence, "sign": class_name},
        )

        return self._parse_alert(alert_data)

    def resolve_fire_incident(self, alert_id: str, resolved_by: str, resolution_note: Optional[str] = None) -> bool:
        alert_ref = self.collection.document(alert_id)
        doc = alert_ref.get()
        if not doc.exists:
            return False

        alert_dict = doc.to_dict()
        steps = alert_dict.get("steps", [])
        steps.append({
            "kind": "RESOLVED",
            "at": current_utc_iso(),
            "label": f"Đã xử lý sự cố an toàn ({resolution_note or 'Đã dập tắt'})",
        })

        user = self.user_repo.get_user_by_id(resolved_by) if resolved_by.startswith("usr_") else None
        resolved_by_name = user.full_name if user else resolved_by

        alert_ref.update({
            "status": AlertStatus.RESOLVED.value,
            "resolved_by": resolved_by,
            "resolved_by_name": resolved_by_name,
            "resolved_at": firestore.SERVER_TIMESTAMP,
            "resolution_note": resolution_note,
            "steps": steps,
            "updated_at": datetime.now(timezone.utc),
        })

        self.create_audit_log(
            group_id=alert_dict.get("group_id", "system"),
            actor_id=resolved_by,
            action=AuditAction.ALERT_RESOLVED,
            target_entity=f"alert:{alert_id}",
            details={"resolution_note": resolution_note},
        )
        return True

    def mark_false_alarm_incident(self, alert_id: str, actor_id: str) -> bool:
        alert_ref = self.collection.document(alert_id)
        doc = alert_ref.get()
        if not doc.exists:
            return False

        alert_dict = doc.to_dict()
        steps = alert_dict.get("steps", [])
        steps.append({
            "kind": "FALSE_ALARM",
            "at": current_utc_iso(),
            "label": "Đánh dấu báo nhầm (False Alarm)",
        })

        alert_ref.update({
            "status": AlertStatus.FALSE_ALARM.value,
            "verification": AlertVerification.CONFIRMED_NOT_FIRE.value if hasattr(AlertVerification, "CONFIRMED_NOT_FIRE") else "CONFIRMED_NOT_FIRE",
            "steps": steps,
            "updated_at": datetime.now(timezone.utc),
        })

        self.create_audit_log(
            group_id=alert_dict.get("group_id", "system"),
            actor_id=actor_id,
            action=AuditAction.ALERT_FALSE_ALARM,
            target_entity=f"alert:{alert_id}",
            details={"action": "mark_false_alarm"},
        )
        return True

    def call_114_incident(self, alert_id: str, caller_id: str) -> bool:
        alert_ref = self.collection.document(alert_id)
        doc = alert_ref.get()
        if not doc.exists:
            return False

        alert_dict = doc.to_dict()
        steps = alert_dict.get("steps", [])
        steps.append({
            "kind": "CALLED_114",
            "at": current_utc_iso(),
            "label": "Người trực bấm Gọi 114 xác nhận cháy",
        })

        alert_ref.update({
            "status": AlertStatus.CONFIRMED.value,
            "called_114_at": firestore.SERVER_TIMESTAMP,
            "escalation_level": 1,
            "steps": steps,
            "updated_at": datetime.now(timezone.utc),
        })

        self.create_audit_log(
            group_id=alert_dict.get("group_id", "system"),
            actor_id=caller_id,
            action=AuditAction.CALL_114_INITIATED,
            target_entity=f"alert:{alert_id}",
            details={"action": "call_114"},
        )
        return True

    def confirm_fire_incident(self, alert_id: str, actor_id: str) -> bool:
        alert_ref = self.collection.document(alert_id)
        doc = alert_ref.get()
        if not doc.exists:
            return False

        alert_dict = doc.to_dict()
        steps = alert_dict.get("steps", [])
        steps.append({
            "kind": "CONFIRMED",
            "at": current_utc_iso(),
            "label": "Người trực bấm xác nhận cháy",
        })

        alert_ref.update({
            "status": AlertStatus.CONFIRMED.value,
            "escalation_level": 1,
            "steps": steps,
            "updated_at": datetime.now(timezone.utc),
        })

        self.create_audit_log(
            group_id=alert_dict.get("group_id", "system"),
            actor_id=actor_id,
            action=AuditAction.ALERT_TRIGGERED,
            target_entity=f"alert:{alert_id}",
            details={"action": "confirmed_fire"},
        )
        return True

    def report_real_fire(self, alert_id: str, actor_id: str) -> bool:
        alert_ref = self.collection.document(alert_id)
        doc = alert_ref.get()
        if not doc.exists:
            return False

        alert_dict = doc.to_dict()
        steps = alert_dict.get("steps", [])
        steps.append({
            "kind": "CONFIRMED",
            "at": current_utc_iso(),
            "label": "Người dùng báo lại: Thật ra là cháy",
        })

        alert_ref.update({
            "status": AlertStatus.CONFIRMED.value,
            "verification": AlertVerification.VERIFIED.value,
            "escalation_level": 1,
            "steps": steps,
            "updated_at": datetime.now(timezone.utc),
        })

        self.create_audit_log(
            group_id=alert_dict.get("group_id", "system"),
            actor_id=actor_id,
            action=AuditAction.ALERT_TRIGGERED,
            target_entity=f"alert:{alert_id}",
            details={"action": "reported_real_fire"},
        )
        return True

    def dismiss_suspect(self, cam_id: str, actor_id: str) -> bool:
        cam = self.camera_repo.get_camera(cam_id)
        if not cam:
            return False

        self.create_audit_log(
            group_id=cam.group_id,
            actor_id=actor_id,
            action=AuditAction.CAMERA_UPDATED,
            target_entity=f"camera:{cam_id}",
            details={"action": "dismiss_suspect"},
        )
        return True

    def get_alert(self, alert_id: str) -> Optional[FireAlertModel]:
        doc = self.collection.document(alert_id).get()
        if not doc.exists:
            return None
        return self._parse_alert(doc.to_dict())

    def list_alerts_by_group(self, group_id: str, limit: int = 50) -> List[FireAlertModel]:
        try:
            query = self.collection.where(filter=FieldFilter("group_id", "==", group_id))
            results = []
            for doc in query.stream():
                results.append(self._parse_alert(doc.to_dict()))
            results.sort(
                key=lambda x: str(x.created_at) if x.created_at else "",
                reverse=True,
            )
            return results[:limit]
        except Exception:
            return []

    def _parse_alert(self, data: Dict[str, Any]) -> FireAlertModel:
        # Backward compatibility for legacy alert documents
        if "sign" in data and isinstance(data["sign"], str):
            if data["sign"] not in [e.value for e in SignType]:
                data["sign"] = SignType.BOTH.value
        if "status" in data and isinstance(data["status"], str):
            if data["status"] not in [e.value for e in AlertStatus]:
                data["status"] = AlertStatus.NEW.value
        if "verification" in data and isinstance(data["verification"], str):
            if data["verification"] not in [e.value for e in AlertVerification]:
                data["verification"] = AlertVerification.VERIFIED.value
        if "location_name" not in data or not data["location_name"]:
            data["location_name"] = data.get("subgroup_name", "Khu vực chung")
        if "summary" not in data or not data["summary"]:
            data["summary"] = "Phát hiện cảnh báo"
        return FireAlertModel(**data)


_alert_repository_instance: Optional[AlertRepository] = None


def get_alert_repository() -> AlertRepository:
    global _alert_repository_instance
    if _alert_repository_instance is None:
        _alert_repository_instance = AlertRepository()
    return _alert_repository_instance
