from rest_framework.exceptions import NotFound, ParseError, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from boundaries.models import LGA, Ward
from climate_pipeline.models import LGAClimate, WardClimate

from .forecast import ForecastError, fetch_forecast
from .services import NasaPowerError, fetch_recent_weather


def _ward_climate(ward: Ward) -> dict | None:
    """
    The offline pipeline's output for this ward (see CLAUDE.md
    "Supervisor's Formal Data-Prep Pipeline").

    These are *climate projections* under an emissions scenario, not
    observations — so they are returned under their own key, never as
    today's conditions. When two periods exist, the change between them is
    included so the app can answer "is my ward getting drier?".
    """
    periods = list(ward.climates.all())
    if not periods:
        return None

    def shape(c):
        return {
            "period": c.period,
            "scenario": c.scenario,
            "temperature_avg_c": c.temperature_avg_c,
            "temperature_max_avg_c": c.temperature_max_avg_c,
            "humidity_avg_pct": c.humidity_avg_pct,
            "precipitation_mm_per_year": c.precipitation_avg_mm,
            "source": c.climate_source,
        }

    # Meta.ordering sorts by period, so the first is the earliest.
    current, later = periods[0], periods[-1]
    result = {**shape(current), "periods": [shape(p) for p in periods]}

    if later is not current:
        result["change"] = {
            "from_period": current.period,
            "to_period": later.period,
            "temperature_avg_c": round(
                later.temperature_avg_c - current.temperature_avg_c, 2
            ),
            "precipitation_mm_per_year": round(
                later.precipitation_avg_mm - current.precipitation_avg_mm, 1
            ),
        }
    return result


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
            ward = Ward.objects.select_related("lga__state").prefetch_related("climates").get(id=ward_id)
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


class ForecastByWardView(APIView):
    """
    Short-range rain forecast for a ward, from Open-Meteo.

    Separate from /weather/ deliberately: that endpoint reports what the
    weather *has been* (NASA POWER, ~3 days behind) and the ward's climate
    projection. This is the only endpoint that says what it will do next.
    """

    def get(self, request, ward_id):
        try:
            ward = Ward.objects.select_related("lga__state").get(id=ward_id)
        except Ward.DoesNotExist as exc:
            raise NotFound("Ward not found.") from exc

        if ward.latitude is None or ward.longitude is None:
            raise ValidationError("This ward has no centroid coordinates on file yet.")

        try:
            data = fetch_forecast(ward.latitude, ward.longitude)
        except ForecastError as exc:
            raise ValidationError(str(exc)) from exc

        data["location"] = {
            "ward": ward.name,
            "lga": ward.lga.name,
            "state": ward.lga.state.name,
        }
        return Response(data)


class ClimateByWardView(APIView):
    """
    The ward's climate outlook, read straight from the database.

    Deliberately makes no network call: the pipeline already stored these
    values, so this endpoint keeps working when the device is offline. The
    rain forecast needs the network; this does not.
    """

    def get(self, request, ward_id):
        try:
            ward = Ward.objects.select_related("lga__state").prefetch_related("climates").get(
                id=ward_id
            )
        except Ward.DoesNotExist as exc:
            raise NotFound("Ward not found.") from exc

        climate = _ward_climate(ward)
        if climate is None:
            raise NotFound("No climate data for this ward yet.")

        climate["location"] = {
            "ward": ward.name,
            "lga": ward.lga.name,
            "state": ward.lga.state.name,
        }
        return Response(climate)


def _lga_climate(lga: LGA) -> dict | None:
    """LGA-level equivalent of _ward_climate, for states without wards."""
    periods = list(lga.climates.all())
    if not periods:
        return None

    def shape(c):
        return {
            "period": c.period,
            "scenario": c.scenario,
            "temperature_avg_c": c.temperature_avg_c,
            "temperature_max_avg_c": c.temperature_max_avg_c,
            "humidity_avg_pct": c.humidity_avg_pct,
            "precipitation_mm_per_year": c.precipitation_avg_mm,
            "source": c.climate_source,
        }

    current, later = periods[0], periods[-1]
    result = {**shape(current), "periods": [shape(p) for p in periods], "level": "lga"}
    if later is not current:
        result["change"] = {
            "from_period": current.period,
            "to_period": later.period,
            "temperature_avg_c": round(later.temperature_avg_c - current.temperature_avg_c, 2),
            "precipitation_mm_per_year": round(
                later.precipitation_avg_mm - current.precipitation_avg_mm, 1
            ),
        }
    return result


class ForecastByLGAView(APIView):
    """
    Rain forecast for an LGA centroid, for the states that have no ward
    boundaries in any open dataset. Coarser than a ward forecast, but far
    better than showing nothing.
    """

    def get(self, request, lga_id):
        try:
            lga = LGA.objects.select_related("state").get(id=lga_id)
        except LGA.DoesNotExist as exc:
            raise NotFound("LGA not found.") from exc

        if lga.latitude is None or lga.longitude is None:
            raise ValidationError("This LGA has no centroid coordinates on file yet.")

        try:
            data = fetch_forecast(lga.latitude, lga.longitude)
        except ForecastError as exc:
            raise ValidationError(str(exc)) from exc

        data["level"] = "lga"
        data["location"] = {"lga": lga.name, "state": lga.state.name}
        return Response(data)


class ClimateByLGAView(APIView):
    """LGA-level climate outlook. Database only — works offline."""

    def get(self, request, lga_id):
        try:
            lga = LGA.objects.select_related("state").prefetch_related("climates").get(id=lga_id)
        except LGA.DoesNotExist as exc:
            raise NotFound("LGA not found.") from exc

        climate = _lga_climate(lga)
        if climate is None:
            raise NotFound("No climate data for this LGA yet.")

        climate["location"] = {"lga": lga.name, "state": lga.state.name}
        return Response(climate)
