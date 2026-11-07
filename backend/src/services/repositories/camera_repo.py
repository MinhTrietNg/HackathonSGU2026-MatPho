"""
Camera Repository for Mắt Phố Backend
Phase 4: Quản lý Camera, Thùng rác 30 ngày, Thăm dò RTSP & Stream HLS
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from .base_repo import BaseFirestoreRepository
from ...models.common import (
    CameraStatus,
    AuditAction,
    generate_semantic_id,
)
from ...models.camera import (
    CameraModel,
    WatchAreaModel,
)

logger = logging.getLogger("backend.repository.camera")


class CameraRepository(BaseFirestoreRepository):
    """Encapsulates all Camera Firestore database operations."""

    def _parse_camera(self, data: Optional[Dict[str, Any]]) -> Optional[CameraModel]:
        if not data:
            return None
        return CameraModel(**data)

    def create_camera(
        self,
        group_id: str,
        cam_name: str,
        rtsp_url: str,
        created_by: str,
        subgroup_id: Optional[str] = None,
        device_name: Optional[str] = None,
        watch_area: Optional[WatchAreaModel] = None,
        edge_device_id: Optional[str] = None,
    ) -> CameraModel:
        """Add a new camera to a group and subgroup."""
        cam_id = generate_semantic_id("cam")
        now_dt = datetime.now(timezone.utc)

        actual_subgroup_id = subgroup_id or "sub_general"
        subgroup_name = "Khu vực chung"
        subgroup_exists = False

        if subgroup_id:
            subgroup_doc = (
                self.db.collection("groups")
                .document(group_id)
                .collection("subgroups")
                .document(subgroup_id)
                .get()
            )
            if subgroup_doc.exists:
                subgroup_exists = True
                subgroup_name = subgroup_doc.to_dict().get("subgroup_name", "Khu vực chung")

        stream_host = os.getenv("MEDIAMTX_HOST", "https://stream.matpho.vn")
        live_stream_url = f"{stream_host}/live/{cam_id}/index.m3u8"
        watch_area_dict = watch_area.model_dump() if watch_area else None

        cam_data = {
            "cam_id": cam_id,
            "group_id": group_id,
            "subgroup_id": actual_subgroup_id,
            "subgroup_name": subgroup_name,
            "cam_name": cam_name,
            "device_name": device_name,
            "edge_device_id": edge_device_id,
            "rtsp_url": rtsp_url,
            "live_stream_url": live_stream_url,
            "watch_area": watch_area_dict,
            "notified_names": [],
            "created_by": created_by,
            "is_active": True,
            "is_ai_enabled": True,
            "status": CameraStatus.ONLINE.value,
            "is_deleted": False,
            "deleted_at": None,
            "purge_at": None,
            "last_seen_at": None,
            "created_at": now_dt,
            "updated_at": now_dt,
        }

        batch = self.db.batch()
        cam_ref = self.db.collection("cameras").document(cam_id)
        group_ref = self.db.collection("groups").document(group_id)

        batch.set(cam_ref, cam_data)
        batch.update(group_ref, {"camera_count": firestore.Increment(1)})
        if subgroup_exists:
            subgroup_ref = group_ref.collection("subgroups").document(actual_subgroup_id)
            batch.update(subgroup_ref, {"camera_count": firestore.Increment(1)})
        batch.commit()

        self.create_audit_log(
            group_id=group_id,
            actor_id=created_by,
            action=AuditAction.CREATE_CAMERA,
            target_entity=f"camera:{cam_id}",
            details={"cam_name": cam_name, "device_name": device_name},
        )
        return CameraModel(**cam_data)

    def get_camera(self, cam_id: str) -> Optional[CameraModel]:
        """Fetch camera by ID."""
        doc = self.get_document("cameras", cam_id)
        return self._parse_camera(doc)

    def list_all_online_cameras(self) -> List[CameraModel]:
        """Fetch all active online cameras across all groups."""
        try:
            docs = (
                self.db.collection("cameras")
                .where(filter=FieldFilter("is_deleted", "==", False))
                .where(filter=FieldFilter("is_active", "==", True))
                .stream()
            )
            return [self._parse_camera(d.to_dict()) for d in docs if self._parse_camera(d.to_dict())]
        except Exception as e:
            logger.debug(f"Error listing all online cameras: {e}")
            try:
                # Fallback in-memory filter if composite index is missing
                all_docs = self.db.collection("cameras").stream()
                results = []
                for d in all_docs:
                    c = self._parse_camera(d.to_dict())
                    if c and not c.is_deleted and c.is_active:
                        results.append(c)
                return results
            except Exception:
                return []

    def list_cameras_by_group(
        self,
        group_id: str,
        subgroup_id: Optional[str] = None,
    ) -> List[CameraModel]:
        """List active (non-deleted) cameras in a group."""
        try:
            query = (
                self.db.collection("cameras")
                .where(filter=FieldFilter("group_id", "==", group_id))
                .where(filter=FieldFilter("is_deleted", "==", False))
            )
            if subgroup_id:
                query = query.where(filter=FieldFilter("subgroup_id", "==", subgroup_id))

            docs = query.stream()
            return [self._parse_camera(d.to_dict()) for d in docs]
        except Exception:
            # Fallback in-memory filter if composite index is absent
            docs = (
                self.db.collection("cameras")
                .where(filter=FieldFilter("group_id", "==", group_id))
                .stream()
            )
            results = []
            for d in docs:
                data = d.to_dict()
                if not data.get("is_deleted", False):
                    if not subgroup_id or data.get("subgroup_id") == subgroup_id:
                        results.append(self._parse_camera(data))
            return results

    def list_trash_cameras(self, group_id: str) -> List[CameraModel]:
        """List soft-deleted cameras in the 30-day trash bin (auto-purging expired items)."""
        now_dt = datetime.now(timezone.utc)
        try:
            docs = (
                self.db.collection("cameras")
                .where(filter=FieldFilter("group_id", "==", group_id))
                .where(filter=FieldFilter("is_deleted", "==", True))
                .stream()
            )
            raw_list = [d.to_dict() for d in docs]
        except Exception:
            docs = (
                self.db.collection("cameras")
                .where(filter=FieldFilter("group_id", "==", group_id))
                .stream()
            )
            raw_list = [
                d.to_dict()
                for d in docs
                if d.to_dict().get("is_deleted", False)
            ]

        results: List[CameraModel] = []
        for data in raw_list:
            cam = self._parse_camera(data)
            if not cam:
                continue
            if cam.purge_at and now_dt >= cam.purge_at:
                try:
                    self.permanent_delete_camera(cam.cam_id, actor_id="system_auto_purge")
                except Exception as e:
                    logger.warning(f"Auto-purge failed for expired camera {cam.cam_id}: {e}")
                continue
            results.append(cam)
        return results

    def purge_expired_cameras(self) -> int:
        """Scan and permanently delete all soft-deleted cameras whose 30-day retention (purge_at) has expired."""
        now_dt = datetime.now(timezone.utc)
        purged_count = 0
        try:
            docs = (
                self.db.collection("cameras")
                .where(filter=FieldFilter("is_deleted", "==", True))
                .stream()
            )
            for d in docs:
                cam = self._parse_camera(d.to_dict())
                if cam and cam.purge_at and now_dt >= cam.purge_at:
                    if self.permanent_delete_camera(cam.cam_id, actor_id="system_auto_purge"):
                        purged_count += 1
        except Exception as e:
            logger.debug(f"Error during scheduled camera trash purge: {e}")
        return purged_count

    def update_camera(
        self,
        cam_id: str,
        actor_id: str,
        cam_name: Optional[str] = None,
        device_name: Optional[str] = None,
        subgroup_id: Optional[str] = None,
        watch_area: Optional[WatchAreaModel] = None,
        is_active: Optional[bool] = None,
        is_ai_enabled: Optional[bool] = None,
        rtsp_url: Optional[str] = None,
    ) -> Optional[CameraModel]:
        """Update camera configuration and adjust subgroup counters if moved."""
        cam = self.get_camera(cam_id)
        if not cam or cam.is_deleted:
            return None

        now_dt = datetime.now(timezone.utc)
        updates: Dict[str, Any] = {"updated_at": now_dt}

        if rtsp_url is not None:
            updates["rtsp_url"] = rtsp_url
        if cam_name is not None:
            updates["cam_name"] = cam_name
        if device_name is not None:
            updates["device_name"] = device_name
        if watch_area is not None:
            updates["watch_area"] = watch_area.model_dump()
        if is_active is not None:
            updates["is_active"] = is_active
            if not is_active:
                updates["status"] = CameraStatus.DISABLED.value
            elif cam.status == CameraStatus.DISABLED:
                updates["status"] = CameraStatus.ONLINE.value
        if is_ai_enabled is not None:
            updates["is_ai_enabled"] = is_ai_enabled

        # Subgroup reassignment
        if subgroup_id is not None and subgroup_id != cam.subgroup_id:
            batch = self.db.batch()
            cam_ref = self.db.collection("cameras").document(cam_id)
            group_ref = self.db.collection("groups").document(cam.group_id)
            old_sub_ref = group_ref.collection("subgroups").document(cam.subgroup_id)
            new_sub_ref = group_ref.collection("subgroups").document(subgroup_id)
            new_sub_doc = new_sub_ref.get()

            subgroup_name = (
                new_sub_doc.to_dict().get("subgroup_name", "Khu vực")
                if new_sub_doc.exists
                else "Khu vực"
            )
            updates["subgroup_id"] = subgroup_id
            updates["subgroup_name"] = subgroup_name

            batch.update(cam_ref, updates)
            if not cam.is_deleted:
                old_snap = old_sub_ref.get()
                if old_snap.exists:
                    old_c = old_snap.to_dict().get("camera_count", 0)
                    batch.update(old_sub_ref, {"camera_count": max(0, old_c - 1)})
                if new_sub_doc.exists:
                    batch.update(new_sub_ref, {"camera_count": firestore.Increment(1)})
            batch.commit()
        else:
            self.db.collection("cameras").document(cam_id).update(updates)

        self.create_audit_log(
            group_id=cam.group_id,
            actor_id=actor_id,
            action=AuditAction.UPDATE_CAMERA,
            target_entity=f"camera:{cam_id}",
            details={"cam_name": cam_name or cam.cam_name},
        )
        return self.get_camera(cam_id)

    def soft_delete_camera(self, cam_id: str, actor_id: str) -> bool:
        """Soft delete camera with 30-day retention before permanent purge."""
        cam = self.get_camera(cam_id)
        if not cam:
            return False
        if cam.is_deleted:
            return True

        now_dt = datetime.now(timezone.utc)
        purge_at = now_dt + timedelta(days=30)

        batch = self.db.batch()
        cam_ref = self.db.collection("cameras").document(cam_id)
        group_ref = self.db.collection("groups").document(cam.group_id)
        subgroup_ref = group_ref.collection("subgroups").document(cam.subgroup_id)

        batch.update(cam_ref, {
            "is_deleted": True,
            "status": CameraStatus.DELETED.value,
            "deleted_at": now_dt,
            "purge_at": purge_at,
            "updated_at": now_dt,
        })

        group_snap = group_ref.get()
        if group_snap.exists:
            curr_count = group_snap.to_dict().get("camera_count", 0)
            batch.update(group_ref, {"camera_count": max(0, curr_count - 1)})

        subgroup_snap = subgroup_ref.get()
        if subgroup_snap.exists:
            curr_sub_count = subgroup_snap.to_dict().get("camera_count", 0)
            batch.update(subgroup_ref, {"camera_count": max(0, curr_sub_count - 1)})

        batch.commit()

        self.create_audit_log(
            group_id=cam.group_id,
            actor_id=actor_id,
            action=AuditAction.DELETE_CAMERA,
            target_entity=f"camera:{cam_id}",
            details={"cam_name": cam.cam_name, "action": "soft_delete"},
        )
        return True

    def restore_camera(self, cam_id: str, actor_id: str) -> bool:
        """Restore camera from trash bin."""
        cam = self.get_camera(cam_id)
        if not cam or not cam.is_deleted:
            return False

        now_dt = datetime.now(timezone.utc)
        batch = self.db.batch()
        cam_ref = self.db.collection("cameras").document(cam_id)
        group_ref = self.db.collection("groups").document(cam.group_id)
        subgroup_ref = group_ref.collection("subgroups").document(cam.subgroup_id)

        batch.update(cam_ref, {
            "is_deleted": False,
            "status": CameraStatus.ONLINE.value,
            "deleted_at": None,
            "purge_at": None,
            "updated_at": now_dt,
        })

        group_snap = group_ref.get()
        if group_snap.exists:
            batch.update(group_ref, {"camera_count": firestore.Increment(1)})

        subgroup_snap = subgroup_ref.get()
        if subgroup_snap.exists:
            batch.update(subgroup_ref, {"camera_count": firestore.Increment(1)})

        batch.commit()

        self.create_audit_log(
            group_id=cam.group_id,
            actor_id=actor_id,
            action=AuditAction.RESTORE_CAMERA,
            target_entity=f"camera:{cam_id}",
            details={"cam_name": cam.cam_name},
        )
        return True

    def permanent_delete_camera(self, cam_id: str, actor_id: str) -> bool:
        """Permanently delete camera document from Firestore (LEADER only)."""
        cam = self.get_camera(cam_id)
        if not cam:
            return False

        # If camera was NOT yet soft-deleted, adjust group counters
        if not cam.is_deleted:
            group_ref = self.db.collection("groups").document(cam.group_id)
            group_snap = group_ref.get()
            if group_snap.exists:
                curr_count = group_snap.to_dict().get("camera_count", 0)
                group_ref.update({"camera_count": max(0, curr_count - 1)})

            subgroup_ref = group_ref.collection("subgroups").document(cam.subgroup_id)
            subgroup_snap = subgroup_ref.get()
            if subgroup_snap.exists:
                curr_sub = subgroup_snap.to_dict().get("camera_count", 0)
                subgroup_ref.update({"camera_count": max(0, curr_sub - 1)})

        self.db.collection("cameras").document(cam_id).delete()

        self.create_audit_log(
            group_id=cam.group_id,
            actor_id=actor_id,
            action=AuditAction.DELETE_CAMERA,
            target_entity=f"camera:{cam_id}",
            details={"action": "permanent_purge", "cam_name": cam.cam_name},
        )
        return True

    def create_audit_log(
        self,
        group_id: str,
        actor_id: str,
        action: AuditAction,
        target_entity: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record an immutable security and audit entry."""
        log_id = generate_semantic_id("aud")
        now_dt = datetime.now(timezone.utc)

        log_data = {
            "log_id": log_id,
            "group_id": group_id,
            "actor_id": actor_id,
            "action": action.value if hasattr(action, "value") else str(action),
            "target_entity": target_entity,
            "details": details or {},
            "created_at": now_dt,
        }

        try:
            self.set_document(f"groups/{group_id}/audit_logs", log_id, log_data)
            self.set_document("audit_logs", log_id, log_data)
        except Exception as e:
            logger.warning(f"Failed to record camera audit log: {e}")

        return log_id


_camera_repo_instance: Optional[CameraRepository] = None


def get_camera_repo() -> CameraRepository:
    global _camera_repo_instance
    if _camera_repo_instance is None:
        _camera_repo_instance = CameraRepository()
    return _camera_repo_instance


get_camera_repository = get_camera_repo

