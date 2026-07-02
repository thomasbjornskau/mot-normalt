"""Felles beregningslogikk for MOT NORMALT!

Inneholder:
- dag-for-dag-klimatologi (normal, p05, p95) fra daglige observasjoner
- sirkulær glatting over kalenderåret
- skuddårshåndtering (29. februar)
- periodedeteksjon (sammenhengende døgn utenfor normalvariasjonen)

Periodedeteksjonen her speiler logikken i frontend (src/app.js).
Endres den ene, må den andre oppdateres tilsvarende.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections import defaultdict

# ---------------------------------------------------------------------------
# Kalenderdager
# ---------------------------------------------------------------------------

# Alle 366 måned-dag-nøkler i kalenderrekkefølge ("01-01" ... "12-31").
# 2000 er skuddår, så 29. februar er med.
ALL_MONTH_DAYS: list[str] = [
    (dt.date(2000, 1, 1) + dt.timedelta(days=i)).strftime("%m-%d") for i in range(366)
]
_MD_INDEX = {md: i for i, md in enumerate(ALL_MONTH_DAYS)}

FEB29 = "02-29"
MIN_OBS_PER_DAY = 30        # minste antall observasjoner i vinduet for gyldig normal
MIN_OBS_FEB29 = 10          # minste antall direkte 29.feb-observasjoner


def month_day(date: dt.date) -> str:
    return date.strftime("%m-%d")


def _circular_window(md: str, half_width: int) -> list[str]:
    """Måned-dag-nøkler i et vindu på ±half_width dager, sirkulært over nyttår."""
    i = _MD_INDEX[md]
    n = len(ALL_MONTH_DAYS)
    return [ALL_MONTH_DAYS[(i + off) % n] for off in range(-half_width, half_width + 1)]


# ---------------------------------------------------------------------------
# Persentiler og glatting
# ---------------------------------------------------------------------------

def percentile(values: list[float], p: float) -> float:
    """Lineærinterpolert persentil (p i [0, 100])."""
    if not values:
        raise ValueError("percentile() krever minst én verdi")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def smooth_circular(values: list[float], window: int = 7) -> list[float]:
    """Sentrert glidende middel over en sirkulær sekvens (kalenderåret)."""
    n = len(values)
    half = window // 2
    out = []
    for i in range(n):
        seg = [values[(i + off) % n] for off in range(-half, half + 1)]
        out.append(sum(seg) / len(seg))
    return out


# ---------------------------------------------------------------------------
# Klimatologi
# ---------------------------------------------------------------------------

def build_climatology(
    observations: dict[dt.date, float],
    baseline_start: int = 1991,
    baseline_end: int = 2020,
    window_days: int = 15,
    smoothing_window: int = 7,
    use_median: bool = False,
) -> list[dict]:
    """Beregner dag-for-dag-klimatologi fra daglige observasjoner.

    For hver kalenderdag hentes alle observasjoner i baselineperioden innenfor
    ±window_days (sirkulært over nyttår). Normal = gjennomsnitt (eller median),
    nedre/øvre grense = 5-/95-persentil. Deretter glattes alle tre kurvene med
    et kort sentrert vindu.

    29. februar: egne verdier hvis nok direkte observasjoner finnes, ellers
    interpolasjon mellom 28. februar og 1. mars (etter glatting).

    Returnerer liste av dicts: {"month_day", "normal", "p05", "p95"},
    sortert i kalenderrekkefølge. Kaster ValueError hvis datagrunnlaget er
    for tynt.
    """
    # Grupper baselineobservasjoner per måned-dag
    by_md: dict[str, list[float]] = defaultdict(list)
    for date, value in observations.items():
        if baseline_start <= date.year <= baseline_end and value is not None:
            by_md[month_day(date)].append(float(value))

    if not by_md:
        raise ValueError("Ingen observasjoner i baselineperioden")

    # Rådverdier per kalenderdag (uten 29. februar i første omgang)
    raw = {}
    for md in ALL_MONTH_DAYS:
        if md == FEB29:
            continue
        pool: list[float] = []
        for wmd in _circular_window(md, window_days):
            pool.extend(by_md.get(wmd, []))
        if len(pool) < MIN_OBS_PER_DAY:
            raise ValueError(
                f"For få observasjoner ({len(pool)}) i vinduet rundt {md} "
                f"for baseline {baseline_start}-{baseline_end}"
            )
        center = statistics.median(pool) if use_median else statistics.fmean(pool)
        raw[md] = {
            "normal": center,
            "p05": percentile(pool, 5),
            "p95": percentile(pool, 95),
        }

    # Glatting over de 365 ordinære dagene (sirkulært)
    days_365 = [md for md in ALL_MONTH_DAYS if md != FEB29]
    smoothed = {}
    for key in ("normal", "p05", "p95"):
        series = smooth_circular([raw[md][key] for md in days_365], smoothing_window)
        for md, v in zip(days_365, series):
            smoothed.setdefault(md, {})[key] = v

    # 29. februar
    feb29_direct = by_md.get(FEB29, [])
    if len(feb29_direct) >= MIN_OBS_FEB29:
        pool: list[float] = []
        for wmd in _circular_window(FEB29, window_days):
            pool.extend(by_md.get(wmd, []))
        center = statistics.median(pool) if use_median else statistics.fmean(pool)
        smoothed[FEB29] = {
            "normal": center,
            "p05": percentile(pool, 5),
            "p95": percentile(pool, 95),
        }
    else:
        a, b = smoothed["02-28"], smoothed["03-01"]
        smoothed[FEB29] = {k: (a[k] + b[k]) / 2 for k in ("normal", "p05", "p95")}

    return [
        {
            "month_day": md,
            "normal": round(smoothed[md]["normal"], 1),
            "p05": round(smoothed[md]["p05"], 1),
            "p95": round(smoothed[md]["p95"], 1),
        }
        for md in ALL_MONTH_DAYS
    ]


# ---------------------------------------------------------------------------
# Periodedeteksjon
# ---------------------------------------------------------------------------

def detect_periods(series: list[dict], min_length: int = 7) -> list[dict]:
    """Finner sammenhengende perioder utenfor normalvariasjonen.

    `series` er en liste med dicts i datorekkefølge:
        {"date": "YYYY-MM-DD", "value": float|None,
         "normal": float, "p05": float, "p95": float}

    Varm periode: value > p95 i minst `min_length` sammenhengende døgn.
    Kald periode: value < p05 i minst `min_length` sammenhengende døgn.
    Manglende verdi (None) bryter perioden.

    Returnerer perioder sortert etter (1) størst absolutt avvik fra normal
    på toppunktet, (2) lengst varighet.
    """
    periods: list[dict] = []
    run: list[dict] = []
    run_kind: str | None = None

    def flush():
        nonlocal run, run_kind
        if run_kind and len(run) >= min_length:
            periods.append(_summarise_period(run, run_kind))
        run, run_kind = [], None

    for d in series:
        v = d.get("value")
        if v is None:
            flush()
            continue
        kind = "warm" if v > d["p95"] else "cold" if v < d["p05"] else None
        if kind != run_kind:
            flush()
            run_kind = kind
        if kind:
            run.append(d)
    flush()

    periods.sort(key=lambda p: (-abs(p["peak_deviation"]), -p["length_days"]))
    return periods


def _summarise_period(run: list[dict], kind: str) -> dict:
    if kind == "warm":
        peak = max(run, key=lambda d: d["value"] - d["normal"])
        band_dev = peak["value"] - peak["p95"]
    else:
        peak = min(run, key=lambda d: d["value"] - d["normal"])
        band_dev = peak["value"] - peak["p05"]

    # "Heteperiode": (nesten) alle dager har maksimumstemperatur over 25 °C
    hot_days = sum(1 for d in run if d["value"] > 25.0)
    is_heatwave = kind == "warm" and hot_days >= len(run) - 1

    return {
        "kind": kind,
        "start": run[0]["date"],
        "end": run[-1]["date"],
        "length_days": len(run),
        "peak_date": peak["date"],
        "peak_value": round(peak["value"], 1),
        "peak_normal": round(peak["normal"], 1),
        "peak_deviation": round(peak["value"] - peak["normal"], 1),
        "peak_band_deviation": round(band_dev, 1),
        "is_heatwave": is_heatwave,
    }
