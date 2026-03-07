# Project Spec

## Name
weather-alerter

## Description
A CLI tool that checks weather forecasts for a given location and sends
desktop notifications when severe weather is expected within the next 24 hours.

## Python Version
3.12

## Input
- City name or lat/lon coordinates (CLI argument)
- Optional: threshold severity level (default: "warning")
- Optional: config file path for saved locations

## Output
- Desktop notification with weather alert summary
- JSON log file of all alerts (appended per run)
- Exit code 0 if no alerts, 1 if alerts found

## Requirements
- Fetch forecast data from Open-Meteo API (free, no key required)
- Parse WMO weather codes into human-readable severity levels
- Support multiple saved locations via a YAML config file
- Send desktop notifications cross-platform (Linux/macOS/Windows)
- Structured logging with loguru
- All data models use Pydantic for validation
- CLI interface built with Typer
- Graceful error handling for network failures and invalid input

## Dependencies
requests, pydantic, typer, loguru, pyyaml, plyer

## Example Usage
```bash
# Check weather for a city
weather-alerter check "Amsterdam"

# Check weather with custom severity threshold
weather-alerter check "Amsterdam" --threshold severe

# Check all saved locations from config
weather-alerter check-all --config locations.yaml

# Show last 10 alerts from log
weather-alerter history --limit 10
```

## Edge Cases
- Network timeout or API unavailability should retry 3 times with backoff
- Unknown city name should give a clear error, not crash
- Empty config file should print a helpful message
- Log file should be created automatically if it doesn't exist

## Documentation
<!-- Optional: put paths to reference docs, API specs, or examples here -->
<!-- These files will be fed to Claude as additional context -->
<!-- docs/open-meteo-api.md -->
<!-- docs/wmo-weather-codes.md -->
