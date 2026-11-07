import pytest

from src.sampler import FrameRateSampler


def run(sampler, times):
    return [t for t in times if sampler.accept(t)]


def series(fps, seconds, start=0.0):
    return [start + i / fps for i in range(int(fps * seconds))]


@pytest.mark.parametrize("src_fps", [25, 30, 24, 15, 12, 60])
@pytest.mark.parametrize("target", [1, 3, 5])
def test_long_term_rate_matches_target(src_fps, target):
    kept = run(FrameRateSampler(target), series(src_fps, 60))
    assert abs(len(kept) - target * 60) <= 1


def test_first_frame_is_always_kept():
    assert FrameRateSampler(3).accept(1234.5) is True


def test_spacing_is_close_to_period():
    kept = run(FrameRateSampler(3), series(25, 10))
    gaps = [b - a for a, b in zip(kept, kept[1:])]
    assert all(abs(g - 1 / 3) <= 1 / 25 + 1e-9 for g in gaps)


def test_source_slower_than_target_keeps_everything():
    times = series(2, 10)
    assert run(FrameRateSampler(3), times) == times


def test_gap_does_not_cause_catch_up_burst():
    s = FrameRateSampler(3)
    first = run(s, series(25, 2))
    after_gap = run(s, series(25, 2, start=60.0))
    assert len(first) == pytest.approx(6, abs=1)
    assert after_gap[0] == 60.0
    assert len(after_gap) == pytest.approx(6, abs=1)


def test_timestamps_going_backwards_reanchor():
    s = FrameRateSampler(3)
    run(s, series(25, 5, start=1000.0))
    restarted = run(s, series(25, 3, start=0.0))
    assert restarted[0] == 0.0
    assert len(restarted) == pytest.approx(9, abs=1)


def test_reset_accepts_next_frame():
    s = FrameRateSampler(1)
    assert s.accept(10.0)
    assert not s.accept(10.1)
    s.reset()
    assert s.accept(10.2)


def test_rejects_invalid_rate():
    with pytest.raises(ValueError):
        FrameRateSampler(0)
