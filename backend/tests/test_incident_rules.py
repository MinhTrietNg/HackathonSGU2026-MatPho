"""
Unit tests: luật "một camera một sự cố đang mở" (services/incident_rules.py).
Thuần Python, không cần Firestore hay Firebase.
"""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Nạp thẳng từ file: gói src.services kéo theo firebase_admin, không cần cho test này.
_DUONG = Path(__file__).resolve().parents[1] / "src" / "services" / "incident_rules.py"
_spec = importlib.util.spec_from_file_location("incident_rules", _DUONG)
incident_rules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(incident_rules)
chon_su_co_dang_mo = incident_rules.chon_su_co_dang_mo
cua_so_ghep_s = incident_rules.cua_so_ghep_s
moc_hoat_dong = incident_rules.moc_hoat_dong
tai_bung = incident_rules.tai_bung

NOW = datetime(2026, 11, 8, 10, 0, 0, tzinfo=timezone.utc)


def _alert(alert_id, cam_id="cam_a", status="NEW", event_id=None, event_ids=None,
           truoc_s=0, last_seen=None):
    created = NOW - timedelta(seconds=truoc_s)
    return {
        "alert_id": alert_id,
        "cam_id": cam_id,
        "status": status,
        "event_id": event_id or alert_id.replace("alt_", ""),
        "event_ids": event_ids if event_ids is not None else [event_id or alert_id.replace("alt_", "")],
        "created_at": created,
        "updated_at": created,
        "last_seen_ts": last_seen,
    }


def test_cung_event_id_luon_ghep_ke_ca_da_resolved():
    docs = [_alert("alt_e1", status="RESOLVED", truoc_s=5000)]
    chon = chon_su_co_dang_mo(docs, event_id="e1", cam_id="cam_a", now=NOW, cua_so_s=900)
    assert chon["alert_id"] == "alt_e1"


def test_event_id_trong_danh_sach_alias():
    docs = [_alert("alt_e1", event_ids=["e1", "e2"])]
    chon = chon_su_co_dang_mo(docs, event_id="e2", cam_id="cam_a", now=NOW, cua_so_s=900)
    assert chon["alert_id"] == "alt_e1"


def test_event_id_moi_ghep_vao_alert_dang_mo_cua_camera():
    """FireWatch chạy lại hoặc clip lặp: event_id mới, cùng camera, alert còn mở -> ghép."""
    docs = [_alert("alt_e1", truoc_s=200)]
    chon = chon_su_co_dang_mo(docs, event_id="e9", cam_id="cam_a", now=NOW, cua_so_s=900)
    assert chon["alert_id"] == "alt_e1"
    assert tai_bung(chon, "created", "e9") is True
    assert tai_bung(chon, "updated", "e9") is False
    assert tai_bung(chon, "created", "e1") is False


def test_alert_mo_qua_cua_so_thi_tao_moi():
    docs = [_alert("alt_e1", truoc_s=901)]
    assert chon_su_co_dang_mo(docs, event_id="e9", cam_id="cam_a", now=NOW, cua_so_s=900) is None


def test_last_seen_ts_moi_giu_alert_cu_con_song():
    moi = (NOW - timedelta(seconds=30)).isoformat()
    docs = [_alert("alt_e1", truoc_s=5000, last_seen=moi)]
    chon = chon_su_co_dang_mo(docs, event_id="e9", cam_id="cam_a", now=NOW, cua_so_s=900)
    assert chon["alert_id"] == "alt_e1"
    assert moc_hoat_dong(docs[0]) == NOW - timedelta(seconds=30)


def test_khong_ghep_sang_camera_khac_hay_alert_da_dong():
    docs = [
        _alert("alt_x", cam_id="cam_b", truoc_s=10),
        _alert("alt_r", status="RESOLVED", truoc_s=10),
        _alert("alt_f", status="FALSE_ALARM", truoc_s=10),
    ]
    assert chon_su_co_dang_mo(docs, event_id="e9", cam_id="cam_a", now=NOW, cua_so_s=900) is None


def test_chon_alert_hoat_dong_gan_nhat_khi_co_nhieu():
    docs = [_alert("alt_cu", truoc_s=600), _alert("alt_moi", truoc_s=60)]
    chon = chon_su_co_dang_mo(docs, event_id=None, cam_id="cam_a", now=NOW, cua_so_s=900)
    assert chon["alert_id"] == "alt_moi"


def test_cua_so_tu_bien_moi_truong(monkeypatch):
    monkeypatch.setenv("INCIDENT_MERGE_WINDOW_S", "120")
    assert cua_so_ghep_s() == 120
    monkeypatch.setenv("INCIDENT_MERGE_WINDOW_S", "xyz")
    assert cua_so_ghep_s() == 900
    monkeypatch.delenv("INCIDENT_MERGE_WINDOW_S")
    assert cua_so_ghep_s() == 900
