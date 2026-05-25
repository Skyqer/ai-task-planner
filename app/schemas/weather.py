"""Weather data schema."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WeatherData:
    """Structured weather information from OpenWeatherMap."""

    temperature: float
    feels_like: float
    description: str
    rain_probability: float  # 0.0 – 1.0
    wind_speed: float  # m/s
    humidity: int  # %
    is_rainy: bool

    def to_context_string(self) -> str:
        """Format weather for LLM context injection."""
        rain_str = f"{self.rain_probability * 100:.0f}%"
        return (
            f"Weather: {self.description}, "
            f"temperature {self.temperature:.0f}°C (feels like {self.feels_like:.0f}°C), "
            f"humidity {self.humidity}%, "
            f"wind speed {self.wind_speed:.1f} m/s, "
            f"rain probability {rain_str}."
        )
