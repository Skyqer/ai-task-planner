"""Tests for the priority engine."""

from datetime import date

from app.schemas.planner import PlannerResponseSchema
from app.schemas.task import DeadlineSchema, FixedTimeSchema, TaskSchema
from app.schemas.weather import WeatherData
from app.services.priority import PriorityEngine


def _make_engine() -> PriorityEngine:
    return PriorityEngine("Europe/Kyiv")


def test_fixed_time_today_minimum_priority_4():
    """Fixed time today should set priority to at least 4."""
    engine = _make_engine()
    today = date.today().isoformat()

    response = PlannerResponseSchema(
        tasks=[
            TaskSchema(
                title="Meeting",
                priority=2,
                fixed_time=FixedTimeSchema(date=today, time="14:00"),
            )
        ]
    )

    result = engine.process(response)
    assert result.tasks[0].priority >= 4


def test_urgency_keywords_boost_priority():
    """Urgency keywords in text should boost priority."""
    engine = _make_engine()

    response = PlannerResponseSchema(
        tasks=[
            TaskSchema(title="Убрать комнату", priority=2),
        ]
    )

    result = engine.process(response, original_text="надо убрать комнату срочно")
    assert result.tasks[0].priority > 2


def test_weather_warning_for_sensitive_task():
    """Weather-sensitive task + rain should generate warning."""
    engine = _make_engine()
    weather = WeatherData(
        temperature=15,
        feels_like=13,
        description="дождь",
        rain_probability=0.8,
        wind_speed=7,
        humidity=90,
        is_rainy=True,
    )

    response = PlannerResponseSchema(
        tasks=[
            TaskSchema(
                title="Прогулка в парке",
                priority=2,
                weather_sensitive=True,
            ),
        ]
    )

    result = engine.process(response, weather=weather)
    assert len(result.warnings) > 0
    assert "погод" in result.warnings[0].lower() or "дождь" in result.warnings[0].lower()


def test_no_weather_warning_for_indoor_task():
    """Non-weather-sensitive task should not get weather warnings."""
    engine = _make_engine()
    weather = WeatherData(
        temperature=15, feels_like=13, description="дождь",
        rain_probability=0.9, wind_speed=10, humidity=95, is_rainy=True,
    )

    response = PlannerResponseSchema(
        tasks=[
            TaskSchema(title="Читать книгу", priority=2, weather_sensitive=False),
        ]
    )

    result = engine.process(response, weather=weather)
    assert len(result.warnings) == 0


def test_conflict_detection():
    """Overlapping fixed-time tasks should generate a conflict warning."""
    engine = _make_engine()
    today = date.today().isoformat()

    response = PlannerResponseSchema(
        tasks=[
            TaskSchema(
                title="Зал",
                priority=4,
                estimated_minutes=90,
                fixed_time=FixedTimeSchema(date=today, time="16:00"),
            ),
            TaskSchema(
                title="Английский",
                priority=4,
                estimated_minutes=60,
                fixed_time=FixedTimeSchema(date=today, time="16:30"),
            ),
        ]
    )

    result = engine.process(response)
    conflict_warnings = [w for w in result.warnings if "Конфликт" in w]
    assert len(conflict_warnings) > 0


def test_no_conflict_for_non_overlapping():
    """Non-overlapping tasks should not trigger conflict warnings."""
    engine = _make_engine()
    today = date.today().isoformat()

    response = PlannerResponseSchema(
        tasks=[
            TaskSchema(
                title="Зал",
                priority=4,
                estimated_minutes=60,
                fixed_time=FixedTimeSchema(date=today, time="14:00"),
            ),
            TaskSchema(
                title="Английский",
                priority=4,
                estimated_minutes=60,
                fixed_time=FixedTimeSchema(date=today, time="16:00"),
            ),
        ]
    )

    result = engine.process(response)
    conflict_warnings = [w for w in result.warnings if "Конфликт" in w]
    assert len(conflict_warnings) == 0
