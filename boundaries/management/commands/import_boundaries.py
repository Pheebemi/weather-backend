"""
Imports REAL State/LGA/Ward boundaries for Northern Nigeria from the HDX
Common Operational Dataset (UN OCHA, "Nigeria - Subnational Administrative
Boundaries"), which is free and needs no authentication.

    python manage.py import_boundaries --download --reset

Coverage warning (matches the caveat in CLAUDE.md): HDX ward-level
(admin3) data currently covers only the northeast BAY states — Borno,
Adamawa and Yobe. The other northern states get State + LGA rows only,
with no wards, until GRID3 ward coverage is obtained for them.
"""

import zipfile
from pathlib import Path
from urllib.request import urlopen

import geopandas as gpd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from boundaries.models import LGA, State, Ward

HDX_SHAPEFILE_URL = (
    "https://data.humdata.org/dataset/81ac1d38-f603-4a98-804d-325c658599a3/"
    "resource/01c65fd9-bd0c-4608-aa1e-2e86bbccf3e5/download/nga_admin_boundaries.shp.zip"
)

NORTHERN_STATES = {
    "Adamawa", "Bauchi", "Benue", "Borno", "Gombe", "Jigawa", "Kaduna",
    "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Nasarawa", "Niger",
    "Plateau", "Sokoto", "Taraba", "Yobe", "Zamfara",
}


class Command(BaseCommand):
    help = "Import real Northern Nigeria State/LGA/Ward boundaries from HDX."

    def add_arguments(self, parser):
        parser.add_argument("--data-dir", default="pipeline_data")
        parser.add_argument(
            "--download", action="store_true", help="Download the HDX archive if missing."
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing State/LGA/Ward rows first (cascades to farmland/climate).",
        )

    def handle(self, *args, **options):
        data_dir = Path(options["data_dir"])
        shp_dir = data_dir / "nga_boundaries"

        if not (shp_dir / "nga_admin1.shp").exists():
            if not options["download"]:
                raise CommandError(f"{shp_dir} not found — re-run with --download.")
            self._download(data_dir, shp_dir)

        states_gdf = gpd.read_file(shp_dir / "nga_admin1.shp")
        lgas_gdf = gpd.read_file(shp_dir / "nga_admin2.shp")
        wards_gdf = gpd.read_file(shp_dir / "nga_admin3.shp")

        states_gdf = states_gdf[states_gdf["adm1_name"].isin(NORTHERN_STATES)]
        lgas_gdf = lgas_gdf[lgas_gdf["adm1_name"].isin(NORTHERN_STATES)]
        wards_gdf = wards_gdf[wards_gdf["adm1_name"].isin(NORTHERN_STATES)]

        with transaction.atomic():
            if options["reset"]:
                State.objects.all().delete()

            states = {}
            for _, row in states_gdf.iterrows():
                state, _ = State.objects.update_or_create(
                    code=row["adm1_pcode"], defaults={"name": row["adm1_name"]}
                )
                states[row["adm1_pcode"]] = state

            lgas = {}
            for _, row in lgas_gdf.iterrows():
                state = states.get(row["adm1_pcode"])
                if state is None:
                    continue
                lga, _ = LGA.objects.update_or_create(
                    code=row["adm2_pcode"],
                    defaults={
                        "name": row["adm2_name"],
                        "state": state,
                        "latitude": row["center_lat"],
                        "longitude": row["center_lon"],
                    },
                )
                lgas[row["adm2_pcode"]] = lga

            ward_count = 0
            for _, row in wards_gdf.iterrows():
                lga = lgas.get(row["adm2_pcode"])
                if lga is None:
                    continue
                Ward.objects.update_or_create(
                    code=row["adm3_pcode"],
                    defaults={
                        "name": row["adm3_name"],
                        "lga": lga,
                        "latitude": row["center_lat"],
                        "longitude": row["center_lon"],
                    },
                )
                ward_count += 1

        covered = sorted(wards_gdf["adm1_name"].unique())
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(states)} states, {len(lgas)} LGAs, {ward_count} wards.\n"
                f"Ward-level coverage only for: {', '.join(covered)} "
                f"(HDX admin3 has no wards for the other northern states yet)."
            )
        )

    def _download(self, data_dir: Path, shp_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        archive = data_dir / "nga_admin_boundaries.shp.zip"
        if not archive.exists():
            self.stdout.write(f"Downloading HDX boundaries to {archive}...")
            with urlopen(HDX_SHAPEFILE_URL) as response, archive.open("wb") as out:
                out.write(response.read())
        self.stdout.write(f"Extracting to {shp_dir}...")
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(shp_dir)
