"""Luật thuần của cổng chuyển tiếp event FireWatch (src/relay_rules.py): không cần PyAV."""
import importlib.util
from pathlib import Path

_DUONG = Path(__file__).resolve().parents[1] / "src" / "relay_rules.py"
_spec = importlib.util.spec_from_file_location("relay_rules", _DUONG)
relay_rules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(relay_rules)
match_cam_id = relay_rules.match_cam_id
bo_su_kien_bi_tu_choi = relay_rules.bo_su_kien_bi_tu_choi
la_dia_chi_noi_bo = relay_rules.la_dia_chi_noi_bo

CAMS = [
    {"cam_id": "cam_10", "cam_name": "Hầm B1"},
    {"cam_id": "cam_1", "cam_name": "ham-b1-cam03"},
    {"cam_id": "cam_gate_01", "cam_name": "Cổng"},
]


def test_khop_cam_id_chinh_xac_khong_khop_chuoi_con():
    # "cam_1" xếp sau "cam_10": so khớp chuỗi con cũ sẽ trả cam_10 (sai camera).
    assert match_cam_id("cam_1", CAMS) == "cam_1"
    assert match_cam_id("cam_10", CAMS) == "cam_10"
    assert match_cam_id("cam", CAMS) == "cam"


def test_khop_ten_camera_chinh_xac():
    assert match_cam_id("HAM-B1-CAM03", CAMS) == "cam_1"
    assert match_cam_id("Hầm B1", CAMS) == "cam_10"
    assert match_cam_id("Hầm", CAMS) == "Hầm"


def test_thieu_id():
    assert match_cam_id(None, CAMS) == "cam_unknown"
    assert match_cam_id("", CAMS) == "cam_unknown"


def test_hang_cho_bo_4xx_tru_auth_va_rate_limit():
    assert bo_su_kien_bi_tu_choi(404) is True
    assert bo_su_kien_bi_tu_choi(422) is True
    for ma in (401, 403, 408, 429, 500, 502, 503):
        assert bo_su_kien_bi_tu_choi(ma) is False, ma


def test_dia_chi_noi_bo():
    assert la_dia_chi_noi_bo("http://localhost:8888")
    assert la_dia_chi_noi_bo("http://127.0.0.1:8888/live/x")
    assert la_dia_chi_noi_bo("http://mediamtx:8888")
    assert not la_dia_chi_noi_bo("http://192.168.1.20:8888")
    assert not la_dia_chi_noi_bo("https://abc.trycloudflare.com")
