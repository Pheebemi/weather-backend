"""
LGA-level fallback for Feature 2.

Benue, Plateau and Taraba have no ward boundaries in any open source
(GRID3 v2/v3, HDX COD, geoBoundaries and eHealth Africa were all checked —
see README). Rather than leave those states with an empty farmland tier,
this runs the same real ESA WorldCover computation against their LGA
polygons instead.

    python manage.py compute_farmland_lga

By default it only processes LGAs whose state has no wards at all, so
states with ward coverage keep using the finer ward-level figures.
"""

from pathlib import Path

import geopandas as gpd
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from boundaries.models import LGA, LGAFarmland, State
from boundaries.worldcover import CROPLAND, SOURCE_LABEL, class_percentages


class Command(BaseCommand):
    help = "Compute LGA-level cropland %% for states that have no ward boundaries."

    def add_arguments(self, parser):
        parser.add_argument("--data-dir", default="pipeline_data")
        parser.add_argument("--threshold", type=float, default=10.0)
        parser.add_argument(
            "--all-states",
            action="store_true",
            help="Process every LGA, not just those in states without ward coverage.",
        )
        parser.add_argument("--skip-existing", action="store_true")

    def handle(self, *args, **options):
        shapefile = Path(options["data_dir"]) / "nga_boundaries" / "nga_admin2.shp"
        if not shapefile.exists():
            raise CommandError(f"{shapefile} not found — run `import_boundaries --download` first.")

        threshold = options["threshold"]
        lgas_gdf = gpd.read_file(shapefile).set_index("adm2_pcode")

        lgas = LGA.objects.select_related("state")
        if not options["all_states"]:
            states_without_wards = (
                State.objects.annotate(n=Count("lgas__wards")).filter(n=0).values_list("id", flat=True)
            )
            lgas = lgas.filter(state_id__in=states_without_wards)
        if options["skip_existing"]:
            lgas = lgas.filter(farmland__isnull=True)

        lgas = list(lgas)
        self.stdout.write(f"Processing {len(lgas)} LGAs...")

        done = failed = 0
        for lga in lgas:
            if lga.code not in lgas_gdf.index:
                continue
            try:
                cropland_pct = class_percentages(lgas_gdf.loc[lga.code, "geometry"], {CROPLAND})
            except Exception as exc:  # noqa: BLE001 — one bad LGA shouldn't kill the batch
                self.stderr.write(f"  {lga.name} ({lga.code}) failed: {exc}")
                failed += 1
                continue

            LGAFarmland.objects.update_or_create(
                lga=lga,
                defaults={
                    "has_agric_land": cropland_pct >= threshold,
                    "cropland_percent": round(cropland_pct, 2),
                    "threshold_used": threshold,
                    "source": SOURCE_LABEL,
                },
            )
            done += 1
            if done % 10 == 0:
                self.stdout.write(f"  ...{done}/{len(lgas)}")

        self.stdout.write(
            self.style.SUCCESS(f"Computed LGA farmland for {done} LGAs ({failed} failed).")
        )
