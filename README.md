# weather-forecast-skill

Claude Code skill — 7-day weather forecast for Marysville, WA via NWS `api.weather.gov` (no auth, no key).

## Install

```bash
git clone https://github.com/jtmilan/weather-forecast-skill ~/weather-forecast-skill
cd ~/weather-forecast-skill
bash install.sh
```

## Use

In any Claude Code session: ask "what's the weather this week" or "7-day forecast" — skill triggers, returns markdown table.

```bash
uv run skills/weather-forecast/forecast.py
```

## Example Output

| Day       | High | Low  | Conditions    | Precip% |
|-----------|------|------|---------------|---------|
| Monday    | 63°F | 47°F | Partly Sunny  | 7%      |
| Tuesday   | 60°F | 43°F | Mostly Cloudy | 11%     |
| Wednesday | 68°F | 46°F | Sunny         | 0%      |

### CLI Options

```bash
uv run skills/weather-forecast/forecast.py --days 3        # Show 3 days
uv run skills/weather-forecast/forecast.py --units metric  # Celsius
uv run skills/weather-forecast/forecast.py --json          # Raw JSON
```

## Stack

- Python 3.10+ (PEP 723 inline deps via `uv run`)
- NWS api.weather.gov (free, no auth)
- `requests` + `requests-mock` for tests

## License

Apache 2.0
