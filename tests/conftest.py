"""Test fixtures."""

# pyrefly: ignore [missing-import]
import pytest


@pytest.fixture
def sample_planner_response():
    """Sample PlannerResponse for testing."""
    from app.schemas.planner import PlannerResponseSchema
    from app.schemas.task import TaskSchema, DeadlineSchema, FixedTimeSchema

    return PlannerResponseSchema(
        mode="task_input",
        status="ok",
        timezone="Europe/Kyiv",
        tasks=[
            TaskSchema(
                title="Математика номер 231",
                type="study",
                priority=4,
                estimated_minutes=45,
                deadline=DeadlineSchema(
                    date="2026-05-22",
                    time="16:00",
                    kind="hard",
                ),
            ),
            TaskSchema(
                title="Зал",
                type="sport",
                priority=4,
                estimated_minutes=90,
                fixed_time=FixedTimeSchema(
                    date="2026-05-22",
                    time="17:00",
                ),
            ),
        ],
        summary="2 задачи добавлены.",
    )


@pytest.fixture
def sample_weather():
    """Sample weather data."""
    from app.schemas.weather import WeatherData

    return WeatherData(
        temperature=18.0,
        feels_like=16.5,
        description="облачно с прояснениями",
        rain_probability=0.7,
        wind_speed=5.2,
        humidity=75,
        is_rainy=True,
    )
