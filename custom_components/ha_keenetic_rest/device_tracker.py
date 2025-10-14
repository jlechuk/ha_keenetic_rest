# noqa: D100

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, UPDATE_COORDINATOR_CLIENTS, NetworkClientSensorDescription
from .entity import NetworkClientBaseSensor, add_network_client_sensors
from .router import KeeneticRouter

NETWORK_CLIENT_SCANNER: tuple[NetworkClientSensorDescription, ...] = (
    NetworkClientSensorDescription(
        key="scanner",
        translation_key="scanner",
        update_coordinator=UPDATE_COORDINATOR_CLIENTS
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

    # Add Scanner for new Network clients
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
            NETWORK_CLIENT_SCANNER,
            NetworkClientScanner,
            async_add_entities
        )

    config_entry.async_on_unload(
        clients_coordinator.async_add_listener(_add_new_client_sensors)
    )

    # Add current Network clients Scanner
    _add_new_client_sensors()


class NetworkClientScanner(NetworkClientBaseSensor, ScannerEntity):
    """Network client Scanner."""

    @property
    def is_connected(self) -> bool:  # noqa: D102
        return self.coordinator.data[self.client_id]["active"]

    @property
    def hostname(self) -> str | None:  # noqa: D102
        return self.coordinator.data[self.client_id]["hostname"]

    @property
    def ip_address(self) -> str | None:  # noqa: D102
        return self.coordinator.data[self.client_id]["ip"]

    @property
    def mac_address(self) -> str:  # noqa: D102
        return self.coordinator.data[self.client_id]["mac"]
