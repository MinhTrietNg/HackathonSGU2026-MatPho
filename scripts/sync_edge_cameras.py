"""Auto-sync 3 RTSP cameras into Edge Backend (:8090).

CHỈ để thử luồng video: các camera này chỉ có ở edge, backend không biết chúng, nên
FireWatch vẫn phát hiện cháy nhưng backend trả 404 CAMERA_NOT_FOUND và app không hú.
Muốn thử báo cháy tới app: tạo camera trong app với RTSP trỏ vào luồng nguồn.

Cameras:
- cam-kitchen : Nhà Bếp (samples/street_fire.mp4 -> Fire scene for AI detection)
- cam-living  : Phòng Khách (samples/street_normal.mp4 -> Normal street scene)
- cam-front   : Cổng Trước (samples/street_normal.mp4 -> Normal street scene)
"""

import json
import sys
import urllib.request

EDGE_CAMERAS = [
    {
        "cam_id": "cam-kitchen",
        "cam_name": "Nha Bep (Kitchen)",
        "rtsp_url": "rtsp://mediamtx:8554/source/cam-kitchen",
    },
    {
        "cam_id": "cam-living",
        "cam_name": "Phong Khach (Living Room)",
        "rtsp_url": "rtsp://mediamtx:8554/source/cam-living",
    },
    {
        "cam_id": "cam-front",
        "cam_name": "Cong Truoc (Front Yard)",
        "rtsp_url": "rtsp://mediamtx:8554/source/cam-front",
    },
]

SECRET = "secure_internal_key_for_ai_and_worker_communication"
ENDPOINT = "http://localhost:8090/api/v1/edge/cameras"


def sync_cameras():
    print("[*] Dang tu dong dong bo 3 camera sang Edge Backend (:8090)...")
    success_count = 0
    for cam in EDGE_CAMERAS:
        payload = json.dumps(
            {
                "cam_id": cam["cam_id"],
                "cam_name": cam["cam_name"],
                "rtsp_url": cam["rtsp_url"],
                "is_active": True,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            ENDPOINT,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-internal-secret": SECRET,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                print(f"  [OK] Dong bo thanh cong: {cam['cam_id']} -> {cam['rtsp_url']}")
                success_count += 1
        except Exception as exc:
            print(f"  [CANH BAO] Khong the dong bo {cam['cam_id']}: {exc}")

    if success_count == len(EDGE_CAMERAS):
        print("[THANH CONG] Toan bo 3 camera da duoc cap nhat vao Edge Database.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(sync_cameras())
