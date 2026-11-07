import pytest

from src.scaling import fit_even


@pytest.mark.parametrize(
    "size, max_edge, expected",
    [
        ((1920, 1080), 640, (640, 360)),
        ((2560, 1440), 640, (640, 360)),
        ((3840, 2160), 960, (960, 540)),
        ((1080, 1920), 640, (360, 640)),
        ((320, 240), 640, (320, 240)),
        ((1280, 720), 1280, (1280, 720)),
        ((1000, 562), 640, (640, 358)),
        ((1919, 1079), 4000, (1918, 1078)),
        ((4, 4000), 100, (2, 100)),
    ],
)
def test_fit_even(size, max_edge, expected):
    out = fit_even(*size, max_edge)
    assert out == expected
    assert out[0] % 2 == 0 and out[1] % 2 == 0
    assert max(out) <= max(size)


def test_aspect_ratio_preserved_within_rounding():
    w, h = fit_even(1920, 1080, 640)
    assert abs(w / h - 1920 / 1080) < 0.01


@pytest.mark.parametrize("args", [(0, 10, 10), (10, 0, 10), (10, 10, 0), (-1, 5, 5)])
def test_rejects_non_positive(args):
    with pytest.raises(ValueError):
        fit_even(*args)
