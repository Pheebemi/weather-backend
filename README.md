# Weather Backend

Django + Django REST Framework API for the Northern Nigeria Weather &
Farmland app. See `CLAUDE.md` for the full project background.

## Stack
- Django 5 / Django REST Framework
- SQLite for local dev; Postgres (Neon) in production via `DATABASE_URL`

## Apps
- `boundaries` — State → LGA → Ward reference data, plus `WardFarmland`
  (Feature 2's pre-computed cropland flag) and `FarmlandReport` (user
  "report incorrect info" submissions).
- `weather_data` — Feature 1: weather lookup by point or by ward. Prefers
  `climate_pipeline.WardClimate` (precomputed) when available, falls back
  to a live NASA POWER call otherwise.
- `climate_pipeline` — Supervisor's formal 4-step data-prep pipeline (see
  CLAUDE.md): offline scripts that populate `WardClimate`.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py import_boundaries --download --reset  # real HDX boundaries
python manage.py compute_farmland                      # real ESA WorldCover flags (~25 min)
python manage.py createsuperuser                       # optional, for /admin/
python manage.py runserver
```

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/states/` | List states |
| `GET /api/states/<id>/lgas/` | List LGAs in a state |
| `GET /api/lgas/<id>/wards/` | List wards in an LGA |
| `GET /api/weather/?lat=&lon=` | Live NASA POWER weather for a point (e.g. a map tap) |
| `GET /api/weather/ward/<id>/` | Weather for a ward — precomputed `WardClimate` if the pipeline has covered it, otherwise a live NASA POWER call |
| `GET /api/wards/<id>/farmland/` | Pre-computed agricultural-land flag for a ward |
| `POST /api/wards/<id>/farmland/report/` | Flag a ward's farmland result as wrong (`{"note": "..."}`, note optional) — reviewed manually in `/admin/` |

## Deploying (Vercel + Neon)
Vercel assigns a **new hostname on every deploy** (production and each
preview), and Django's `ALLOWED_HOSTS`/CORS checks reject anything not on
their allowlist by default — that shows up as an HTTP 400
`DisallowedHost` error. `config/settings.py` handles this automatically
when `VERCEL=1` is set (Vercel sets it for you): it allows any
`*.vercel.app` host/origin. You don't need to add each generated URL by
hand; set `DJANGO_ALLOWED_HOSTS`/`CORS_ALLOWED_ORIGINS` only once you're on
a custom domain.

For the database, `DATABASES` reads `DATABASE_URL` (via `dj-database-url`)
and falls back to local SQLite when it's unset. In the Vercel project's
Environment Variables settings, add:
```
DATABASE_URL=<Neon's pooled connection string, includes ?sslmode=require>
DJANGO_SECRET_KEY=<a real secret, not the dev default>
DJANGO_DEBUG=false
```
Then run migrations against Neon once (locally, pointed at the same
`DATABASE_URL`, or via a Vercel deploy hook): `python manage.py migrate`.

## Boundary data (real)
`import_boundaries --download` pulls the HDX Common Operational Dataset
(UN OCHA, "Nigeria - Subnational Administrative Boundaries") — free, no
authentication — and loads real `State`/`LGA`/`Ward` rows with real
centroids for the 19 northern states.

Ward polygons come from **GRID3 NGA Operational Wards v3.0** — the primary
source named in CLAUDE.md — loaded by `import_wards_grid3 --download`.
That gives **4,009 wards across 16 of the 19 northern states**, with every
LGA in those states fully covered.

⚠️ **Benue, Plateau and Taraba have no ward polygons in any open source.**
Checked: GRID3 v3.0 and v2.0, HDX COD admin3, geoBoundaries (404 for
Nigeria ADM3), the INEC ward list (tabular, no geometry) and eHealth
Africa's ward service (host no longer resolves). Those three states work at
State + LGA level, and `compute_farmland_lga` computes their cropland from
LGA polygons instead so they are not left empty.

## Farmland flag batch job (real)
`compute_farmland` is Feature 2's real batch job. For each ward polygon it
computes the percent of ward area that ESA WorldCover v200 (2021, 10m)
classifies as Cropland, applies a threshold (default 10%), and writes the
flag to `WardFarmland`. A full run covers all 4,009 wards.

WorldCover tiles are public Cloud-Optimized GeoTIFFs on AWS Open Data — no
Google Earth Engine account or credentials are needed, and only the pixels
covering each ward are fetched over HTTP range requests. A full run over
4,009 wards takes roughly two hours; `--skip-existing` resumes an
interrupted run and `--limit N` is useful for spot checks.

Tune the threshold by spot-checking known wards (`--threshold 15`).
Corrections after launch are reactive: either flip
`WardFarmland.manually_corrected`/`has_agric_land` by hand, or review
submissions in `FarmlandReport` (populated via the "report incorrect info"
endpoint above) in `/admin/`.

## Climate data-prep pipeline
`climate_pipeline` implements the Supervisor's formal 4-step pipeline from
CLAUDE.md as Django management commands under
`climate_pipeline/management/commands/`. Each step writes/reads files under
`pipeline_data/` (gitignored) and the last step writes directly to the
`WardClimate` table via the ORM.

```bash
python manage.py fetch_cmip6            # download the downscaled CMIP6 input
python manage.py run_climate_pipeline   # then Steps 1-4
```

### Climate input: NEX-GDDP-CMIP6
`fetch_cmip6` pulls **NASA Earth Exchange Global Daily Downscaled
Projections (NEX-GDDP-CMIP6)** — raw CMIP6 GCM output (~100-250km) put
through BCSD statistical downscaling and bias correction to **0.25°
(~25km)**. This is the "downscaled/bias-corrected CMIP6 product" Step 2
calls for rather than raw CMIP6.

It reads the monthly **ensemble-median** Cloud-Optimized GeoTIFFs (the
median across downscaled models — more defensible than one cherry-picked
GCM; `p10`/`p90` files exist on the same bucket for uncertainty bands).
Public AWS Open Data, CC0, no credentials. Only Nigeria's window of each
global file is fetched via HTTP range requests.

Defaults: scenario `ssp245`, period `2026-2035`, variables `tas`,
`tasmax`, `hurs`, `pr`. CMIP6 ships Kelvin and the fetch converts units,
with a plausibility check per variable so bad units cannot silently reach
the database.

Everything is stored locally — `pipeline_data/cmip6_nigeria.nc`, then
clipped to `climate_grid.nc`, then one `WardClimate` row per ward. The
running app never calls AWS; it reads the database.

⚠️ **`WardClimate` is a projection, not an observation.** The weather API
therefore always returns live NASA POWER as the observed conditions and
attaches the CMIP6 figures separately under `climate`, labelled with
their scenario and period. Never render a projection as today's weather.

At 25km, wards smaller than a grid cell share a value. Finer products
exist (CHELSA/ClimateAF at ~1km) but are climatologies, not
present-and-future time series.

Steps can also be run individually (`step1_delineate_boundary`,
`step2_extract_climate`, `step3_filter_wards_by_lulc`,
`step4_resample_to_wards`) — see each command's module docstring for its
arguments. `weather_data.views.WeatherByWardView` reads `WardClimate` first
and only falls back to a live NASA POWER call for wards the pipeline
hasn't covered, per CLAUDE.md.

Note: Step 1's boundary refinement against satellite imagery and Step 3's
LULC classification against a real ESA WorldCover raster are scaffolded
with real geopandas/rasterio/xarray/rioxarray logic, but still need real
GRID3/HDX/CMIP6/WorldCover inputs (and, for GEE-hosted WorldCover, Earth
Engine credentials) to produce production data — `--demo` mode exists so
the pipeline's wiring can be verified without them.
