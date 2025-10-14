# noqa: D100

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, UPDATE_COORDINATOR_CLIENTS, NetworkClientSensorDescription
from .entity import NetworkClientBaseSensor, add_network_client_sensors
from .router import KeeneticRouter

NETWORK_CLIENT_BINARY_SENSORS: tuple[NetworkClientSensorDescription, ...] = (
    NetworkClientSensorDescription(
        key="active",
        translation_key="active",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        update_coordinator=UPDATE_COORDINATOR_CLIENTS,
        extra_attributes = [
            "mac", "hostname", "name", "registered",
            "access", "link", "speed", "port"
        ]
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Add Keentic router and Network clients SENSOR entities."""
    router: KeeneticRouter = hass.data[DOMAIN][config_entry.entry_id]
    tracked_client_ids = set()

    # Add sensors for new Network clients
    clients_coordinator: DataUpdateCoordinator = router.\
        update_coordinators[UPDATE_COORDINATOR_CLIENTS]

    @callback
    def _add_new_client_sensors() -> None:
        new_client_ids = set(clients_coordinator.data.keys()).\
            difference(tracked_client_ids)
        tracked_client_ids.update(new_client_ids)

        add_network_client_sensors(
            router,
            new_client_ids,
            NETWORK_CLIENT_BINARY_SENSORS,
            NetworkClientBinarySensor,
            async_add_entities
        )

    config_entry.async_on_unload(
        clients_coordinator.async_add_listener(_add_new_client_sensors)
    )

    # Add current Network clients sensors
    _add_new_client_sensors()


class NetworkClientBinarySensor(NetworkClientBaseSensor, BinarySensorEntity):
    """Network client binary sensor."""
    @property
    def is_on(self) -> bool | None:  # noqa: D102
        if self.client_id in self.coordinator.data:
            return self.coordinator.\
                data[self.client_id][self.entity_description.key]
        return None
