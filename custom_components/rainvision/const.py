"""Constants for Rain Vision integration."""

DOMAIN = "rainvision"
MANUFACTURER = "Rain S.p.A."
MODEL_CLOUD = "Nuvola Vision"
MODEL_DEVICE = "Pure Vision"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_TOKEN = "token"

# Polling interval in seconds
UPDATE_INTERVAL = 60

# Programs available
PROGRAMS = ["A", "B", "C", "D"]

# Default manual irrigation duration (minutes)
DEFAULT_MANUAL_DURATION = 10

# Services
SERVICE_START_ZONE = "start_zone"
SERVICE_STOP_ZONE = "stop_zone"

ATTR_DURATION = "duration"
ATTR_ZONE = "zone"
