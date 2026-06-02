# Rain Vision — Sensor Reference

All sensors are created under the `rainvision` domain.
Polling interval: **3 minutes** (`UPDATE_INTERVAL = 180`).

---

## Nuvola Vision-EV (Cloud Hub)

| Sensor | Entity ID | State | API | Field |
|--------|-----------|-------|-----|-------|
| Cloud Battery | `sensor.nuvola_vision_ev_battery` | Battery % (0–100) | `GetPlaces` | `clouds[N].battery` |
| Last BLE Scan | `sensor.nuvola_vision_ev_last_scanned` | ISO timestamp | `GetPlaces` | `clouds[N].last_scanned_at` |
| Last Connection | `sensor.nuvola_vision_ev_last_connection` | ISO timestamp (null in your setup) | `GetPlaces` | `clouds[N].last_connection` |
| Last Ping | `sensor.nuvola_vision_ev_last_ping` | ISO timestamp (null in your setup) | `GetPlaces` | `clouds[N].last_ping_at` |

---

## Pure Vision-EV (Irrigation Controller)

| Sensor | Entity ID | State | API | Field |
|--------|-----------|-------|-----|-------|
| Battery | `sensor.pure_vision_ev_battery` | Battery % (0–100) | `nuvola/device` → fallback `GetPlaces` | `data.status.battery` → `devices[N].battery` |
| Online | `sensor.pure_vision_ev_status` | `Online` / `Offline` | `GetPlaces` | `devices[N].online` |
| Active Programs | `sensor.pure_vision_ev_active_programs` | e.g. `[A,B,C,D]` | `GetPlaces` | `devices[N].active_programs` |
| Meteo Pause | `sensor.pure_vision_ev_meteo_pause` | `Paused` / `Running` | `GetPlaces` | `devices[N].meteo_pause_json[*].should_run` |
| Last Updated | `sensor.pure_vision_ev_last_updated` | ISO timestamp | `GetPlaces` | `devices[N].updated_at` |
| Realtime Timestamp | `sensor.pure_vision_ev_realtime_timestamp` | ISO timestamp | `nuvola/device` | `timestamp` (root) |
| BLE RSSI | `sensor.pure_vision_ev_ble_rssi` | dBm (e.g. 88) | `nuvola/scan/full` | `peers[N].rssi` |
| **Active Zone** | `sensor.pure_vision_ev_active_zone` | Zone name or `Idle` | `nuvola/device` | `data.status.status` bytes 4–5 |

### Active Zone — Bitmask Decoding

Bytes 8–9 of `data.status.status` hex string:

| Hex | Bitmask | Zone | Name |
|-----|---------|------|------|
| `00` | 0 | — | Idle |
| `01` | 1 | Zone 1 | Prato 1 |
| `02` | 2 | Zone 2 | Prato 2 |
| `04` | 4 | Zone 3 | Piante |
| `08` | 8 | Zone 4 | Orto |

### Online Sensor — Extra Attributes

| Attribute | Source | Description |
|-----------|--------|-------------|
| `last_update` | `nuvola/device` → `timestamp` | Timestamp of last realtime response |
| `next_update` | `nuvola/device` → `next_update` | Next scheduled update (often null) |
| `status_hex` | `nuvola/device` → `data.status.status` | Full zone state hex string |
| `pause_hex` | `nuvola/device` → `data.status.pause` | Pause schedule hex string |

### Realtime Timestamp — Extra Attributes

| Attribute | Source | Description |
|-----------|--------|-------------|
| `raw_value` | `nuvola/device` → `timestamp` | Raw ISO timestamp string |
| `next_update` | `nuvola/device` → `next_update` | Next scheduled update |
| `battery` | `nuvola/device` → `data.status.battery` | Battery from realtime response |
| `status_hex` | `nuvola/device` → `data.status.status` | Full zone state hex string |
| `pause_hex` | `nuvola/device` → `data.status.pause` | Pause schedule hex string |
| `last_poll_at` | Coordinator | ISO UTC timestamp of last successful poll |

### Active Zone — Extra Attributes

| Attribute | Source | Description |
|-----------|--------|-------------|
| `zone_bitmask` | `data.status.status` bytes 8–9 | Raw bitmask value (0, 1, 2, 4, 8) |
| `zone_progressive` | Derived | Progressive zone index (1–4) or null |
| `status_hex` | `nuvola/device` → `data.status.status` | Full raw status hex string |
| `last_poll_at` | Coordinator | ISO UTC timestamp of last successful poll |

---

## Irrigation Programs (A / B / C / D)

One sensor per program, created from `GetDeviceProgramList`.
Program names come from `devices[N].fullprogramnames`.

| Sensor | Entity ID | State | API | Field |
|--------|-----------|-------|-----|-------|
| Program A | `sensor.pure_vision_ev_programma_a_prato` | Next active start time (HH:MM) or `Inactive` | `GetDeviceProgramList` | `programs[N].times[*].time` where `active=true` |
| Program B | `sensor.pure_vision_ev_programma_b_piante` | idem | idem | idem |
| Program C | `sensor.pure_vision_ev_programma_c_orto` | idem | idem | idem |
| Program D | `sensor.pure_vision_ev_programma_d` | idem | idem | idem |

### Program Sensor — Flat Attributes

#### Metadata

| Attribute | Source Field | Description |
|-----------|-------------|-------------|
| `type` | `programs[N].type` | Schedule type: `cycle` or `weekdays` |
| `cycle` | `programs[N].cycle` | Cycle frequency in hours (string, e.g. `"48"`) |
| `active` | Derived from `devices[N].active_programs` | Whether this program is enabled (`GetPlaces`) |
| `even` | `programs[N].even` | Internal scheduling bitmask (e.g. `"253"`) |
| `total_duration_minutes` | Computed | Sum of all active zone durations in minutes |

#### Start Times (up to 6 slots, N = 0–5)

| Attribute | Source Field | Description |
|-----------|-------------|-------------|
| `times_N_time` | `programs[N].times[N].time` | Start time string (HH:MM) |
| `times_N_active` | `programs[N].times[N].active` | Whether this slot is enabled |

#### Zones (4 zones, N = 0–3)

| Attribute | Source Field | Description |
|-----------|-------------|-------------|
| `zones_N_id` | `programs[N].zones[N].id` | Zone bitmask ID (1, 2, 4, 8) |
| `zones_N_progressive` | `programs[N].zones[N].progressive` | Zone index (1–4) |
| `zones_N_name` | Injected from `devices[N].zonenames` | Custom zone name (e.g. "Prato 1") |
| `zones_N_duration_seconds` | `programs[N].zones[N].duration` | Duration in seconds |
| `zones_N_duration_minutes` | Computed | Duration in minutes (rounded to 1 decimal) |
| `zones_N_active` | Computed | True if duration > 0 |

#### Weekdays (7 days, N = 0–6, only when type = weekdays)

| Attribute | Source Field | Description |
|-----------|-------------|-------------|
| `weekdays_N_name` | `programs[N].weekdays[N].name` | Day name (e.g. "Lunedì") |
| `weekdays_N_index` | `programs[N].weekdays[N].index` | Day index (1=Sun … 7=Sat) |
| `weekdays_N_is_checked` | `programs[N].weekdays[N].isChecked` | Whether this day is active |

---

## ACQUA VISION (BLE Water Sensor)

Discovered via `nuvola/scan/full`. Created dynamically after first poll.

| Sensor | Entity ID | State | API | Field |
|--------|-----------|-------|-----|-------|
| Battery | `sensor.acqua_vision_battery` | Battery % (e.g. 60) | `nuvola/scan/full` | `peers[N].battery` |
| BLE RSSI | `sensor.acqua_vision_ble_rssi` | dBm (e.g. 81) | `nuvola/scan/full` | `peers[N].rssi` |

### ACQUA VISION RSSI — Extra Attributes

| Attribute | Source | Description |
|-----------|--------|-------------|
| `device_name` | `peers[N].device.name` | Device name |
| `device_type` | `peers[N].devicetype.name` | Device type name |
| `puid` | `peers[N].device.puid` | Device PUID string |
| `paired` | `peers[N].paired` | Whether paired to the Nuvola hub |
| `fw` | `peers[N].fw` | Firmware version string |
| `mdata` | `peers[N].mdata` | Raw BLE manufacturer data hex string |

---

## API Endpoints Summary

| Endpoint | Method | Called every | Used for |
|----------|--------|-------------|---------|
| `POST /api/v5/token` | — | Once at setup | Authentication |
| `POST /api/v5/GetPlaces` | — | Every 3 min | Clouds, devices, zone names, program names, active_programs, meteo_pause |
| `POST /api/v5/nuvola/device` | — | Every 3 min | Real-time battery, status hex, pause hex, timestamp |
| `POST /api/v5/nuvola/scan/full` | — | Every 3 min | BLE RSSI for all visible devices (Pure Vision + Acqua Vision) |
| `POST /api/v5/GetDeviceProgramList` | — | Every 3 min | Program schedules (times, zones, weekdays, type, cycle) |
| `POST /api/v5/SetDeviceProgramsNuvola` | — | On demand | Update program settings |
| `POST /api/v5/nuvola/device/write` | — | On demand | Manual start / stop irrigation |
