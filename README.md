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

## Stack

- Python 3.10+ (PEP 723 inline deps via `uv run`)
- NWS api.weather.gov (free, no auth)
- `requests` + `requests-mock` for tests

## License

Apache 2.0
