"""
Fetches the real downscaled CMIP6 climate input for Step 2 of the
Supervisor's pipeline (see CLAUDE.md).

Source: NEX-GDDP-CMIP6 — NASA Earth Exchange Global Daily Downscaled
Projections, CMIP6. Raw CMIP6 GCM output (~100-250km) put through BCSD
statistical downscaling and bias correction to 0.25° (~25km), which is the
"downscaled/bias-corrected CMIP6 product" Step 2 calls for rather than raw
CMIP6.

We read the monthly ensemble-median Cloud-Optimized GeoTIFFs: the median
across the downscaled models (downscaling happens per model first), which
is more defensible than picking a single GCM. Public AWS Open Data, no
credentials, CC0. Only the Nigeria window of each global file is fetched,
via HTTP range requests.

    python manage.py fetch_cmip6 --scenario ssp245 --start-year 2026 --end-year 2035

Writes a NetCDF with annual-mean temperature (°C) and annual total
rainfall (mm/year) per grid cell, which step2_extract_climate then clips
to the Northern Nigeria boundary.
"""

import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
from django.core.management.base import BaseCommand, CommandError
from rasterio.windows import from_bounds

BASE_URL = (
    "https://nex-gddp-cmip6-cog.s3.us-west-2.amazonaws.com/monthly/"
    "CMIP6_ensemble_median/{var}/{var}_month_ensemble-median_{scenario}_{yyyymm}.tif"
)

# Nigeria bounding box (lon_min, lat_min, lon_max, lat_max) with a margin.
NIGERIA_BBOX = (2.0, 3.5, 15.5, 14.5)

KELVIN_OFFSET = 273.15

# How each CMIP6 variable is aggregated from monthly fields to one annual
# figure per grid cell, and what it becomes in the output.
#   "mean" — average of every monthly field across the whole period
#   "annual_total" — monthly totals summed per year, then averaged over years
VARIABLE_SPECS = {
    "tas": {
        "agg": "mean",
        "offset": -KELVIN_OFFSET,
        "units": "degC",
        "long_name": "Annual mean temperature",
        "plausible": (15, 40),
    },
    "tasmax": {
        "agg": "mean",
        "offset": -KELVIN_OFFSET,
        "units": "degC",
        "long_name": "Annual mean daily maximum temperature",
        "plausible": (20, 48),
    },
    "hurs": {
        "agg": "mean",
        "offset": 0.0,
        "units": "%",
        "long_name": "Annual mean relative humidity",
        "plausible": (5, 100),
    },
    "pr": {
        "agg": "annual_total",
        "offset": 0.0,
        "units": "mm/year",
        "long_name": "Annual total rainfall",
        "plausible": (100, 4000),
    },
}

DEFAULT_VARIABLES = ["tas", "tasmax", "hurs", "pr"]


class Command(BaseCommand):
    help = "Download the downscaled CMIP6 (NEX-GDDP) climate grid for Nigeria."

    def add_arguments(self, parser):
        parser.add_argument("--scenario", default="ssp245")
        parser.add_argument("--start-year", type=int, default=2026)
        parser.add_argument("--end-year", type=int, default=2035)
        parser.add_argument("--workers", type=int, default=12)
        parser.add_argument(
            "--variables",
            nargs="+",
            default=DEFAULT_VARIABLES,
            choices=sorted(VARIABLE_SPECS),
            help="CMIP6 variables to fetch.",
        )
        parser.add_argument("--out", default="pipeline_data/cmip6_nigeria.nc")

    def handle(self, *args, **options):
        scenario = options["scenario"]
        variables = options["variables"]
        years = list(range(options["start_year"], options["end_year"] + 1))
        if not years:
            raise CommandError("--start-year must not be after --end-year.")

        jobs = [
            (var, f"{year}{month:02d}")
            for var in variables
            for year in years
            for month in range(1, 13)
        ]
        self.stdout.write(
            f"Fetching {len(jobs)} monthly grids "
            f"({scenario}, {years[0]}-{years[-1]}, NEX-GDDP-CMIP6 ensemble median)..."
        )

        results: dict[str, list[np.ndarray]] = {var: [] for var in variables}
        coords: dict[str, np.ndarray] = {}
        failures = []

        def fetch(job):
            var, yyyymm = job
            url = "/vsicurl/" + BASE_URL.format(var=var, scenario=scenario, yyyymm=yyyymm)
            with rasterio.open(url) as src:
                window = from_bounds(*NIGERIA_BBOX, src.transform)
                data = src.read(1, window=window, masked=True).filled(np.nan)
                transform = src.window_transform(window)
            return var, data, transform, data.shape

        with ThreadPoolExecutor(max_workers=options["workers"]) as pool:
            for i, outcome in enumerate(pool.map(self._safe(fetch, failures), jobs), 1):
                if outcome is None:
                    continue
                var, data, transform, shape = outcome
                results[var].append(data)
                if "lat" not in coords:
                    rows, cols = shape
                    coords["lon"] = transform.c + transform.a * (np.arange(cols) + 0.5)
                    coords["lat"] = transform.f + transform.e * (np.arange(rows) + 0.5)
                if i % 50 == 0:
                    self.stdout.write(f"  ...{i}/{len(jobs)}")

        if failures:
            self.stderr.write(f"{len(failures)} grids failed, e.g. {failures[0]}")
        missing = [var for var in variables if not results[var]]
        if missing:
            raise CommandError(
                f"No grids downloaded for {', '.join(missing)} — check scenario/year range."
            )

        n_years = len(years)
        data_vars = {}
        with warnings.catch_warnings():
            # Cells that are all-NaN (ocean) are expected — the bbox includes sea.
            warnings.filterwarnings("ignore", "Mean of empty slice", RuntimeWarning)
            for var in variables:
                spec = VARIABLE_SPECS[var]
                stacked = np.stack(results[var])
                if spec["agg"] == "annual_total":
                    values = np.nansum(stacked, axis=0) / n_years
                else:
                    values = np.nanmean(stacked, axis=0)
                values = values + spec["offset"]
                self._sanity_check(var, values, spec)
                data_vars[var] = (
                    ["lat", "lon"],
                    values,
                    {"units": spec["units"], "long_name": spec["long_name"]},
                )

        ds = xr.Dataset(
            data_vars,
            coords={"lat": coords["lat"], "lon": coords["lon"]},
            attrs={
                "source": "NEX-GDDP-CMIP6 ensemble median (BCSD downscaled/bias-corrected CMIP6, 0.25deg)",
                "scenario": scenario,
                "period": f"{years[0]}-{years[-1]}",
            },
        )

        out_path = Path(options["out"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        ds.to_netcdf(out_path)
        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {out_path} — {scenario} {years[0]}-{years[-1]}, "
                f"variables {', '.join(variables)}, grid {ds.sizes['lat']}x{ds.sizes['lon']}"
            )
        )

    @staticmethod
    def _safe(fn, failures):
        def wrapper(job):
            try:
                return fn(job)
            except Exception as exc:  # noqa: BLE001 — one bad month shouldn't kill the batch
                failures.append(f"{job}: {exc}")
                return None

        return wrapper

    def _sanity_check(self, var, values, spec):
        """Flag obviously wrong units before bad data can reach the database."""
        mean = float(np.nanmean(values))
        self.stdout.write(f"  {var}: mean {mean:.1f} {spec['units']}")
        low, high = spec["plausible"]
        if not low < mean < high:
            self.stderr.write(
                self.style.WARNING(
                    f"  {var} mean {mean:.1f} outside plausible {low}-{high} {spec['units']} "
                    "— check units!"
                )
            )
