"""Cổng chặn tên cũ của model, dữ liệu và kiểm dạng tên hiển thị.

Port từ ``tests/test_ten_cu.py`` của FireWatch-Model; bảng đối chiếu tên cũ sang
tên mới nằm ở ``CHANGELOG.md`` của repo đó, không chép sang đây. Mẫu regex được
ghép từ từng mảnh để chính file test không tự khớp.

Khác bản gốc: thêm hai mẫu ID và file model cũ của repo vận hành (tiền tố ID đội
cũ và file checkpoint mặc định của Ultralytics trong thư mục models), và danh
sách miễn trừ là hai file không được đổi (lý do ghi trong ``DUOC_PHEP``).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_MANH = [
    ("mat" "pho", "_fire"), ("mat" "pho", "-fire"), ("mat" "pho", "-v"),
    ("best_full", "_v121"), ("best_v2", "_base"), ("team_full", "_v121"),
    ("v2", "_base"), ("best_fasdd", "_2310"), ("dau_dfire", "_v"),
    ("team_yolo26n", "_v2" "_base"),
    ("team_yolo", "26n_"), ("be" "st", ".pt"),
]
TEN_CU = re.compile("|".join(re.escape(a + b) for a, b in _MANH), re.IGNORECASE)

DUOC_PHEP = {
    # Đang khoá theo quy tắc của repo (không sửa detector.py); docstring dòng 3
    # còn nhắc tên file checkpoint cũ. Gỡ miễn trừ khi file được mở khoá.
    "src/firewatch/detector.py":
        "file khoá, docstring còn tên checkpoint cũ",
    # ID model ở đây là tên cột trong bảng nguon_train của T1-dev (dữ liệu, chưa
    # có trong repo nên test đang skip). Đổi ID thì test sai khi có dữ liệu.
    "tests/test_t1_dev_ro_ri.py":
        "ID khớp cột của bảng dữ liệu T1-dev",
}
NHI_PHAN = {".pt", ".onnx", ".zip", ".png", ".jpg", ".jpeg", ".pdf", ".npz"}


def file_trong_repo() -> list[str]:
    """File được git theo dõi hoặc sẽ được thêm (không tính file bị ignore)."""
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT,
        capture_output=True, text=True, check=True, encoding="utf-8")
    return [p for p in out.stdout.splitlines() if p and (ROOT / p).is_file()]


def doc(rel: str) -> str:
    """Nội dung văn bản của file, rỗng nếu là file nhị phân."""
    if Path(rel).suffix.lower() in NHI_PHAN:
        return ""
    try:
        return (ROOT / rel).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def test_khong_con_ten_cu():
    vi_pham = []
    for rel in file_trong_repo():
        if rel in DUOC_PHEP:
            continue
        if TEN_CU.search(rel):
            vi_pham.append(f"{rel}: tên file")
        for i, dong in enumerate(doc(rel).splitlines(), 1):
            m = TEN_CU.search(dong)
            if m:
                vi_pham.append(f"{rel}:{i}: {m.group(0)}")
    assert not vi_pham, "Tên cũ ngoài nơi được phép:\n" + "\n".join(vi_pham)


def test_mien_tru_van_con_can():
    """Miễn trừ chỉ giữ khi file đó thật sự còn tên cũ."""
    for rel in DUOC_PHEP:
        assert TEN_CU.search(doc(rel)), f"{rel} hết tên cũ, gỡ khỏi DUOC_PHEP"


_CODE_KHOI = re.compile(r"```.*?```", re.DOTALL)
_CODE_DONG = re.compile(r"`[^`\n]*`")
_DUONG_DAN = re.compile(r"\S*[/\\]\S*|\S+\.(?:pt|onnx|zip|md|json|ya?ml|txt|csv"
                        r"|ipynb|py)\b", re.IGNORECASE)
_CO_VERSION = re.compile(r"(?i)\b(?:data)?fire\s*watch[\s_-]*v?\d+(?:\.\d+)*")
_DUNG = re.compile(r"(?:Data)?FireWatch-v\d+\.\d+(?:\.\d+)?")


def loi_ten_hien_thi(van_ban: str) -> list[str]:
    """Các chữ 'firewatch + version' sai dạng hiển thị, ngoài code và đường dẫn."""
    s = _CODE_KHOI.sub(" ", van_ban)
    s = _CODE_DONG.sub(" ", s)
    s = _DUONG_DAN.sub(" ", s)
    return [m.group(0) for m in _CO_VERSION.finditer(s)
            if not _DUNG.fullmatch(m.group(0))]


def test_ten_hien_thi_dung_dang():
    vi_pham = []
    for rel in file_trong_repo():
        if rel.endswith(".md"):
            vi_pham += [f"{rel}: {x}" for x in loi_ten_hien_thi(doc(rel))]
    assert not vi_pham, "Tên hiển thị sai dạng:\n" + "\n".join(vi_pham)


def test_bo_kiem_ten_hien_thi_bat_duoc_loi():
    sai = "FireWatch v2.0, Firewatch-v1.5, FW, firewatch-v2.0 và DataFireWatch v2"
    assert loi_ten_hien_thi(sai) == ["FireWatch v2.0", "Firewatch-v1.5",
                                     "firewatch-v2.0", "DataFireWatch v2"]
    dung = ("FireWatch-v2.0, DataFireWatch-v2.0.1, `firewatch-v2.0`, "
            "models/firewatch-v1.0.pt, firewatch-v2.0.1.pt")
    assert loi_ten_hien_thi(dung) == []


def test_mau_ten_cu_bat_duoc():
    for a, b in _MANH:
        assert TEN_CU.search(("x" + a + b + "y").upper())
