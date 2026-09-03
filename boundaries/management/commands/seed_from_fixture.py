"""
Bulk-loads the committed fixture into the configured database.

`loaddata` inserts one row at a time, which is fine locally but unusable
against a remote Postgres: at ~2s round-trip latency, 12,000 rows takes
hours. This does the same job with bulk_create in batches, turning tens of
thousands of round-trips into a few dozen.

    DATABASE_URL='postgresql://...' python manage.py seed_from_fixture
"""

import gzip
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from boundaries.models import LGA, LGAFarmland, State, Ward, WardFarmland
from climate_pipeline.models import LGAClimate, WardClimate

# Parents before children — bulk_create does not resolve FK ordering.
MODELS = [
    ("boundaries.state", State),
    ("boundaries.lga", LGA),
    ("boundaries.ward", Ward),
    ("boundaries.wardfarmland", WardFarmland),
    ("boundaries.lgafarmland", LGAFarmland),
    ("climate_pipeline.wardclimate", WardClimate),
    ("climate_pipeline.lgaclimate", LGAClimate),
]


class Command(BaseCommand):
    help = "Bulk-load fixtures/seed_data.json.gz (much faster than loaddata over a remote DB)."

    def add_arguments(self, parser):
        parser.add_argument("--fixture", default="fixtures/seed_data.json.gz")
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing rows in these tables first.",
        )

    def handle(self, *args, **options):
        path = Path(options["fixture"])
        if not path.exists():
            raise CommandError(f"{path} not found.")

        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt") as fh:
            records = json.load(fh)

        grouped: dict[str, list] = {}
        for rec in records:
            grouped.setdefault(rec["model"], []).append(rec)

        batch = options["batch_size"]
        with transaction.atomic():
            if options["flush"]:
                for _, model in reversed(MODELS):
                    model.objects.all().delete()
                self.stdout.write("Flushed existing rows.")

            for label, model in MODELS:
                rows = grouped.get(label, [])
                if not rows:
                    continue
                objects = [model(pk=r["pk"], **self._fields(model, r["fields"])) for r in rows]
                model.objects.bulk_create(objects, batch_size=batch)
                self.stdout.write(f"  {label:32} {len(objects)}")

            # Explicit PKs leave the sequences behind, so the next insert
            # from the app would collide. Reset them to the current max.
            self._reset_sequences()

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(records)} records."))

    @staticmethod
    def _fields(model, fields):
        """Map fixture field names onto the model, turning FKs into *_id."""
        out = {}
        fk_names = {f.name for f in model._meta.fields if f.is_relation}
        for key, value in fields.items():
            out[f"{key}_id" if key in fk_names else key] = value
        return out

    def _reset_sequences(self):
        with connection.cursor() as cursor:
            for _, model in MODELS:
                table = model._meta.db_table
                if connection.vendor != "postgresql":
                    continue
                cursor.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1), true)"
                )
        self.stdout.write("  sequences reset")
