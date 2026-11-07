"""Kiểm SHA-256 trọng số trong ``models/`` theo bảng của ``models/README.md``.

``run.sh`` và ``run.ps1`` gọi script này trước khi chạy FireWatch; mã thoát khác
0 thì không chạy. Quy tắc, theo ``models/README.md``:

* file ``.pt`` có trong bảng phải tồn tại và trùng SHA-256: danh tính của model
  là SHA của ``.pt``. Thiếu hoặc lệch thì lỗi (mã 1);
* file ONNX lệch SHA chỉ có nghĩa là đã được export lại trên máy này, model vẫn
  đúng nếu ``.pt`` đúng: cảnh báo, không lỗi. Thiếu ONNX thì detector tự export.

Chỉ dùng thư viện chuẩn, để chạy được trước cả khi môi trường đủ gói.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
DONG_SHA = re.compile(r"`([\w.\-]+\.(?:pt|onnx))`, SHA-256 `([0-9a-f]{64})`")


def doc_bang(readme: Path) -> dict[str, str]:
    """``{tên file: sha256}`` từ các dòng ``\\`<file>\\`, SHA-256 \\`<hex>\\```."""
    return {m.group(1): m.group(2)
            for m in DONG_SHA.finditer(readme.read_text(encoding="utf-8"))}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for khoi in iter(lambda: f.read(1 << 20), b""):
            h.update(khoi)
    return h.hexdigest()


def kiem(models: Path, readme: Path) -> tuple[list[str], list[str]]:
    """Trả (lỗi, cảnh báo); lỗi rỗng nghĩa là được chạy."""
    bang = doc_bang(readme)
    loi: list[str] = []
    canh_bao: list[str] = []
    if not any(t.endswith(".pt") for t in bang):
        return [f"{readme} không có dòng SHA-256 nào cho file .pt"], []
    for ten, mong in bang.items():
        p = models / ten
        if not p.is_file():
            if ten.endswith(".pt"):
                loi.append(f"thiếu {p} (lấy file theo models/README.md)")
            else:
                canh_bao.append(f"chưa có {ten}: detector sẽ tự export từ .pt")
            continue
        thuc = sha256(p)
        if thuc == mong:
            print(f"OK  {ten}  {thuc[:12]}…")
        elif ten.endswith(".pt"):
            loi.append(f"{ten} lệch SHA-256: {thuc} khác {mong}")
        else:
            canh_bao.append(f"{ten} lệch SHA-256 ({thuc[:12]}…): đã export lại trên "
                            "máy này; model vẫn đúng vì .pt đúng")
    return loi, canh_bao


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", type=Path, default=GOC / "models")
    ap.add_argument("--readme", type=Path, default=None,
                    help="mặc định <models>/README.md")
    args = ap.parse_args(argv)
    readme = args.readme or args.models / "README.md"
    loi, canh_bao = kiem(args.models, readme)
    for c in canh_bao:
        print(f"CẢNH BÁO  {c}")
    for e in loi:
        print(f"LỖI  {e}", file=sys.stderr)
    if loi:
        print("Không chạy FireWatch: trọng số không đúng models/README.md.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
