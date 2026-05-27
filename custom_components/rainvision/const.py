"""Constants for the Rainvision integration."""

DOMAIN = "rainvision"

BASE_URL = "https://www.rainvision.it/api/v5"

# Config entry keys
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_CLOUD_PUID = "cloud_puid"
CONF_DEVICE_PUID = "device_puid"
CONF_TOKEN = "token"

# How often to poll the cloud API (seconds)
SCAN_INTERVAL_SECONDS = 60

# Entity attribute names
ATTR_BATTERY = "battery"
ATTR_STATUS = "status"
ATTR_PROGRAMS = "programs"
ATTR_ZONES = "zones"
ATTR_METEO_PAUSE = "meteo_pause"
ATTR_FIRMWARE = "firmware_id"
ATTR_LAST_UPDATE = "last_update"
ATTR_ACTIVE_PROGRAMS = "active_programs"

# Keys used inside the coordinator data dict
COORDINATOR_DEVICE = "device"
COORDINATOR_STAT = "stat"
COORDINATOR_PROGRAMS = "programs"
COORDINATOR_ZONES = "zones"
