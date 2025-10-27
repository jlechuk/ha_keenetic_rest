# noqa: D100

from dataclasses import dataclass

from homeassistant.components.device_tracker import (
    ScannerEntity,
    ScannerEntityDescription,
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


class NetworkClientScanner(BaseKeeneticNetworkClientEntity, ScannerEntity):
    """Network client scanner."""

    @property
    def is_connected(self) -> bool:  # noqa: D102
        return self._get_coordinator_data().get("active")

    @property
    def hostname(self) -> str | None:  # noqa: D102
        return self._get_coordinator_data().get("hostname")

    @property
    def ip_address(self) -> str | None:  # noqa: D102
        return self._get_coordinator_data().get("ip")

    @property
    def mac_address(self) -> str:  # noqa: D102
        return self._get_coordinator_data().get("mac")


@dataclass
class NetworkClientScannerDescription(
    BaseKeeneticEntityDescription, ScannerEntityDescription):
    """Network client scanner description."""
    entity_class = NetworkClientScanner
    entity_registry_enabled_default = False


NETWORK_CLIENT_SCANNER: tuple[NetworkClientScannerDescription, ...] = (
    NetworkClientScannerDescription(
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
    """Add Network clients scanners."""
    router: KeeneticRouter = hass.data[DOMAIN][config_entry.entry_id]

    # Add current Network clients scanners
    add_network_client_entities(router, router.tracked_network_client_ids,
                               NETWORK_CLIENT_SCANNER, async_add_entities)

    # Add scanners for new Network clients
    @callback
    def _add_new_client_sensors(new_client_ids) -> None:
        add_network_client_entities(router, new_client_ids,
                                   NETWORK_CLIENT_SCANNER, async_add_entities)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_NETWORK_CLIENTS, _add_new_client_sensors
        )
    )
