"""run.log xoay vòng theo kích thước, giữ đúng số bản cũ (3D)."""

from __future__ import annotations

import logging
from pathlib import Path

from firewatch.config import Config
from firewatch.pipeline import _attach_file_log


def test_run_log_xoay_vong_va_gioi_han_tong_dung_luong(tmp_path: Path):
    path = tmp_path / "run.log"
    fh = _attach_file_log(path, toi_da_mb=0.01, so_ban=2)      # ~10 KB mỗi file
    lg = logging.getLogger("firewatch.thu_log_xoay")
    cu = lg.level
    lg.setLevel(logging.INFO)
    try:
        for i in range(2000):
            lg.info("heartbeat %05d %s", i, "x" * 60)
    finally:
        logging.getLogger().removeHandler(fh)
        fh.close()
        lg.setLevel(cu)
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["run.log", "run.log.1", "run.log.2"]
    gioi_han = int(0.01 * 1024 * 1024)
    for p in tmp_path.iterdir():
        assert p.stat().st_size <= gioi_han + 200
    assert "heartbeat 01999" in path.read_text(encoding="utf-8")


def test_config_mac_dinh_log_xoay():
    out = Config().output
    assert (out.log_toi_da_mb, out.log_so_ban) == (20.0, 5)
