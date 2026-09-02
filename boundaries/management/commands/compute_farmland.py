"""
Feature 2's real batch job: computes each ward's agricultural-land flag
from REAL ESA WorldCover satellite land-cover data (10m, v200/2021).

No Google Earth Engine account or credentials needed — see
boundaries/worldcover.py.

    python manage.py compute_farmland

Ward polygons come from the same HDX shapefile used by import_boundaries
(geometry lives in the shapefile; only the computed result is stored in
the DB, per CLAUDE.md Feature 2).
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from boundaries.grid3 import NORTHERN_STATES, load_grid3_wards
from boundaries.models import Ward, WardFarmland
from boundaries.worldcover import CROPLAND, SOURCE_LABEL, class_percentages


class Command(BaseCommand):
    help = "Compute real per-ward cropland %% from ESA WorldCover and store the agric-land flag."

    def add_arguments(self, parser):
        parser.add_argument("--data-dir", default="pipeline_data")
        parser.add_argument(
            "--threshold",
            type=float,
            default=10.0,
            help="Cropland %% at or above which a ward is flagged as having agricultural land.",
        )
        parser.add_argument("--limit", type=int, help="Only process the first N wards (for testing).")
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip wards that already have a WardFarmland row (resume an interrupted run).",
        )

    def handle(self, *args, **options):
        wards_path = Path(options["data_dir"]) / "grid3_wards.gpkg"
        if not wards_path.exists():
            raise CommandError(
                f"{wards_path} not found — run `import_wards_grid3 --download` first."
            )

        threshold = options["threshold"]
        wards_gdf = load_grid3_wards(wards_path, states=NORTHERN_STATES).set_index("ward_code")

        wards = Ward.objects.all()
        if options["skip_existing"]:
            wards = wards.filter(farmland__isnull=True)
        if options["limit"]:
            wards = wards[: options["limit"]]

        done = failed = 0
        for ward in wards:
            if ward.code not in wards_gdf.index:
                continue
            try:
                cropland_pct = class_percentages(wards_gdf.loc[ward.code, "geometry"], {CROPLAND})
            except Exception as exc:  # noqa: BLE001 — one bad ward shouldn't kill a long batch
                self.stderr.write(f"  {ward.name} ({ward.code}) failed: {exc}")
                failed += 1
                continue

            WardFarmland.objects.update_or_create(
                ward=ward,
                defaults={
                    "has_agric_land": cropland_pct >= threshold,
                    "cropland_percent": round(cropland_pct, 2),
                    "threshold_used": threshold,
                    "source": SOURCE_LABEL,
                },
            )
            done += 1
            if done % 25 == 0:
                self.stdout.write(f"  ...{done} wards processed")

        self.stdout.write(
            self.style.SUCCESS(f"Computed farmland flags for {done} wards ({failed} failed).")
        )
