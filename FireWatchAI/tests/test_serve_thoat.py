"""serve --exit-on-pipeline-stop: pipeline chết thì báo để server dừng (3D)."""

from __future__ import annotations

from types import SimpleNamespace

from firewatch.__main__ import _build_parser
from firewatch.pipeline import PipelineHealth
from firewatch.server import chay_pipeline_nen


class _Pipe:
    def __init__(self, ket_qua=None, loi: BaseException | None = None):
        self.ket_qua, self.loi = ket_qua, loi

    def run(self):
        if self.loi is not None:
            raise self.loi
        return self.ket_qua


def _chay(pipe) -> tuple[bool, list[int], PipelineHealth]:
    goi: list[int] = []
    health = PipelineHealth()
    return chay_pipeline_nen(pipe, health, lambda: goi.append(1)), goi, health


def test_nguon_live_ket_thuc_la_dung_bat_thuong():
    bat_thuong, goi, _ = _chay(_Pipe(SimpleNamespace(live_source_lost=True)))
    assert bat_thuong and goi == [1]


def test_pipeline_loi_la_dung_bat_thuong_va_ghi_vao_health():
    bat_thuong, goi, health = _chay(_Pipe(loi=RuntimeError("camera hỏng")))
    assert bat_thuong and goi == [1]
    assert health.snapshot()["status"] == "dead"
    assert "camera hỏng" in health.error


def test_trong_so_sai_systemexit_cung_la_dung_bat_thuong():
    bat_thuong, goi, _ = _chay(_Pipe(loi=SystemExit("weights không có class")))
    assert bat_thuong and goi == [1]


def test_nguon_file_chay_het_khong_phai_bat_thuong():
    bat_thuong, goi, _ = _chay(_Pipe(SimpleNamespace(live_source_lost=False)))
    assert not bat_thuong and goi == []


def test_co_cli():
    args = _build_parser().parse_args(["serve", "--exit-on-pipeline-stop"])
    assert args.exit_on_pipeline_stop is True
    assert _build_parser().parse_args(["serve"]).exit_on_pipeline_stop is False
