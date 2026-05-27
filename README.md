# Rainvision for Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)](https://www.home-assistant.io)
[![Version](https://img.shields.io/github/v/release/your-user/rainvision-ha)](https://github.com/your-user/rainvision-ha/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Home Assistant custom integration for **Rainvision** smart irrigation systems.
Connects to the Rainvision cloud API v5 to monitor and expose your irrigation controller data.

---

## Features

- **Sensors** — device battery, hub battery, active programs, firmware version, weather temperature, rain probability, wind speed, irrigation adjustment variable, per-zone names, last data update timestamp
- **Binary sensors** — cloud connectivity, weather-gate status per program (A & B)
- **Switches** — read-only state of programs A–D
- **Automatic token refresh** — validates the stored token on every HA startup via `/check-token`; re-authenticates transparently when expired
- **60-second polling** — configurable in `const.py`

---

## Installation

### Via HACS (recommended)

1. In Home Assistant open **HACS → Integrations**
2. Click the three-dot menu (⋮) → **Custom repositories**
3. Enter `https://github.com/your-user/rainvision-ha` and select category **Integration**
4. Click **Add**, then search for **Rainvision** and install it
5. Restart Home Assistant

### Manual

1. Copy `custom_components/rainvision/` into your `<config>/custom_components/` directory
2. Restart Home Assistant

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Rainvision**
3. Fill in:
   - **Email** and **Password** of your rainvision.it account
   - **Hub PUID** — your NUVOLA VISION hub PUID (starts with `2000…`)
   - **Device PUID** — your PURE VISION irrigation controller PUID (starts with `1000…`)

> **Where to find PUIDs:** open the Rainvision app, go to device details, and note the PUID shown there. The hub PUID starts with `2000`, the controller PUID starts with `1000`.

---

## Entities

### Sensors

| Entity ID | Description |
|---|---|
| `sensor.rainvision_irrigation_device_battery` | Device battery (%) |
| `sensor.rainvision_hub_battery` | Hub battery (%) |
| `sensor.rainvision_active_programs` | Active programs (e.g. `A B C D`) |
| `sensor.rainvision_firmware_version` | Installed firmware ID |
| `sensor.rainvision_weather_temperature` | Forecast temperature (°C) |
| `sensor.rainvision_rain_probability` | Probability of precipitation (%) |
| `sensor.rainvision_wind_speed` | Wind speed (m/s) |
| `sensor.rainvision_irrigation_adjustment` | Weather-based irrigation variable (%) |
| `sensor.rainvision_last_data_update` | Timestamp of last successful API poll |
| `sensor.rainvision_<zone_name>` | One sensor per zone (name from the app) |

### Binary sensors

| Entity ID | Description |
|---|---|
| `binary_sensor.rainvision_cloud_connected` | Cloud connectivity |
| `binary_sensor.rainvision_program_a_weather_ok` | Weather allows program A to run |
| `binary_sensor.rainvision_program_b_weather_ok` | Weather allows program B to run |

### Switches

| Entity ID | Description |
|---|---|
| `switch.rainvision_program_a` | Program A active state (read-only) |
| `switch.rainvision_program_b` | Program B active state (read-only) |
| `switch.rainvision_program_c` | Program C active state (read-only) |
| `switch.rainvision_program_d` | Program D active state (read-only) |

> **Note on switches:** the Rainvision cloud API does not expose an endpoint to enable or disable programs remotely. Switches reflect the current state only. Use them as conditions in automations.

---

## Automation examples

```yaml
# Notify when a program is paused due to rain forecast
automation:
  - alias: "Rainvision — program A paused by weather"
    trigger:
      - platform: state
        entity_id: binary_sensor.rainvision_program_a_weather_ok
        to: "off"
    action:
      - service: notify.mobile_app
        data:
          title: "Rainvision"
          message: "Program A suspended — rain forecast"
```

```yaml
# Alert when device battery is low
automation:
  - alias: "Rainvision — low device battery"
    trigger:
      - platform: numeric_state
        entity_id: sensor.rainvision_irrigation_device_battery
        below: 20
    action:
      - service: persistent_notification.create
        data:
          title: "Rainvision"
          message: "Device battery at {{ states('sensor.rainvision_irrigation_device_battery') }}%"
```

---

## Update interval

Default: **60 seconds**. Change `SCAN_INTERVAL_SECONDS` in `custom_components/rainvision/const.py`.

---

## License

MIT — see [LICENSE](LICENSE).
