"""
Imports real ward boundaries from GRID3 NGA Operational Wards v3.0 — the
primary ward source named in CLAUDE.md (HDX admin3 is the backup, and only
covers Borno/Adamawa/Yobe).

    python manage.py import_wards_grid3 --replace

States/LGAs must already exist (run `import_boundaries --download` first);
this only loads wards and attaches them to the matching LGA by name.
"""

import difflib
from pathlib import Path
from urllib.request import urlopen

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from boundaries.grid3 import GRID3_WARDS_HDX_URL, NORTHERN_STATES, load_grid3_wards, normalize
from boundaries.models import LGA, Ward


class Command(BaseCommand):
    help = "Import real ward boundaries for Northern Nigeria from GRID3 v3.0."

    def add_arguments(self, parser):
        parser.add_argument("--path", default="pipeline_data/grid3_wards.gpkg")
        parser.add_argument("--download", action="store_true")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete existing wards first (cascades to farmland/climate rows).",
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            if not options["download"]:
                raise CommandError(f"{path} not found — re-run with --download.")
            path.parent.mkdir(parents=True, exist_ok=True)
            self.stdout.write(f"Downloading GRID3 wards to {path} (~199MB)...")
            with urlopen(GRID3_WARDS_HDX_URL) as response, path.open("wb") as out:
                out.write(response.read())

        gdf = load_grid3_wards(path, states=NORTHERN_STATES)
        self.stdout.write(f"Read {len(gdf)} GRID3 wards across {gdf['state'].nunique()} states.")

        # Index existing LGAs by normalized (state, lga) for matching.
        lgas = list(LGA.objects.select_related("state"))
        if not lgas:
            raise CommandError("No LGAs in the database — run `import_boundaries --download` first.")
        by_key = {(normalize(l.state.name), normalize(l.name)): l for l in lgas}
        by_state: dict[str, list[str]] = {}
        for state_key, lga_key in by_key:
            by_state.setdefault(state_key, []).append(lga_key)

        unmatched, created = set(), 0
        with transaction.atomic():
            if options["replace"]:
                deleted, _ = Ward.objects.all().delete()
                self.stdout.write(f"Deleted {deleted} existing ward rows.")

            for row in gdf.itertuples():
                state_key = normalize(row.state)
                # Some LGAs are slash-joined in one source but not the other
                # ("Birnin Magaji/Kiyaw" vs "Birnin Magaji"), so try each part.
                candidates = [row.lga, *str(row.lga).split("/")]
                lga = next(
                    (by_key[(state_key, normalize(c))] for c in candidates
                     if (state_key, normalize(c)) in by_key),
                    None,
                )
                if lga is None:
                    # Spelling variants between GRID3 and the HDX COD list
                    # (e.g. "Birnin Kudu" vs "Birni Kudu") — match within state.
                    close = difflib.get_close_matches(
                        normalize(row.lga), by_state.get(state_key, []), n=1, cutoff=0.85
                    )
                    if close:
                        lga = by_key[(state_key, close[0])]
                if lga is None:
                    unmatched.add(f"{row.state}/{row.lga}")
                    continue

                point = row.geometry.representative_point()
                Ward.objects.update_or_create(
                    code=row.ward_code,
                    defaults={
                        "name": row.ward,
                        "lga": lga,
                        "latitude": point.y,
                        "longitude": point.x,
                    },
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Imported {created} wards."))
        if unmatched:
            self.stderr.write(
                self.style.WARNING(
                    f"{len(unmatched)} LGA(s) had no match and their wards were skipped: "
                    + ", ".join(sorted(unmatched)[:10])
                )
            )
        missing = sorted(set(NORTHERN_STATES) - set(gdf["state"].unique()))
        if missing:
            self.stdout.write(
                self.style.WARNING(
                    f"GRID3 v3.0 has no ward coverage for: {', '.join(missing)} "
                    "— these states remain State+LGA only."
                )
            )
