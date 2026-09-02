from rest_framework import serializers

from .models import LGA, State, Ward, WardFarmland


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
