"""
User Repository for Mắt Phố Backend
Handles Users, Phone Registry & Personal Group Creation via Atomic Firestore Transactions.
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from google.cloud import firestore

from google.cloud.firestore_v1.base_query import FieldFilter
from .base_repo import BaseFirestoreRepository
from ...models.user import UserModel, PhoneRegistryModel
from ...models.common import generate_semantic_id, UserRole
from ...core.formatters import normalize_phone_e164, current_utc_iso, parse_iso_utc

logger = logging.getLogger("backend.repository.user")


class UserRepository(BaseFirestoreRepository):
    def register_user_transaction(
        self,
        phone_number: str,
        password_hash: str,
        full_name: str,
        fcm_token: Optional[str] = None,
    ) -> UserModel:
        """
        Atomic registration:
        1. Checks phone_registry/{phone_e164}. If exists, raises ValueError("PHONE_ALREADY_REGISTERED").
        2. Creates phone_registry/{phone_e164}.
        3. Creates users/{uid}.
        4. Creates default personal group groups/grp_personal_{uid}.
        5. Adds user as LEADER in groups/grp_personal_{uid}/members/{uid}.
        6. Adds user membership in users/{uid}/group_memberships/grp_personal_{uid}.
        """
        phone_e164 = normalize_phone_e164(phone_number)
        user_id = generate_semantic_id("usr")
        personal_grp_id = f"grp_personal_{user_id}"
        fcm_tokens = [fcm_token] if fcm_token else []
        now_dt = datetime.now(timezone.utc)
        now_iso = current_utc_iso()

        phone_ref = self.db.collection("phone_registry").document(phone_e164)
        user_ref = self.db.collection("users").document(user_id)
        group_ref = self.db.collection("groups").document(personal_grp_id)
        member_ref = group_ref.collection("members").document(user_id)
        membership_ref = user_ref.collection("group_memberships").document(personal_grp_id)

        transaction = self.db.transaction()

        @firestore.transactional
        def _register(txn):
            snapshot = phone_ref.get(transaction=txn)
            if snapshot.exists:
                raise ValueError("PHONE_ALREADY_REGISTERED")

            # 1. Lock phone in phone_registry
            txn.set(
                phone_ref,
                {"user_id": user_id, "created_at": now_dt},
            )

            # 2. Create User Profile
            user_data = {
                "user_id": user_id,
                "phone_number": phone_e164,
                "full_name": full_name,
                "password_hash": password_hash,
                "failed_attempts": 0,
                "locked_until": None,
                "fcm_tokens": fcm_tokens,
                "loud_when_silent": True,
                "personal_group_id": personal_grp_id,
                "created_at": now_dt,
                "updated_at": now_dt,
            }
            txn.set(user_ref, user_data)

            # 3. Create Default Personal Group
            group_data = {
                "group_id": personal_grp_id,
                "group_name": "Cá nhân",
                "is_personal": True,
                "address": None,
                "creator_id": user_id,
                "member_count": 1,
                "camera_count": 0,
                "created_at": now_dt,
                "updated_at": now_dt,
            }
            txn.set(group_ref, group_data)

            # 4. Add User as LEADER in Personal Group
            member_data = {
                "user_id": user_id,
                "role": UserRole.LEADER.value,
                "full_name": full_name,
                "phone_number": phone_e164,
                "nickname": "Tôi",
                "note": "Chủ sở hữu nhóm cá nhân",
                "joined_at": now_dt,
                "camera_ids": None,  # None means access to all personal cameras
            }
            txn.set(member_ref, member_data)

            # 5. Add Group Membership mapping for O(1) user group lookup
            membership_data = {
                "group_id": personal_grp_id,
                "role": UserRole.LEADER.value,
                "is_personal": True,
                "joined_at": now_dt,
            }
            txn.set(membership_ref, membership_data)

            return user_data

        user_data = _register(transaction)
        return UserModel(**user_data)

    def get_user_by_id(self, user_id: str) -> Optional[UserModel]:
        """Fetch user by ID."""
        doc = self.get_document("users", user_id)
        if not doc:
            return None
        return UserModel(**doc)

    def get_user_by_phone(self, phone_number: str) -> Optional[UserModel]:
        """Fetch user by Phone Number via O(1) phone_registry lookup."""
        phone_e164 = normalize_phone_e164(phone_number)
        reg_doc = self.get_document("phone_registry", phone_e164)
        if reg_doc and "user_id" in reg_doc:
            return self.get_user_by_id(reg_doc["user_id"])

        # Fallback query directly on users collection
        query = self.db.collection("users").where(filter=FieldFilter("phone_number", "==", phone_e164)).limit(1).stream()
        for doc in query:
            data = doc.to_dict()
            return UserModel(**data)
        return None

    def record_login_attempt(self, user_id: str, success: bool) -> Tuple[int, Optional[datetime]]:
        """
        Record login attempt:
        - If success: resets failed_attempts to 0 and clears locked_until.
        - If failed: increments failed_attempts. If >= 5, sets locked_until to now + 15 minutes.
        Returns: (failed_attempts, locked_until)
        """
        user_ref = self.db.collection("users").document(user_id)
        now_dt = datetime.now(timezone.utc)

        if success:
            user_ref.update({
                "failed_attempts": 0,
                "locked_until": None,
                "updated_at": now_dt,
            })
            return 0, None

        doc = user_ref.get()
        if not doc.exists:
            return 1, None

        data = doc.to_dict() or {}
        fails = data.get("failed_attempts", 0) + 1
        locked_until = None

        if fails >= 5:
            locked_until = now_dt + timedelta(minutes=15)

        user_ref.update({
            "failed_attempts": fails,
            "locked_until": locked_until,
            "updated_at": now_dt,
        })
        return fails, locked_until

    def update_user_password(self, user_id: str, password_hash: str) -> bool:
        """Update password for user."""
        user_ref = self.db.collection("users").document(user_id)
        user_ref.update({
            "password_hash": password_hash,
            "failed_attempts": 0,
            "locked_until": None,
            "updated_at": datetime.now(timezone.utc),
        })
        return True

    def update_user_password_by_phone(self, phone_number: str, password_hash: str) -> bool:
        """Update password using verified phone number."""
        user = self.get_user_by_phone(phone_number)
        if not user:
            return False
        return self.update_user_password(user.user_id, password_hash)

    def update_user_settings(
        self,
        user_id: str,
        loud_when_silent: Optional[bool] = None,
        full_name: Optional[str] = None,
    ) -> None:
        """Update user preferences."""
        updates: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        if loud_when_silent is not None:
            updates["loud_when_silent"] = loud_when_silent
        if full_name is not None and full_name.strip():
            updates["full_name"] = full_name.strip()
        self.update_document("users", user_id, updates)

    def add_user_fcm_token(self, user_id: str, fcm_token: str) -> None:
        """Add unique FCM token to user's device list."""
        if not fcm_token:
            return
        user_ref = self.db.collection("users").document(user_id)
        user_ref.update({
            "fcm_tokens": firestore.ArrayUnion([fcm_token]),
            "updated_at": datetime.now(timezone.utc),
        })

    def remove_user_fcm_token(self, user_id: str, fcm_token: str) -> None:
        """Remove FCM token on logout."""
        if not fcm_token:
            return
        user_ref = self.db.collection("users").document(user_id)
        user_ref.update({
            "fcm_tokens": firestore.ArrayRemove([fcm_token]),
            "updated_at": datetime.now(timezone.utc),
        })

    def clear_user_fcm_tokens(self, user_id: str) -> None:
        """Clear all FCM tokens when password is reset on all devices."""
        user_ref = self.db.collection("users").document(user_id)
        user_ref.update({
            "fcm_tokens": [],
            "updated_at": datetime.now(timezone.utc),
        })


_user_repo_instance: Optional[UserRepository] = None


def get_user_repo() -> UserRepository:
    global _user_repo_instance
    if _user_repo_instance is None:
        _user_repo_instance = UserRepository()
    return _user_repo_instance
