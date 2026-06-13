from __future__ import annotations

import math

import pytest

from kathakaar.statistics import bootstrap_interval, wilson_interval


def test_wilson_zero_total_is_empty():
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_wilson_perfect_score_admits_uncertainty():
    lo, hi = wilson_interval(6, 6)
    assert hi == 1.0 and lo < 1.0


def test_wilson_small_sample_wider():
    small = wilson_interval(5, 6)
    large = wilson_interval(50, 60)
    assert (small[1] - small[0]) > (large[1] - large[0])


def test_wilson_brackets_point():
    lo, hi = wilson_interval(4, 6)
    assert lo <= 4 / 6 <= hi


def test_wilson_rejects_out_of_range():
    with pytest.raises(ValueError):
        wilson_interval(7, 6)


def test_bootstrap_constant_zero_width():
    lo, hi = bootstrap_interval([1.0] * 30)
    assert math.isclose(lo, 1.0) and math.isclose(hi, 1.0)


def test_bootstrap_deterministic():
    vals = [1.0, 0.0, 1.0, 1.0, 0.0]
    assert bootstrap_interval(vals) == bootstrap_interval(vals)
