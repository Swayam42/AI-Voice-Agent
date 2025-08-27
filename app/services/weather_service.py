import os
import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger("voice-agent.weather")


class OpenWeather:
    """Thin wrapper around OpenWeather current weather API.

    Reads OPENWEATHER_API_KEY from env.
    Exposes current_weather(location, units) -> Dict suitable as a tool response.
    """

    BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENWEATHER_API_KEY is not set")

    def current_weather(self, location: str, units: str = "metric") -> Dict[str, Any]:
        """Fetch current weather by city name or 'city,countryCode'.

        - location: e.g., 'Delhi', 'London,UK', 'San Francisco,US'
        - units: 'metric' | 'imperial' (default 'metric')
        """
        units = (units or "metric").lower()
        if units not in ("metric", "imperial"):
            units = "metric"

        params = {
            "q": location,
            "appid": self.api_key,
            "units": units,
        }
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("OpenWeather error: %s", e)
            return {
                "location": location,
                "units": units,
                "error": str(e),
            }

        # Normalize useful fields
        name = data.get("name")
        sys = data.get("sys") or {}
        country = sys.get("country")
        main = data.get("main") or {}
        weather_list = data.get("weather") or []
        weather0 = weather_list[0] if weather_list else {}
        wind = data.get("wind") or {}
        coord = data.get("coord") or {}

        return {
            "location": location,
            "resolved_name": ", ".join(x for x in [name, country] if x),
            "units": units,
            "temperature": main.get("temp"),
            "feels_like": main.get("feels_like"),
            "humidity": main.get("humidity"),
            "pressure": main.get("pressure"),
            "description": weather0.get("description"),
            "wind_speed": wind.get("speed"),
            "wind_deg": wind.get("deg"),
            "coordinates": coord,
            "source": "OpenWeather",
        }
