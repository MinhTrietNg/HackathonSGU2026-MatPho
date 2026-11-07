#!/usr/bin/env python3
"""
Clean and Seed Cloud Firestore Database for AI Surveillance & Fire Emergency Platform (NOD89)
Project: matpho-c7e77
Matches Figma Wireframes, Mobile UI Tests (40-Item Alignment), and docs/DATABASE_DESIGN.md v3.2 exactly.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
import bcrypt
import firebase_admin
from firebase_admin import credentials, firestore

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
CREDENTIALS_PATH = BACKEND_DIR / "credentials" / "firebase-service-account.json"

if not CREDENTIALS_PATH.exists():
    print(f"❌ Error: Firebase Service Account JSON not found at {CREDENTIALS_PATH}")
    sys.exit(1)

print("================================================================================")
print("🚀 BẮT ĐẦU DỌN SẠCH VÀ SEED DATABASE CHUẨN LÊN CLOUD FIRESTORE")
print(f"📂 Credentials: {CREDENTIALS_PATH}")
print("================================================================================")

try:
    cred = credentials.Certificate(str(CREDENTIALS_PATH))
    try:
        firebase_admin.initialize_app(cred)
    except ValueError:
        pass
    db = firestore.client()
    print("✅ Kết nối Firebase Admin SDK thành công!")
except Exception as e:
    print(f"❌ Lỗi kết nối Firebase: {e}")
    sys.exit(1)

# ==============================================================================
# BƯỚC 1: DỌN SẠCH CÁC DOCUMENTS VÀ SUBCOLLECTIONS CŨ
# ==============================================================================
print("\n[Bước 1/8] Dọn dẹp sạch toàn bộ các collection & subcollection hiện có...")

# Xóa các subcollections trước qua collection_group
for sub_name in ["subgroups", "members", "invitations", "group_memberships"]:
    cg = db.collection_group(sub_name)
    sub_count = 0
    while True:
        refs = [doc.reference for doc in cg.limit(500).stream()]
        if not refs:
            break
        batch = db.batch()
        for r in refs:
            batch.delete(r)
        batch.commit()
        sub_count += len(refs)
    if sub_count > 0:
        print(f"  🗑️ Đã xóa {sub_count} document trong subcollection [{sub_name}]")

# Xóa các root collections
root_collections = ["users", "groups", "cameras", "fire_alerts", "audit_logs", "phone_registry", "invitation_lookup"]
for col_name in root_collections:
    col = db.collection(col_name)
    col_count = 0
    while True:
        refs = [doc.reference for doc in col.limit(500).stream()]
        if not refs:
            break
        batch = db.batch()
        for r in refs:
            batch.delete(r)
        batch.commit()
        col_count += len(refs)
    if col_count > 0:
        print(f"  🗑️ Đã xóa {col_count} document trong collection [{col_name}]")

print("✅ Cơ sở dữ liệu đã được dọn sạch hoàn toàn!")

# ==============================================================================
# BƯỚC 2: KHỞI TẠO BỘ TÀI KHOẢN & SỐ ĐIỆN THOẠI (phone_registry & users)
# ==============================================================================
print("\n[Bước 2/8] Khởi tạo collection: phone_registry & users...")

salt = bcrypt.gensalt(rounds=12)
demo_password_hash = bcrypt.hashpw(b"matkhau123", salt).decode("utf-8")

accounts = [
    # Main user / Root Leader
    ("usr_leader_matpho_01", "+84912345678", "Nguyễn Minh Anh"),
    # Sky Garden members
    ("usr_lan", "+84908000001", "Phạm Thị Lan"),
    ("usr_tuan", "+84912000678", "Trần Anh Tuấn"),
    # Home group members
    ("usr_me", "+84912000002", "Mẹ"),
    ("usr_bin", "+84912000003", "Bin"),
    ("usr_na", "+84912000004", "Bé Na"),
    # Office group members
    ("usr_long", "+84909000001", "Anh Long"),
    ("usr_mai", "+84909000002", "Chị Mai"),
    # Riverside group owner
    ("usr_hoa", "+84909998877", "Chị Hoa"),
]

admin_uid = "usr_leader_matpho_01"
admin_phone = "+84912345678"

for uid, phone, name in accounts:
    # 2.1 phone_registry
    db.collection("phone_registry").document(phone).set({
        "user_id": uid,
        "created_at": firestore.SERVER_TIMESTAMP,
    })
    
    # 2.2 users
    personal_grp_id = f"grp_personal_{uid}" if uid == admin_uid else None
    user_data = {
        "user_id": uid,
        "phone_number": phone,
        "full_name": name,
        "password_hash": demo_password_hash,
        "failed_attempts": 0,
        "locked_until": None,
        "fcm_tokens": [f"fcm_tok_{uid}_seed_demo"],
        "loud_when_silent": True,
        "personal_group_id": personal_grp_id,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    db.collection("users").document(uid).set(user_data)
    print(f"  ✓ User created: {uid} ({name} - {phone})")

# Spare registered phone for testing J2 checks
db.collection("phone_registry").document("+84987654321").set({
    "user_id": "usr_spare_01",
    "created_at": firestore.SERVER_TIMESTAMP,
})
print("  ✓ Spare phone_registry/+84987654321 -> usr_spare_01")

# ==============================================================================
# BƯỚC 3: KHỞI TẠO GROUPS, SUBGROUPS, MEMBERS & GROUP_MEMBERSHIPS
# ==============================================================================
print("\n[Bước 3/8] Khởi tạo collection: groups & subcollections (5 Nhóm chuẩn)...")

# 3.A: Nhóm Cá Nhân ("Camera của tôi")
personal_grp_id = f"grp_personal_{admin_uid}"
db.collection("groups").document(personal_grp_id).set({
    "group_id": personal_grp_id,
    "group_name": "Camera của tôi",
    "is_personal": True,
    "leader_id": admin_uid,
    "address": "Khu vực cá nhân",
    "member_count": 1,
    "camera_count": 0,
    "is_deleted": False,
    "deleted_at": None,
    "purge_at": None,
    "created_at": firestore.SERVER_TIMESTAMP,
    "updated_at": firestore.SERVER_TIMESTAMP,
})
db.collection("groups").document(personal_grp_id).collection("members").document(admin_uid).set({
    "user_id": admin_uid,
    "role": "LEADER",
    "nickname": "Tôi",
    "note": None,
    "phone_number": admin_phone,
    "full_name": "Nguyễn Minh Anh",
    "camera_ids": None,
    "joined_at": firestore.SERVER_TIMESTAMP,
    "updated_at": firestore.SERVER_TIMESTAMP,
})
db.collection("users").document(admin_uid).collection("group_memberships").document(personal_grp_id).set({
    "group_id": personal_grp_id,
    "role": "LEADER",
    "nickname": "Tôi",
    "updated_at": firestore.SERVER_TIMESTAMP,
})
print(f"  ✓ Nhóm Cá Nhân (Camera của tôi): {personal_grp_id}")

# 3.B: Chung cư Sky Garden (g-sky)
sky_grp_id = "g-sky"
sky_members = [
    {
        "user_id": admin_uid,
        "role": "LEADER",
        "nickname": "Minh Anh",
        "note": None,
        "phone_number": admin_phone,
        "full_name": "Nguyễn Minh Anh",
        "camera_ids": None,
    },
    {
        "user_id": "usr_lan",
        "role": "MEMBER_MANAGER",
        "nickname": "Lan",
        "note": "Quản lý toà nhà",
        "phone_number": "+84908000001",
        "full_name": "Phạm Thị Lan",
        "camera_ids": None,
    },
    {
        "user_id": "usr_tuan",
        "role": "MEMBER",
        "nickname": "Chú Tuấn bảo vệ",
        "note": "Trực hầm B1 và B2",
        "phone_number": "+84912000678",
        "full_name": "Trần Anh Tuấn",
        "camera_ids": ["cam-charger", "cam-ramp", "cam-down", "cam-lift", "cam-lobby"],
    },
]

db.collection("groups").document(sky_grp_id).set({
    "group_id": sky_grp_id,
    "group_name": "Chung cư Sky Garden",
    "is_personal": False,
    "leader_id": admin_uid,
    "address": "Hầm B1, chung cư Sky Garden, 12 Nguyễn Văn Linh, Q.7",
    "member_count": len(sky_members),
    "camera_count": 5,
    "is_deleted": False,
    "deleted_at": None,
    "purge_at": None,
    "created_at": firestore.SERVER_TIMESTAMP,
    "updated_at": firestore.SERVER_TIMESTAMP,
})

sky_subgroups = [
    {"subgroup_id": "a-b1", "subgroup_name": "Hầm B1", "camera_count": 3},
    {"subgroup_id": "a-b2", "subgroup_name": "Hầm B2", "camera_count": 1},
    {"subgroup_id": "a-lobby", "subgroup_name": "Sảnh tầng 1", "camera_count": 1},
]
for sub in sky_subgroups:
    db.collection("groups").document(sky_grp_id).collection("subgroups").document(sub["subgroup_id"]).set({
        **sub,
        "created_by": admin_uid,
        "created_at": firestore.SERVER_TIMESTAMP,
    })

for m in sky_members:
    db.collection("groups").document(sky_grp_id).collection("members").document(m["user_id"]).set({
        **m,
        "joined_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    })
    db.collection("users").document(m["user_id"]).collection("group_memberships").document(sky_grp_id).set({
        "group_id": sky_grp_id,
        "role": m["role"],
        "nickname": m.get("nickname"),
        "updated_at": firestore.SERVER_TIMESTAMP,
    })

# Lời mời chờ duyệt trong Sky Garden (J1/J2)
db.collection("groups").document(sky_grp_id).collection("invitations").document("inv_pending_night_guard").set({
    "invitation_id": "inv_pending_night_guard",
    "group_id": sky_grp_id,
    "group_name": "Chung cư Sky Garden",
    "group_address": "Hầm B1, chung cư Sky Garden, 12 Nguyễn Văn Linh, Q.7",
    "phone_number": "+84903456112",
    "role": "MEMBER",
    "nickname": "Bảo vệ ca đêm",
    "suggested_nickname": "Bảo vệ ca đêm",
    "camera_ids": ["cam-charger", "cam-ramp", "cam-down"],
    "camera_names": ["Khu sạc xe", "Lối lên dốc", "Lối xuống"],
    "invited_by": admin_uid,
    "invited_by_name": "Nguyễn Minh Anh",
    "status": "PENDING",
    "created_at": firestore.SERVER_TIMESTAMP,
})
db.collection("invitation_lookup").document("+84903456112").set({
    "invitation_id": "inv_pending_night_guard",
    "group_id": sky_grp_id,
    "phone_number": "+84903456112",
    "status": "PENDING",
    "created_at": firestore.SERVER_TIMESTAMP,
})
print(f"  ✓ Nhóm g-sky: Chung cư Sky Garden (3 thành viên, 1 lời mời chờ)")

# 3.C: Nhà mình (g-home)
home_grp_id = "g-home"
home_members = [
    {"user_id": admin_uid, "role": "LEADER", "nickname": "Ba", "phone_number": admin_phone, "full_name": "Nguyễn Minh Anh", "camera_ids": None},
    {"user_id": "usr_me", "role": "MEMBER_MANAGER", "nickname": "Mẹ", "phone_number": "+84912000002", "full_name": "Mẹ", "camera_ids": None},
    {"user_id": "usr_bin", "role": "NOTIFIER", "nickname": "Bin (con)", "phone_number": "+84912000003", "full_name": "Bin", "camera_ids": ["cam-living", "cam-kitchen", "cam-front"]},
    {"user_id": "usr_na", "role": "MEMBER", "nickname": "Bé Na (con)", "phone_number": "+84912000004", "full_name": "Bé Na", "camera_ids": ["cam-living"]},
]
db.collection("groups").document(home_grp_id).set({
    "group_id": home_grp_id,
    "group_name": "Nhà mình",
    "is_personal": False,
    "leader_id": admin_uid,
    "address": "Số 45 Đường số 7, KDC Him Lam, Tân Hưng, Q.7, TP.HCM",
    "member_count": len(home_members),
    "camera_count": 3,
    "is_deleted": False,
    "deleted_at": None,
    "purge_at": None,
    "created_at": firestore.SERVER_TIMESTAMP,
    "updated_at": firestore.SERVER_TIMESTAMP,
})
db.collection("groups").document(home_grp_id).collection("subgroups").document("a-home").set({
    "subgroup_id": "a-home",
    "subgroup_name": "Trong nhà",
    "camera_count": 3,
    "created_by": admin_uid,
    "created_at": firestore.SERVER_TIMESTAMP,
})
for m in home_members:
    db.collection("groups").document(home_grp_id).collection("members").document(m["user_id"]).set({
        **m,
        "joined_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    })
    db.collection("users").document(m["user_id"]).collection("group_memberships").document(home_grp_id).set({
        "group_id": home_grp_id,
        "role": m["role"],
        "nickname": m.get("nickname"),
        "updated_at": firestore.SERVER_TIMESTAMP,
    })
print(f"  ✓ Nhóm g-home: Nhà mình (4 thành viên)")

# 3.D: Văn phòng công ty (g-office)
office_grp_id = "g-office"
db.collection("groups").document(office_grp_id).set({
    "group_id": office_grp_id,
    "group_name": "Văn phòng công ty",
    "is_personal": False,
    "leader_id": "usr_long",
    "address": "Tầng 8, Tòa nhà Bitexco, Q.1, TP.HCM",
    "member_count": 3,
    "camera_count": 2,
    "is_deleted": False,
    "deleted_at": None,
    "purge_at": None,
    "created_at": firestore.SERVER_TIMESTAMP,
    "updated_at": firestore.SERVER_TIMESTAMP,
})
db.collection("groups").document(office_grp_id).collection("subgroups").document("a-office").set({
    "subgroup_id": "a-office",
    "subgroup_name": "Kho tầng 1",
    "camera_count": 2,
    "created_by": "usr_long",
    "created_at": firestore.SERVER_TIMESTAMP,
})
office_members = [
    {"user_id": "usr_long", "role": "LEADER", "nickname": "Anh Long", "note": "Giám đốc", "phone_number": "+84909000001", "full_name": "Anh Long", "camera_ids": None},
    {"user_id": "usr_mai", "role": "MEMBER_MANAGER", "nickname": "Chị Mai", "note": "Phụ trách IT", "phone_number": "+84909000002", "full_name": "Chị Mai", "camera_ids": None},
    {"user_id": admin_uid, "role": "MEMBER", "nickname": "Minh Anh", "phone_number": admin_phone, "full_name": "Nguyễn Minh Anh", "camera_ids": ["cam-store", "cam-back"]},
]
for m in office_members:
    db.collection("groups").document(office_grp_id).collection("members").document(m["user_id"]).set({
        **m,
        "joined_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    })
    db.collection("users").document(m["user_id"]).collection("group_memberships").document(office_grp_id).set({
        "group_id": office_grp_id,
        "role": m["role"],
        "nickname": m.get("nickname"),
        "updated_at": firestore.SERVER_TIMESTAMP,
    })
print(f"  ✓ Nhóm g-office: Văn phòng công ty (Minh Anh là MEMBER)")

# 3.E: Chung cư Riverside (g-riverside) - Nơi gửi lời mời J3 tới Minh Anh!
riverside_grp_id = "g-riverside"
db.collection("groups").document(riverside_grp_id).set({
    "group_id": riverside_grp_id,
    "group_name": "Chung cư Riverside",
    "is_personal": False,
    "leader_id": "usr_hoa",
    "address": "Chung cư Riverside, 15 Nguyễn Lương Bằng, Tân Phú, Q.7, TP.HCM",
    "member_count": 1,
    "camera_count": 2,
    "is_deleted": False,
    "deleted_at": None,
    "purge_at": None,
    "created_at": firestore.SERVER_TIMESTAMP,
    "updated_at": firestore.SERVER_TIMESTAMP,
})
db.collection("groups").document(riverside_grp_id).collection("subgroups").document("a-riv-b1").set({
    "subgroup_id": "a-riv-b1",
    "subgroup_name": "Hầm B1",
    "camera_count": 1,
    "created_by": "usr_hoa",
    "created_at": firestore.SERVER_TIMESTAMP,
})
db.collection("groups").document(riverside_grp_id).collection("subgroups").document("a-riv-b2").set({
    "subgroup_id": "a-riv-b2",
    "subgroup_name": "Hầm B2",
    "camera_count": 1,
    "created_by": "usr_hoa",
    "created_at": firestore.SERVER_TIMESTAMP,
})
db.collection("groups").document(riverside_grp_id).collection("members").document("usr_hoa").set({
    "user_id": "usr_hoa",
    "role": "LEADER",
    "nickname": "Chị Hoa",
    "note": "Ban quản trị Riverside",
    "phone_number": "+84909998877",
    "full_name": "Chị Hoa",
    "camera_ids": None,
    "joined_at": firestore.SERVER_TIMESTAMP,
    "updated_at": firestore.SERVER_TIMESTAMP,
})

# Lời mời J3 gửi tới Nguyễn Minh Anh (+84912345678)
invitation_j3 = {
    "invitation_id": "inv-riverside",
    "group_id": riverside_grp_id,
    "group_name": "Chung cư Riverside",
    "group_address": "Chung cư Riverside, 15 Nguyễn Lương Bằng, Tân Phú, Q.7, TP.HCM",
    "phone_number": admin_phone,
    "role": "MEMBER",
    "nickname": "Minh Anh tầng 5",
    "suggested_nickname": "Minh Anh tầng 5",
    "camera_ids": ["cam-riv-b1", "cam-riv-b2"],
    "camera_names": ["Hầm B1", "Hầm B2"],
    "camera_count": 2,
    "invited_by": "usr_hoa",
    "invited_by_name": "Chị Hoa",
    "status": "PENDING",
    "created_at": firestore.SERVER_TIMESTAMP,
}
db.collection("groups").document(riverside_grp_id).collection("invitations").document("inv-riverside").set(invitation_j3)
db.collection("invitation_lookup").document(admin_phone).set({
    "invitation_id": "inv-riverside",
    "group_id": riverside_grp_id,
    "phone_number": admin_phone,
    "status": "PENDING",
    "created_at": firestore.SERVER_TIMESTAMP,
})
db.collection("invitation_lookup").document("inv-riverside").set({
    "invitation_id": "inv-riverside",
    "group_id": riverside_grp_id,
    "phone_number": admin_phone,
    "status": "PENDING",
    "created_at": firestore.SERVER_TIMESTAMP,
})
print(f"  ✓ Nhóm g-riverside: Chung cư Riverside + Lời mời J3 (inv-riverside -> {admin_phone})")

# ==============================================================================
# BƯỚC 4: KHỞI TẠO CAMERAS (12 Camera chuẩn theo các màn hình Figma I5, I8, I12)
# ==============================================================================
print("\n[Bước 4/8] Khởi tạo collection: cameras...")

cameras_data = [
    # Sky Garden Cameras (5 camera theo J7 Figma)
    {
        "cam_id": "cam-charger",
        "group_id": sky_grp_id,
        "subgroup_id": "a-b1",
        "subgroup_name": "Hầm B1",
        "cam_name": "Khu sạc xe",
        "device_name": "Hikvision DS-2CD2143G2-I (4MP IP Dome)",
        "rtsp_url": "rtsp://192.168.1.10:554/stream1",
        "live_stream_url": "https://stream.matpho.vn/live/cam-charger/index.m3u8",
        "preview_snapshot_url": "https://stream.matpho.vn/snapshots/cam-charger.jpg",
        "watch_area": {"left": 0.06, "top": 0.41, "width": 0.47, "height": 0.46},
        "created_by": admin_uid,
        "is_active": True,
        "is_ai_enabled": True,
        "status": "ONLINE",
        "is_deleted": False,
        "deleted_at": None,
        "purge_at": None,
        "last_seen_at": firestore.SERVER_TIMESTAMP,
        "notified_names": ["Phạm Thị Lan"],
    },
    {
        "cam_id": "cam-ramp",
        "group_id": sky_grp_id,
        "subgroup_id": "a-b1",
        "subgroup_name": "Hầm B1",
        "cam_name": "Lối lên dốc",
        "device_name": "Hikvision DS-2CD2143G2-I (4MP IP Dome)",
        "rtsp_url": "rtsp://192.168.1.11:554/stream1",
        "live_stream_url": "https://stream.matpho.vn/live/cam-ramp/index.m3u8",
        "preview_snapshot_url": "https://stream.matpho.vn/snapshots/cam-ramp.jpg",
        "watch_area": {"left": 0.1, "top": 0.1, "width": 0.8, "height": 0.8},
        "created_by": admin_uid,
        "is_active": True,
        "is_ai_enabled": True,
        "status": "ONLINE",
        "is_deleted": False,
        "deleted_at": None,
        "purge_at": None,
        "last_seen_at": firestore.SERVER_TIMESTAMP,
    },
    {
        "cam_id": "cam-lift",
        "group_id": sky_grp_id,
        "subgroup_id": "a-b1",
        "subgroup_name": "Hầm B1",
        "cam_name": "Khu thang máy",
        "device_name": "Hikvision DS-2CD2143G2-I (4MP IP Dome)",
        "rtsp_url": "rtsp://192.168.1.13:554/stream1",
        "live_stream_url": "https://stream.matpho.vn/live/cam-lift/index.m3u8",
        "preview_snapshot_url": "https://stream.matpho.vn/snapshots/cam-lift.jpg",
        "watch_area": None,
        "created_by": admin_uid,
        "is_active": True,
        "is_ai_enabled": True,
        "status": "ONLINE",
        "is_deleted": False,
        "deleted_at": None,
        "purge_at": None,
        "last_seen_at": firestore.SERVER_TIMESTAMP,
    },
    {
        "cam_id": "cam-down",
        "group_id": sky_grp_id,
        "subgroup_id": "a-b2",
        "subgroup_name": "Hầm B2",
        "cam_name": "Lối xuống",
        "device_name": "Hikvision DS-2CD2143G2-I (4MP IP Dome)",
        "rtsp_url": "rtsp://192.168.1.12:554/stream1",
        "live_stream_url": "https://stream.matpho.vn/live/cam-down/index.m3u8",
        "preview_snapshot_url": "https://stream.matpho.vn/snapshots/cam-down.jpg",
        "watch_area": None,
        "created_by": admin_uid,
        "is_active": True,
        "is_ai_enabled": True,
        "status": "OFFLINE",  # OFFLINE cho màn I8 (Mất tín hiệu)
        "is_deleted": False,
        "deleted_at": None,
        "purge_at": None,
        "last_seen_at": firestore.SERVER_TIMESTAMP,
        "notified_names": ["Phạm Thị Lan"],
    },
    {
        "cam_id": "cam-lobby",
        "group_id": sky_grp_id,
        "subgroup_id": "a-lobby",
        "subgroup_name": "Sảnh tầng 1",
        "cam_name": "Sảnh lễ tân",
        "device_name": "Hikvision DS-2CD2143G2-I (4MP IP Dome)",
        "rtsp_url": "rtsp://192.168.1.14:554/stream1",
        "live_stream_url": "https://stream.matpho.vn/live/cam-lobby/index.m3u8",
        "preview_snapshot_url": "https://stream.matpho.vn/snapshots/cam-lobby.jpg",
        "watch_area": None,
        "created_by": admin_uid,
        "is_active": True,
        "is_ai_enabled": True,
        "status": "ONLINE",
        "is_deleted": False,
        "deleted_at": None,
        "purge_at": None,
        "last_seen_at": firestore.SERVER_TIMESTAMP,
    },
    # Home Cameras (3 camera)
    {
        "cam_id": "cam-living",
        "group_id": home_grp_id,
        "subgroup_id": "a-home",
        "subgroup_name": "Trong nhà",
        "cam_name": "Phòng khách",
        "device_name": "Ezviz C6N 1080P",
        "rtsp_url": "rtsp://192.168.0.21:554/stream1",
        "live_stream_url": "https://stream.matpho.vn/live/cam-living/index.m3u8",
        "preview_snapshot_url": "https://stream.matpho.vn/snapshots/cam-living.jpg",
        "status": "ONLINE",
        "is_active": True,
        "is_ai_enabled": True,
        "is_deleted": False,
    },
    {
        "cam_id": "cam-kitchen",
        "group_id": home_grp_id,
        "subgroup_id": "a-home",
        "subgroup_name": "Trong nhà",
        "cam_name": "Bếp",
        "device_name": "Ezviz C6N 1080P",
        "rtsp_url": "rtsp://192.168.0.22:554/stream1",
        "live_stream_url": "https://stream.matpho.vn/live/cam-kitchen/index.m3u8",
        "preview_snapshot_url": "https://stream.matpho.vn/snapshots/cam-kitchen.jpg",
        "status": "ONLINE",
        "is_active": True,
        "is_ai_enabled": True,
        "is_deleted": False,
    },
    {
        "cam_id": "cam-front",
        "group_id": home_grp_id,
        "subgroup_id": "a-home",
        "subgroup_name": "Trong nhà",
        "cam_name": "Cửa trước",
        "device_name": "Imou Bullet 2C",
        "rtsp_url": "rtsp://192.168.0.23:554/stream1",
        "live_stream_url": "https://stream.matpho.vn/live/cam-front/index.m3u8",
        "preview_snapshot_url": "https://stream.matpho.vn/snapshots/cam-front.jpg",
        "status": "ONLINE",
        "is_active": True,
        "is_ai_enabled": True,
        "is_deleted": False,
    },
    # Office Cameras (2 camera)
    {
        "cam_id": "cam-store",
        "group_id": office_grp_id,
        "subgroup_id": "a-office",
        "subgroup_name": "Kho tầng 1",
        "cam_name": "Kho hàng",
        "device_name": "Dahua IPC-HFW2431S",
        "rtsp_url": "rtsp://10.0.0.21:554/stream1",
        "live_stream_url": "https://stream.matpho.vn/live/cam-store/index.m3u8",
        "preview_snapshot_url": "https://stream.matpho.vn/snapshots/cam-store.jpg",
        "status": "ONLINE",
        "is_active": True,
        "is_ai_enabled": True,
        "is_deleted": False,
    },
    {
        "cam_id": "cam-back",
        "group_id": office_grp_id,
        "subgroup_id": "a-office",
        "subgroup_name": "Kho tầng 1",
        "cam_name": "Cửa sau",
        "device_name": "Dahua IPC-HFW2431S",
        "rtsp_url": "rtsp://10.0.0.22:554/stream1",
        "live_stream_url": "https://stream.matpho.vn/live/cam-back/index.m3u8",
        "preview_snapshot_url": "https://stream.matpho.vn/snapshots/cam-back.jpg",
        "status": "ONLINE",
        "is_active": True,
        "is_ai_enabled": True,
        "is_deleted": False,
    },
    # Riverside Cameras (2 camera)
    {
        "cam_id": "cam-riv-b1",
        "group_id": riverside_grp_id,
        "subgroup_id": "a-riv-b1",
        "subgroup_name": "Hầm B1",
        "cam_name": "Hầm B1",
        "device_name": "KBVision KX-2004C4",
        "rtsp_url": "rtsp://192.168.2.11:554/stream1",
        "live_stream_url": "https://stream.matpho.vn/live/cam-riv-b1/index.m3u8",
        "preview_snapshot_url": "https://stream.matpho.vn/snapshots/cam-riv-b1.jpg",
        "status": "ONLINE",
        "is_active": True,
        "is_ai_enabled": True,
        "is_deleted": False,
    },
    {
        "cam_id": "cam-riv-b2",
        "group_id": riverside_grp_id,
        "subgroup_id": "a-riv-b2",
        "subgroup_name": "Hầm B2",
        "cam_name": "Hầm B2",
        "device_name": "KBVision KX-2004C4",
        "rtsp_url": "rtsp://192.168.2.12:554/stream1",
        "live_stream_url": "https://stream.matpho.vn/live/cam-riv-b2/index.m3u8",
        "preview_snapshot_url": "https://stream.matpho.vn/snapshots/cam-riv-b2.jpg",
        "status": "ONLINE",
        "is_active": True,
        "is_ai_enabled": True,
        "is_deleted": False,
    },
]

for cam in cameras_data:
    cam["created_at"] = firestore.SERVER_TIMESTAMP
    cam["updated_at"] = firestore.SERVER_TIMESTAMP
    db.collection("cameras").document(cam["cam_id"]).set(cam)
    print(f"  ✓ Camera created: {cam['cam_id']} ({cam['cam_name']} - {cam['group_id']})")

# ==============================================================================
# BƯỚC 5: KHỞI TẠO FIRE_ALERTS (5 Tình huống sự cố kinh điển Figma & Test Cases)
# ==============================================================================
print("\n[Bước 5/8] Khởi tạo collection: fire_alerts...")

alerts_to_seed = [
    # 1. Sự cố ĐANG DIỄN RA: Cháy pin xe điện tại trạm sạc (F2, G1) -> Dùng để test còi hú realtime!
    {
        "alert_id": "alt_demo_fire_01",
        "group_id": sky_grp_id,
        "subgroup_id": "a-b1",
        "subgroup_name": "Hầm B1",
        "location_name": "Hầm B1 · Khu sạc xe",
        "cam_id": "cam-charger",
        "cam_name": "Khu sạc xe",
        "summary": "Cháy pin xe điện tại trạm sạc",
        "detail": "Phát hiện khói và ngọn lửa bùng phát từ cụm sạc số 3 hầm B1.",
        "call_script": "Cháy xe máy điện tại khu sạc hầm B1 Chung cư Sky Garden, 12 Nguyễn Văn Linh, Q.7",
        "sign": "BOTH",
        "check_count": 3,
        "confidence": 0.94,
        "status": "CONFIRMED",
        "verification": "VERIFIED",
        "address": "Hầm B1, chung cư Sky Garden, 12 Nguyễn Văn Linh, Q.7",
        "fire_image_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Fcharger_fire.jpg?alt=media",
        "still_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Fcharger_fire.jpg?alt=media",
        "escalation_level": 1,
        "steps": [
            {"kind": "DETECTED", "at": "2026-11-07T07:15:00Z", "label": "Camera phát hiện dấu hiệu nhiệt & khói"},
            {"kind": "IMAGE_SENT", "at": "2026-11-07T07:15:00.500Z", "label": "Gửi snapshot về AI Service (+0.5s)"},
            {"kind": "AI_VERIFIED", "at": "2026-11-07T07:15:01.200Z", "label": "Mô hình xác nhận độ tin cậy 94%"},
            {"kind": "ALERT_TRIGGERED", "at": "2026-11-07T07:15:02.000Z", "label": "Kích hoạt còi hú & push FCM"},
        ],
        "timeline_snapshots": [
            {
                "snapshot_id": "snap_01",
                "image_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Fcharger_fire.jpg?alt=media",
                "confidence": 0.94,
                "timestamp": "2026-11-07T07:15:00Z",
                "bbox": [0.15, 0.35, 0.25, 0.40]
            }
        ],
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    },
    # 2. Sự cố Cháy thật đã dập tắt & đã gọi 114 (F2, G1)
    {
        "alert_id": "evt-fire",
        "group_id": sky_grp_id,
        "subgroup_id": "a-b1",
        "subgroup_name": "Hầm B1",
        "cam_id": "cam-charger",
        "cam_name": "Khu sạc xe",
        "location_name": "Hầm B1 · Khu sạc xe",
        "summary": "Lửa ở xe máy",
        "detail": "Lửa và khói ở xe máy bên trái khu trạm sạc.",
        "sign": "FIRE",
        "confidence": 0.93,
        "check_count": 2,
        "status": "RESOLVED",
        "verification": "CONFIRMED_FIRE",
        "address": "Hầm B1, chung cư Sky Garden, 12 Nguyễn Văn Linh, Q.7",
        "fire_image_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Fcharger_fire.jpg?alt=media",
        "called_114_at": "2025-10-23T21:47:35Z",
        "resolved_at": "2025-10-23T22:15:00Z",
        "resolved_by": admin_uid,
        "resolved_by_name": "Nguyễn Minh Anh",
        "resolution_note": "Bảo vệ đã dùng bình bột dập tắt kịp thời, đã báo 114",
        "escalation_level": 1,
        "timeline_snapshots": [
            {
                "snapshot_id": "snap-fire-1",
                "image_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Fcharger_fire.jpg?alt=media",
                "timestamp": "2025-10-23T21:47:31Z",
                "bbox": [0.15, 0.35, 0.25, 0.40],
                "confidence": 0.93,
            }
        ],
        "steps": [
            {"kind": "DETECTED", "at": "2025-10-23T21:47:31Z", "label": "Camera phát hiện dấu hiệu ngọn lửa"},
            {"kind": "IMAGE_SENT", "at": "2025-10-23T21:47:31.400Z", "label": "Gửi ảnh +0,4 s"},
            {"kind": "CONFIRMED_FIRE", "at": "2025-10-23T21:47:36.100Z", "label": "Xác nhận cháy +5,1 s"},
            {"kind": "NOTIFIED", "at": "2025-10-23T21:47:37.800Z", "label": "Báo tới điện thoại +6,8 s"},
        ],
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    },
    # 3. Báo nhầm AI bỏ qua: Đèn xe chiếu (G5, E4) -> status: NEW, verification: SUPPRESSED
    {
        "alert_id": "evt-dismissed",
        "group_id": sky_grp_id,
        "subgroup_id": "a-b1",
        "subgroup_name": "Hầm B1",
        "cam_id": "cam-charger",
        "cam_name": "Khu sạc xe",
        "location_name": "Hầm B1 · Khu sạc xe",
        "summary": "Đèn xe chiếu lên tường",
        "detail": "AI kiểm tra lại 2 lần, không thấy khói hay lửa.",
        "sign": "LIGHT",
        "confidence": 0.45,
        "check_count": 2,
        "status": "NEW",
        "verification": "SUPPRESSED",
        "address": "Hầm B1, chung cư Sky Garden, 12 Nguyễn Văn Linh, Q.7",
        "fire_image_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Fcar_headlight.jpg?alt=media",
        "escalation_level": 0,
        "timeline_snapshots": [
            {
                "snapshot_id": "snap-dismissed-1",
                "image_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Fcar_headlight.jpg?alt=media",
                "timestamp": "2025-10-23T21:40:12Z",
                "bbox": [0.20, 0.40, 0.30, 0.25],
                "confidence": 0.45,
            }
        ],
        "steps": [
            {"kind": "DETECTED", "at": "2025-10-23T21:40:12Z", "label": "Phát hiện ánh sáng nghi ngờ"},
            {"kind": "CONFIRMED_NOT_FIRE", "at": "2025-10-23T21:40:16.600Z", "label": "Xác nhận không cháy +4,6 s"},
        ],
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    },
    # 4. Nghi ngờ khói chưa xác định (F4) -> status: NEW, verification: UNVERIFIED
    {
        "alert_id": "evt-unverified",
        "group_id": sky_grp_id,
        "subgroup_id": "a-b2",
        "subgroup_name": "Hầm B2",
        "cam_id": "cam-down",
        "cam_name": "Lối xuống",
        "location_name": "Hầm B2 · Lối xuống",
        "summary": "Khói mờ ở lối xuống",
        "detail": "Camera phát hiện vùng mờ nghi là khói. AI đang theo dõi thêm.",
        "sign": "SMOKE",
        "confidence": 0.61,
        "check_count": 1,
        "status": "NEW",
        "verification": "UNVERIFIED",
        "address": "Hầm B1, chung cư Sky Garden, 12 Nguyễn Văn Linh, Q.7",
        "fire_image_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Fsmoke_faint.jpg?alt=media",
        "escalation_level": 0,
        "timeline_snapshots": [
            {
                "snapshot_id": "snap-unverified-1",
                "image_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Fsmoke_faint.jpg?alt=media",
                "timestamp": "2025-10-22T19:02:00Z",
                "bbox": [0.30, 0.20, 0.40, 0.50],
                "confidence": 0.61,
            }
        ],
        "steps": [
            {"kind": "DETECTED", "at": "2025-10-22T19:02:00Z", "label": "Phát hiện khói mờ"},
            {"kind": "IMAGE_SENT", "at": "2025-10-22T19:02:00.400Z", "label": "Gửi ảnh +0,4 s"},
        ],
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    },
    # 5. Người dùng đánh dấu Báo nhầm (G1) -> status: FALSE_ALARM, verification: CONFIRMED_NOT_FIRE
    {
        "alert_id": "evt-false-alarm",
        "group_id": sky_grp_id,
        "subgroup_id": "a-b1",
        "subgroup_name": "Hầm B1",
        "cam_id": "cam-charger",
        "cam_name": "Khu sạc xe",
        "location_name": "Hầm B1 · Khu sạc xe",
        "summary": "Hơi nước từ ống xả",
        "detail": "Hơi nước từ ống xả xe nổ máy trong hầm kín.",
        "sign": "SMOKE",
        "confidence": 0.58,
        "check_count": 1,
        "status": "FALSE_ALARM",
        "verification": "CONFIRMED_NOT_FIRE",
        "address": "Hầm B1, chung cư Sky Garden, 12 Nguyễn Văn Linh, Q.7",
        "fire_image_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Fsteam_exhaust.jpg?alt=media",
        "escalation_level": 0,
        "resolved_by": admin_uid,
        "resolved_by_name": "Nguyễn Minh Anh",
        "resolution_note": "Báo nhầm, chỉ là hơi nước xe hơi",
        "timeline_snapshots": [
            {
                "snapshot_id": "snap-false-1",
                "image_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Fsteam_exhaust.jpg?alt=media",
                "timestamp": "2025-10-23T20:10:00Z",
                "bbox": [0.40, 0.50, 0.20, 0.20],
                "confidence": 0.58,
            }
        ],
        "steps": [
            {"kind": "DETECTED", "at": "2025-10-23T20:10:00Z", "label": "Phát hiện khói nghi vấn"},
            {"kind": "RESOLVED", "at": "2025-10-23T20:12:00Z", "label": "Người dùng xác nhận báo nhầm"}
        ],
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    },
]

for alt in alerts_to_seed:
    db.collection("fire_alerts").document(alt["alert_id"]).set(alt)
    print(f"  ✓ Alert created: {alt['alert_id']} ({alt['summary']} - status={alt['status']})")

# ==============================================================================
# BƯỚC 6: KHỞI TẠO AUDIT LOGS
# ==============================================================================
print("\n[Bước 6/8] Khởi tạo collection: audit_logs...")

db.collection("audit_logs").document("log_demo_init_01").set({
    "log_id": "log_demo_init_01",
    "group_id": sky_grp_id,
    "actor_id": admin_uid,
    "action": "SYSTEM_INITIALIZED",
    "target_entity": f"group:{sky_grp_id}",
    "details": {
        "reason": "Clean & reset with official test fixtures matching DATABASE_DESIGN.md v3.2",
        "seeded_groups": 5,
        "seeded_cameras": 12,
        "seeded_alerts": 5,
    },
    "created_at": firestore.SERVER_TIMESTAMP,
})
print("  ✓ Audit Log created: log_demo_init_01")

print("\n================================================================================")
print("🎉 HOÀN THÀNH: ĐÃ DỌN SẠCH VÀ SEED ĐẦY ĐỦ 100% CẤU TRÚC DATABASE TEST!")
print("================================================================================")
