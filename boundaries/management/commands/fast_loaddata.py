import gzip
from itertools import groupby

from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class Command(BaseCommand):
    help = (
        "Faster alternative to loaddata for large fixtures. Stock loaddata "
        "does one INSERT per row, which means one network round trip per "
        "row against a remote database (e.g. Neon) — painfully slow for a "
        "fixture with thousands of rows. This batches consecutive same-model "
        "rows into bulk_create calls instead, cutting round trips from "
        "one-per-row to one-per-batch. Same fixture format as loaddata; only "
        "use it against an empty/fresh target, since (unlike loaddata) it "
        "does not upsert existing rows."
    )

    def add_arguments(self, parser):
        parser.add_argument("fixture", help="Path to a .json or .json.gz fixture file.")
        parser.add_argument("--batch-size", type=int, default=1000)

    def handle(self, fixture, batch_size, **options):
        opener = gzip.open if fixture.endswith(".gz") else open
        try:
            with opener(fixture, "rt", encoding="utf-8") as f:
                content = f.read()
        except OSError as exc:
            raise CommandError(f"Could not read fixture '{fixture}': {exc}") from exc

        deserialized_objects = list(serializers.deserialize("json", content))

        total = 0
        batches = 0
        models_seen: set = set()
        with transaction.atomic():
            for model, group in groupby(deserialized_objects, key=lambda o: o.object.__class__):
                batch = []
                for deserialized in group:
                    batch.append(deserialized.object)
                    if len(batch) >= batch_size:
                        model.objects.bulk_create(batch, batch_size=batch_size)
                        total += len(batch)
                        batches += 1
                        batch = []
                if batch:
                    model.objects.bulk_create(batch, batch_size=batch_size)
                    total += len(batch)
                    batches += 1
                models_seen.add(model)

            self._reset_sequences(models_seen)

        self.stdout.write(
            self.style.SUCCESS(f"Loaded {total} objects from {fixture} in {batches} batches.")
        )

    def _reset_sequences(self, models):
        """
        bulk_create with explicit primary keys does not advance Postgres'
        sequences, so the first row the app creates afterwards collides on
        a duplicate key. Move each sequence past the ids just inserted.
        """
        if connection.vendor != "postgresql":
            return
        with connection.cursor() as cursor:
            for model in models:
                table = model._meta.db_table
                pk = model._meta.pk.column
                cursor.execute(
                    f"SELECT setval(pg_get_serial_sequence(%s, %s), "
                    f"COALESCE((SELECT MAX({pk}) FROM {table}), 1), true)",
                    [table, pk],
                )
        self.stdout.write("  sequences reset")
