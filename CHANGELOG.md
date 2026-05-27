# Changelog

All notable changes to this project will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2024-01-01

### Added
- Initial release
- Authentication via POST `/token` with automatic token validation on startup via POST `/check-token`
- Sensors: device battery, hub battery, active programs, firmware version, weather temperature, rain probability, wind speed, irrigation adjustment, last data update timestamp
- Dynamic zone sensors from `GetZoneNames → fullzonenames`
- Binary sensors: cloud connectivity, program A & B weather-gate (`should_run`)
- Switches: read-only state for programs A–D
- Config flow with email / password / cloud PUID / device PUID
- Re-auth flow triggered when stored token is invalid
- Italian UI translation
- HACS support (`hacs.json`, MIT license, GitHub Actions validation & release workflows)
