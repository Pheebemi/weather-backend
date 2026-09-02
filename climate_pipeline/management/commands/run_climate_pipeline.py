"""
Runs Steps 1-4 of the Supervisor's formal data-prep pipeline (see
CLAUDE.md) in sequence. See the individual step commands for details.

Steps 1 and 3 use the real HDX boundaries and real public ESA WorldCover
tiles already fetched by `import_boundaries --download`. Step 2 needs a
real downscaled/bias-corrected CMIP6 NetCDF, which you must supply:

    python manage.py run_climate_pipeline --climate-nc path/to/downscaled_cmip6.nc
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run Steps 1-4 of the climate data-prep pipeline in sequence."

    def add_arguments(self, parser):
        parser.add_argument("--climate-nc", required=True)
        parser.add_argument("--threshold", type=float, default=15.0)

    def handle(self, *args, **options):
        if not options["climate_nc"]:
            raise CommandError(
                "--climate-nc is required: a real downscaled/bias-corrected CMIP6 NetCDF."
            )

        self.stdout.write("Step 1/4: delineate boundary...")
        call_command("step1_delineate_boundary")

        self.stdout.write("Step 2/4: extract climate...")
        call_command("step2_extract_climate", climate_nc=options["climate_nc"])

        self.stdout.write("Step 3/4: filter wards by LULC...")
        call_command("step3_filter_wards_by_lulc", threshold=options["threshold"])

        self.stdout.write("Step 4/4: resample climate onto wards...")
        call_command("step4_resample_to_wards")

        self.stdout.write(self.style.SUCCESS("Pipeline complete."))
