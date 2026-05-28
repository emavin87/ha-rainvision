# Rain Vision — Home Assistant Integration

Unofficial HACS integration for the [Rain Vision](https://www.rainvision.it) smart irrigation system by RAIN S.p.A.

---

## Features

### Sensors
| Entity | Description |
|---|---|
| `sensor.<device>_battery` | Pure Vision battery level (%) |
| `sensor.<nuvola>_battery` | Nuvola hub battery level (%) |
| `sensor.<device>_status` | Device online / offline |
| `sensor.<device>_active_programs` | Currently enabled programs (A–H) |
| `sensor.<device>_meteo_pause` | Weather-based pause status |
| `sensor.<device>_program_<X>_(<name>)` | Next start time + full schedule for program X |
| `sensor.<device>_prog_<X>_<zone>_duration` | Irrigation duration for one zone in one program |

### Switches
| Entity | Description |
|---|---|
| `switch.<device>_<zone>` | Manually start / stop irrigation on a zone |
| `switch.<device>_program_<X>` | Enable / disable a scheduled program |

### Select helpers
| Entity | Description |
|---|---|
| `select.rain_vision_select_nuvola_hub` | Lists all hubs — shows cloud_id in attributes |
| `select.rain_vision_select_device` | Lists all devices — shows device_id + puid |
| `select.rain_vision_select_device_puid` | Lists all PUIDs — for program services |

### Services
| Service | Description |
|---|---|
| `rainvision.manual_start` | Start manual irrigation on a zone |
| `rainvision.manual_stop` | Stop all manual irrigation on a device |
| `rainvision.set_zone_duration` | Update zone duration in a program |
| `rainvision.set_program_start_time` | Update a start-time slot (up to 6 per program) |
| `rainvision.set_program_cycle` | Update repeat frequency (hours) |
| `rainvision.set_program_weekdays` | Update active weekdays |
| `rainvision.set_programs` | Send a complete programs payload |

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
3. Enter your rainvision.it email and password
4. Entities are created automatically

---

## API endpoints used

| Endpoint | Purpose |
|---|---|
| `POST /api/v5/token` | Login — obtain Bearer token |
| `POST /api/v5/check-token` | Validate stored token |
| `POST /api/v5/GetPlaces` | Full place/cloud/device hierarchy |
| `POST /api/v5/nuvola/device` | Real-time device status (battery, status hex) |
| `POST /api/v5/GetDeviceProgramList` | Programs with zones and durations |
| `POST /api/v5/GetZoneNames` | Zone names |
| `POST /api/v5/GetProgramNames` | Program names |
| `POST /api/v5/SetDeviceProgramsNuvola` | Save full programs payload |
| `POST /api/v5/ManualStart` | Start manual irrigation |
| `POST /api/v5/ManualStop` | Stop manual irrigation |
| `POST /api/v5/SetProgramActive` | Enable/disable a program |

---

## Disclaimer

This is an **unofficial** integration not affiliated with RAIN S.p.A. Use at your own risk.
