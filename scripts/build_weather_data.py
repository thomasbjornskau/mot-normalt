#!/usr/bin/env python3
"""Bygger datafiler for MOT NORMALT!

Kjøres lokalt eller i GitHub Actions:

    export FROST_CLIENT_ID=...
    python scripts/build_weather_data.py

For hver stasjon i WANTED_STATIONS:
1. sjekker at stasjonen finnes (sources)
2. sjekker at den har max(air_temperature P1D) (availableTimeSeries)
3. henter baselineobservasjoner 1991-2020
4. henter nyere observasjoner (fra OBS_FROM_YEAR til i dag)
5. beregner dag-for-dag-normal, p05 og p95
6. skriver /data/{station_id}.json og /data/stations.json

Stasjoner uten tilstrekkelig datagrunnlag utelates, med tydelig logg.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys
from pathlib import Path

from fetch_frost import ELEMENT, FrostClient, FrostError
from utils import build_climatology

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

BASELINE_START = 1991
BASELINE_END = 2020
OBS_FROM_YEAR = 2020          # observasjoner som følger med til frontend
MIN_BASELINE_COVERAGE = 0.80  # minst 80 % av døgnene i baseline må ha data

# Kuratert stasjonsliste for førsteversjonen. Id-ene valideres mot Frost ved
# kjøring; stasjoner som ikke finnes eller mangler elementet utelates automatisk.
WANTED_STATIONS = [
    {"id": "SN18700", "name": "Oslo - Blindern"},
    {"id": "SN50540", "name": "Bergen - Florida"},
    {"id": "SN68860", "name": "Trondheim - Voll"},
    {"id": "SN90450", "name": "Tromsø"},
    {"id": "SN44560", "name": "Stavanger - Sola"},
    {"id": "SN82290", "name": "Bodø"},
    {"id": "SN97251", "name": "Karasjok - Markannjárga"},
]


def build_station(client: FrostClient, wanted: dict) -> dict | None:
    sid = wanted["id"]
    log.info("Stasjon %s (%s)", sid, wanted["name"])

    source = client.get_source(sid)
    if not source:
        log.warning("  UTELATT: finnes ikke i Frost sources")
        return None

    ts = client.has_element(sid)
    if not ts:
        log.warning("  UTELATT: mangler elementet %s", ELEMENT)
        return None

    valid_from = ts.get("validFrom", "")
    if valid_from and valid_from[:4] > str(BASELINE_START):
        log.warning("  UTELATT: tidsserien starter først %s (trenger %s)",
                    valid_from[:10], BASELINE_START)
        return None

    today = dt.date.today()

    # Baseline
    baseline = client.get_daily_max(
        sid, dt.date(BASELINE_START, 1, 1), dt.date(BASELINE_END, 12, 31)
    )
    baseline_days = (dt.date(BASELINE_END, 12, 31) - dt.date(BASELINE_START, 1, 1)).days + 1
    coverage = len(baseline) / baseline_days
    log.info("  baseline: %d av %d døgn (%.0f %%)", len(baseline), baseline_days, coverage * 100)
    if coverage < MIN_BASELINE_COVERAGE:
        log.warning("  UTELATT: baselinedekning under %.0f %%", MIN_BASELINE_COVERAGE * 100)
        return None

    # Nyere observasjoner
    recent = client.get_daily_max(sid, dt.date(OBS_FROM_YEAR, 1, 1), today)
    if not recent:
        log.warning("  UTELATT: ingen observasjoner fra %s og framover", OBS_FROM_YEAR)
        return None
    latest = max(recent)
    if (today - latest).days > 30:
        log.warning("  UTELATT: siste observasjon er %s (mer enn 30 dager gammel)", latest)
        return None

    # Klimatologi
    try:
        climatology = build_climatology(
            {d: o["value"] for d, o in baseline.items()},
            BASELINE_START, BASELINE_END,
        )
    except ValueError as e:
        log.warning("  UTELATT: %s", e)
        return None

    geometry = (source.get("geometry") or {}).get("coordinates", [None, None])
    station_meta = {
        "id": sid,
        "name": wanted["name"],
        "municipality": source.get("municipality", ""),
        "county": source.get("county", ""),
        "lat": geometry[1],
        "lon": geometry[0],
        "elevation_m": source.get("masl"),
    }

    payload = {
        "station": station_meta,
        "metadata": {
            "source": "Frost / MET Norway",
            "element": ELEMENT,
            "unit": "degC",
            "baseline": f"{BASELINE_START}-{BASELINE_END}",
            "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "latest_observation_date": latest.isoformat(),
        },
        "climatology": climatology,
        "observations": [
            {"date": d.isoformat(), "value": round(o["value"], 1), "quality": o["quality"]}
            for d, o in sorted(recent.items())
        ],
    }

    out = DATA_DIR / f"{sid}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log.info("  OK: %s (%d observasjoner, siste %s)", out.name, len(recent), latest)

    return {**station_meta, "source": "Frost / MET Norway", "last_updated": latest.isoformat()}


def main() -> int:
    client_id = os.environ.get("FROST_CLIENT_ID")
    if not client_id:
        log.error("Miljøvariabelen FROST_CLIENT_ID er ikke satt")
        return 1

    DATA_DIR.mkdir(exist_ok=True)
    client = FrostClient(client_id)

    included, excluded = [], []
    for wanted in WANTED_STATIONS:
        try:
            entry = build_station(client, wanted)
        except FrostError as e:
            log.error("  UTELATT: Frost-feil: %s", e)
            entry = None
        (included if entry else excluded).append(entry or wanted)

    if not included:
        log.error("Ingen stasjoner kunne bygges - stations.json skrives ikke")
        return 1

    (DATA_DIR / "stations.json").write_text(
        json.dumps(included, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    log.info("Ferdig. Inkludert: %s", ", ".join(s["id"] for s in included))
    if excluded:
        log.info("Utelatt: %s", ", ".join(s["id"] for s in excluded))
    return 0


if __name__ == "__main__":
    sys.exit(main())
