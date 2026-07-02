#!/usr/bin/env python3
"""Genererer syntetiske demodata for MOT NORMALT!

Brukes kun for å kunne forhåndsvise appen uten Frost client id.
Kjør scripts/build_weather_data.py med FROST_CLIENT_ID satt for å erstatte
demodataene med reelle observasjoner. Demofilene er tydelig merket med
"source": "DEMO - syntetiske data".

    python scripts/make_demo_data.py [YYYY-MM-DD]

Valgfritt argument setter "siste observasjonsdato" (default: i går).
"""

from __future__ import annotations

import datetime as dt
import json
import math
import random
import sys
from pathlib import Path

from utils import build_climatology

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# Enkle sesongmodeller: (årsmiddel maks-temp, amplitude, dag for topp, støy-std)
STATIONS = [
    {"id": "SN18700", "name": "Oslo - Blindern", "municipality": "Oslo",
     "county": "Oslo", "lat": 59.94, "lon": 10.72, "elevation_m": 94,
     "mean": 10.5, "amp": 11.5, "peak_doy": 200, "sigma": 3.6},
    {"id": "SN50540", "name": "Bergen - Florida", "municipality": "Bergen",
     "county": "Vestland", "lat": 60.38, "lon": 5.33, "elevation_m": 12,
     "mean": 10.8, "amp": 7.0, "peak_doy": 205, "sigma": 3.0},
    {"id": "SN90450", "name": "Tromsø", "municipality": "Tromsø",
     "county": "Troms", "lat": 69.65, "lon": 18.94, "elevation_m": 100,
     "mean": 5.0, "amp": 9.0, "peak_doy": 200, "sigma": 3.4},
]


def seasonal(st: dict, date: dt.date) -> float:
    doy = date.timetuple().tm_yday
    return st["mean"] + st["amp"] * math.cos(2 * math.pi * (doy - st["peak_doy"]) / 365.25)


def generate(st: dict, start: dt.date, end: dt.date, rng: random.Random,
             anomalies: list[tuple[dt.date, dt.date, float]] = ()) -> dict[dt.date, float]:
    """AR(1)-støy rundt sesongkurven, pluss ev. injiserte avviksperioder."""
    obs = {}
    noise = 0.0
    d = start
    while d <= end:
        noise = 0.75 * noise + rng.gauss(0, st["sigma"] * 0.66)
        value = seasonal(st, d) + noise
        for a_start, a_end, offset in anomalies:
            if a_start <= d <= a_end:
                value = seasonal(st, d) + offset + rng.gauss(0, 0.8)
        obs[d] = round(value, 1)
        d += dt.timedelta(days=1)
    return obs


def main():
    latest = (dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1
              else dt.date.today() - dt.timedelta(days=1))
    DATA_DIR.mkdir(exist_ok=True)
    rng = random.Random(42)
    index = []

    for st in STATIONS:
        baseline = generate(st, dt.date(1991, 1, 1), dt.date(2020, 12, 31), rng)
        climatology = build_climatology(baseline)

        # Injiser demoperioder i det synlige 90-dagersvinduet:
        # en varm periode på ~10 døgn og en kald på ~8 døgn (kun Oslo får begge).
        warm_start = latest - dt.timedelta(days=25)
        cold_start = latest - dt.timedelta(days=70)
        anomalies = [(warm_start, warm_start + dt.timedelta(days=9), st["sigma"] * 2.4)]
        if st["id"] == "SN18700":
            anomalies.append((cold_start, cold_start + dt.timedelta(days=7), -st["sigma"] * 2.4))

        recent = generate(st, dt.date(2020, 1, 1), latest, rng, anomalies)

        # Et lite datahull for å vise at appen tåler det
        for gap in range(3):
            recent.pop(latest - dt.timedelta(days=45 + gap), None)

        payload = {
            "station": {k: st[k] for k in
                        ("id", "name", "municipality", "county", "lat", "lon", "elevation_m")},
            "metadata": {
                "source": "DEMO - syntetiske data",
                "element": "max(air_temperature P1D)",
                "unit": "degC",
                "baseline": "1991-2020",
                "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "latest_observation_date": latest.isoformat(),
            },
            "climatology": climatology,
            "observations": [
                {"date": d.isoformat(), "value": v, "quality": "0"}
                for d, v in sorted(recent.items())
            ],
        }
        out = DATA_DIR / f"{st['id']}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
        print(f"skrev {out.name} ({out.stat().st_size // 1024} kB)")

        index.append({**{k: st[k] for k in
                         ("id", "name", "municipality", "county", "lat", "lon", "elevation_m")},
                      "source": "DEMO - syntetiske data",
                      "last_updated": latest.isoformat()})

    (DATA_DIR / "stations.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print("skrev stations.json")


if __name__ == "__main__":
    main()
