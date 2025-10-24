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
    BaseKeeneticEntityDescription,
)
from .entity import BaseKeeneticNetworkClientEntity, add_network_client_entities
from .router import KeeneticRouter


class NetworkClientBinarySensor(
    BaseKeeneticNetworkClientEntity, BinarySensorEntity):
    """Network client binary sensor."""
    @property
    def is_on(self) -> bool | None:  # noqa: D102
        if self.client_id in self.coordinator.data:
            return self.coordinator.\
                data[self.client_id][self.entity_description.key]
        return None


@dataclass
class NetworkClientBinarySensorDescription(
    BaseKeeneticEntityDescription, BinarySensorEntityDescription):
    """Network client binary sensor description."""
    entity_class = NetworkClientBinarySensor


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
                            "Security": "security", "RSSI": "rssi"}
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Add Router and Network clients binary sensors."""
    router: KeeneticRouter = hass.data[DOMAIN][config_entry.entry_id]

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
