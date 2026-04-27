#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
# ]
# ///
"""
Weather Forecast Skill - Retrieve 7-day forecast from NWS API.

This PEP 723 script fetches weather forecasts for Marysville, WA using
the National Weather Service api.weather.gov API.
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Optional

import requests


# Constants
LAT: float = 48.0518
LON: float = -122.1771
USER_AGENT: str = "weather-forecast-skill/0.1 (jtmilan@gmail.com)"
POINTS_URL_TEMPLATE: str = "https://api.weather.gov/points/{lat},{lon}"
REQUEST_TIMEOUT: int = 10  # seconds
RETRY_DELAY: float = 2.0  # seconds
MAX_DAYS: int = 7


@dataclass
class DailyForecast:
    """Aggregated day/night forecast pair."""

    day_name: str
    high_temp: int
    low_temp: Optional[int]
    conditions: str
    precip_pct: int


def make_request(url: str, session: requests.Session) -> requests.Response:
    """
    Make HTTP GET request with retry logic.

    Args:
        url: Full URL to fetch
        session: requests.Session with User-Agent header preset

    Returns:
        requests.Response object on success

    Raises:
        SystemExit: On 4xx error (exits with code 1, prints to stderr)
        SystemExit: On connection error (exits with code 1, prints to stderr)
        SystemExit: On 5xx after retry fails (exits with code 1, prints to stderr)
    """
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)

        # Handle 5xx errors with retry
        if response.status_code >= 500:
            time.sleep(RETRY_DELAY)
            try:
                response = session.get(url, timeout=REQUEST_TIMEOUT)
                if response.status_code >= 500:
                    print(
                        f"Error: {response.status_code} {response.text[:200]}",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            except requests.RequestException as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)

        # Handle 4xx errors
        if 400 <= response.status_code < 500:
            print(
                f"Error: {response.status_code} {response.text[:200]}",
                file=sys.stderr,
            )
            sys.exit(1)

        response.raise_for_status()
        return response

    except requests.RequestException as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def fetch_forecast_url(session: requests.Session) -> str:
    """
    Step 1: GET /points/{lat},{lon} to retrieve forecast URL.

    Args:
        session: requests.Session with User-Agent header preset

    Returns:
        Forecast URL string extracted from response.properties.forecast

    Raises:
        SystemExit: On HTTP error (via make_request)
        KeyError: If response JSON missing expected fields
    """
    url = POINTS_URL_TEMPLATE.format(lat=LAT, lon=LON)
    response = make_request(url, session)
    data = response.json()
    return data["properties"]["forecast"]


def fetch_periods(forecast_url: str, session: requests.Session) -> list[dict]:
    """
    Step 2: GET forecast URL to retrieve period array.

    Args:
        forecast_url: URL from fetch_forecast_url()
        session: requests.Session with User-Agent header preset

    Returns:
        List of period dicts from response.properties.periods

    Raises:
        SystemExit: On HTTP error (via make_request)
        KeyError: If response JSON missing expected fields
    """
    response = make_request(forecast_url, session)
    data = response.json()
    return data["properties"]["periods"]


def aggregate_periods(periods: list[dict], max_days: int) -> list[DailyForecast]:
    """
    Convert 14 day/night periods into max_days daily forecasts.

    Args:
        periods: Raw period dicts from NWS API
        max_days: Maximum number of days to return (1-7)

    Returns:
        List of DailyForecast objects, length <= max_days

    Algorithm:
        1. Find first isDaytime=true period (skip leading night if present)
        2. Pair each day period with its following night period
        3. Extract: day_name, high_temp (day), low_temp (night),
           conditions (day.shortForecast), precip_pct (day.probabilityOfPrecipitation.value or 0)
        4. If night period missing (end of data), set low_temp=None
        5. Return first max_days results
    """
    forecasts: list[DailyForecast] = []

    # Find first isDaytime=true period
    start_idx = 0
    for i, period in enumerate(periods):
        if period.get("isDaytime"):
            start_idx = i
            break

    # Pair day and night periods
    i = start_idx
    while i < len(periods) and len(forecasts) < max_days:
        day_period = periods[i]

        # Make sure we have a day period
        if not day_period.get("isDaytime"):
            i += 1
            continue

        # Look for corresponding night period
        night_period = None
        if i + 1 < len(periods):
            next_period = periods[i + 1]
            if not next_period.get("isDaytime"):
                night_period = next_period

        # Extract values
        day_name = day_period.get("name", "Unknown")
        high_temp = day_period.get("temperature", 0)
        low_temp = night_period.get("temperature") if night_period else None
        conditions = day_period.get("shortForecast", "Unknown")
        precip_pct = (
            day_period.get("probabilityOfPrecipitation", {}).get("value") or 0
        )

        forecasts.append(
            DailyForecast(
                day_name=day_name,
                high_temp=high_temp,
                low_temp=low_temp,
                conditions=conditions,
                precip_pct=precip_pct,
            )
        )

        # Move to next day period (skip night if present)
        i += 2 if night_period else 1

    return forecasts


def fahrenheit_to_celsius(f: int) -> int:
    """Convert Fahrenheit to Celsius, rounded to nearest integer."""
    return round((f - 32) * 5 / 9)


def format_markdown_table(forecasts: list[DailyForecast], units: str) -> str:
    """
    Format forecasts as markdown table.

    Args:
        forecasts: List of DailyForecast objects
        units: "imperial" or "metric"

    Returns:
        Markdown table string with header and data rows
    """
    # Format temperature based on units
    def format_temp(temp: int) -> str:
        if units == "metric":
            celsius = fahrenheit_to_celsius(temp)
            return f"{celsius}°C"
        else:
            return f"{temp}°F"

    lines = []
    lines.append("| Day       | High | Low  | Conditions    | Precip% |")
    lines.append("|-----------|------|------|---------------|---------|")

    for forecast in forecasts:
        high_str = format_temp(forecast.high_temp)
        low_str = (
            format_temp(forecast.low_temp)
            if forecast.low_temp is not None
            else "N/A"
        )
        precip_str = f"{forecast.precip_pct}%"

        # Truncate conditions to fit in column
        conditions = forecast.conditions[:13].ljust(13)
        day_name = forecast.day_name[:9].ljust(9)

        line = f"| {day_name} | {high_str:>4} | {low_str:>4} | {conditions} | {precip_str:>7} |"
        lines.append(line)

    return "\n".join(lines)


def format_json(periods: list[dict], max_days: int) -> str:
    """
    Format raw periods as JSON.

    Args:
        periods: Raw period dicts from NWS API
        max_days: Limit output to first max_days*2 periods

    Returns:
        JSON string (pretty-printed with indent=2)
    """
    limited_periods = periods[: max_days * 2]
    return json.dumps(limited_periods, indent=2)


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Namespace with:
            - days: int (1-7, default 7)
            - units: str ("imperial" or "metric", default "imperial")
            - json: bool (default False)
    """
    parser = argparse.ArgumentParser(
        description="Get a 7-day weather forecast for Marysville, WA"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to show (1-7, default: 7)",
    )
    parser.add_argument(
        "--units",
        choices=["imperial", "metric"],
        default="imperial",
        help="Temperature units (default: imperial)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of markdown table",
    )

    args = parser.parse_args()

    # Validate days argument
    if args.days < 1 or args.days > 7:
        parser.error("--days must be between 1 and 7")

    return args


def main() -> None:
    """
    Main entrypoint.

    Flow:
        1. Parse CLI args
        2. Create requests.Session with User-Agent header
        3. Fetch forecast URL (step 1)
        4. Fetch periods (step 2)
        5. If --json: format_json() and print
        6. Else: aggregate_periods() -> format_markdown_table() and print

    Exit Codes:
        0: Success
        1: HTTP error or connection error
    """
    args = parse_args()

    # Create session with User-Agent header
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # Fetch forecast URL
    forecast_url = fetch_forecast_url(session)

    # Fetch periods
    periods = fetch_periods(forecast_url, session)

    # Output
    if args.json:
        output = format_json(periods, args.days)
    else:
        forecasts = aggregate_periods(periods, args.days)
        output = format_markdown_table(forecasts, args.units)

    print(output)


if __name__ == "__main__":
    main()
