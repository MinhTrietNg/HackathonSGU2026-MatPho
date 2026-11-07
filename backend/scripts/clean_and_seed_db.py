#!/usr/bin/env python3
"""
Clean and Seed Cloud Firestore Database with official Test Fixtures.
Project: matpho-c7e77
"""

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
print("🧹 DỌN SẠCH DATABASE & SEED DỮ LIỆU TEST CHUẨN LÊN CLOUD FIRESTORE")
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

def delete_collection(coll_ref, batch_size=50):
    docs = list(coll_ref.limit(batch_size).stream())
    deleted = 0
    while docs:
        batch = db.batch()
        for doc in docs:
            # Delete any known subcollections
            for sub_name in ["members", "subgroups", "invitations"]:
                sub_ref = doc.reference.collection(sub_name)
                for sub_doc in sub_ref.stream():
                    batch.delete(sub_doc.reference)
            batch.delete(doc.reference)
            deleted += 1
        batch.commit()
        docs = list(coll_ref.limit(batch_size).stream())
    return deleted

print("\n[Bước 1/2] Đang xóa sạch các documents cũ trong database...")
root_collections = ["users", "groups", "cameras", "fire_alerts", "audit_logs", "phone_registry", "invitation_lookup"]

for col_name in root_collections:
    col_ref = db.collection(col_name)
    count = delete_collection(col_ref)
    print(f"  🗑️ Đã dọn collection [{col_name}]: {count} documents")

print("✅ Đã dọn dẹp sạch toàn bộ collections chính!")

print("\n[Bước 2/2] Bắt đầu gieo mầm (Seed) bộ dữ liệu test chuẩn (Figma & Scenario)...")

now = datetime.now(timezone.utc)
salt = bcrypt.gensalt(rounds=12)
demo_password_hash = bcrypt.hashpw(b"matkhau123", salt).decode("utf-8")

# 1. Seed phone_registry & users
accounts = [
    ("usr_leader_matpho_01", "+84912345678", "Nguyễn Minh Anh"),
    ("usr_lan", "+84908000001", "Phạm Thị Lan"),
    ("usr_tuan", "+84912000678", "Trần Anh Tuấn"),
    ("usr_me", "+84912000002", "Mẹ"),
    ("usr_bin", "+84912000003", "Bin"),
    ("usr_na", "+84912000004", "Bé Na"),
    ("usr_long", "+84909000001", "Anh Long"),
    ("usr_mai", "+84909000002", "Chị Mai"),
    ("usr_hoa", "+84909998877", "Chị Hoa"),
]

for uid, phone, name in accounts:
    db.collection("phone_registry").document(phone).set({
        "user_id": uid,
        "created_at": firestore.SERVER_TIMESTAMP,
    })
    
    personal_grp_id = f"grp_personal_{uid}" if uid == "usr_leader_matpho_01" else None
    user_data = {
        "user_id": uid,
        "phone_number": phone,
        "full_name": name,
        "password_hash": demo_password_hash,
        "failed_attempts": 0,
        "locked_until": None,
        "loud_when_silent": True,
        "fcm_tokens": ["fcm_demo_token_admin"] if uid == "usr_leader_matpho_01" else [],
        "personal_group_id": personal_grp_id,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    db.collection("users").document(uid).set(user_data)
    print(f"  ✓ User created: {uid} ({name} - {phone})")

# 2. Seed Groups & Subcollections
admin_uid = "usr_leader_matpho_01"
sky_grp_id = "grp-sky-garden"
home_grp_id = "grp-home"
office_grp_id = "grp-office"

groups_data = [
    {
        "group_id": sky_grp_id,
        "group_name": "Chung cư Sky Garden",
        "is_personal": False,
        "leader_id": admin_uid,
        "address": "12 Nguyễn Văn Linh, Q.7, TP.HCM",
        "member_count": 3,
        "camera_count": 3,
        "is_deleted": False,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
        "subgroups": [
            {"subgroup_id": "a-b1", "subgroup_name": "Hầm B1", "description": "Khu để xe máy và sạc xe điện", "camera_count": 2},
            {"subgroup_id": "a-lobby", "subgroup_name": "Sảnh A", "description": "Sảnh lễ tân và thang máy", "camera_count": 1},
        ],
        "members": [
            {"user_id": admin_uid, "role": "LEADER", "nickname": "Trưởng BQL", "phone_number": "+84912345678", "full_name": "Nguyễn Minh Anh", "camera_ids": None},
            {"user_id": "usr_lan", "role": "MEMBER_MANAGER", "nickname": "Chị Lan BQL", "phone_number": "+84908000001", "full_name": "Phạm Thị Lan", "camera_ids": None},
            {"user_id": "usr_tuan", "role": "MEMBER", "nickname": "Tuấn Kỹ Thuật", "phone_number": "+84912000678", "full_name": "Trần Anh Tuấn", "camera_ids": ["cam-charger"]},
        ],
        "invitations": [
            {
                "invitation_id": "inv_sky_01",
                "group_id": sky_grp_id,
                "group_name": "Chung cư Sky Garden",
                "phone_number": "+84987654321",
                "role": "NOTIFIER",
                "nickname": "Bảo vệ trực đêm",
                "invited_by": admin_uid,
                "invited_by_name": "Nguyễn Minh Anh",
                "status": "PENDING",
                "created_at": firestore.SERVER_TIMESTAMP,
            }
        ]
    },
    {
        "group_id": f"grp_personal_{admin_uid}",
        "group_name": "Nhóm Cá Nhân",
        "is_personal": True,
        "leader_id": admin_uid,
        "address": "Nhà riêng",
        "member_count": 1,
        "camera_count": 1,
        "is_deleted": False,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
        "subgroups": [
            {"subgroup_id": "sub_pers_1", "subgroup_name": "Phòng khách", "description": "Khu vực tầng trệt", "camera_count": 1}
        ],
        "members": [
            {"user_id": admin_uid, "role": "LEADER", "nickname": "Tôi", "phone_number": "+84912345678", "full_name": "Nguyễn Minh Anh", "camera_ids": None}
        ],
        "invitations": []
    }
]

for grp in groups_data:
    grp_id = grp["group_id"]
    subgroups = grp.pop("subgroups")
    members = grp.pop("members")
    invitations = grp.pop("invitations")
    
    db.collection("groups").document(grp_id).set(grp)
    
    for sub in subgroups:
        sub["created_by"] = admin_uid
        sub["created_at"] = firestore.SERVER_TIMESTAMP
        db.collection("groups").document(grp_id).collection("subgroups").document(sub["subgroup_id"]).set(sub)
        
    for mem in members:
        mem["joined_at"] = firestore.SERVER_TIMESTAMP
        mem["updated_at"] = firestore.SERVER_TIMESTAMP
        db.collection("groups").document(grp_id).collection("members").document(mem["user_id"]).set(mem)
        
    for inv in invitations:
        db.collection("groups").document(grp_id).collection("invitations").document(inv["invitation_id"]).set(inv)
        db.collection("invitation_lookup").document(inv["phone_number"]).set({
            "invitation_id": inv["invitation_id"],
            "group_id": grp_id,
            "status": "PENDING"
        })
    print(f"  ✓ Group created: {grp_id} ({grp['group_name']})")

# 3. Seed Cameras
cameras_data = [
    {
        "cam_id": "cam-charger",
        "group_id": sky_grp_id,
        "subgroup_id": "a-b1",
        "subgroup_name": "Hầm B1",
        "cam_name": "Khu sạc xe máy điện",
        "device_name": "Hikvision DS-2CD2143G2-I (4MP)",
        "rtsp_url": "rtsp://admin:matpho123@192.168.1.101:554/live",
        "live_stream_url": "http://localhost:8888/live/cam-charger/index.m3u8",
        "watch_area": {"left": 0.15, "top": 0.20, "width": 0.70, "height": 0.65},
        "notified_names": ["Nguyễn Minh Anh", "Phạm Thị Lan", "Trần Anh Tuấn"],
        "created_by": admin_uid,
        "is_active": True,
        "is_ai_enabled": True,
        "status": "ONLINE",
        "is_deleted": False,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    },
    {
        "cam_id": "cam-b1-ramp",
        "group_id": sky_grp_id,
        "subgroup_id": "a-b1",
        "subgroup_name": "Hầm B1",
        "cam_name": "Dốc lên hầm B1",
        "device_name": "Dahua IPC-HFW2431S-S-S2",
        "rtsp_url": "rtsp://admin:matpho123@192.168.1.102:554/live",
        "live_stream_url": "http://localhost:8888/live/cam-b1-ramp/index.m3u8",
        "watch_area": {"left": 0.1, "top": 0.1, "width": 0.8, "height": 0.8},
        "notified_names": ["Nguyễn Minh Anh", "Phạm Thị Lan"],
        "created_by": admin_uid,
        "is_active": True,
        "is_ai_enabled": True,
        "status": "ONLINE",
        "is_deleted": False,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    },
    {
        "cam_id": "cam-lobby",
        "group_id": sky_grp_id,
        "subgroup_id": "a-lobby",
        "subgroup_name": "Sảnh A",
        "cam_name": "Sảnh chính lễ tân",
        "device_name": "Ezviz C6N 1080P",
        "rtsp_url": "rtsp://admin:matpho123@192.168.1.103:554/live",
        "live_stream_url": "http://localhost:8888/live/cam-lobby/index.m3u8",
        "watch_area": None,
        "notified_names": ["Nguyễn Minh Anh", "Phạm Thị Lan"],
        "created_by": admin_uid,
        "is_active": True,
        "is_ai_enabled": False,
        "status": "ONLINE",
        "is_deleted": False,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    },
    {
        "cam_id": "cam-pers-living",
        "group_id": f"grp_personal_{admin_uid}",
        "subgroup_id": "sub_pers_1",
        "subgroup_name": "Phòng khách",
        "cam_name": "Camera phòng khách gia đình",
        "device_name": "Imou Ranger 2",
        "rtsp_url": "rtsp://admin:matpho123@192.168.1.200:554/live",
        "live_stream_url": "http://localhost:8888/live/cam-pers-living/index.m3u8",
        "watch_area": None,
        "notified_names": ["Nguyễn Minh Anh"],
        "created_by": admin_uid,
        "is_active": True,
        "is_ai_enabled": True,
        "status": "ONLINE",
        "is_deleted": False,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
]

for cam in cameras_data:
    db.collection("cameras").document(cam["cam_id"]).set(cam)
    print(f"  ✓ Camera created: {cam['cam_id']} ({cam['cam_name']})")

# 4. Seed Fire Alerts
alerts_data = [
    {
        "alert_id": "alt_demo_fire_01",
        "group_id": sky_grp_id,
        "subgroup_id": "a-b1",
        "subgroup_name": "Hầm B1",
        "location_name": "Hầm B1 · Khu sạc xe",
        "cam_id": "cam-charger",
        "cam_name": "Khu sạc xe máy điện",
        "summary": "Cháy pin xe điện tại trạm sạc",
        "detail": "Phát hiện khói và ngọn lửa bùng phát từ cụm sạc số 3 hầm B1.",
        "call_script": "Cháy xe máy điện tại khu sạc hầm B1 Chung cư Sky Garden, 12 Nguyễn Văn Linh, Q.7",
        "sign": "BOTH",
        "check_count": 3,
        "confidence": 0.94,
        "status": "CONFIRMED",
        "verification": "VERIFIED",
        "fire_image_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Ffire_charger.jpg?alt=media",
        "still_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Ffire_charger.jpg?alt=media",
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
                "image_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Ffire_charger.jpg?alt=media",
                "confidence": 0.94,
                "timestamp": "2026-11-07T07:15:00Z",
                "bbox": [0.25, 0.35, 0.30, 0.45]
            }
        ],
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    },
    {
        "alert_id": "alt_demo_smoke_02",
        "group_id": sky_grp_id,
        "subgroup_id": "a-b1",
        "subgroup_name": "Hầm B1",
        "location_name": "Hầm B1 · Dốc lên",
        "cam_id": "cam-b1-ramp",
        "cam_name": "Dốc lên hầm B1",
        "summary": "Khói nhẹ gần khu vực dốc lên",
        "detail": "Khói mờ từ ống xả phương tiện tải trọng lớn.",
        "call_script": None,
        "sign": "SMOKE",
        "check_count": 1,
        "confidence": 0.62,
        "status": "FALSE_ALARM",
        "verification": "CONFIRMED_NOT_FIRE",
        "fire_image_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Fsteam_exhaust.jpg?alt=media",
        "still_url": "https://firebasestorage.googleapis.com/v0/b/matpho-c7e77.firebasestorage.app/o/demo%2Fsteam_exhaust.jpg?alt=media",
        "escalation_level": 0,
        "resolved_by": admin_uid,
        "resolved_by_name": "Nguyễn Minh Anh",
        "resolution_note": "Báo nhầm, khói ống xả xe tải nổ máy.",
        "steps": [
            {"kind": "DETECTED", "at": "2026-11-06T14:20:00Z", "label": "Phát hiện khói mờ"},
            {"kind": "RESOLVED", "at": "2026-11-06T14:21:00Z", "label": "Xác nhận báo nhầm"}
        ],
        "timeline_snapshots": [],
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
]

for alt in alerts_data:
    db.collection("fire_alerts").document(alt["alert_id"]).set(alt)
    print(f"  ✓ Alert created: {alt['alert_id']} ({alt['summary']})")

# 5. Seed Audit Logs
log_data = {
    "log_id": "log_demo_init_01",
    "group_id": sky_grp_id,
    "actor_id": admin_uid,
    "action": "SYSTEM_INITIALIZED",
    "target_entity": f"group:{sky_grp_id}",
    "details": {"reason": "Clean & reset with official test fixtures"},
    "created_at": firestore.SERVER_TIMESTAMP
}
db.collection("audit_logs").document(log_data["log_id"]).set(log_data)
print(f"  ✓ Audit Log created: {log_data['log_id']}")

print("\n================================================================================")
print("🎉 HOÀN THÀNH: ĐÃ DỌN SẠCH VÀ SEED DỮ LIỆU TEST CHUẨN THÀNH CÔNG!")
print("================================================================================")
