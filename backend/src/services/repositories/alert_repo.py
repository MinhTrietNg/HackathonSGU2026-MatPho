"""
Alert Repository & Incident Aggregation Engine for Mắt Phố (Phase 6)
"""

from typing import Optional, List, Dict, Any, Tuple
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
    AIFireEventPayload,
    AISnapshotUploadPayload,
    AIEventBoxModel,
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
from ..incident_rules import chon_su_co_dang_mo, cung_event, tai_bung


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
    # FIRE ALERTS & INCIDENT AGGREGATION ENGINE (Two-Phase: Signal + 1 Snapshot)
    # =========================================================================

    def _tim_su_co_dang_mo(self, cam_id: str, event_id: Optional[str], now: datetime):
        """
        Find the alert document to merge a new fire signal into (see services/incident_rules).
        Candidates: alt_{event_id}, alerts carrying event_id (field or alias list), and the
        latest alerts of the camera. Returns a Firestore snapshot or None.
        """
        snaps: Dict[str, Any] = {}

        def them(doc) -> None:
            if doc is not None and getattr(doc, "exists", True) and doc.id not in snaps:
                snaps[doc.id] = doc

        if event_id:
            try:
                them(self.collection.document(f"alt_{event_id}").get())
            except Exception:
                pass
            for field, op in (("event_id", "=="), ("event_ids", "array_contains")):
                try:
                    for doc in self.collection.where(filter=FieldFilter(field, op, event_id)).limit(1).stream():
                        them(doc)
                except Exception:
                    pass
        try:
            stream = (
                self.collection
                .where(filter=FieldFilter("cam_id", "==", cam_id))
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(5)
                .stream()
            )
            for doc in stream:
                them(doc)
        except Exception:
            try:
                for doc in self.collection.where(filter=FieldFilter("cam_id", "==", cam_id)).stream():
                    them(doc)
            except Exception:
                pass

        docs = []
        for doc_id, snap in snaps.items():
            d = snap.to_dict() or {}
            d["alert_id"] = doc_id
            docs.append(d)
        chon = chon_su_co_dang_mo(docs, event_id=event_id, cam_id=cam_id, now=now)
        return snaps[chon["alert_id"]] if chon else None

    def upsert_fire_incident_signal(
        self,
        payload: AIFireEventPayload,
    ) -> Tuple[FireAlertModel, bool, Dict[str, Any]]:
        """
        Fast Phase 1 ingestion (<30ms, no snapshot upload waiting):
        1. Look up camera info.
        2. Format boxes (xyxy, xyxyn, cls, conf), compute primary_bbox, sign, max_conf.
        3. Upsert into the camera's open incident (incident_rules.chon_su_co_dang_mo):
           - If existing: update fields, status, verification, vlm, verifier.
             Returns (alert, False, ghep) with ghep["tai_bung"] True when a ``created``
             carrying a new event_id was merged (fire flared up again on the same alert).
           - If new: create alert with snapshot_status="PENDING". Returns (alert, True, ghep).
        """
        cam_id = payload.cam_id or payload.camera_id
        if not cam_id or str(cam_id).strip().lower() in ("null", "none", ""):
            raise NotFoundException("Mã camera (cam_id) không hợp lệ hoặc bị thiếu.", code="CAMERA_NOT_FOUND")

        cam = self.camera_repo.get_camera(cam_id)
        if not cam:
            raise NotFoundException(f"Không tìm thấy camera tương ứng ({cam_id}).", code="CAMERA_NOT_FOUND")

        group_id = cam.group_id
        subgroup_id = cam.subgroup_id
        subgroup_name = cam.subgroup_name

        now = datetime.now(timezone.utc)

        # 1. Parse Boxes & Coordinates
        formatted_boxes = []
        has_fire = False
        has_smoke = False
        max_conf = payload.confidence if payload.confidence is not None else 0.8
        primary_bbox = payload.bbox or []

        fw = payload.frame_w or 1920
        fh = payload.frame_h or 1080

        if payload.boxes:
            conf_candidates = []
            for b in payload.boxes:
                b_cls = str(b.cls).lower()
                if "fire" in b_cls:
                    has_fire = True
                if "smoke" in b_cls:
                    has_smoke = True
                conf_candidates.append(b.conf)

                # Compute normalized xyxyn if not provided
                xyxyn = list(b.xyxyn)
                if not xyxyn and len(b.xyxy) == 4 and fw > 0 and fh > 0:
                    xyxyn = [
                        round(b.xyxy[0] / fw, 4),
                        round(b.xyxy[1] / fh, 4),
                        round(b.xyxy[2] / fw, 4),
                        round(b.xyxy[3] / fh, 4),
                    ]

                formatted_boxes.append({
                    "cls": b_cls,
                    "conf": b.conf,
                    "xyxy": b.xyxy,
                    "xyxyn": xyxyn,
                })

            if conf_candidates:
                max_conf = max(conf_candidates)
            # Pick best box for primary_bbox
            best_b = max(payload.boxes, key=lambda x: x.conf)
            primary_bbox = best_b.xyxyn or best_b.xyxy
        else:
            cls_name = (payload.class_name or "fire").lower()
            if "fire" in cls_name:
                has_fire = True
            if "smoke" in cls_name:
                has_smoke = True

        if has_fire and has_smoke:
            sign = SignType.BOTH
        elif has_smoke:
            sign = SignType.SMOKE
        else:
            sign = SignType.FIRE

        # 2. VLM / Verifier description & verification status
        summary = f"Phát hiện dấu hiệu {sign.value} tại {subgroup_name}"
        detail = f"Hệ thống phát hiện {sign.value} với độ tin cậy {max_conf:.2f}."

        if payload.vlm and payload.vlm.description_vi:
            detail = payload.vlm.description_vi
            summary = payload.vlm.description_vi[:100]

        is_suppressed = (
            payload.verification == "SUPPRESSED"
            or (payload.verifier and payload.verifier.status == "REJECTED")
        )

        # 3. Locate the open incident of this camera (one open incident per camera):
        #    same event_id / alias, else the alert still NEW/CONFIRMED and active within
        #    INCIDENT_MERGE_WINDOW_S (services/incident_rules.py).
        event_id = payload.event_id
        existing_alert_doc = self._tim_su_co_dang_mo(cam_id, event_id, now)

        # 4. Handle Existing Alert (type == "updated" or repeat within debounce)
        if existing_alert_doc:
            alert_id = existing_alert_doc.id
            alert_dict = existing_alert_doc.to_dict()

            update_data: Dict[str, Any] = {
                "updated_at": datetime.now(timezone.utc),
                "last_seen_ts": payload.last_seen_ts or current_utc_iso(),
            }
            if payload.status:
                update_data["ai_status"] = payload.status
            if payload.severity:
                update_data["severity"] = payload.severity
            if formatted_boxes:
                update_data["boxes"] = formatted_boxes
                update_data["bbox"] = primary_bbox
            if max_conf > alert_dict.get("confidence", 0.0):
                update_data["confidence"] = max_conf
            if payload.luot_xac_minh:
                update_data["check_count"] = payload.luot_xac_minh
            if payload.vlm:
                update_data["vlm"] = payload.vlm.model_dump()
                if payload.vlm.description_vi:
                    update_data["detail"] = payload.vlm.description_vi
            if payload.verifier:
                update_data["verifier"] = payload.verifier.model_dump()
                update_data["needs_human_check"] = payload.verifier.needs_human_check

            if is_suppressed:
                update_data["status"] = AlertStatus.SUPPRESSED.value
                update_data["verification"] = AlertVerification.SUPPRESSED.value
            elif payload.verification == "VERIFIED":
                update_data["verification"] = AlertVerification.VERIFIED.value

            ghep = {"tai_bung": tai_bung(alert_dict, payload.type, event_id),
                    "event_id_moi": bool(event_id) and not cung_event(alert_dict, event_id)}
            if ghep["event_id_moi"]:
                update_data["event_ids"] = firestore.ArrayUnion([event_id])
                update_data["ai_status"] = payload.status or "open"
            self.collection.document(alert_id).update(update_data)
            if ghep["event_id_moi"]:
                update_data["event_ids"] = list(alert_dict.get("event_ids") or []) + [event_id]
            alert_dict.update(update_data)
            return self._parse_alert(alert_dict), False, ghep

        # 5. Handle New Alert (type == "created")
        alert_id = f"alt_{event_id}" if event_id else generate_semantic_id("alt")

        steps = [
            StepTimelineModel(kind="DETECTED", at=current_utc_iso(), label="Camera phát hiện dấu hiệu ngọn lửa"),
            StepTimelineModel(kind="IMAGE_SENT", at=current_utc_iso(), label="FireWatch gửi tín hiệu về FastAPI Gateway"),
            StepTimelineModel(kind="AI_VERIFIED", at=current_utc_iso(), label=f"Mô hình FireWatch xác nhận độ tin cậy {int(max_conf*100)}%"),
            StepTimelineModel(kind="ALERT_TRIGGERED", at=current_utc_iso(), label="Kích hoạt còi hú cấp 1 tới Leader & Member Manager"),
        ]

        alert_data = {
            "alert_id": alert_id,
            "event_id": event_id or alert_id,
            "event_ids": [event_id] if event_id else [],
            "group_id": group_id,
            "subgroup_id": subgroup_id,
            "subgroup_name": subgroup_name,
            "location_name": subgroup_name,
            "cam_id": cam_id,
            "cam_name": cam.cam_name,
            "summary": summary,
            "detail": detail,
            "call_script": f"Cháy tại {subgroup_name}, cơ sở {cam.cam_name}",
            "sign": sign.value,
            "check_count": payload.luot_xac_minh or 1,
            "fire_image_url": "",
            "still_url": "",
            "snapshot_status": "PENDING",
            "confidence": max_conf,
            "status": AlertStatus.SUPPRESSED.value if is_suppressed else AlertStatus.NEW.value,
            "verification": AlertVerification.SUPPRESSED.value if is_suppressed else (
                AlertVerification.VERIFIED.value if payload.verification == "VERIFIED" else AlertVerification.UNVERIFIED.value
            ),
            "ai_status": payload.status or "open",
            "severity": payload.severity or "WARNING",
            "fire_type": payload.fire_type,
            "started_at": payload.started_at or current_utc_iso(),
            "last_seen_ts": payload.last_seen_ts or current_utc_iso(),
            "frame_ts": payload.frame_ts or current_utc_iso(),
            "frame_w": fw,
            "frame_h": fh,
            "boxes": formatted_boxes,
            "bbox": primary_bbox,
            "vlm": payload.vlm.model_dump() if payload.vlm else None,
            "verifier": payload.verifier.model_dump() if payload.verifier else None,
            "steps": [s.model_dump() for s in steps],
            "timeline_snapshots": [],
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
            details={"cam_id": cam_id, "confidence": max_conf, "sign": sign.value, "event_id": event_id},
        )

        return self._parse_alert(alert_data), True, {"tai_bung": False, "event_id_moi": False}

    def attach_incident_snapshot(
        self,
        event_id: str,
        cam_id: Optional[str] = None,
        snapshot_base64: str = "",
        frame_ts: Optional[Any] = None,
        boxes: Optional[List[Any]] = None,
        frame_w: Optional[int] = 1920,
        frame_h: Optional[int] = 1080,
    ) -> Optional[FireAlertModel]:
        """
        Phase 2 background ingestion of history snapshot (1 single image per incident):
        1. Find alert by event_id (or alert_id).
        2. If alert already has snapshot_status == "READY" and fire_image_url != "", skip upload.
        3. Upload snapshot to Firebase Storage.
        4. Update Firestore with fire_image_url, still_url, snapshot_status="READY", and single snapshot in timeline_snapshots.
        """
        if not snapshot_base64:
            return None

        # Locate alert
        alert_doc = None
        # Try direct alt_{event_id} or event_id
        for candidate_id in (f"alt_{event_id}", event_id):
            try:
                doc = self.collection.document(candidate_id).get()
                if doc.exists:
                    alert_doc = doc
                    break
            except Exception:
                pass

        if not alert_doc:
            try:
                stream = self.collection.where(filter=FieldFilter("event_id", "==", event_id)).limit(1).stream()
                for doc in stream:
                    alert_doc = doc
                    break
            except Exception:
                pass

        if not alert_doc:
            return None

        alert_id = alert_doc.id
        alert_dict = alert_doc.to_dict()

        # If already ready, avoid redundant upload
        if alert_dict.get("snapshot_status") == "READY" and alert_dict.get("fire_image_url"):
            return self._parse_alert(alert_dict)

        group_id = alert_dict.get("group_id", "grp_default")
        alert_cam_id = alert_dict.get("cam_id") or cam_id or "cam_unknown"

        # Upload single history snapshot
        _, download_url = self.storage.upload_fire_snapshot(
            group_id=group_id,
            cam_id=alert_cam_id,
            alert_id=alert_id,
            image_data=snapshot_base64,
            filename="history_snapshot.jpg",
        )

        # Build single snapshot timeline entry
        current_boxes = boxes if boxes is not None else alert_dict.get("boxes", [])
        current_fw = frame_w or alert_dict.get("frame_w", 1920)
        current_fh = frame_h or alert_dict.get("frame_h", 1080)

        single_snapshot = [{
            "snapshot_id": f"snap_{alert_id}",
            "image_url": download_url,
            "confidence": alert_dict.get("confidence", 0.9),
            "timestamp": str(frame_ts or current_utc_iso()),
            "bbox": alert_dict.get("bbox", []),
            "boxes": current_boxes,
            "frame_w": current_fw,
            "frame_h": current_fh,
        }]

        update_payload: Dict[str, Any] = {
            "fire_image_url": download_url,
            "still_url": download_url,
            "snapshot_status": "READY",
            "timeline_snapshots": single_snapshot,
            "updated_at": datetime.now(timezone.utc),
        }
        if boxes:
            update_payload["boxes"] = boxes
        if frame_w:
            update_payload["frame_w"] = frame_w
        if frame_h:
            update_payload["frame_h"] = frame_h

        self.collection.document(alert_id).update(update_payload)
        alert_dict.update(update_payload)
        return self._parse_alert(alert_dict)

    def save_fire_incident(
        self,
        cam_id: str,
        class_name: str,
        confidence: float,
        bbox: List[float],
        image_data: Optional[str] = None,
    ) -> FireAlertModel:
        """Backward-compatible wrapper combining Phase 1 signal + Phase 2 snapshot upload."""
        payload = AIFireEventPayload(
            cam_id=cam_id,
            class_name=class_name,
            confidence=confidence,
            bbox=bbox,
            snapshot_base64=image_data,
        )
        alert_record, _, _ = self.upsert_fire_incident_signal(payload)
        if image_data:
            updated = self.attach_incident_snapshot(
                event_id=alert_record.event_id or alert_record.alert_id,
                cam_id=cam_id,
                snapshot_base64=image_data,
                boxes=[{"cls": class_name, "conf": confidence, "xyxy": bbox, "xyxyn": bbox}],
            )
            return updated or alert_record
        return alert_record


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
