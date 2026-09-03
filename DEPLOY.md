# Deploying

The frontend and backend deploy to different places, for a reason worth
knowing before you start.

## Backend on Vercel — what to watch

The backend is deployed on Vercel and `config/settings.py` already handles
Vercel's per-deploy hostnames (any `*.vercel.app` host/origin is allowed
when `VERCEL=1` is set). Two constraints matter there:

- **Keep the geo stack out of the deployment.** geopandas, rasterio and
  xarray together are far too large for a serverless bundle. The serving
  API never imports them — see the split below — so deploy with
  `requirements.txt` only.
- **The pipeline cannot run on Vercel.** `compute_farmland` takes ~2 hours
  over 4,009 wards; serverless functions time out in minutes. Run every
  management command locally and push the *results* to the database.

If cold starts on the free tier become a problem, a service that keeps a
process warm (Render, Railway, Fly) is the alternative — `render.yaml` is
included for that case, and nothing else in the setup changes.

## Runtime vs pipeline dependencies

The serving API never imports geopandas, rasterio or xarray — those are
used only by the offline management commands. The split keeps the deployed
image small:

```bash
pip install -r requirements.txt                              # serving the API
pip install -r requirements.txt -r requirements-pipeline.txt # + running the pipeline
```

Deploy with `requirements.txt` only. Run the pipeline locally and push its
*output* to the database.

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
the satellite jobs. Use fast_loaddata, not loaddata — stock loaddata does
one INSERT per row, which over a remote connection takes hours:

```bash
DATABASE_URL='...' python manage.py migrate
DATABASE_URL='...' python manage.py fast_loaddata fixtures/seed_data.json.gz
```

Regenerate it after a pipeline re-run:

```bash
python manage.py dumpdata boundaries climate_pipeline \
    --natural-foreign --indent 0 --output fixtures/seed_data.json
gzip -f fixtures/seed_data.json
```

The raw `.json` is gitignored; only the `.gz` is committed.

## 3. Backend environment variables

On Vercel these go in Project Settings → Environment Variables:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Neon connection string |
| `DJANGO_SECRET_KEY` | a fresh random secret — not the dev default |
| `DJANGO_DEBUG` | `false` |
| `DJANGO_ALLOWED_HOSTS` | only needed on a custom domain — `*.vercel.app` is automatic |
| `CORS_ALLOWED_ORIGINS` | only needed on a custom domain |
| `CSRF_TRUSTED_ORIGINS` | your frontend URL, if you add admin/POST from a browser |

On Render/Railway/Fly instead, the start command is
`gunicorn config.wsgi:application` (add `gunicorn` to requirements).

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
