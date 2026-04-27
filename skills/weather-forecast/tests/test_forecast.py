"""Test suite for weather forecast skill."""

import sys
from io import StringIO
from pathlib import Path

import pytest
import requests_mock

# Add parent directory to path so we can import forecast module
sys.path.insert(0, str(Path(__file__).parent.parent))

from forecast import (
    DailyForecast,
    LAT,
    LON,
    aggregate_periods,
    fetch_forecast_url,
    fetch_periods,
    format_markdown_table,
    main,
)


def make_mock_periods(start_with_night: bool = False) -> list[dict]:
    """
    Generate 14 synthetic periods for testing.

    Args:
        start_with_night: If True, first period is isDaytime=false

    Returns:
        List of 14 period dicts with predictable values
    """
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    periods = []

    if start_with_night:
        periods.append(
            {
                "number": 1,
                "name": "Tonight",
                "isDaytime": False,
                "temperature": 40,
                "temperatureUnit": "F",
                "probabilityOfPrecipitation": {"value": 5},
                "shortForecast": "Clear",
            }
        )

    for i, day in enumerate(days):
        if len(periods) >= 14:
            break
        # Day period
        periods.append(
            {
                "number": len(periods) + 1,
                "name": day,
                "isDaytime": True,
                "temperature": 60 + i * 2,  # 60, 62, 64, ...
                "temperatureUnit": "F",
                "probabilityOfPrecipitation": {"value": i * 5},  # 0, 5, 10, ...
                "shortForecast": f"Sunny Day {i+1}",
            }
        )
        # Night period
        if len(periods) < 14:
            periods.append(
                {
                    "number": len(periods) + 1,
                    "name": f"{day} Night",
                    "isDaytime": False,
                    "temperature": 45 + i * 2,  # 45, 47, 49, ...
                    "temperatureUnit": "F",
                    "probabilityOfPrecipitation": {"value": i * 3},
                    "shortForecast": f"Clear Night {i+1}",
                }
            )

    return periods[:14]


MOCK_POINTS_RESPONSE = {
    "properties": {"forecast": "https://api.weather.gov/gridpoints/SEW/134,88/forecast"}
}

MOCK_FORECAST_RESPONSE = {"properties": {"periods": make_mock_periods()}}


def test_success_path_returns_markdown_table(requests_mock):
    """
    Test the success path: mock both API calls, verify markdown table output.

    Verifies:
    - Exit code 0 (doesn't raise SystemExit)
    - Output contains markdown table headers
    - Output contains expected number of rows
    """
    # Mock the points endpoint
    points_url = f"https://api.weather.gov/points/{LAT},{LON}"
    requests_mock.get(points_url, json=MOCK_POINTS_RESPONSE)

    # Mock the forecast endpoint
    forecast_url = MOCK_POINTS_RESPONSE["properties"]["forecast"]
    requests_mock.get(forecast_url, json=MOCK_FORECAST_RESPONSE)

    # Capture output
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        main(args=[])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = old_stdout

    # Verify markdown table structure
    assert "| Day" in output, "Output should contain markdown table header"
    assert "| High | Low" in output, "Output should contain High/Low columns"
    assert "| Conditions" in output, "Output should contain Conditions column"
    assert "| Precip%" in output, "Output should contain Precip% column"

    # Verify we have data rows (should be 7 rows + 2 header rows)
    lines = output.strip().split("\n")
    assert len(lines) >= 9, f"Expected at least 9 lines (2 header + 7 data), got {len(lines)}"

    # Count data rows (lines with temps like °F)
    data_rows = [line for line in lines if "°F" in line]
    assert len(data_rows) >= 7, f"Expected at least 7 data rows, got {len(data_rows)}"


def test_aggregate_periods_pairs_day_and_night():
    """
    Test aggregation logic: verify 14 periods -> 7 daily forecasts.

    Verifies:
    - Returns 7 DailyForecast objects
    - High temps come from isDaytime=true periods
    - Low temps come from isDaytime=false periods
    - Day names are extracted correctly
    """
    periods = make_mock_periods(start_with_night=False)
    forecasts = aggregate_periods(periods, max_days=7)

    # Verify we have 7 forecasts
    assert len(forecasts) == 7, f"Expected 7 forecasts, got {len(forecasts)}"

    # Verify first forecast
    first = forecasts[0]
    assert first.day_name == "Monday", f"Expected 'Monday', got '{first.day_name}'"
    assert first.high_temp == 60, f"Expected high_temp=60, got {first.high_temp}"
    assert first.low_temp == 45, f"Expected low_temp=45, got {first.low_temp}"
    assert first.conditions == "Sunny Day 1", f"Expected 'Sunny Day 1', got '{first.conditions}'"
    assert first.precip_pct == 0, f"Expected precip_pct=0, got {first.precip_pct}"

    # Verify second forecast
    second = forecasts[1]
    assert second.day_name == "Tuesday", f"Expected 'Tuesday', got '{second.day_name}'"
    assert second.high_temp == 62, f"Expected high_temp=62, got {second.high_temp}"
    assert second.low_temp == 47, f"Expected low_temp=47, got {second.low_temp}"
    assert second.precip_pct == 5, f"Expected precip_pct=5, got {second.precip_pct}"

    # Verify that all forecasts have the expected structure
    for i, forecast in enumerate(forecasts):
        assert isinstance(forecast, DailyForecast)
        assert forecast.day_name is not None
        assert forecast.high_temp > 0
        assert forecast.conditions is not None
        assert forecast.precip_pct >= 0


def test_aggregate_periods_skips_leading_night():
    """Test that aggregation skips leading night period if present."""
    periods = make_mock_periods(start_with_night=True)
    forecasts = aggregate_periods(periods, max_days=7)

    # Should still get 7 forecasts since we skip the leading night
    assert len(forecasts) == 7, f"Expected 7 forecasts, got {len(forecasts)}"

    # First forecast should still be Monday (skipped the leading night)
    first = forecasts[0]
    assert first.day_name == "Monday", f"Expected 'Monday', got '{first.day_name}'"


def test_retry_on_5xx_succeeds_after_backoff(requests_mock):
    """
    Test 5xx retry logic: first request returns 503, second returns 200.

    Verifies:
    - Function completes successfully
    - Total of 2 requests were made to the points endpoint
    """
    points_url = f"https://api.weather.gov/points/{LAT},{LON}"
    forecast_url = MOCK_POINTS_RESPONSE["properties"]["forecast"]

    # Mock first request to points endpoint returns 503
    # Second request returns 200 with valid data
    requests_mock.get(points_url, [
        {"status_code": 503, "text": "Service Unavailable"},
        {"json": MOCK_POINTS_RESPONSE},
    ])

    # Mock forecast endpoint
    requests_mock.get(forecast_url, json=MOCK_FORECAST_RESPONSE)

    # Capture output
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        main(args=[])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = old_stdout

    # Verify we got output (indicating success)
    assert "| Day" in output, "Should have successful output after retry"

    # Verify that we made 2 requests to the points endpoint
    request_history = [r for r in requests_mock.request_history if points_url in r.url]
    assert len(request_history) == 2, f"Expected 2 requests to points endpoint, got {len(request_history)}"


def test_format_markdown_table_imperial():
    """Test markdown table formatting with imperial units."""
    forecasts = [
        DailyForecast(
            day_name="Monday",
            high_temp=63,
            low_temp=47,
            conditions="Partly Sunny",
            precip_pct=7,
        ),
        DailyForecast(
            day_name="Tuesday",
            high_temp=60,
            low_temp=43,
            conditions="Mostly Cloudy",
            precip_pct=11,
        ),
    ]

    output = format_markdown_table(forecasts, "imperial")

    # Verify table structure
    assert "| Day" in output
    assert "| High | Low" in output
    assert "Monday" in output
    assert "63°F" in output
    assert "47°F" in output
    assert "Partly Sunny" in output
    assert "7%" in output


def test_format_markdown_table_metric():
    """Test markdown table formatting with metric units."""
    forecasts = [
        DailyForecast(
            day_name="Monday",
            high_temp=63,
            low_temp=47,
            conditions="Partly Sunny",
            precip_pct=7,
        ),
    ]

    output = format_markdown_table(forecasts, "metric")

    # 63°F = 17°C, 47°F = 8°C (with rounding)
    assert "17°C" in output, f"Expected '17°C' in output, got: {output}"
    assert "8°C" in output, f"Expected '8°C' in output, got: {output}"


def test_format_markdown_table_missing_low_temp():
    """Test markdown table formatting when low_temp is None."""
    forecasts = [
        DailyForecast(
            day_name="Monday",
            high_temp=63,
            low_temp=None,
            conditions="Partly Sunny",
            precip_pct=7,
        ),
    ]

    output = format_markdown_table(forecasts, "imperial")

    # Verify that N/A is shown for missing low temp
    assert "N/A" in output, f"Expected 'N/A' for missing low temp, got: {output}"
