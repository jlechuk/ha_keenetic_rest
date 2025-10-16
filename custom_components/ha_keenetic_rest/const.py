# noqa: D100

from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntityDescription

DOMAIN = 'ha_keenetic_rest'

CONNECTION_TIMEOUT = 30

DEFAULT_NAME = "Keenetic"
DEFAULT_HOST = "192.168.1.1"
DEFAULT_PORT = 80

PROTOCOL_HTTP = "HTTP"
PROTOCOL_HTTPS = "HTTPS"

CONF_DATA_SERIAL = "serial"
CONF_DATA_MODEL = "product"
CONF_DATA_MODEL_ID = "ndmhwid"

ERROR_INVALID_URL = "invalid_url"
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_INVALID_CREDENTIALS = "invalid_credentials"
ERROR_UNSUPPORTED = "unsupported"
ERROR_UNKNOWN = "unknown"

ABORT_ALREADY_CONFIGURED = "already_configured"
ABORT_WRONG_ROUTER = "wrong_router"

UPDATE_COORDINATOR_FW = "system firmware"
UPDATE_COORDINATOR_STAT = "system statistics"
UPDATE_COORDINATOR_CLIENTS = "network clients"
UPDATE_COORDINATOR_RX = "network clients RX speed"
UPDATE_COORDINATOR_TX = "network clients TX speed"

SIGNAL_NEW_NETWORK_CLIENTS = "signal_new_network_clients"


@dataclass
class BaseSensorDescription(SensorEntityDescription):
    """Common sensor description."""
    extra_attributes: list | None = None
    update_coordinator: str = None


@dataclass
class NetworkClientSensorDescription(BaseSensorDescription):
    """Connected device sensor description."""
