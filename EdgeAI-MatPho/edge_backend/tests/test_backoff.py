import pytest

from src.backoff import ExponentialBackoff


def test_doubles_up_to_cap_without_jitter():
    b = ExponentialBackoff(1.0, 10.0, jitter=0.0)
    assert [b.next_delay() for _ in range(6)] == [1, 2, 4, 8, 10, 10]


def test_reset_restarts_schedule():
    b = ExponentialBackoff(1.0, 10.0, jitter=0.0)
    for _ in range(4):
        b.next_delay()
    b.reset()
    assert b.next_delay() == 1.0


def test_jitter_bounds():
    low = ExponentialBackoff(10.0, 10.0, jitter=0.2, rng=lambda: 0.0)
    high = ExponentialBackoff(10.0, 10.0, jitter=0.2, rng=lambda: 1.0)
    assert low.next_delay() == pytest.approx(8.0)
    assert high.next_delay() == pytest.approx(12.0)


def test_random_jitter_stays_in_range():
    b = ExponentialBackoff(5.0, 5.0, jitter=0.5)
    delays = [b.next_delay() for _ in range(200)]
    assert all(2.5 <= d <= 7.5 for d in delays)
    assert len(set(delays)) > 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"initial": 0, "maximum": 1},
        {"initial": 2, "maximum": 1},
        {"initial": 1, "maximum": 2, "factor": 0.5},
        {"initial": 1, "maximum": 2, "jitter": 1.0},
    ],
)
def test_rejects_invalid_arguments(kwargs):
    with pytest.raises(ValueError):
        ExponentialBackoff(**kwargs)
