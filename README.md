# Rain Vision — Home Assistant Integration

Unofficial HACS integration for the [Rain Vision](https://www.rainvision.it) smart irrigation system by RAIN S.p.A.

Reverse-engineered from the Rain Vision web app API. Supports the **Nuvola Vision-EV** hub and **Pure Vision-EV** irrigation controller.

---

## Requirements

- Home Assistant 2024.1 or later
- Nuvola Vision-EV hub connected to the internet
- Pure Vision-EV irrigation controller paired to the hub
- Active Rain Vision account

---

## Installation

### Via HACS (recommended)
1. Open HACS → Integrations → ⋮ → Custom repositories
2. Add this repository URL, category: **Integration**
3. Search for **Rain Vision** and install
4. Restart Home Assistant

### Manual
1. Copy `custom_components/rainvision/` to your `config/custom_components/` folder
2. Restart Home Assistant

---

## Configuration

1. **Settings → Devices & Services → Add Integration**
2. Search for **Rain Vision**
3. Enter your rainvision.it **email** and **password**
4. Set the desired **polling interval** in seconds (default: 180 = 3 minutes, min: 60, max: 3600)
5. Entities are created automatically after the first successful poll

To change the polling interval later: **Settings → Devices & Services → Rain Vision → Configure**

---

## Sensors

### Nuvola Vision-EV (Cloud Hub)

| Entity | State | Description |
|--------|-------|-------------|
| `sensor.nuvola_vision_ev_battery` | `%` | Hub battery level |
| `sensor.nuvola_vision_ev_last_scanned` | timestamp | Last BLE scan of the Pure Vision device |
| `sensor.nuvola_vision_ev_last_connection` | timestamp | Last cloud connection (null on some setups) |
| `sensor.nuvola_vision_ev_last_ping` | timestamp | Last heartbeat ping (null on some setups) |
| `sensor.nuvola_vision_ev_meteo` | `°C` | Current temperature at hub location |

#### `sensor.nuvola_vision_ev_meteo` attributes

| Attribute | Unit | Description |
|-----------|------|-------------|
| `temp` | °C | Current temperature |
| `temp_min` / `temp_max` | °C | Daily min/max temperature |
| `feels_like` | °C | Apparent temperature |
| `humidity` | % | Relative humidity |
| `pressure` | hPa | Atmospheric pressure |
| `visibility` | m | Visibility distance |
| `wind_speed` | m/s | Wind speed |
| `wind_deg` | ° | Wind direction |
| `wind_gust` | m/s | Wind gust speed (null if unavailable) |
| `clouds` | % | Cloud coverage |
| `weather_main` | — | Weather category (e.g. `Clear`) |
| `description` | — | Weather description (e.g. `cielo sereno`) |
| `icon` | — | OpenWeatherMap icon code (e.g. `01d`) |

---

### Pure Vision-EV (Irrigation Controller)

| Entity | State | Description |
|--------|-------|-------------|
| `sensor.pure_vision_ev_battery` | `%` | Controller battery level |
| `sensor.pure_vision_ev_status` | `Online` / `Offline` | Device connectivity status |
| `sensor.pure_vision_ev_active_programs` | e.g. `[A,B,C,D]` | Currently enabled programs |
| `sensor.pure_vision_ev_meteo_pause` | `Paused` / `Running` | Weather-based pause status |
| `sensor.pure_vision_ev_last_updated` | timestamp | Last record update in Rain Vision cloud |
| `sensor.pure_vision_ev_realtime_timestamp` | timestamp | Timestamp of last real-time API response |
| `sensor.pure_vision_ev_ble_rssi` | dBm | BLE signal strength to Nuvola hub |
| `sensor.pure_vision_ev_active_zone` | zone name / `Idle` | Zone currently irrigating |

#### `sensor.pure_vision_ev_active_zone` attributes

| Attribute | Description |
|-----------|-------------|
| `zone_bitmask` | Raw bitmask (0=idle, 1=Z1, 2=Z2, 4=Z3, 8=Z4) |
| `zone_progressive` | Progressive zone index (1–4) |
| `status_hex` | Full raw status hex string from device |
| `last_poll_at` | datetime of last successful poll |

#### `sensor.pure_vision_ev_realtime_timestamp` attributes

| Attribute | Description |
|-----------|-------------|
| `battery` | Battery from real-time response |
| `status_hex` | Zone state hex string |
| `pause_hex` | Pause schedule hex string |
| `next_update` | Next scheduled update (often null) |
| `last_poll_at` | datetime of last successful poll |

---

### Irrigation Programs (A / B / C / D)

One sensor per program. State = next active start time (HH:MM) or `Inactive`.

| Entity | Description |
|--------|-------------|
| `sensor.pure_vision_ev_programma_a_prato` | Program A — Lawn |
| `sensor.pure_vision_ev_programma_b_piante` | Program B — Plants |
| `sensor.pure_vision_ev_programma_c_orto` | Program C — Garden |
| `sensor.pure_vision_ev_programma_d` | Program D |

#### Program sensor flat attributes

**Metadata**

| Attribute | Description |
|-----------|-------------|
| `type` | Schedule type: `cycle` or `weekdays` |
| `cycle` | Cycle frequency in hours (string, e.g. `"48"`) |
| `active` | Whether program is enabled (from `active_programs`) |
| `even` | Internal scheduling bitmask |
| `total_duration_minutes` | Sum of all active zone durations |

**Start times** (N = 0–5)

| Attribute | Description |
|-----------|-------------|
| `times_N_time` | Start time (HH:MM) |
| `times_N_active` | Whether this slot is enabled |

**Zones** (N = 0–3)

| Attribute | Description |
|-----------|-------------|
| `zones_N_id` | Zone bitmask ID (1, 2, 4, 8) |
| `zones_N_progressive` | Zone index (1–4) |
| `zones_N_name` | Custom zone name (e.g. `Prato 1`) |
| `zones_N_duration_seconds` | Duration in seconds |
| `zones_N_duration_minutes` | Duration in minutes |
| `zones_N_active` | True if duration > 0 |

**Weekdays** (N = 0–6, only when `type = weekdays`)

| Attribute | Description |
|-----------|-------------|
| `weekdays_N_name` | Day name (e.g. `Lunedì`) |
| `weekdays_N_index` | Day index (1=Sun … 7=Sat) |
| `weekdays_N_is_checked` | Whether this day is active |

---

### ACQUA VISION (BLE Water Sensor)

Discovered automatically via BLE scan. Created after the first poll.

| Entity | State | Description |
|--------|-------|-------------|
| `sensor.acqua_vision_battery` | `%` | Sensor battery level |
| `sensor.acqua_vision_ble_rssi` | dBm | BLE signal strength to Nuvola hub |

#### `sensor.acqua_vision_ble_rssi` attributes

| Attribute | Description |
|-----------|-------------|
| `paired` | Whether paired to the Nuvola hub |
| `fw` | Firmware version |
| `mdata` | Raw BLE manufacturer data hex string |
| `puid` | Device PUID string |

---

## Switches

| Entity | Description |
|--------|-------------|
| `switch.pure_vision_ev_programma_a_prato` | Enable / disable Program A |
| `switch.pure_vision_ev_programma_b_piante` | Enable / disable Program B |
| `switch.pure_vision_ev_programma_c_orto` | Enable / disable Program C |
| `switch.pure_vision_ev_programma_d` | Enable / disable Program D |

---

## Services

| Service | Parameters | Description |
|---------|-----------|-------------|
| `rainvision.manual_start` | `device_puid`, `zone_progressive` (1–4), `duration_minutes` | Start manual irrigation on a zone |
| `rainvision.manual_stop` | `device_puid` | Stop all manual irrigation immediately |
| `rainvision.set_zone_duration` | `device_puid`, `program`, `zone_id`, `duration_seconds` | Update zone duration in a program |
| `rainvision.set_program_start_time` | `device_puid`, `program`, `time_index`, `time`, `active` | Update a start-time slot (0–5) |
| `rainvision.set_program_cycle` | `device_puid`, `program`, `cycle_hours` | Update repeat frequency in hours |
| `rainvision.set_program_weekdays` | `device_puid`, `program`, `weekdays` | Update active weekdays |
| `rainvision.set_programs` | `device_puid`, `programs` | Send a complete programs payload (A–D) |

### Manual start zone mapping

| `zone_progressive` | Zone name |
|-------------------|-----------|
| `1` | Zone 1 (Prato 1) |
| `2` | Zone 2 (Prato 2) |
| `3` | Zone 3 (Piante) |
| `4` | Zone 4 (Orto) |

---

## API Endpoints

| Endpoint | Method | Polling | Description |
|----------|--------|---------|-------------|
| `POST /api/v5/token` | — | Once | Login — obtain Bearer token |
| `POST /api/v5/check-token` | — | Once | Validate stored token on startup |
| `POST /api/v5/GetPlaces` | — | Every poll | Full hub/device hierarchy, zone names, program names, active_programs, meteo_pause |
| `POST /api/v5/nuvola/device` | — | Every poll | Real-time status: battery, zone state hex, pause hex, weather |
| `POST /api/v5/nuvola/scan/full` | — | Every poll | BLE scan: RSSI and battery for all visible devices |
| `POST /api/v5/GetDeviceProgramList` | — | Every poll | Program schedules: times, zones, weekdays, type, cycle |
| `POST /api/v5/SetDeviceProgramsNuvola` | — | On demand | Save updated programs payload |
| `POST /api/v5/nuvola/device/write` | — | On demand | Manual start / stop irrigation via BLE commands |

---

## Dashboard Cards

The following Lovelace YAML files are included in the repository:

| File | Description |
|------|-------------|
| `lovelace-entities-program-a.yaml` | All attributes for Program A |
| `lovelace-entities-program-b.yaml` | All attributes for Program B |
| `lovelace-entities-program-c.yaml` | All attributes for Program C |
| `lovelace-edit-section.yaml` | Edit program settings from dashboard |
| `lovelace-manual-section.yaml` | Manual irrigation with zone duration inputs |
| `lovelace-meteo-button.yaml` | Weather card (button-card) |
| `lovelace-meteo-section.yaml` | Full weather section |
| `helpers.yaml` | HA input helpers for the edit section |

---

## Disclaimer

This is an **unofficial** integration not affiliated with or endorsed by RAIN S.p.A.
Use at your own risk. Rain Vision API may change without notice.
