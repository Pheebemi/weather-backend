"""
Step 3 of the Supervisor's formal data-prep pipeline (see CLAUDE.md):
classify land cover (LULC — the formal name for what ESA WorldCover does,
see Feature 2) across the region and keep ONLY wards that are significantly
agricultural or forested. Wards that are mostly urban, bare, water, etc.
are dropped from the working dataset entirely here, not just flagged.

Runs against the real HDX ward boundaries and the real public ESA
WorldCover tiles fetched by `import_boundaries --download`:

    python manage.py step3_filter_wards_by_lulc --threshold 15
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from boundaries.grid3 import NORTHERN_STATES, load_grid3_wards
from boundaries.models import Ward, WardFarmland
from boundaries.worldcover import CROPLAND, TREE_COVER, class_percentages

# Percent of ward area that must be agricultural/forested to keep the ward
# in the study — tune by spot-checking known wards, per CLAUDE.md Step 3.
DEFAULT_THRESHOLD_PCT = 15.0
AGRIC_FOREST_CLASSES = {TREE_COVER, CROPLAND}


class Command(BaseCommand):
    help = "Step 3: keep only wards that are significantly agricultural or forested."

    def add_arguments(self, parser):
        parser.add_argument(
            "--wards-path",
            default="pipeline_data/grid3_wards.gpkg",
            help="GRID3 ward geopackage (same source the wards were imported from).",
        )
        parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD_PCT)
        parser.add_argument("--out", default="pipeline_data/filtered_wards.json")
        parser.add_argument(
            "--no-reuse",
            action="store_true",
            help="Read every ward from the satellite instead of reusing stored cropland results.",
        )

    def handle(self, *args, **options):
        wards_path = Path(options["wards_path"])
        if not wards_path.exists():
            raise CommandError(
                f"{wards_path} not found — run `python manage.py import_wards_grid3 --download` first."
            )

        threshold = options["threshold"]
        wards_gdf = load_grid3_wards(wards_path, states=NORTHERN_STATES)

        known_codes = set(Ward.objects.values_list("code", flat=True))
        if not known_codes:
            raise CommandError("No wards in the database — run `import_wards_grid3` first.")

        # Cropland alone is already known per ward from compute_farmland, and
        # the filter keeps wards that are cropland OR forest. So any ward
        # already at/above the threshold on cropland qualifies without
        # touching the satellite again — only the remainder need a read to
        # see whether tree cover carries them over.
        cropland = dict(
            WardFarmland.objects.values_list("ward__code", "cropland_percent")
        ) if not options["no_reuse"] else {}

        results, reused, read = [], 0, 0
        for _, row in wards_gdf.iterrows():
            code = row["ward_code"]
            if code not in known_codes:
                continue

            known_cropland = cropland.get(code)
            if known_cropland is not None and known_cropland >= threshold:
                results.append(
                    {"ward_code": code, "agric_forest_pct": round(float(known_cropland), 2),
                     "basis": "cropland (from stored WorldCover result)"}
                )
                reused += 1
                continue

            try:
                pct = class_percentages(row.geometry, AGRIC_FOREST_CLASSES)
            except Exception as exc:  # noqa: BLE001 — one bad ward shouldn't kill a long batch
                self.stderr.write(f"  {code} failed: {exc}")
                continue
            read += 1
            if read % 50 == 0:
                self.stdout.write(f"  ...{read} wards read from satellite")
            if pct >= threshold:
                results.append(
                    {"ward_code": code, "agric_forest_pct": round(float(pct), 2),
                     "basis": "cropland + tree cover"}
                )

        out_path = Path(options["out"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2))
        self.stdout.write(
            self.style.SUCCESS(
                f"Kept {len(results)} agric/forest wards (>= {threshold}%) -> {out_path}\n"
                f"  {reused} qualified on stored cropland; {read} needed a satellite read."
            )
        )
