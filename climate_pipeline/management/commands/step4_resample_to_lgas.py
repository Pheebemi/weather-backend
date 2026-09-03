"""
LGA-level counterpart to step 4, for states with no ward boundaries
(Benue, Plateau, Taraba — see the backend README).

Same area-weighted resample of the Step 2 climate grid, run against LGA
polygons instead of ward polygons, so those states are not left blank.

    python manage.py step4_resample_to_lgas
"""

import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import rioxarray  # noqa: F401 — registers the .rio accessor
import xarray as xr
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from boundaries.models import LGA, State
from climate_pipeline.models import LGAClimate


class Command(BaseCommand):
    help = "Resample the climate grid onto LGA polygons for states without wards."

    def add_arguments(self, parser):
        parser.add_argument("--climate-grid", default="pipeline_data/climate_grid.nc")
        parser.add_argument("--lgas-shapefile", default="pipeline_data/nga_boundaries/nga_admin2.shp")
        parser.add_argument(
            "--all-states",
            action="store_true",
            help="Process every LGA, not just those in states without ward coverage.",
        )

    def handle(self, *args, **options):
        grid_path = Path(options["climate_grid"])
        shapefile = Path(options["lgas_shapefile"])
        if not grid_path.exists():
            raise CommandError(f"{grid_path} not found — run step2_extract_climate first.")
        if not shapefile.exists():
            raise CommandError(f"{shapefile} not found — run import_boundaries --download first.")

        ds = xr.open_dataset(grid_path)
        ds = ds.rio.set_spatial_dims(x_dim="lon", y_dim="lat", inplace=False)
        ds = ds.rio.write_crs("EPSG:4326", inplace=False)
        scenario = ds.attrs.get("scenario", "")
        period = ds.attrs.get("period", "")
        source = ds.attrs.get("source", "")

        lgas = LGA.objects.select_related("state")
        if not options["all_states"]:
            without_wards = (
                State.objects.annotate(n=Count("lgas__wards")).filter(n=0).values_list("id", flat=True)
            )
            lgas = lgas.filter(state_id__in=without_wards)
        code_to_lga = {l.code: l for l in lgas}
        if not code_to_lga:
            raise CommandError("No matching LGAs found.")

        gdf = gpd.read_file(shapefile)
        written = nearest = skipped = 0

        for _, row in gdf.iterrows():
            lga = code_to_lga.get(row["adm2_pcode"])
            if lga is None:
                continue

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", "Mean of empty slice", RuntimeWarning)
                clipped = ds.rio.clip([row.geometry], gdf.crs, drop=True, all_touched=True)
                values = {v: self._mean(clipped, v) for v in ("tas", "pr", "tasmax", "hurs")}

                if values["tas"] is None and lga.latitude is not None:
                    point = ds.sel(lat=lga.latitude, lon=lga.longitude, method="nearest")
                    values = {v: self._value(point, v) for v in values}
                    if values["tas"] is not None:
                        nearest += 1

            if values["tas"] is None or values["pr"] is None:
                skipped += 1
                continue

            LGAClimate.objects.update_or_create(
                lga=lga,
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
                f"Wrote LGAClimate for {written} LGA(s); {nearest} used the nearest "
                f"grid cell, {skipped} had no covering data."
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
