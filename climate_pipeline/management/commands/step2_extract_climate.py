"""
Step 2 of the Supervisor's formal data-prep pipeline (see CLAUDE.md):
extract temperature and rainfall for the whole Northern Nigeria boundary
(Step 1) from a downscaled/bias-corrected CMIP6 product.

Raw CMIP6 GCM output is coarse (often 100km+ per cell) — too rough for
ward-level work. This command expects an already-downscaled product
(0.25°/10km/~1km-for-Africa examples exist), not raw CMIP6.

Real run:
    python manage.py step2_extract_climate \
        --climate-nc path/to/downscaled_cmip6.nc

Demo run (synthesizes a small, plausible savannah-climate grid instead of
requiring a real downscaled CMIP6 file):
    python manage.py step2_extract_climate --demo
"""

from pathlib import Path

import geopandas as gpd
import rioxarray  # noqa: F401 — registers the .rio accessor on xarray objects
import xarray as xr
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Step 2: extract temperature/rainfall over Northern Nigeria from a downscaled CMIP6 product."

    def add_arguments(self, parser):
        parser.add_argument(
            "--climate-nc",
            default="pipeline_data/cmip6_nigeria.nc",
            help="Downscaled/bias-corrected CMIP6 NetCDF with 'tas'/'pr' (default: output of fetch_cmip6).",
        )
        parser.add_argument("--boundary", default="pipeline_data/northern_nigeria_boundary.geojson")
        parser.add_argument("--out", default="pipeline_data/climate_grid.nc")

    def handle(self, *args, **options):
        boundary_path = Path(options["boundary"])
        if not boundary_path.exists():
            raise CommandError(f"{boundary_path} not found — run step1_delineate_boundary first.")
        boundary = gpd.read_file(boundary_path)

        nc_path = Path(options["climate_nc"])
        if not nc_path.exists():
            raise CommandError(
                f"{nc_path} not found — run `python manage.py fetch_cmip6` first. "
                "This pipeline does not synthesize climate data."
            )
        ds = xr.open_dataset(nc_path)
        # NOTE: adjust x_dim/y_dim below if the real product names its
        # coordinates something other than lon/lat (e.g. longitude/latitude).

        ds = ds.rio.set_spatial_dims(x_dim="lon", y_dim="lat", inplace=False)
        ds = ds.rio.write_crs("EPSG:4326", inplace=False)
        clipped = ds.rio.clip(boundary.geometry.values, boundary.crs, drop=True)

        out_path = Path(options["out"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        clipped.to_netcdf(out_path)
        self.stdout.write(self.style.SUCCESS(f"Wrote clipped climate grid to {out_path}"))
