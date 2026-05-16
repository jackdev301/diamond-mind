"""Open-Meteo weather client (no API key required).

Returns WeatherSnapshot for a venue given lat/lon and game time.
Stubs gracefully when coordinates are unavailable.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional

from app.contracts import WeatherSnapshot

_BASE = "https://api.open-meteo.com/v1/forecast"

# Dome venues — weather irrelevant
_DOME_VENUES = {
    "Tropicana Field",
    "Minute Maid Park",
    "T-Mobile Park",
    "Rogers Centre",
    "Chase Field",
    "Globe Life Field",
    "loanDepot park",
    "American Family Field",
}


def fetch_weather(
    game_id: int,
    venue: str,
    game_time_utc: datetime,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Optional[WeatherSnapshot]:
    """
    Fetch weather for a game. Returns None if coordinates unavailable.
    Dome venues return a stub with is_dome=True and nulled weather fields.
    """
    if venue in _DOME_VENUES:
        return WeatherSnapshot(
            game_id=game_id,
            temperature_f=None,
            wind_speed_mph=None,
            wind_direction_deg=None,
            precipitation_chance=None,
            humidity_pct=None,
            is_dome=True,
            captured_at=datetime.now(tz=timezone.utc),
        )

    if lat is None or lon is None:
        return None

    date_str = game_time_utc.strftime("%Y-%m-%d")
    hour = game_time_utc.hour

    url = (
        f"{_BASE}?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,precipitation_probability,windspeed_10m,"
        f"winddirection_10m,relativehumidity_2m"
        f"&temperature_unit=fahrenheit&windspeed_unit=mph"
        f"&start_date={date_str}&end_date={date_str}&timezone=UTC"
    )

    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
    except (urllib.error.URLError, json.JSONDecodeError):
        return None

    hourly = data.get("hourly", {})
    try:
        temp = hourly["temperature_2m"][hour]
        precip = hourly["precipitation_probability"][hour] / 100.0
        wind_speed = hourly["windspeed_10m"][hour]
        wind_dir = int(hourly["winddirection_10m"][hour])
        humidity = hourly["relativehumidity_2m"][hour]
    except (KeyError, IndexError, TypeError):
        return None

    return WeatherSnapshot(
        game_id=game_id,
        temperature_f=temp,
        wind_speed_mph=wind_speed,
        wind_direction_deg=wind_dir,
        precipitation_chance=precip,
        humidity_pct=humidity,
        is_dome=False,
        captured_at=datetime.now(tz=timezone.utc),
    )


def is_available() -> bool:
    return True  # Open-Meteo requires no key
