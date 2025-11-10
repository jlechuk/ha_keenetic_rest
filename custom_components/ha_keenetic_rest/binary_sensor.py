# noqa: D100

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SIGNAL_NEW_NETWORK_CLIENTS,
    UPDATE_COORDINATOR_CLIENTS,
    UPDATE_COORDINATOR_INTERNET_STATUS,
    BaseKeeneticEntityDescription,
)
from .entity import (
    BaseKeeneticNetworkClientEntity,
    BaseKeeneticRouterEntity,
    add_network_client_entities,
)
from .router import KeeneticRouter


class RouterGeneralBinarySensor(BaseKeeneticRouterEntity, BinarySensorEntity):
    """Router binary sensor."""
    @property
    def is_on(self) -> bool | None:  # noqa: D102
        return self._get_coordinator_data().get(self.entity_description.key)


class NetworkClientGeneralBinarySensor(
    BaseKeeneticNetworkClientEntity, BinarySensorEntity):
    """Network client binary sensor."""
    @property
    def is_on(self) -> bool | None:  # noqa: D102
        return self._get_coordinator_data().get(self.entity_description.key)


@dataclass
class RouterBinarySensorDescription(
    BaseKeeneticEntityDescription, BinarySensorEntityDescription):
    """Router binary sensor description."""


@dataclass
class NetworkClientBinarySensorDescription(
    BaseKeeneticEntityDescription, BinarySensorEntityDescription):
    """Network client binary sensor description."""


ROUTER_BINARY_SENSORS: tuple[RouterBinarySensorDescription, ...] = (
    RouterBinarySensorDescription(
        key="internet",
        translation_key="router_internet_status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        update_coordinator=UPDATE_COORDINATOR_INTERNET_STATUS,
        extra_attributes={"Enabled": "enabled",
                          "Gateway accessible": "gateway-accessible",
                          "DNS accessible": "dns-accessible",
                          "Captive accessible": "captive-accessible",
                          "Interface": {"gateway": "interface"},
                          "IP address": {"gateway": "address"},
                          "Captive host": {"captive": "host"}},
        entity_class=RouterGeneralBinarySensor
    ),
)

NETWORK_CLIENT_BINARY_SENSORS: tuple[NetworkClientBinarySensorDescription, ...] = (
    NetworkClientBinarySensorDescription(
        key="active",
        translation_key="active",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        update_coordinator=UPDATE_COORDINATOR_CLIENTS,
        extra_attributes = {"MAC": "mac", "IP": "ip",
                            "Hostname": "hostname", "Name": "name",
                            "Interface ID": {"interface": "id"},
                            "Interface name": {"interface": "name"},
                            "Interface description": {"interface": "description"},
                            "Speed": "speed",
                            "Port": "port", "SSID": "ssid",
                            "Security": "security", "RSSI": "rssi"},
        entity_class=NetworkClientGeneralBinarySensor
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Add Router and Network clients binary sensors."""
    router: KeeneticRouter = hass.data[DOMAIN][config_entry.entry_id]

    # Add Router binary sensors
    router_sensors = [
        description.entity_class(
            router, description
        ) for description in ROUTER_BINARY_SENSORS
    ]
    async_add_entities(router_sensors)


    # Add current Network clients binary sensors
    add_network_client_entities(router, router.tracked_network_client_ids,
                               NETWORK_CLIENT_BINARY_SENSORS,
                               async_add_entities)

    # Add binary sensors for new Network clients
    @callback
    def _add_new_client_sensors(new_client_ids) -> None:
        add_network_client_entities(router, new_client_ids,
                                   NETWORK_CLIENT_BINARY_SENSORS,
                                   async_add_entities)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_NETWORK_CLIENTS, _add_new_client_sensors
        )
    )
