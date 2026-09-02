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
