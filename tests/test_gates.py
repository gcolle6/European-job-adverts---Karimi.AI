"""Measured scores against thresholds fixed BEFORE the scores they gate.

    python -m pytest -m gates

Slow (the count check re-runs the splitter on 120 items), so not on every
commit: before a release and after any rule change. Fixed 2026-11-04, before
the batch was regenerated with P10-P15, from what the pre-release library
measured; a release that falls below them is not released.

* the blind count must not fall below 0.75 exact (measured 0.78, 95% CI
  0.68-0.88: the floor sits inside the interval, so this catches a real drop,
  not noise);
* wrong merges stay rare where they are fatal: roles at most 1 of 9 blind,
  requirement groups at most 2 per 15 blind;
* every pattern case passes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from karimi_normalise import quality  # noqa: E402

pytestmark = pytest.mark.gates

MIN_COUNT_EXACT_BLIND = 0.75
MAX_ROLE_WRONG_MERGES = 1
MAX_REQ_WRONG_MERGE_RATE = 2 / 15


def test_count_exact_blind():
    s = quality.split_count()["blind_half"]
    assert s["exact"] >= MIN_COUNT_EXACT_BLIND, s


def test_wrong_merges_blind():
    p = quality.pairs()["blind"]
    assert p["role"]["merged"]["errors"] <= MAX_ROLE_WRONG_MERGES, p["role"]
    m = p["requirement_group"]["merged"]
    assert m["errors"] / m["pairs"] <= MAX_REQ_WRONG_MERGE_RATE, m


def test_all_pattern_cases():
    t = quality.tests()
    assert t["passed"] == t["total"], t
