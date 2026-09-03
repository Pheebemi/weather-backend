from datetime import datetime, timedelta

import requests
from django.conf import settings

# T2M = temperature at 2m (°C), PRECTOTCORR = bias-corrected precipitation (mm/day),
# RH2M = relative humidity at 2m (%). See https://power.larc.nasa.gov/docs/services/api/
POWER_PARAMETERS = "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M"

# NASA POWER's documented sentinel for "not yet processed / unavailable" — it
# fills every requested parameter with exactly -999 rather than omitting the
# date. Its real reporting lag varies (often longer than a couple of days),
# so a request can land entirely on unfilled days; treat the value as
# missing rather than showing "-999.0°C" as if it were a real reading.
FILL_VALUE_THRESHOLD = -900


class NasaPowerError(Exception):
    pass


def _clean(value):
    if value is None or value <= FILL_VALUE_THRESHOLD:
        return None
    return value


def fetch_recent_weather(latitude: float, longitude: float, days: int = 12) -> dict:
    """
    Query NASA POWER for the last `days` days of daily weather at a point.
    NASA POWER's reporting lag is variable, so request a wider window ending
    a few days back rather than "today", and let the caller fall back to the
    most recent day that actually has data (see `latest` below).
    """
    end = datetime.utcnow().date() - timedelta(days=4)
    start = end - timedelta(days=days - 1)

    params = {
        "parameters": POWER_PARAMETERS,
        "community": "AG",
        "longitude": longitude,
        "latitude": latitude,
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }

    try:
        response = requests.get(settings.NASA_POWER_BASE_URL, params=params, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise NasaPowerError(f"NASA POWER request failed: {exc}") from exc

    payload = response.json()
    parameter_data = payload.get("properties", {}).get("parameter", {})
    if not parameter_data:
        raise NasaPowerError("NASA POWER response did not include parameter data.")

    dates = sorted(next(iter(parameter_data.values())).keys())
    daily = [
        {
            "date": datetime.strptime(date, "%Y%m%d").date().isoformat(),
            "temperature_avg_c": _clean(parameter_data.get("T2M", {}).get(date)),
            "temperature_max_c": _clean(parameter_data.get("T2M_MAX", {}).get(date)),
            "temperature_min_c": _clean(parameter_data.get("T2M_MIN", {}).get(date)),
            "precipitation_mm": _clean(parameter_data.get("PRECTOTCORR", {}).get(date)),
            "relative_humidity_pct": _clean(parameter_data.get("RH2M", {}).get(date)),
        }
        for date in dates
    ]

    # NASA POWER's lag means the newest requested days are often still
    # unfilled — walk backward to the most recent day with a real reading
    # rather than always showing the last (possibly all-null) day.
    latest = next(
        (day for day in reversed(daily) if day["temperature_avg_c"] is not None),
        None,
    )

    return {
        "latitude": latitude,
        "longitude": longitude,
        "source": "NASA POWER (~50km grid cell average, not exact-point)",
        "daily": daily,
        "latest": latest,
    }
