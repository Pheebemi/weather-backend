# Deploying

The frontend and backend deploy to different places, for a reason worth
knowing before you start.

## Why the backend does not go on Vercel

Vercel runs the Next.js frontend well. It is a poor fit for this Django
backend:

- Vercel's Python runtime is serverless. Django expects a long-running
  process, and cold starts hurt on every first request.
- The management commands are batch jobs that run for minutes to hours
  (`compute_farmland` takes ~2h over 4,009 wards). Serverless functions
  time out long before that.
- Even with the geo stack excluded, a serverless bundle is a tight fit;
  with geopandas/rasterio/xarray it is far over the limit.

So: **frontend on Vercel, backend on a service that runs a real process**
— Render, Railway or Fly.io all work. Database on Neon either way.

## Runtime vs pipeline dependencies

The serving API never imports geopandas, rasterio or xarray — those are
used only by the offline management commands. The split keeps the deployed
image small:

```bash
pip install -r requirements.txt                              # serving the API
pip install -r requirements.txt -r requirements-pipeline.txt # + running the pipeline
```

Deploy with `requirements.txt` only. Run the pipeline locally (or on a
machine with the geo stack) and push its *output* to the database.

## 1. Database on Neon

Create a Neon project, copy the connection string, and set it as
`DATABASE_URL`. `config/settings.py` switches to Postgres whenever that
variable is present and falls back to SQLite locally, so nothing changes
for local development.

```bash
export DATABASE_URL='postgresql://user:pass@ep-xxx.neon.tech/dbname'
python manage.py migrate
```

## 2. Getting the existing data into Neon

All 12,097 rows — boundaries, farmland flags and ward climate — are
committed as a compressed fixture, so production does not need to re-run
the satellite jobs:

```bash
DATABASE_URL='...' python manage.py migrate
DATABASE_URL='...' python manage.py loaddata fixtures/seed_data.json.gz
```

Regenerate it after a pipeline re-run:

```bash
python manage.py dumpdata boundaries climate_pipeline \
    --natural-foreign --indent 0 --output fixtures/seed_data.json
gzip -f fixtures/seed_data.json
```

The raw `.json` is gitignored; only the `.gz` is committed.

## 3. Backend service

`render.yaml` is included. Environment variables to set:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Neon connection string |
| `DJANGO_SECRET_KEY` | a fresh random secret — not the dev default |
| `DJANGO_DEBUG` | `false` |
| `DJANGO_ALLOWED_HOSTS` | your backend hostname |
| `CORS_ALLOWED_ORIGINS` | your Vercel frontend URL |
| `CSRF_TRUSTED_ORIGINS` | your Vercel frontend URL |

Start command: `gunicorn config.wsgi:application`. Static files are served
by WhiteNoise, so run `collectstatic` at build time.

## 4. Frontend on Vercel

Set one environment variable:

```
NEXT_PUBLIC_API_BASE_URL=https://your-backend-host/api
```

It is baked in at build time, so redeploy after changing it.

## 5. Re-running the pipeline later

The pipeline stays a local/offline job. After a re-run, either dump and
load the fixture as above, or point the commands straight at Neon:

```bash
DATABASE_URL='...' python manage.py compute_farmland
```

That writes results directly to production. Reads are the slow part
(satellite tiles), not the writes.
