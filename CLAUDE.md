# Northern Nigeria Weather & Farmland App — Project Notes

## Overview
This app has two related features for Northern Nigeria, both built on the same
base layer: administrative boundary shapefiles (State → LGA → Ward).

---

## Feature 1: Weather

### What it does
Shows current/local weather (rainfall, temperature, etc.) for a location the
user selects (state, LGA, or a map point).

### Data source
- **NASA POWER API** — https://power.larc.nasa.gov
- Free, no authentication required, plain HTTP GET requests
- Provides 40+ years of satellite/reanalysis meteorological data
- Resolution: ~50km grid (0.5° x 0.625°) — one averaged value per grid cell,
  not per exact point
- Reliability notes:
  - Correlates well with ground stations in comparable regions (r ≈ 0.6–0.94
    depending on season/region)
  - More reliable for temperature than for heavy/short rainfall events
  - Performs relatively well in savannah/dry-season climates — which matches
    Northern Nigeria's climate zone

### How it works (runtime flow)
1. User selects a location (state/LGA, or taps a map point).
2. App resolves that selection to a latitude/longitude.
3. App queries NASA POWER API for that lat/lon (live, per request — no
   caching of boundaries needed here).
4. NASA POWER returns weather values for the ~50km grid cell containing that
   point.
5. App displays it as "weather for [selected location]."

### Role of shapefiles here
Shapefiles are **not** part of the live weather lookup. They're only used
once, upfront, to define the State → LGA → Ward dropdown/selection options
so a user's click can be converted into a lat/lon. Shapefiles carry no
weather data themselves — they're pure boundary geometry.

### Boundary data source (for the dropdowns/menus)
- **GRID3** (data.grid3.org) — State, LGA, and Ward-level operational
  boundaries for Nigeria. Primary source; actively maintained.
- **HDX** (data.humdata.org) — UN-maintained alternative/backup for the same
  boundary levels.
- ⚠️ Verify ward-level coverage for target states before relying on it —
  coverage has historically been strongest in northeast Nigeria first, then
  expanded to other states.

---

## Feature 2: Farmland Mapping

### What it does
User clicks State → LGA → Ward and sees whether that ward has agricultural
land (yes/no). Example: Bulunkutu ward in Maiduguri = urban, no agric land.

### Data source
- **ESA WorldCover** — free global land-cover map, 10m resolution, satellite
  Sentinel-1/2 derived, classifies land into 11 categories including
  "Cropland."
- Access via Google Earth Engine (free) or Digital Earth Africa's hosted copy.

### Reliability notes
- One study testing WorldCover specifically on Nigerian cropland found ~87%
  accuracy / 0.825 F1-score — the best-performing global map tested.
- A separate broader comparison found some Nigerian regions dropped below
  70% overall accuracy for global land-cover maps generally (not
  WorldCover-specific).
- Treat as "generally reliable, not guaranteed per-ward" — good enough as an
  automated first pass, not a certified ground-truth source.
- Manual ward-by-ward verification was considered but ruled out due to lack
  of resources (774 LGAs / thousands of wards nationally is not feasible
  solo).

### How it works (setup — one-time, not per-request)
1. For each ward boundary (from the same GRID3/HDX shapefiles used in
   Feature 1), calculate what % of the ward's area WorldCover classifies as
   "Cropland."
2. Apply a threshold (e.g. >10–15% cropland → mark ward as having
   agricultural land). Exact threshold to be tuned by spot-checking a few
   known wards.
3. Store the resulting yes/no flag per ward in the app's own database.
4. This is a one-time batch process (script), re-run only if you want to
   refresh with newer WorldCover imagery.

### How it works (runtime flow)
1. User clicks State → LGA → Ward.
2. App looks up the pre-computed yes/no flag for that ward from the
   database — no live satellite query happens per click.
3. App displays the result.

### Correction strategy
No upfront manual review planned. Flags are corrected reactively: if a user
or supervisor reports a wrong ward, that single flag is manually flipped in
the database. Data should be labeled as satellite-derived / auto-generated,
not manually verified, for transparency.

---

## Summary: Mental Model

| | Weather | Farmland |
|---|---|---|
| Data source | NASA POWER | ESA WorldCover |
| When computed | Live, per request | Once, in advance (batch) |
| Shapefile role | Convert click → lat/lon | Define ward boundaries for the %-cropland calculation |
| Accuracy | Good for temp, weaker for rain; decent in savannah zones | ~87% in one Nigeria-specific test, lower in some broader comparisons |
| Update frequency | Always current (live API) | Static until re-run with newer imagery |
