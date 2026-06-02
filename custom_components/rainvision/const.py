"""
Constants for the Rain Vision integration.

Centralises all fixed values used across the integration:
domain name, manufacturer info, config entry keys, polling
interval, service names and supported program letters.
"""

# Integration domain — must match the folder name and manifest domain
DOMAIN = "rainvision"

# Device registry metadata
MANUFACTURER = "Rain S.p.A."
MODEL_CLOUD  = "Nuvola Vision"
MODEL_DEVICE = "Pure Vision"

# Config entry data keys
CONF_TOKEN = "token"

# How often the coordinator polls the Rain Vision API (seconds)
UPDATE_INTERVAL    = 180   # default polling interval in seconds (3 minutes)
CONF_SCAN_INTERVAL = "scan_interval"  # config entry key for polling interval
MIN_SCAN_INTERVAL  = 60    # minimum allowed polling interval (1 minute)
MAX_SCAN_INTERVAL  = 3600  # maximum allowed polling interval (1 hour)

# Default duration used when manually starting a zone without specifying one
DEFAULT_MANUAL_DURATION = 10  # minutes

# Valid irrigation program letters (A through H)
PROGRAMS = ["A", "B", "C", "D"]  # E-H not yet supported

# ── Service names ─────────────────────────────────────────────────────────────
SVC_MANUAL_START      = "manual_start"
SVC_MANUAL_STOP       = "manual_stop"
SVC_SET_ZONE_DURATION = "set_zone_duration"
SVC_SET_START_TIME    = "set_program_start_time"
SVC_SET_CYCLE         = "set_program_cycle"
SVC_SET_WEEKDAYS      = "set_program_weekdays"
SVC_SET_PROGRAMS      = "set_programs"
