"""Tynn klient mot Frost API (Meteorologisk institutt).

Dokumentasjon: https://frost.met.no/api.html
Autentisering: HTTP Basic med client id som brukernavn og tomt passord.
"""

from __future__ import annotations

import datetime as dt
import logging
import time

import requests

log = logging.getLogger("frost")

BASE_URL = "https://frost.met.no"
ELEMENT = "max(air_temperature P1D)"


class FrostError(RuntimeError):
    pass


class FrostClient:
    def __init__(self, client_id: str, timeout: int = 60):
        self.session = requests.Session()
        self.session.auth = (client_id, "")
        self.timeout = timeout

    def _get(self, path: str, params: dict) -> list[dict]:
        url = f"{BASE_URL}{path}"
        for attempt in range(3):
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json().get("data", [])
            if resp.status_code == 404:
                # Frost bruker 404 for "ingen data funnet"
                return []
            if resp.status_code in (429, 500, 502, 503) and attempt < 2:
                wait = 5 * (attempt + 1)
                log.warning("HTTP %s fra Frost, prøver igjen om %ss", resp.status_code, wait)
                time.sleep(wait)
                continue
            raise FrostError(f"Frost API {resp.status_code}: {resp.text[:300]}")
        raise FrostError("Ga opp etter gjentatte forsøk")

    # -- Metadata ------------------------------------------------------------

    def get_source(self, station_id: str) -> dict | None:
        """Stasjonsmetadata fra sources-endepunktet."""
        data = self._get("/sources/v0.jsonld", {"ids": station_id})
        return data[0] if data else None

    def has_element(self, station_id: str, element: str = ELEMENT) -> dict | None:
        """Sjekker via availableTimeSeries at stasjonen har ønsket element.

        Returnerer tidsserie-metadata (bl.a. validFrom) eller None.
        """
        data = self._get(
            "/observations/availableTimeSeries/v0.jsonld",
            {
                "sources": station_id,
                "elements": element,
                "timeoffsets": "default",
                "levels": "default",
            },
        )
        return data[0] if data else None

    # -- Observasjoner ---------------------------------------------------------

    def get_daily_max(
        self,
        station_id: str,
        start: dt.date,
        end: dt.date,
        chunk_years: int = 5,
    ) -> dict[dt.date, dict]:
        """Henter daglig maksimumstemperatur i [start, end].

        Henter i bolker på noen år av gangen for å holde responsene små.
        Returnerer {dato: {"value": float, "quality": str}}. Ved flere
        observasjoner samme dato beholdes den med best kvalitetskode.
        """
        result: dict[dt.date, dict] = {}
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(
                dt.date(chunk_start.year + chunk_years - 1, 12, 31), end
            )
            reftime = f"{chunk_start.isoformat()}/{(chunk_end + dt.timedelta(days=1)).isoformat()}"
            log.info("  henter %s: %s", station_id, reftime)
            rows = self._get(
                "/observations/v0.jsonld",
                {
                    "sources": station_id,
                    "elements": ELEMENT,
                    "referencetime": reftime,
                    "timeoffsets": "default",
                    "levels": "default",
                    "qualities": "0,1,2,3,4",
                },
            )
            for row in rows:
                date = dt.datetime.fromisoformat(
                    row["referenceTime"].replace("Z", "+00:00")
                ).date()
                for obs in row.get("observations", []):
                    value = obs.get("value")
                    if value is None:
                        continue
                    quality = str(obs.get("qualityCode", ""))
                    prev = result.get(date)
                    if prev is None or _quality_rank(quality) < _quality_rank(prev["quality"]):
                        result[date] = {"value": float(value), "quality": quality}
            chunk_start = chunk_end + dt.timedelta(days=1)
        return result


def _quality_rank(code: str) -> int:
    try:
        return int(code)
    except (TypeError, ValueError):
        return 99
