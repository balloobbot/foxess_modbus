"""Constants for the FoxESS - Modbus integration."""

from datetime import timedelta

DOMAIN = "foxess_modbus"
MANUFACTURER = "FoxESS"

CONF_ADAPTER = "adapter"
CONF_PROTOCOL = "protocol"
CONF_UNIT_ID = "unit_id"
CONF_POLL_INTERVAL = "poll_interval"
CONF_MAX_READ = "max_read"
CONF_ROUND_VALUES = "round_sensor_values"

PROTOCOL_TCP = "tcp"
PROTOCOL_UDP = "udp"
PROTOCOL_RTU_OVER_TCP = "rtu_over_tcp"
PROTOCOL_SERIAL = "serial"

DEFAULT_UNIT_ID = 247
DEFAULT_PORT = 502

# Settings only change when something writes them.
SETTINGS_INTERVAL = timedelta(minutes=5)
