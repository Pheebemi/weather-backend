"""
Step 4 of the Supervisor's formal data-prep pipeline (see CLAUDE.md):
overlay the Step 2 climate grid onto the Step 3 filtered ward boundaries
and write an area-weighted temperature/rainfall average into WardClimate
for each surviving ward. This is the table weather_data/views.py reads
from in preference to a live NASA POWER call.

    python manage.py step4_resample_to_wards
"""

import json
import warnings
from pathlib import Path

import numpy as np
import rioxarray  # noqa: F401 — registers the .rio accessor on xarray objects
import xarray as xr
from django.core.management.base import BaseCommand, CommandError

from boundaries.grid3 import NORTHERN_STATES, load_grid3_wards
from boundaries.models import Ward
from climate_pipeline.models import WardClimate

SOURCE = "Downscaled/bias-corrected CMIP6 (offline pipeline, Step 4 output)"


class Command(BaseCommand):
    help = "Step 4: resample the climate grid onto filtered ward boundaries and store per-ward averages."

    def add_arguments(self, parser):
        parser.add_argument("--climate-grid", default="pipeline_data/climate_grid.nc")
        parser.add_argument("--filtered-wards", default="pipeline_data/filtered_wards.json")
        parser.add_argument("--wards-path", default="pipeline_data/grid3_wards.gpkg")

    def handle(self, *args, **options):
        grid_path = Path(options["climate_grid"])
        filtered_path = Path(options["filtered_wards"])
        wards_path = Path(options["wards_path"])
        if not grid_path.exists():
            raise CommandError(f"{grid_path} not found — run step2_extract_climate first.")
        if not filtered_path.exists():
            raise CommandError(f"{filtered_path} not found — run step3_filter_wards_by_lulc first.")
        if not wards_path.exists():
            raise CommandError(f"{wards_path} not found — run import_wards_grid3 --download first.")

        ds = xr.open_dataset(grid_path)
        ds = ds.rio.set_spatial_dims(x_dim="lon", y_dim="lat", inplace=False)
        ds = ds.rio.write_crs("EPSG:4326", inplace=False)

        # Carried through from fetch_cmip6 so each stored value says which
        # scenario and period it represents.
        scenario = ds.attrs.get("scenario", "")
        period = ds.attrs.get("period", "")
        source = ds.attrs.get("source", SOURCE)

        filtered_codes = {row["ward_code"] for row in json.loads(filtered_path.read_text())}
        code_to_ward = {w.code: w for w in Ward.objects.filter(code__in=filtered_codes)}
        if not code_to_ward:
            raise CommandError("No DB wards matched the filtered ward codes from Step 3.")

        wards_gdf = load_grid3_wards(wards_path, states=NORTHERN_STATES)
        written = nearest = skipped = 0

        for _, row in wards_gdf.iterrows():
            ward = code_to_ward.get(row["ward_code"])
            if ward is None:
                continue

            # The source grid is regular lat/lon, so the mean of cells
            # clipped to the ward polygon *is* the area-weighted average.
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", "Mean of empty slice", RuntimeWarning)
                clipped = ds.rio.clip([row.geometry], wards_gdf.crs, drop=True, all_touched=True)
                values = {var: self._mean(clipped, var) for var in ("tas", "pr", "tasmax", "hurs")}

                # A ward smaller than a 25km cell, or sitting on cells the
                # boundary clip masked out, yields no value. Assign it the
                # nearest cell to its centroid rather than dropping it.
                if values["tas"] is None and ward.latitude is not None:
                    point = ds.sel(lat=ward.latitude, lon=ward.longitude, method="nearest")
                    values = {var: self._value(point, var) for var in values}
                    if values["tas"] is not None:
                        nearest += 1

            if values["tas"] is None or values["pr"] is None:
                skipped += 1
                continue

            WardClimate.objects.update_or_create(
                ward=ward,
                scenario=scenario,
                period=period,
                defaults={
                    "temperature_avg_c": values["tas"],
                    "precipitation_avg_mm": values["pr"],
                    "temperature_max_avg_c": values["tasmax"],
                    "humidity_avg_pct": values["hurs"],
                    "climate_source": source,
                },
            )
            written += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote WardClimate for {written} ward(s).\n"
                f"  {nearest} used the nearest grid cell (ward smaller than the grid); "
                f"{skipped} had no climate data and were skipped."
            )
        )

    @staticmethod
    def _mean(dataset, var):
        if var not in dataset:
            return None
        value = float(dataset[var].mean(skipna=True).values)
        return None if np.isnan(value) else value

    @staticmethod
    def _value(point, var):
        if var not in point:
            return None
        value = float(point[var].values)
        return None if np.isnan(value) else value
