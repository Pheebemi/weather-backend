"""
Short-range rain forecast from Open-Meteo.

NASA POWER is a reanalysis product running ~3 days behind, and CMIP6 is a
decadal projection — neither can answer "will it rain this week". Open-Meteo
is an actual forecast: free, no API key, and it reports precipitation
*probability*, which matters here because Sahel rainfall is convective and
single-model amounts disagree wildly (0-11mm for the same day across
models). A probability is honest where a millimetre figure is not.
"""

import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 15

# WMO weather codes -> plain words a non-technical reader can act on.
# https://open-meteo.com/en/docs
WEATHER_CODES = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Cloudy",
    45: "Fog", 48: "Fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
}


class ForecastError(Exception):
    pass


def describe(code):
    return WEATHER_CODES.get(code, "Unknown")


def is_wet(code):
    """Codes from drizzle upwards — used to pick a rain icon in the UI."""
    return code is not None and code >= 51


def fetch_forecast(latitude: float, longitude: float, days: int = 7) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "precipitation_probability,weather_code",
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max,precipitation_sum"
        ),
        "forecast_days": days,
        "timezone": "Africa/Lagos",
    }
    try:
        response = requests.get(FORECAST_URL, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ForecastError(f"Open-Meteo request failed: {exc}") from exc

    payload = response.json()
    hourly, daily = payload.get("hourly", {}), payload.get("daily", {})
    if not hourly or not daily:
        raise ForecastError("Open-Meteo response was missing forecast data.")

    # Today at 3-hourly steps: eight readable columns rather than 24.
    today = daily["time"][0]
    slots = []
    for i, stamp in enumerate(hourly["time"]):
        if not stamp.startswith(today) or i % 3:
            continue
        code = hourly["weather_code"][i]
        slots.append({
            "time": stamp,
            "hour": stamp[11:16],
            "rain_chance_pct": hourly["precipitation_probability"][i],
            "weather_code": code,
            "description": describe(code),
            "is_wet": is_wet(code),
        })

    forecast_days = []
    for i, date in enumerate(daily["time"]):
        code = daily["weather_code"][i]
        forecast_days.append({
            "date": date,
            "weather_code": code,
            "description": describe(code),
            "is_wet": is_wet(code),
            "rain_chance_pct": daily["precipitation_probability_max"][i],
            "rain_mm": daily["precipitation_sum"][i],
            "temp_min_c": daily["temperature_2m_min"][i],
            "temp_max_c": daily["temperature_2m_max"][i],
        })

    return {
        "source": "Open-Meteo forecast",
        "today_hourly": slots,
        "daily": forecast_days,
    }
