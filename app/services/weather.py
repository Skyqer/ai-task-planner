"""OpenWeatherMap weather service with in-memory TTL cache."""

from __future__ import annotations

import logging
import time as time_mod

import httpx

from app.config import Settings
from app.schemas.weather import WeatherData

logger = logging.getLogger(__name__)

_OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/forecast"
_CACHE_TTL_SECONDS = 1800  # 30 minutes


class WeatherService:
    """Fetches and caches weather data from OpenWeatherMap."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.openweather_api_key
        self._city = settings.weather_city
        self._country = settings.weather_country
        self._cache: dict[str, tuple[float, WeatherData]] = {}

    async def get_current_weather(
        self, city: str | None = None
    ) -> WeatherData | None:
        """Get current weather for the city. Returns None on failure.

        Uses 5-day/3-hour forecast endpoint, takes the nearest forecast.
        """
        city = city or self._city
        cache_key = city.lower()

        # Check cache
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if time_mod.time() - cached_time < _CACHE_TTL_SECONDS:
                return cached_data

        if not self._api_key:
            logger.warning("OpenWeather API key not configured")
            return None

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    _OPENWEATHER_URL,
                    params={
                        "q": f"{city},{self._country}",
                        "appid": self._api_key,
                        "units": "metric",
                        "lang": "ru",
                        "cnt": 3,  # next ~9 hours
                    },
                )
                response.raise_for_status()
                data = response.json()

            weather = self._parse_forecast(data)
            if weather:
                self._cache[cache_key] = (time_mod.time(), weather)
            return weather

        except (httpx.HTTPError, KeyError, IndexError) as exc:
            logger.error("Weather fetch failed: %s", exc)
            return None

    @staticmethod
    def _parse_forecast(data: dict) -> WeatherData | None:
        """Parse the nearest forecast entry."""
        forecasts = data.get("list", [])
        if not forecasts:
            return None

        entry = forecasts[0]
        main = entry["main"]
        weather_info = entry["weather"][0] if entry.get("weather") else {}
        wind = entry.get("wind", {})

        # Rain probability from 'pop' (probability of precipitation)
        rain_prob = entry.get("pop", 0.0)

        # Check for rain in weather conditions
        rain_codes = {200, 201, 202, 300, 301, 302, 500, 501, 502, 503, 504, 511, 520, 521, 522}
        weather_id = weather_info.get("id", 0)
        is_rainy = weather_id in rain_codes or rain_prob > 0.5

        return WeatherData(
            temperature=main.get("temp", 0),
            feels_like=main.get("feels_like", 0),
            description=weather_info.get("description", "нет данных"),
            rain_probability=rain_prob,
            wind_speed=wind.get("speed", 0),
            humidity=main.get("humidity", 0),
            is_rainy=is_rainy,
        )
