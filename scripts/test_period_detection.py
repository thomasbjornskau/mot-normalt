"""Tester for periodedeteksjon m.m. Kjør med: python -m pytest scripts/ -q
eller bare: python scripts/test_period_detection.py
"""

import datetime as dt

from utils import ALL_MONTH_DAYS, build_climatology, detect_periods, percentile


def _series(spec):
    """spec: liste av (value | None). normal=10, p05=5, p95=15 for alle dager."""
    start = dt.date(2026, 4, 1)
    return [
        {
            "date": (start + dt.timedelta(days=i)).isoformat(),
            "value": v,
            "normal": 10.0,
            "p05": 5.0,
            "p95": 15.0,
        }
        for i, v in enumerate(spec)
    ]


def test_no_periods_when_inside_band():
    assert detect_periods(_series([10.0] * 90)) == []


def test_warm_period_of_exactly_seven_days():
    s = _series([10.0] * 10 + [16.0] * 7 + [10.0] * 10)
    periods = detect_periods(s)
    assert len(periods) == 1
    p = periods[0]
    assert p["kind"] == "warm"
    assert p["length_days"] == 7
    assert p["start"] == "2026-04-11"
    assert p["end"] == "2026-04-17"


def test_six_days_is_not_enough():
    s = _series([10.0] * 10 + [16.0] * 6 + [10.0] * 10)
    assert detect_periods(s) == []


def test_missing_value_breaks_the_run():
    # 6 dager + hull + 6 dager: ingen periode
    s = _series([10.0] * 5 + [16.0] * 6 + [None] + [16.0] * 6 + [10.0] * 5)
    assert detect_periods(s) == []


def test_cold_period_and_peak():
    vals = [10.0] * 5 + [4.0, 3.0, 1.0, 2.0, 4.0, 4.5, 4.9] + [10.0] * 5
    periods = detect_periods(_series(vals))
    assert len(periods) == 1
    p = periods[0]
    assert p["kind"] == "cold"
    assert p["peak_value"] == 1.0
    assert p["peak_deviation"] == -9.0
    assert p["peak_band_deviation"] == -4.0  # 1.0 - p05(5.0)


def test_sorting_by_peak_deviation_then_length():
    vals = (
        [16.5] * 8        # varm, avvik 6.5
        + [10.0] * 3
        + [19.0] * 7      # varm, avvik 9.0 -> skal først
        + [10.0] * 3
        + [4.0] * 10      # kald, avvik -6.0
    )
    periods = detect_periods(_series(vals))
    assert [p["peak_deviation"] for p in periods] == [9.0, 6.5, -6.0]


def test_warm_to_cold_switch_without_gap_gives_two_periods():
    vals = [16.0] * 7 + [4.0] * 7
    periods = detect_periods(_series(vals))
    kinds = sorted(p["kind"] for p in periods)
    assert kinds == ["cold", "warm"]


def test_heatwave_flag():
    warm_not_hot = detect_periods(_series([16.0] * 7))[0]
    assert not warm_not_hot["is_heatwave"]
    hot = detect_periods(_series([27.0] * 7))[0]
    assert hot["is_heatwave"]


def test_percentile():
    assert percentile([1, 2, 3, 4, 5], 50) == 3
    assert percentile([1, 2, 3, 4, 5], 0) == 1
    assert percentile([1, 2, 3, 4, 5], 100) == 5


def test_climatology_shape_and_feb29():
    # Syntetisk sinusklima 1991-2020
    obs = {}
    d = dt.date(1991, 1, 1)
    import math
    while d <= dt.date(2020, 12, 31):
        doy = d.timetuple().tm_yday
        obs[d] = 5 + 12 * math.sin(2 * math.pi * (doy - 105) / 365.25)
        d += dt.timedelta(days=1)
    clim = build_climatology(obs)
    assert len(clim) == 366
    assert [c["month_day"] for c in clim] == ALL_MONTH_DAYS
    for c in clim:
        assert c["p05"] <= c["normal"] <= c["p95"]
    # 29. februar skal ligge mellom nabodagene
    by_md = {c["month_day"]: c for c in clim}
    feb29 = by_md["02-29"]["normal"]
    lo, hi = sorted([by_md["02-28"]["normal"], by_md["03-01"]["normal"]])
    assert lo - 0.2 <= feb29 <= hi + 0.2


if __name__ == "__main__":
    import sys
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except AssertionError as e:
                failed += 1
                print(f"FEIL {name}: {e}")
    sys.exit(1 if failed else 0)
