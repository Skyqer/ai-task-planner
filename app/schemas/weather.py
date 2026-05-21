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
            f"Погода: {self.description}, "
            f"температура {self.temperature:.0f}°C (ощущается {self.feels_like:.0f}°C), "
            f"влажность {self.humidity}%, "
            f"ветер {self.wind_speed:.1f} м/с, "
            f"вероятность дождя {rain_str}."
        )
