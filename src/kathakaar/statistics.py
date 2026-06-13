"""Confidence-interval utilities for evaluation metrics.

Small benchmarks make point estimates (``accuracy = 1.0``) easy to over-read.
These helpers attach uncertainty:

* ``wilson_interval`` - exact-ish CI for a proportion (the right tool for
  accuracy / recall / rejection rates), deterministic, no sampling.
* ``bootstrap_interval`` - percentile bootstrap for an arbitrary list of values,
  deterministic given the seed.

Pure standard library; mypy-strict clean.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

Interval = tuple[float, float]


def wilson_interval(successes: int, total: int, z: float = 1.96) -> Interval:
    """Wilson score interval for a binomial proportion.

    Returns (low, high) clamped to [0, 1]. With no observations returns (0, 0).
    """
    if total <= 0:
        return (0.0, 0.0)
    if successes < 0 or successes > total:
        raise ValueError("successes must be in [0, total]")
    p = successes / total
    z2 = z * z
    denom = 1.0 + z2 / total
    center = (p + z2 / (2 * total)) / denom
    margin = (z * math.sqrt(p * (1 - p) / total + z2 / (4 * total * total))) / denom
    low = max(0.0, center - margin)
    high = min(1.0, center + margin)
    return (round(low, 4), round(high, 4))


def bootstrap_interval(
    values: Sequence[float],
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 13,
) -> Interval:
    """Percentile bootstrap CI for the mean of ``values`` (deterministic)."""
    n = len(values)
    if n == 0:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_boot):
        total = 0.0
        for _ in range(n):
            total += values[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (round(lo, 4), round(hi, 4))
