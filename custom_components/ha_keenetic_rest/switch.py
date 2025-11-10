# noqa: D100

from dataclasses import dataclass

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
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


class NetworkClientRegisteredSwitch(
    BaseKeeneticNetworkClientEntity, SwitchEntity):
    """Network client Registered switch."""

    @property
    def is_on(self) -> bool | None:  # noqa: D102
        return self._get_coordinator_data().get(self.entity_description.key)

    async def async_turn_on(self, **kwargs):  # noqa: D102
        mac = self._get_coordinator_data().get("mac")
        name = self.device_info.get("name")
        if mac and name:
            await self.router.change_client_registered_setting(
                register=True, mac=mac, name=name)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):  # noqa: D102
        if mac := self._get_coordinator_data().get("mac"):
            await self.router.change_client_registered_setting(
                register=False, mac=mac)
        await self.coordinator.async_request_refresh()


class NetworkClientInternetAccessSwitch(
    BaseKeeneticNetworkClientEntity, SwitchEntity):
    """Network client Internet access switch."""

    @property
    def is_on(self) -> bool | None:  # noqa: D102
        state = self._get_coordinator_data().get(self.entity_description.key)
        if state:
            return state == "permit"
        return None

    async def async_turn_on(self, **kwargs):  # noqa: D102
        if mac := self._get_coordinator_data().get("mac"):
            await self.router.change_client_internet_access_setting(
                permit=True, mac=mac)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):  # noqa: D102
        if mac := self._get_coordinator_data().get("mac"):
            await self.router.change_client_internet_access_setting(
                permit=False, mac=mac)
        await self.coordinator.async_request_refresh()

    @property
    def available(self) -> bool:  # noqa: D102
        return super().available \
              and self.router.is_client_registered(self.client_id)


@dataclass
class NetworkClientSwitchDescription(
    BaseKeeneticEntityDescription, SwitchEntityDescription):
    """Network client switch description."""


NETWORK_CLIENT_SWITCHES: tuple[NetworkClientSwitchDescription, ...] = (
    NetworkClientSwitchDescription(
        key="registered",
        translation_key="client_registered",
        device_class=SwitchDeviceClass.SWITCH,
        update_coordinator=UPDATE_COORDINATOR_CLIENTS,
        entity_class=NetworkClientRegisteredSwitch
    ),
    NetworkClientSwitchDescription(
        key="access",
        translation_key="client_internet_access",
        device_class=SwitchDeviceClass.SWITCH,
        update_coordinator=UPDATE_COORDINATOR_CLIENTS,
        entity_class=NetworkClientInternetAccessSwitch
    )
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Add Router and Network clients switches."""
    router: KeeneticRouter = hass.data[DOMAIN][config_entry.entry_id]

        # Add current Network clients binary sensors
    add_network_client_entities(router, router.tracked_network_client_ids,
                               NETWORK_CLIENT_SWITCHES,
                               async_add_entities)

    # Add binary sensors for new Network clients
    @callback
    def _add_new_client_sensors(new_client_ids) -> None:
        add_network_client_entities(router, new_client_ids,
                                   NETWORK_CLIENT_SWITCHES,
                                   async_add_entities)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_NETWORK_CLIENTS, _add_new_client_sensors
        )
    )
