from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LGA, FarmlandReport, LGAFarmland, State, Ward, WardFarmland
from .serializers import (
    FarmlandReportSerializer,
    LGAFarmlandSerializer,
    LGASerializer,
    StateSerializer,
    WardFarmlandSerializer,
    WardSerializer,
)


class StateListView(generics.ListAPIView):
    queryset = State.objects.all()
    serializer_class = StateSerializer


class LGAListView(generics.ListAPIView):
    serializer_class = LGASerializer

    def get_queryset(self):
        return LGA.objects.filter(state_id=self.kwargs["state_id"])


class WardListView(generics.ListAPIView):
    serializer_class = WardSerializer

    def get_queryset(self):
        return Ward.objects.filter(lga_id=self.kwargs["lga_id"])


class WardFarmlandView(APIView):
    """
    Feature 2: returns the pre-computed agricultural-land flag for a ward.
    No live satellite query happens here — see boundaries/management/commands
    for the offline batch job that populates WardFarmland.
    """

    def get(self, request, ward_id):
        try:
            farmland = WardFarmland.objects.select_related("ward").get(ward_id=ward_id)
        except WardFarmland.DoesNotExist as exc:
            raise NotFound("No farmland assessment available for this ward yet.") from exc
        return Response(WardFarmlandSerializer(farmland).data)


class StatsView(APIView):
    """Coverage counts for the landing page, so it states real numbers."""

    def get(self, request):
        from climate_pipeline.models import WardClimate

        return Response(
            {
                "states": State.objects.count(),
                "lgas": LGA.objects.count(),
                "wards": Ward.objects.count(),
                "wards_with_farmland": WardFarmland.objects.count(),
                "wards_with_climate": WardClimate.objects.count(),
            }
        )


class LGAFarmlandView(APIView):
    """
    LGA-level farmland fallback for states with no ward boundaries
    (Benue, Plateau, Taraba). Coarser than the ward result — the
    serializer marks it `level: "lga"` so the UI can say so.
    """

    def get(self, request, lga_id):
        try:
            farmland = LGAFarmland.objects.select_related("lga").get(lga_id=lga_id)
        except LGAFarmland.DoesNotExist as exc:
            raise NotFound("No farmland assessment available for this LGA yet.") from exc
        return Response(LGAFarmlandSerializer(farmland).data)


class FarmlandReportCreateView(generics.CreateAPIView):
    """
    "Report incorrect info" affordance (see CLAUDE.md Build Guidance /
    Correction strategy). Reports are reviewed manually in /admin/ — no
    automatic correction happens here.
    """

    serializer_class = FarmlandReportSerializer

    def create(self, request, *args, **kwargs):
        ward = generics.get_object_or_404(Ward, id=kwargs["ward_id"])
        serializer = self.get_serializer(data={**request.data, "ward": ward.id})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
