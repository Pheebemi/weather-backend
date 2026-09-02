from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LGA, State, Ward, WardFarmland
from .serializers import (
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
