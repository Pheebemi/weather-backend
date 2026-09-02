from rest_framework import serializers

from .models import LGA, FarmlandReport, LGAFarmland, State, Ward, WardFarmland


class StateSerializer(serializers.ModelSerializer):
    class Meta:
        model = State
        fields = ["id", "name", "code"]


class LGASerializer(serializers.ModelSerializer):
    class Meta:
        model = LGA
        fields = ["id", "name", "code", "state"]


class WardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ward
        fields = ["id", "name", "code", "lga", "latitude", "longitude"]


class WardFarmlandSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = WardFarmland
        fields = [
            "ward",
            "ward_name",
            "has_agric_land",
            "cropland_percent",
            "threshold_used",
            "source",
            "manually_corrected",
            "computed_at",
        ]


class LGAFarmlandSerializer(serializers.ModelSerializer):
    lga_name = serializers.CharField(source="lga.name", read_only=True)
    level = serializers.SerializerMethodField()

    class Meta:
        model = LGAFarmland
        fields = [
            "lga",
            "lga_name",
            "level",
            "has_agric_land",
            "cropland_percent",
            "threshold_used",
            "source",
            "manually_corrected",
            "computed_at",
        ]

    def get_level(self, obj):
        # Tells the UI to label this as coarser than a ward result.
        return "lga"


class FarmlandReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = FarmlandReport
        fields = ["id", "ward", "note", "created_at", "resolved"]
        read_only_fields = ["id", "created_at", "resolved"]
