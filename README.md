# MOT NORMALT!

Statisk webapp som viser daglig maksimumstemperatur de siste 90 dagene ved
norske værstasjoner, sammenlignet med en historisk normal (1991–2020) for de
samme kalenderdagene. Røde flater viser dager over normalen, blå flater dager
under. Sammenhengende perioder på minst sju døgn utenfor normalvariasjonen
markeres automatisk i grafen og oppsummeres i tekst.

Dette er **ikke** en værvarsel-app. Den viser bare historiske observasjoner.

## Datakilde

Observasjonsdata fra [Frost API](https://frost.met.no) (Meteorologisk
institutt), element `max(air_temperature P1D)` – daglig maksimumstemperatur.
Data hentes med et Python-script og lagres som ferdige JSON-filer i `data/`.
Frontend kaller aldri Frost direkte og trenger ingen nøkkel.

> **Merk:** Repoet leveres med syntetiske demodata (merket
> `"source": "DEMO - syntetiske data"`) slik at appen kan prøves umiddelbart.
> Kjør `scripts/build_weather_data.py` med en Frost client id for å erstatte
> dem med reelle observasjoner.

## Skaffe Frost client id

1. Gå til <https://frost.met.no/auth/requestCredentials.html>
2. Registrer deg med e-postadresse (gratis)
3. Du får en `client id` – det er alt du trenger (client secret brukes ikke)

## Kjøre databygg lokalt

```bash
pip install requests
export FROST_CLIENT_ID=din-client-id
python scripts/build_weather_data.py
```

Scriptet logger tydelig hvilke stasjoner som ble inkludert og hvilke som ble
utelatt (manglende element, for tynn baseline, foreldede data osv.).

Tester:

```bash
python scripts/test_period_detection.py
```

## Kjøre appen lokalt

Appen er ren statisk HTML/CSS/JS (D3 fra CDN). `fetch()` krever en webserver:

```bash
python -m http.server 8000
# åpne http://localhost:8000
```

## GitHub-oppsett

1. **Secret:** Settings → Secrets and variables → Actions → New repository
   secret. Navn: `FROST_CLIENT_ID`, verdi: din client id.
   Ikke legg client id i frontend-kode eller i repoet.
2. **Workflow:** `.github/workflows/update-weather-data.yml` kjører hver morgen
   (og manuelt via *Run workflow*), bygger datafilene og committer endringer
   tilbake til repoet.
3. **GitHub Pages:** Settings → Pages → Deploy from branch → `main` / rot.
   Appen publiseres på `https://<bruker>.github.io/<repo>/`.

## Slik beregnes normalen

Månedlige klimanormaler er for grove for en dag-for-dag-graf, så appen
beregner en egen empirisk normal fra observasjonene:

- **Baseline:** 1991–2020.
- For hver kalenderdag hentes alle observasjoner av daglig
  maksimumstemperatur innenfor et vindu på **±15 kalenderdager** rundt dagen,
  fra alle 30 baselineår (opptil ca. 31 × 30 verdier). Vinduet er sirkulært
  over nyttår.
- **Normal** = gjennomsnitt av verdiene i vinduet.
- **Normalvariasjon** = 5.- og 95.-persentil av de samme verdiene.
- Alle tre kurvene glattes med et sentrert 7-dagersvindu.
- **29. februar** får egne verdier hvis det finnes nok direkte observasjoner,
  ellers interpoleres det mellom 28. februar og 1. mars.

Det grå båndet i grafen viser altså **historisk normalvariasjon** – spennet
de fleste dager (90 %) i baselineperioden lå innenfor. Det er verken
statistisk usikkerhet eller et prognoseintervall.

## Periodedeteksjon

- **Varm periode:** maksimumstemperatur over 95-persentilen i minst 7
  sammenhengende døgn.
- **Kald periode:** under 5-persentilen i minst 7 sammenhengende døgn.
- Manglende observasjoner bryter perioden. Observasjoner interpoleres ikke.
- «Heteperiode» brukes bare når (nesten) alle døgn i perioden også har
  maksimumstemperatur over 25 °C.

Logikken finnes i `scripts/utils.py` (med tester) og er speilet i
`src/app.js`. Endres den ene, må den andre oppdateres.

## Filstruktur

```
index.html                     appen
src/app.js                     tilstand, datalasting, periodedeteksjon, tekst
src/chart.js                   D3-grafen
src/style.css                  stilark
data/stations.json             stasjonsliste
data/SNxxxxx.json              klimatologi + observasjoner per stasjon
scripts/build_weather_data.py  hovedscript for databygg
scripts/fetch_frost.py         Frost API-klient
scripts/utils.py               klimatologi og periodedeteksjon
scripts/test_period_detection.py
scripts/make_demo_data.py      syntetiske demodata (kun forhåndsvisning)
.github/workflows/update-weather-data.yml
```

## Begrensninger

- Viser historiske observasjoner, ikke værvarsel.
- Normalen er beregnet empirisk fra valgt stasjon for perioden 1991–2020.
- Det grå båndet viser historisk normalvariasjon, ikke usikkerhet i en
  prognose.
- Stasjonsdata kan ha hull; hull vises som brudd i kurven.
- Stasjoner kan ha flyttet, endret instrumentering eller hatt driftsavbrudd,
  noe som kan påvirke både baseline og nyere observasjoner.
- Sammenligningen gjelder valgt stasjon, ikke nødvendigvis hele kommunen
  eller regionen.
- Stasjons-id-ene i `scripts/build_weather_data.py` valideres ved kjøring;
  stasjoner som ikke finnes eller mangler elementet utelates automatisk.

## Delingslenker

Appen støtter query-parametre: `?station=SN18700&date=2026-06-15`
