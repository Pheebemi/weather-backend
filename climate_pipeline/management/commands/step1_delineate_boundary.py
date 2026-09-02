"""
Step 1 of the Supervisor's formal data-prep pipeline (see CLAUDE.md):
merge the 19 northern Nigeria states into one unified regional boundary
polygon. Every later step clips/masks against this boundary.

Defaults to the real HDX admin1 boundaries fetched by
`import_boundaries --download`:

    python manage.py step1_delineate_boundary

Or point it at another source (e.g. GRID3):

    python manage.py step1_delineate_boundary \
        --states-shapefile path/to/nigeria_states.shp --name-field statename
"""

from pathlib import Path

import geopandas as gpd
from django.core.management.base import BaseCommand, CommandError

NORTHERN_STATES = [
    "Adamawa", "Bauchi", "Benue", "Borno", "Gombe", "Jigawa", "Kaduna",
    "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Nasarawa", "Niger",
    "Plateau", "Sokoto", "Taraba", "Yobe", "Zamfara",
]


class Command(BaseCommand):
    help = "Step 1: merge the 19 northern Nigeria states into one boundary polygon."

    def add_arguments(self, parser):
        parser.add_argument(
            "--states-shapefile",
            default="pipeline_data/nga_boundaries/nga_admin1.shp",
            help="State-boundary shapefile/GeoJSON (defaults to the HDX admin1 layer).",
        )
        parser.add_argument(
            "--name-field",
            default="adm1_name",
            help="Attribute in --states-shapefile holding the state name.",
        )
        parser.add_argument("--out", default="pipeline_data/northern_nigeria_boundary.geojson")

    def handle(self, *args, **options):
        shapefile = Path(options["states_shapefile"])
        if not shapefile.exists():
            raise CommandError(
                f"{shapefile} not found — run `python manage.py import_boundaries --download` first."
            )

        states_gdf = gpd.read_file(shapefile)
        name_field = options["name_field"]
        northern = states_gdf[states_gdf[name_field].isin(NORTHERN_STATES)]
        if northern.empty:
            raise CommandError(
                f"No rows in '{shapefile}' matched NORTHERN_STATES via field '{name_field}'."
            )

        # TODO: refine this against Landsat/NASA Earth-observation imagery
        # before treating it as final — an off-the-shelf political boundary
        # taken at face value is only a first pass here, per CLAUDE.md Step 1
        # ("Refine/verify... not just an off-the-shelf political boundary
        # file taken at face value").
        merged = northern.geometry.union_all()
        gdf = gpd.GeoDataFrame(
            {"name": ["Northern Nigeria"]}, geometry=[merged], crs=states_gdf.crs
        )

        out_path = Path(options["out"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_file(out_path, driver="GeoJSON")
        self.stdout.write(
            self.style.SUCCESS(f"Merged {len(northern)} northern states -> {out_path}")
        )
