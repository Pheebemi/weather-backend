from rest_framework.exceptions import NotFound, ParseError, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from boundaries.models import Ward

from .services import NasaPowerError, fetch_recent_weather


class WeatherByPointView(APIView):
    """Feature 1: live weather lookup for an arbitrary lat/lon (e.g. a map tap)."""

    def get(self, request):
        lat = request.query_params.get("lat")
        lon = request.query_params.get("lon")
        if lat is None or lon is None:
            raise ValidationError("Both 'lat' and 'lon' query parameters are required.")
        try:
            lat, lon = float(lat), float(lon)
        except ValueError as exc:
            raise ParseError("'lat' and 'lon' must be numbers.") from exc

        try:
            data = fetch_recent_weather(lat, lon)
        except NasaPowerError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(data)


class WeatherByWardView(APIView):
    """Feature 1: live weather lookup for a ward selected via the State > LGA > Ward flow."""

    def get(self, request, ward_id):
        try:
            ward = Ward.objects.select_related("lga__state").get(id=ward_id)
        except Ward.DoesNotExist as exc:
            raise NotFound("Ward not found.") from exc

        if ward.latitude is None or ward.longitude is None:
            raise ValidationError("This ward has no centroid coordinates on file yet.")

        try:
            data = fetch_recent_weather(ward.latitude, ward.longitude)
        except NasaPowerError as exc:
            raise ValidationError(str(exc)) from exc

        data["location"] = {
            "ward": ward.name,
            "lga": ward.lga.name,
            "state": ward.lga.state.name,
        }
        return Response(data)
