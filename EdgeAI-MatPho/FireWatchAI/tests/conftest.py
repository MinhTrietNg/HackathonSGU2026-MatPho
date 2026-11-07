"""Fixture dùng chung cho test verifier bền vững (đồ giả ở ``he_verifier.py``)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import he_verifier


@pytest.fixture()
def he(tmp_path: Path):
    """Dựng hệ cờ bật với đồng hồ giả; trả hàm ``dung(**cau_hinh)``.

    Mỗi lần gọi dựng một hệ riêng (thư mục riêng); mọi hệ được dọn sau test.
    Tham số của ``dung`` xem :func:`he_verifier.dung_he`.
    """
    da_dung: list[SimpleNamespace] = []

    def dung(**cau_hinh) -> SimpleNamespace:
        h = he_verifier.dung_he(tmp_path / f"he{len(da_dung)}", **cau_hinh)
        da_dung.append(h)
        return h

    yield dung
    for h in da_dung:
        he_verifier.don_he(h)
