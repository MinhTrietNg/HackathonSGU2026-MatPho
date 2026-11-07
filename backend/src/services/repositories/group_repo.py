"""
Group Repository for Mắt Phố Backend
Manages Groups, Subgroups, Members, 4-Role RBAC, Invitations, and Audit Logs.
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from .base_repo import BaseFirestoreRepository
from ...core.formatters import normalize_phone_e164
from ...models.common import (
    UserRole,
    InvitationStatus,
    AuditAction,
    generate_semantic_id,
)
from ...models.group import (
    GroupModel,
    MemberModel,
    SubgroupModel,
    InvitationModel,
)
from .user_repo import get_user_repo

logger = logging.getLogger("backend.repository.group")


class GroupRepository(BaseFirestoreRepository):
    """
    Encapsulates all Group, Subgroup, Member & Invitation Firestore operations.
    """

    # ==========================================================================
    # 1. GROUP LIFECYCLE
    # ==========================================================================

    def create_group(
        self,
        group_name: str,
        leader_id: str,
        address: Optional[str] = None,
        my_nickname: Optional[str] = None,
    ) -> GroupModel:
        """
        Create a new Group Lớn (Family / Liên Gia / Business).
        Atomically sets creator as LEADER in members and group_memberships.
        """
        user_repo = get_user_repo()
        leader = user_repo.get_user_by_id(leader_id)
        if not leader:
            raise ValueError("LEADER_NOT_FOUND")

        group_id = generate_semantic_id("grp")
        now_dt = datetime.now(timezone.utc)

        group_data = {
            "group_id": group_id,
            "group_name": group_name.strip(),
            "is_personal": False,
            "leader_id": leader_id,
            "address": address.strip() if address else None,
            "member_count": 1,
            "camera_count": 0,
            "is_deleted": False,
            "deleted_at": None,
            "created_at": now_dt,
            "updated_at": now_dt,
        }

        member_data = {
            "user_id": leader_id,
            "role": UserRole.LEADER.value,
            "nickname": my_nickname or "Trưởng Nhóm",
            "note": "Chủ sở hữu nhóm",
            "phone_number": leader.phone_number,
            "full_name": leader.full_name,
            "camera_ids": None,  # None means full access to all cameras
            "joined_at": now_dt,
            "updated_at": now_dt,
        }

        membership_data = {
            "group_id": group_id,
            "role": UserRole.LEADER.value,
            "nickname": my_nickname or "Trưởng Nhóm",
            "is_personal": False,
            "created_at": now_dt,
        }

        batch = self.db.batch()
        group_ref = self.db.collection("groups").document(group_id)
        member_ref = group_ref.collection("members").document(leader_id)
        user_membership_ref = (
            self.db.collection("users")
            .document(leader_id)
            .collection("group_memberships")
            .document(group_id)
        )

        batch.set(group_ref, group_data)
        batch.set(member_ref, member_data)
        batch.set(user_membership_ref, membership_data)
        batch.commit()

        self.create_audit_log(
            group_id=group_id,
            actor_id=leader_id,
            action=AuditAction.CREATE_GROUP,
            target_entity=f"group:{group_id}",
            details={"group_name": group_name, "address": address},
        )

        return GroupModel(**group_data)

    def get_group(self, group_id: str) -> Optional[GroupModel]:
        """Fetch group by ID."""
        doc = self.get_document("groups", group_id)
        if not doc or doc.get("is_deleted", False):
            return None
        return GroupModel(**doc)

    def list_groups_for_user(self, user_id: str) -> List[Tuple[GroupModel, str, Optional[str]]]:
        """
        List all active groups for a user via O(1) group_memberships subcollection.
        Returns: List of (GroupModel, my_role, my_nickname)
        """
        memberships_ref = (
            self.db.collection("users")
            .document(user_id)
            .collection("group_memberships")
        )
        docs = memberships_ref.stream()

        results = []
        for d in docs:
            m_data = d.to_dict()
            grp_id = m_data.get("group_id")
            if not grp_id:
                continue

            grp = self.get_group(grp_id)
            if not grp:
                continue

            # Fetch fresh member info
            member_doc = self.get_document(f"groups/{grp_id}/members", user_id)
            role = member_doc.get("role", m_data.get("role", UserRole.MEMBER.value)) if member_doc else m_data.get("role", UserRole.MEMBER.value)
            nickname = member_doc.get("nickname", m_data.get("nickname")) if member_doc else m_data.get("nickname")

            results.append((grp, role, nickname))

        # Sort: Personal group first, then newest
        results.sort(key=lambda x: (not x[0].is_personal, str(x[0].created_at or "")), reverse=True)
        return results

    def update_group(
        self,
        group_id: str,
        name: Optional[str] = None,
        address: Optional[str] = None,
    ) -> Optional[GroupModel]:
        """Update group name or 114 address (Leader only)."""
        updates: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        if name is not None and name.strip():
            updates["group_name"] = name.strip()
        if address is not None:
            updates["address"] = address.strip() if address.strip() else None

        self.update_document("groups", group_id, updates)
        return self.get_group(group_id)

    def delete_group(self, group_id: str, actor_id: Optional[str] = None) -> bool:
        """Soft delete group. Personal groups cannot be deleted."""
        grp = self.get_group(group_id)
        if not grp:
            raise ValueError("GROUP_NOT_FOUND")
        if grp.is_personal or group_id.startswith("grp_personal_"):
            raise ValueError("CANNOT_DELETE_PERSONAL_GROUP")

        now_dt = datetime.now(timezone.utc)
        self.update_document("groups", group_id, {
            "is_deleted": True,
            "deleted_at": now_dt,
            "updated_at": now_dt,
        })
        if actor_id:
            self.create_audit_log(
                group_id=group_id,
                actor_id=actor_id,
                action=AuditAction.UPDATE_GROUP,
                target_entity=f"group:{group_id}",
                details={"action": "dissolve_group"},
            )
        return True

    def transfer_ownership(
        self, group_id: str, current_leader_id: str, new_leader_id: str
    ) -> GroupModel:
        """
        Transfer LEADER role to another existing group member.
        Current leader becomes MEMBER.
        """
        group = self.get_group(group_id)
        if not group:
            raise ValueError("GROUP_NOT_FOUND")
        if group.is_personal or group_id.startswith("grp_personal_"):
            raise ValueError("CANNOT_TRANSFER_PERSONAL_GROUP")
        if group.leader_id != current_leader_id:
            raise ValueError("NOT_LEADER")

        new_leader_member = self.get_member(group_id, new_leader_id)
        if not new_leader_member:
            raise ValueError("TARGET_NOT_A_MEMBER")

        now_dt = datetime.now(timezone.utc)
        batch = self.db.batch()

        # 1. Update Group document
        group_ref = self.db.collection("groups").document(group_id)
        batch.update(group_ref, {"leader_id": new_leader_id, "updated_at": now_dt})

        # 2. Demote old leader to MEMBER
        old_mem_ref = group_ref.collection("members").document(current_leader_id)
        batch.update(old_mem_ref, {"role": UserRole.MEMBER.value, "updated_at": now_dt})

        # 3. Promote new leader to LEADER
        new_mem_ref = group_ref.collection("members").document(new_leader_id)
        batch.update(new_mem_ref, {"role": UserRole.LEADER.value, "updated_at": now_dt})

        # 4. Update user memberships
        old_user_ms_ref = (
            self.db.collection("users")
            .document(current_leader_id)
            .collection("group_memberships")
            .document(group_id)
        )
        batch.update(old_user_ms_ref, {"role": UserRole.MEMBER.value})

        new_user_ms_ref = (
            self.db.collection("users")
            .document(new_leader_id)
            .collection("group_memberships")
            .document(group_id)
        )
        batch.update(new_user_ms_ref, {"role": UserRole.LEADER.value})

        batch.commit()

        self.create_audit_log(
            group_id=group_id,
            actor_id=current_leader_id,
            action=AuditAction.TRANSFER_OWNERSHIP,
            target_entity=f"user:{new_leader_id}",
            details={"action": "transfer_ownership", "new_leader_id": new_leader_id},
        )
        return self.get_group(group_id)

    # ==========================================================================
    # 2. MEMBERS & 4-ROLE RBAC
    # ==========================================================================

    def add_member_direct(
        self,
        group_id: str,
        user_id: str,
        role: UserRole = UserRole.MEMBER,
        nickname: Optional[str] = None,
        camera_ids: Optional[List[str]] = None,
    ) -> MemberModel:
        """Directly add user as a group member (bypassing invitation for tests/admin)."""
        user_repo = get_user_repo()
        user = user_repo.get_user_by_id(user_id)
        if not user:
            raise ValueError("USER_NOT_FOUND")

        now_dt = datetime.now(timezone.utc)
        member_data = {
            "user_id": user_id,
            "role": role.value if hasattr(role, "value") else str(role),
            "full_name": user.full_name,
            "phone_number": user.phone_number,
            "nickname": nickname or user.full_name,
            "note": None,
            "camera_ids": camera_ids,
            "joined_at": now_dt,
        }
        self.db.collection("groups").document(group_id).collection("members").document(user_id).set(member_data)
        self.db.collection("users").document(user_id).collection("group_memberships").document(group_id).set({
            "group_id": group_id,
            "role": role.value if hasattr(role, "value") else str(role),
            "joined_at": now_dt,
        })
        try:
            self.db.collection("groups").document(group_id).update({
                "member_count": firestore.Increment(1),
            })
        except Exception:
            pass

        return MemberModel(**member_data)

    add_member = add_member_direct

    def get_member(self, group_id: str, user_id: str) -> Optional[MemberModel]:
        """Fetch member in group."""
        doc = self.get_document(f"groups/{group_id}/members", user_id)
        if not doc:
            return None
        return MemberModel(**doc)

    def list_members(self, group_id: str) -> List[MemberModel]:
        """List all members of a group."""
        docs = self.db.collection("groups").document(group_id).collection("members").stream()
        return [MemberModel(**d.to_dict()) for d in docs]

    def update_member_role(self, group_id: str, user_id: str, new_role: UserRole) -> bool:
        """Update role of a member (Leader only)."""
        member = self.get_member(group_id, user_id)
        if not member:
            return False

        now_dt = datetime.now(timezone.utc)
        batch = self.db.batch()

        mem_ref = (
            self.db.collection("groups")
            .document(group_id)
            .collection("members")
            .document(user_id)
        )
        batch.update(mem_ref, {"role": new_role.value, "updated_at": now_dt})

        ms_ref = (
            self.db.collection("users")
            .document(user_id)
            .collection("group_memberships")
            .document(group_id)
        )
        batch.update(ms_ref, {"role": new_role.value})

        batch.commit()
        return True

    def update_member_cameras(
        self, group_id: str, user_id: str, camera_ids: Optional[List[str]]
    ) -> bool:
        """Assign specific cameras to a MEMBER."""
        mem_ref = (
            self.db.collection("groups")
            .document(group_id)
            .collection("members")
            .document(user_id)
        )
        mem_ref.update({
            "camera_ids": camera_ids,
            "updated_at": datetime.now(timezone.utc),
        })
        return True

    def update_member_nickname(
        self, group_id: str, user_id: str, nickname: Optional[str]
    ) -> bool:
        """Update member's group nickname."""
        clean_nick = nickname.strip() if nickname else None
        now_dt = datetime.now(timezone.utc)

        batch = self.db.batch()
        mem_ref = (
            self.db.collection("groups")
            .document(group_id)
            .collection("members")
            .document(user_id)
        )
        batch.update(mem_ref, {"nickname": clean_nick, "updated_at": now_dt})

        ms_ref = (
            self.db.collection("users")
            .document(user_id)
            .collection("group_memberships")
            .document(group_id)
        )
        batch.update(ms_ref, {"nickname": clean_nick})
        batch.commit()
        return True

    def remove_member(self, group_id: str, user_id: str) -> bool:
        """
        Remove member from group.
        Personal groups cannot have members removed.
        """
        grp = self.get_group(group_id)
        if not grp or grp.is_personal or group_id.startswith("grp_personal_"):
            return False

        if grp.leader_id == user_id:
            raise ValueError("LEADER_CANNOT_LEAVE")

        transaction = self.db.transaction()
        group_ref = self.db.collection("groups").document(group_id)
        member_ref = group_ref.collection("members").document(user_id)
        ms_ref = (
            self.db.collection("users")
            .document(user_id)
            .collection("group_memberships")
            .document(group_id)
        )

        @firestore.transactional
        def _remove(txn):
            mem_snap = member_ref.get(transaction=txn)
            if not mem_snap.exists:
                return False

            txn.delete(member_ref)
            txn.delete(ms_ref)

            new_count = max(1, (grp.member_count or 1) - 1)
            txn.update(group_ref, {
                "member_count": new_count,
                "updated_at": datetime.now(timezone.utc),
            })
            return True

        return _remove(transaction)

    # ==========================================================================
    # 3. SUBGROUPS (Khu vực / Vị trí lắp đặt)
    # ==========================================================================

    def create_subgroup(
        self,
        group_id: str,
        subgroup_name: str,
        description: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> SubgroupModel:
        """Create a new location / area in group."""
        subgroup_id = generate_semantic_id("sub")
        data = {
            "subgroup_id": subgroup_id,
            "subgroup_name": subgroup_name.strip(),
            "description": description.strip() if description else None,
            "camera_count": 0,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc),
        }
        self.set_document(f"groups/{group_id}/subgroups", subgroup_id, data)
        return SubgroupModel(**data)

    def list_subgroups(self, group_id: str) -> List[SubgroupModel]:
        """List all subgroups/areas in group."""
        docs = (
            self.db.collection("groups")
            .document(group_id)
            .collection("subgroups")
            .stream()
        )
        return [SubgroupModel(**d.to_dict()) for d in docs]

    def update_subgroup(
        self,
        group_id: str,
        subgroup_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[SubgroupModel]:
        """Update subgroup name or description."""
        doc_ref = (
            self.db.collection("groups")
            .document(group_id)
            .collection("subgroups")
            .document(subgroup_id)
        )
        doc = doc_ref.get()
        if not doc.exists:
            return None

        updates: Dict[str, Any] = {}
        if name is not None and name.strip():
            updates["subgroup_name"] = name.strip()
        if description is not None:
            updates["description"] = description.strip() if description.strip() else None

        if updates:
            doc_ref.update(updates)

        updated_dict = doc.to_dict()
        updated_dict.update(updates)
        return SubgroupModel(**updated_dict)

    def delete_subgroup(self, group_id: str, subgroup_id: str) -> bool:
        """Delete subgroup/area."""
        doc_ref = (
            self.db.collection("groups")
            .document(group_id)
            .collection("subgroups")
            .document(subgroup_id)
        )
        doc = doc_ref.get()
        if not doc.exists:
            return False

        doc_ref.delete()
        return True

    # ==========================================================================
    # 4. INVITATIONS
    # ==========================================================================

    def create_invitation(
        self,
        group_id: str,
        phone_number: str,
        role: UserRole,
        invited_by: str,
        nickname: Optional[str] = None,
        camera_ids: Optional[List[str]] = None,
    ) -> InvitationModel:
        """
        Create a new invitation for a user via Phone Number.
        Writes to groups/{group_id}/invitations and invitation_lookup for O(1) query.
        """
        group = self.get_group(group_id)
        if not group:
            raise ValueError("GROUP_NOT_FOUND")

        user_repo = get_user_repo()
        inviter = user_repo.get_user_by_id(invited_by)
        inviter_name = inviter.full_name if inviter else "Trưởng nhóm"

        phone_e164 = normalize_phone_e164(phone_number)
        invitation_id = generate_semantic_id("inv")
        now_dt = datetime.now(timezone.utc)

        inv_data = {
            "invitation_id": invitation_id,
            "group_id": group_id,
            "group_name": group.group_name,
            "group_address": group.address,
            "phone_number": phone_e164,
            "role": role.value,
            "nickname": nickname,
            "suggested_nickname": nickname,
            "member_count": group.member_count or 1,
            "camera_count": len(camera_ids) if camera_ids else 0,
            "camera_names": [],
            "camera_ids": camera_ids,
            "invited_by": invited_by,
            "invited_by_name": inviter_name,
            "status": InvitationStatus.PENDING.value,
            "expires_at": None,
            "created_at": now_dt,
        }

        batch = self.db.batch()
        inv_ref = (
            self.db.collection("groups")
            .document(group_id)
            .collection("invitations")
            .document(invitation_id)
        )
        lookup_ref = self.db.collection("invitation_lookup").document(invitation_id)

        batch.set(inv_ref, inv_data)
        batch.set(lookup_ref, {
            "invitation_id": invitation_id,
            "group_id": group_id,
            "phone_number": phone_e164,
            "status": InvitationStatus.PENDING.value,
            "created_at": now_dt,
        })
        batch.commit()

        self.create_audit_log(
            group_id=group_id,
            actor_id=invited_by,
            action=AuditAction.INVITE_MEMBER,
            target_entity=f"invitation:{invitation_id}",
            details={"phone_number": phone_e164, "role": role.value},
        )
        return InvitationModel(**inv_data)

    def get_invitation(self, invitation_id: str) -> Optional[InvitationModel]:
        """Fetch invitation details via O(1) invitation_lookup."""
        lookup_doc = self.get_document("invitation_lookup", invitation_id)
        if not lookup_doc:
            return None

        group_id = lookup_doc.get("group_id")
        if not group_id:
            return None

        inv_doc = self.get_document(f"groups/{group_id}/invitations", invitation_id)
        if not inv_doc:
            return None
        return InvitationModel(**inv_doc)

    def list_invitations(self, group_id: str) -> List[InvitationModel]:
        """List all pending invitations in a group."""
        docs = (
            self.db.collection("groups")
            .document(group_id)
            .collection("invitations")
            .where(filter=FieldFilter("status", "==", InvitationStatus.PENDING.value))
            .stream()
        )
        return [InvitationModel(**d.to_dict()) for d in docs]

    def list_invitations_for_user(self, phone_number: str) -> List[InvitationModel]:
        """List all pending invitations sent to a user's phone number."""
        phone_e164 = normalize_phone_e164(phone_number)
        query = (
            self.db.collection("invitation_lookup")
            .where(filter=FieldFilter("phone_number", "==", phone_e164))
            .where(filter=FieldFilter("status", "==", InvitationStatus.PENDING.value))
            .stream()
        )

        results = []
        for d in query:
            item = d.to_dict()
            inv = self.get_invitation(item["invitation_id"])
            if inv and inv.status == InvitationStatus.PENDING:
                results.append(inv)
        return results

    def accept_invitation_transaction(
        self,
        invitation_id: str,
        user_id: str,
        nickname: Optional[str] = None,
    ) -> MemberModel:
        """
        Atomically accept an invitation:
        1. Checks invitation status is PENDING.
        2. Sets invitation status to ACCEPTED.
        3. Creates member record in groups/{group_id}/members.
        4. Creates membership record in users/{user_id}/group_memberships.
        5. Increments group.member_count.
        """
        user_repo = get_user_repo()
        user = user_repo.get_user_by_id(user_id)
        if not user:
            raise ValueError("USER_NOT_FOUND")

        lookup_doc = self.get_document("invitation_lookup", invitation_id)
        if not lookup_doc:
            raise ValueError("INVITATION_NOT_FOUND")

        group_id = lookup_doc["group_id"]
        group_ref = self.db.collection("groups").document(group_id)
        inv_ref = group_ref.collection("invitations").document(invitation_id)
        lookup_ref = self.db.collection("invitation_lookup").document(invitation_id)
        member_ref = group_ref.collection("members").document(user_id)
        user_ms_ref = (
            self.db.collection("users")
            .document(user_id)
            .collection("group_memberships")
            .document(group_id)
        )

        transaction = self.db.transaction()
        now_dt = datetime.now(timezone.utc)
        member_res = {}

        @firestore.transactional
        def _accept(txn):
            inv_snap = inv_ref.get(transaction=txn)
            if not inv_snap.exists:
                raise ValueError("INVITATION_NOT_FOUND")

            inv_dict = inv_snap.to_dict()
            if inv_dict.get("status") != InvitationStatus.PENDING.value:
                raise ValueError("INVITATION_UNAVAILABLE")

            # Check if user already joined
            existing_mem = member_ref.get(transaction=txn)
            if existing_mem.exists:
                raise ValueError("ALREADY_IN_GROUP")

            # Read group before any writes (Firestore: all reads must precede writes)
            grp_snap = group_ref.get(transaction=txn)
            current_count = grp_snap.to_dict().get("member_count", 1) if grp_snap.exists else 1

            role_val = inv_dict.get("role", UserRole.MEMBER.value)
            camera_ids = inv_dict.get("camera_ids")
            final_nickname = nickname or inv_dict.get("nickname") or "Thành viên"

            # 1. Update invitation status
            txn.update(inv_ref, {
                "status": InvitationStatus.ACCEPTED.value,
                "updated_at": now_dt,
            })
            txn.update(lookup_ref, {
                "status": InvitationStatus.ACCEPTED.value,
            })

            # 2. Add member
            mem_data = {
                "user_id": user_id,
                "role": role_val,
                "nickname": final_nickname,
                "note": "Thành viên gia nhập qua lời mời",
                "phone_number": user.phone_number,
                "full_name": user.full_name,
                "camera_ids": camera_ids,
                "joined_at": now_dt,
                "updated_at": now_dt,
            }
            txn.set(member_ref, mem_data)

            # 3. Add user membership
            txn.set(user_ms_ref, {
                "group_id": group_id,
                "role": role_val,
                "nickname": final_nickname,
                "is_personal": False,
                "created_at": now_dt,
            })

            # 4. Increment member count
            txn.update(group_ref, {
                "member_count": current_count + 1,
                "updated_at": now_dt,
            })

            member_res.update(mem_data)

        _accept(transaction)

        self.create_audit_log(
            group_id=group_id,
            actor_id=user_id,
            action=AuditAction.ACCEPT_INVITATION,
            target_entity=f"member:{user_id}",
            details={"action": "joined_via_invitation", "invitation_id": invitation_id},
        )
        return MemberModel(**member_res)

    def decline_invitation(self, invitation_id: str) -> bool:
        """Decline a pending invitation."""
        lookup_doc = self.get_document("invitation_lookup", invitation_id)
        if not lookup_doc:
            return False

        group_id = lookup_doc["group_id"]
        inv_ref = (
            self.db.collection("groups")
            .document(group_id)
            .collection("invitations")
            .document(invitation_id)
        )
        lookup_ref = self.db.collection("invitation_lookup").document(invitation_id)

        now_dt = datetime.now(timezone.utc)
        batch = self.db.batch()
        batch.update(inv_ref, {
            "status": InvitationStatus.REJECTED.value,
            "updated_at": now_dt,
        })
        batch.update(lookup_ref, {
            "status": InvitationStatus.REJECTED.value,
        })
        batch.commit()
        return True

    def cancel_invitation(self, group_id: str, invitation_id: str) -> bool:
        """Cancel or revoke an invitation."""
        inv_ref = (
            self.db.collection("groups")
            .document(group_id)
            .collection("invitations")
            .document(invitation_id)
        )
        lookup_ref = self.db.collection("invitation_lookup").document(invitation_id)

        now_dt = datetime.now(timezone.utc)
        batch = self.db.batch()
        batch.update(inv_ref, {
            "status": InvitationStatus.CANCELLED.value,
            "updated_at": now_dt,
        })
        batch.update(lookup_ref, {
            "status": InvitationStatus.CANCELLED.value,
        })
        batch.commit()
        return True

    # ==========================================================================
    # 5. AUDIT LOGS
    # ==========================================================================

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
            # Store in group audit_logs subcollection
            self.set_document(f"groups/{group_id}/audit_logs", log_id, log_data)
            # Also store in global audit_logs collection for centralized access
            self.set_document("audit_logs", log_id, log_data)
        except Exception as e:
            logger.warning(f"Failed to record audit log: {e}")

        return log_id

    def list_audit_logs(self, group_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """List audit logs for a group."""
        docs = (
            self.db.collection("groups")
            .document(group_id)
            .collection("audit_logs")
            .limit(limit)
            .stream()
        )
        return [d.to_dict() for d in docs]


_group_repo_instance: Optional[GroupRepository] = None


def get_group_repo() -> GroupRepository:
    global _group_repo_instance
    if _group_repo_instance is None:
        _group_repo_instance = GroupRepository()
    return _group_repo_instance


get_group_repository = get_group_repo

