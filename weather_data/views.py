from rest_framework.exceptions import NotFound, ParseError, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from boundaries.models import Ward
from climate_pipeline.models import WardClimate

from .services import NasaPowerError, fetch_recent_weather


def _ward_climate(ward: Ward) -> dict | None:
    """
    The Supervisor's offline pipeline output for this ward (see CLAUDE.md
    "Supervisor's Formal Data-Prep Pipeline").

    This is a *climate projection* (downscaled CMIP6 under an emissions
    scenario), not an observation — so it is returned alongside the live
    observed weather under its own key, never as today's conditions.
    """
    try:
        climate = ward.climate
    except WardClimate.DoesNotExist:
        return None

    return {
        "temperature_avg_c": climate.temperature_avg_c,
        "temperature_max_avg_c": climate.temperature_max_avg_c,
        "humidity_avg_pct": climate.humidity_avg_pct,
        "precipitation_mm_per_year": climate.precipitation_avg_mm,
        "scenario": climate.scenario,
        "period": climate.period,
        "source": climate.climate_source,
    }


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
    """Feature 1: weather lookup for a ward selected via the State > LGA > Ward flow.

    Observed conditions always come live from NASA POWER. If the offline
    pipeline has covered this ward, its downscaled-CMIP6 projection is
    attached under `climate` — clearly separated, because a projection for
    a future period is not a report of today's weather.
    """

    def get(self, request, ward_id):
        try:
            ward = Ward.objects.select_related("lga__state", "climate").get(id=ward_id)
        except Ward.DoesNotExist as exc:
            raise NotFound("Ward not found.") from exc

        if ward.latitude is None or ward.longitude is None:
            raise ValidationError("This ward has no centroid coordinates on file yet.")
        try:
            data = fetch_recent_weather(ward.latitude, ward.longitude)
        except NasaPowerError as exc:
            raise ValidationError(str(exc)) from exc

        data["climate"] = _ward_climate(ward)
        data["location"] = {
            "ward": ward.name,
            "lga": ward.lga.name,
            "state": ward.lga.state.name,
        }
        return Response(data)
