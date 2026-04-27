---
name: weather-forecast
---

# Weather Forecast Skill

Get a 7-day weather forecast for Marysville, WA with daily high/low temperatures, conditions, and precipitation probability.

## Trigger Phrases

This skill activates when you ask about:
- **weather** (general weather inquiries)
- **forecast** (weather predictions)
- **marysville weather** (location-specific)
- **7 day forecast** or **7-day forecast** (multi-day outlook)
- **weekly forecast** (full week weather)

## How to Use

To retrieve the weather forecast, run:

```bash
uv run skills/weather-forecast/forecast.py
```

### Options

- `--days N` - Show forecast for N days (1-7, default: 7)
- `--units {imperial,metric}` - Temperature units (default: imperial)
- `--json` - Output raw JSON instead of formatted table

### Examples

```bash
# Get 7-day forecast in Fahrenheit
uv run skills/weather-forecast/forecast.py

# Get 3-day forecast in Celsius
uv run skills/weather-forecast/forecast.py --days 3 --units metric

# Get raw JSON response
uv run skills/weather-forecast/forecast.py --json
```

## Output

The default output is a formatted markdown table:

```
| Day       | High | Low  | Conditions    | Precip% |
|-----------|------|------|---------------|---------|
| Monday    | 63°F | 47°F | Partly Sunny  | 7%      |
| Tuesday   | 60°F | 43°F | Mostly Cloudy | 11%     |
| Wednesday | 68°F | 46°F | Sunny         | 0%      |
```

## Data Source

This skill uses the free National Weather Service (NWS) API (api.weather.gov) to retrieve weather data for Marysville, WA (48.0518°N, 122.1771°W). No API key is required.
