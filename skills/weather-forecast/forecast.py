# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
# ]
# ///
"""Weather forecast skill for Marysville, WA."""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Optional

import requests


# Constants
LAT = 48.0518
LON = -122.1771
USER_AGENT = "weather-forecast-skill/0.1 (jtmilan@gmail.com)"
POINTS_URL_TEMPLATE = "https://api.weather.gov/points/{lat},{lon}"
REQUEST_TIMEOUT = 10
RETRY_DELAY = 2.0
MAX_DAYS = 7


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
    Make HTTP GET request with retry logic for 5xx errors.

    Args:
        url: Full URL to fetch
        session: requests.Session with User-Agent header preset

    Returns:
        requests.Response object on success

    Raises:
        SystemExit: On 4xx error, connection error, or 5xx after retry
    """
    try:
        # Try first request
        response = session.get(url, timeout=REQUEST_TIMEOUT)

        # Handle 5xx with retry
        if 500 <= response.status_code < 600:
            time.sleep(RETRY_DELAY)
            response = session.get(url, timeout=REQUEST_TIMEOUT)

        # Handle 4xx errors
        if 400 <= response.status_code < 500:
            error_msg = f"Error: {response.status_code} {response.text[:200]}"
            print(error_msg, file=sys.stderr)
            sys.exit(1)

        # Handle remaining 5xx errors after retry
        if 500 <= response.status_code < 600:
            error_msg = f"Error: {response.status_code} {response.text[:200]}"
            print(error_msg, file=sys.stderr)
            sys.exit(1)

        response.raise_for_status()
        return response

    except requests.RequestException as e:
        error_msg = f"Error: {e}"
        print(error_msg, file=sys.stderr)
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
    forecasts = []
    i = 0

    # Skip leading night period if present
    if periods and not periods[0].get("isDaytime", True):
        i = 1

    # Pair day/night periods
    while i < len(periods) and len(forecasts) < max_days:
        day_period = periods[i]

        # Ensure this is a daytime period
        if not day_period.get("isDaytime", True):
            i += 1
            continue

        # Try to get the night period
        low_temp = None
        if i + 1 < len(periods):
            night_period = periods[i + 1]
            if not night_period.get("isDaytime", True):
                low_temp = night_period.get("temperature")

        # Extract data from day period
        day_name = day_period.get("name", "Day")
        high_temp = day_period.get("temperature", 0)
        conditions = day_period.get("shortForecast", "Unknown")
        precip_data = day_period.get("probabilityOfPrecipitation", {})
        precip_pct = precip_data.get("value", 0) if precip_data else 0
        if precip_pct is None:
            precip_pct = 0

        forecasts.append(
            DailyForecast(
                day_name=day_name,
                high_temp=high_temp,
                low_temp=low_temp,
                conditions=conditions,
                precip_pct=int(precip_pct),
            )
        )

        i += 2  # Move to next day period

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
    # Header
    lines = [
        "| Day       | High | Low  | Conditions    | Precip% |",
        "|-----------|------|------|---------------|---------|",
    ]

    # Data rows
    for forecast in forecasts:
        if units == "metric":
            high_str = f"{fahrenheit_to_celsius(forecast.high_temp)}°C"
            low_str = (
                f"{fahrenheit_to_celsius(forecast.low_temp)}°C"
                if forecast.low_temp is not None
                else "N/A"
            )
        else:  # imperial
            high_str = f"{forecast.high_temp}°F"
            low_str = f"{forecast.low_temp}°F" if forecast.low_temp is not None else "N/A"

        # Pad day name, conditions to consistent width
        day_padded = forecast.day_name.ljust(9)
        conditions_padded = forecast.conditions.ljust(13)

        line = f"| {day_padded} | {high_str:>4} | {low_str:>4} | {conditions_padded} | {forecast.precip_pct:>5}% |"
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
    limit = max_days * 2
    return json.dumps(periods[:limit], indent=2)


def parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    """
    Parse command-line arguments.

    Args:
        args: Optional list of arguments. If None, uses sys.argv.

    Returns:
        Namespace with:
            - days: int (1-7, default 7)
            - units: str ("imperial" or "metric", default "imperial")
            - json: bool (default False)
    """
    parser = argparse.ArgumentParser(
        description="Get 7-day weather forecast for Marysville, WA"
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
        help="Temperature units: imperial or metric (default: imperial)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of markdown table",
    )

    parsed_args = parser.parse_args(args)

    # Validate days argument
    if not 1 <= parsed_args.days <= 7:
        parser.error("--days must be between 1 and 7")

    return parsed_args


def main(args: Optional[list[str]] = None) -> None:
    """
    Main entrypoint.

    Args:
        args: Optional list of CLI arguments. If None, uses sys.argv.

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
    parsed_args = parse_args(args)

    # Create session with User-Agent header
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # Fetch data
    forecast_url = fetch_forecast_url(session)
    periods = fetch_periods(forecast_url, session)

    # Output
    if parsed_args.json:
        output = format_json(periods, parsed_args.days)
    else:
        forecasts = aggregate_periods(periods, parsed_args.days)
        output = format_markdown_table(forecasts, parsed_args.units)

    print(output)


if __name__ == "__main__":
    main()
