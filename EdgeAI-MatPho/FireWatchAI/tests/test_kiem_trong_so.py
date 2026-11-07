"""tools/kiem_trong_so.py: kiểm SHA-256 trọng số theo models/README.md (3D)."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("kiem_trong_so",
                                               GOC / "tools" / "kiem_trong_so.py")
kts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kts)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _models(tmp: Path, pt: bytes | None, onnx: bytes | None,
            sha_pt: str, sha_onnx: str) -> Path:
    d = tmp / "models"
    d.mkdir()
    (d / "README.md").write_text(
        "| File `.pt` | `m.pt`, SHA-256 `" + sha_pt + "` |\n"
        "| File ONNX 640 | `m_640.onnx`, SHA-256 `" + sha_onnx + "` |\n",
        encoding="utf-8")
    if pt is not None:
        (d / "m.pt").write_bytes(pt)
    if onnx is not None:
        (d / "m_640.onnx").write_bytes(onnx)
    return d


def test_doc_bang_that_cua_repo_co_dung_hai_file_v2():
    bang = kts.doc_bang(GOC / "models" / "README.md")
    assert bang["firewatch-v2.0.pt"].startswith("58def3d0")
    assert bang["firewatch-v2.0_640.onnx"].startswith("9d2e93b2")


def test_dung_sha_thi_chay(tmp_path):
    d = _models(tmp_path, b"pt", b"onnx", _sha(b"pt"), _sha(b"onnx"))
    assert kts.main(["--models", str(d)]) == 0


def test_lech_hoac_thieu_pt_thi_khong_chay(tmp_path, capsys):
    d = _models(tmp_path, b"pt-khac", b"onnx", _sha(b"pt"), _sha(b"onnx"))
    assert kts.main(["--models", str(d)]) == 1
    assert "lệch SHA-256" in capsys.readouterr().err
    (d / "m.pt").unlink()
    assert kts.main(["--models", str(d)]) == 1


def test_onnx_lech_hoac_thieu_chi_canh_bao(tmp_path, capsys):
    d = _models(tmp_path, b"pt", b"onnx-export-lai", _sha(b"pt"), _sha(b"onnx"))
    assert kts.main(["--models", str(d)]) == 0
    assert "export lại" in capsys.readouterr().out
    (d / "m_640.onnx").unlink()
    assert kts.main(["--models", str(d)]) == 0


def test_readme_khong_co_dong_sha_thi_khong_chay(tmp_path):
    d = tmp_path / "models"
    d.mkdir()
    (d / "README.md").write_text("không có bảng\n", encoding="utf-8")
    assert kts.main(["--models", str(d)]) == 1
