# Weather Backend

Django + Django REST Framework API for the Northern Nigeria Weather &
Farmland app. See `CLAUDE.md` for the full project background.

## Stack
- Django 5 / Django REST Framework
- SQLite for local dev (swap `DATABASES` in `config/settings.py` for
  Postgres in production)

## Apps
- `boundaries` — State → LGA → Ward reference data, plus `WardFarmland`
  (Feature 2's pre-computed cropland flag).
- `weather_data` — Feature 1: live NASA POWER lookups by point or by ward.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_boundaries   # placeholder demo boundaries
python manage.py createsuperuser   # optional, for /admin/
python manage.py runserver
```

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/states/` | List states |
| `GET /api/states/<id>/lgas/` | List LGAs in a state |
| `GET /api/lgas/<id>/wards/` | List wards in an LGA |
| `GET /api/weather/?lat=&lon=` | Live NASA POWER weather for a point (e.g. a map tap) |
| `GET /api/weather/ward/<id>/` | Live NASA POWER weather for a ward's centroid |
| `GET /api/wards/<id>/farmland/` | Pre-computed agricultural-land flag for a ward |

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

## Boundary data (TODO — replace placeholder seed)
`seed_boundaries` only inserts a handful of demo wards so the app runs
end-to-end locally. For real coverage, import GRID3 (data.grid3.org) or HDX
(data.humdata.org) State/LGA/Ward shapefiles: for each ward, compute a
centroid (lat/lon) and load `State`/`LGA`/`Ward` rows from it. Verify
ward-level coverage per target state before relying on it.

## Farmland flag batch job (TODO)
Feature 2's `WardFarmland` rows are meant to be populated by a one-time,
offline script (not included yet) that, per ward boundary, computes the
percent of ward area ESA WorldCover classifies as "Cropland" (via Google
Earth Engine or Digital Earth Africa) and applies a threshold (~10-15%,
tune by spot-checking known wards). Corrections after launch are reactive:
flip `WardFarmland.manually_corrected` and `has_agric_land` by hand when a
ward is reported wrong.
