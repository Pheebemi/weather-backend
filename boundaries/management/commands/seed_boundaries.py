from django.core.management.base import BaseCommand

from boundaries.models import LGA, State, Ward

# Placeholder seed data so the app is runnable end-to-end before the real
# GRID3/HDX ward-level shapefiles are imported (see README "Boundary data").
# Coordinates are approximate ward/LGA centroids for demo purposes only.
SEED = {
    "Borno": {
        "code": "NG008",
        "lgas": {
            "Maiduguri": {
                "code": "NG008001",
                "wards": {
                    "Bulunkutu": (11.847, 13.151),
                    "Gwange": (11.845, 13.148),
                },
            },
            "Jere": {
                "code": "NG008002",
                "wards": {
                    "Dusuman": (11.933, 13.207),
                },
            },
        },
    },
    "Kano": {
        "code": "NG020",
        "lgas": {
            "Kano Municipal": {
                "code": "NG020001",
                "wards": {
                    "Dala": (12.0, 8.516),
                },
            },
        },
    },
}


class Command(BaseCommand):
    help = "Seed a small set of placeholder State/LGA/Ward boundaries for local development."

    def handle(self, *args, **options):
        for state_name, state_data in SEED.items():
            state, _ = State.objects.update_or_create(
                name=state_name, defaults={"code": state_data["code"]}
            )
            for lga_name, lga_data in state_data["lgas"].items():
                lga, _ = LGA.objects.update_or_create(
                    state=state, name=lga_name, defaults={"code": lga_data["code"]}
                )
                for ward_name, (lat, lon) in lga_data["wards"].items():
                    Ward.objects.update_or_create(
                        lga=lga,
                        name=ward_name,
                        defaults={
                            "code": f"{lga.code}-{ward_name[:3].upper()}",
                            "latitude": lat,
                            "longitude": lon,
                        },
                    )
        self.stdout.write(self.style.SUCCESS("Seeded placeholder boundaries."))
