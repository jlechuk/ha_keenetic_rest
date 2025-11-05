"""Setup Keentic router."""

import asyncio
import datetime
from functools import partial
import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    #    CONF_PROTOCOL,
    CONF_USERNAME,
    #    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KeeneticAPI
from .const import (
    DOMAIN,
    PROTOCOL_HTTP,
    SIGNAL_NEW_NETWORK_CLIENTS,
    UPDATE_COORDINATOR_CLIENTS,
    UPDATE_COORDINATOR_CLIENTS_RX_SPEED,
    UPDATE_COORDINATOR_CLIENTS_TX_SPEED,
    UPDATE_COORDINATOR_IF_STATS,
    UPDATE_COORDINATOR_INTERNET_STATUS,
    UPDATE_COORDINATOR_SYS_FW,
    UPDATE_COORDINATOR_SYS_STATS,
)

_LOGGER = logging.getLogger(__name__)


UPDATE_INTERVALS = {
    UPDATE_COORDINATOR_SYS_FW: datetime.timedelta(minutes=60),
    UPDATE_COORDINATOR_SYS_STATS: datetime.timedelta(seconds=30),
    UPDATE_COORDINATOR_INTERNET_STATUS: datetime.timedelta(seconds=30),
    UPDATE_COORDINATOR_CLIENTS: datetime.timedelta(seconds=30),
    UPDATE_COORDINATOR_CLIENTS_RX_SPEED: datetime.timedelta(seconds=30),
    UPDATE_COORDINATOR_CLIENTS_TX_SPEED: datetime.timedelta(seconds=30)
}


class KeeneticAuthFailed(HomeAssistantError):
    """Keenetic authentication error."""
    def __init__(  # noqa: D107
        self,
        message:str | None = None,
        error_code: str | None = None
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


class KeeneticRouter:
    """Representation of Keenetic router."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:  # noqa: D107
        self.hass = hass
        self.config_entry = config_entry
        self.update_coordinators = {}
        self.tracked_network_client_ids = []
        self.wan_interface_name = None

        self._authenticated = False
        self._device_ids = {}

        self.api = KeeneticAPI(
            scheme=PROTOCOL_HTTP, #config_entry.data[CONF_PROTOCOL],
            host=config_entry.data[CONF_HOST],
            port=config_entry.data[CONF_PORT],
            ssl_validation=False #config_entry.data[CONF_VERIFY_SSL]
        )


    async def async_setup(self) -> None:
        """Create update coordinators to fetch data using Keenetic api."""
        await self._auth()

        # General update coordinators
        update_methods = {
            UPDATE_COORDINATOR_SYS_FW: partial(self._fetch_data,
                                           self.api.get_system_fw),
            UPDATE_COORDINATOR_INTERNET_STATUS: partial(self._fetch_data,
                                                        self.api.get_internet_status),
            UPDATE_COORDINATOR_CLIENTS: partial(self._fetch_data,
                                                self.api.get_network_clients),
            UPDATE_COORDINATOR_SYS_STATS: self._get_system_stats,
            UPDATE_COORDINATOR_CLIENTS_RX_SPEED: self._get_network_clients_rx,
            UPDATE_COORDINATOR_CLIENTS_TX_SPEED: self._get_network_clients_tx
        }

        for coordinator_type, method in update_methods.items():
            self.update_coordinators[coordinator_type] = DataUpdateCoordinator(
                self.hass, _LOGGER,
                name=f"{coordinator_type}",
                update_method=method,
                update_interval=UPDATE_INTERVALS[coordinator_type]
            )
            await self.update_coordinators[coordinator_type].\
                async_config_entry_first_refresh()

        self.tracked_network_client_ids = list(
            self.get_network_clients_data().keys()
        )

        # Get WAN interface name
        self.wan_interface_name = \
            self.update_coordinators[UPDATE_COORDINATOR_INTERNET_STATUS].\
                data.get("gateway", {}).get("interface")

        # Interfaces stats update coordinator
        self.update_coordinators[UPDATE_COORDINATOR_IF_STATS] = \
            DataUpdateCoordinator(
                self.hass, _LOGGER,
                name=UPDATE_COORDINATOR_IF_STATS,
                update_method=partial(self._get_interface_stats,
                                      names=[self.wan_interface_name]),
                update_interval=datetime.timedelta(seconds=30)
            )
        await self.update_coordinators[UPDATE_COORDINATOR_IF_STATS].\
            async_config_entry_first_refresh()

        # Add coordinators' listeners
        ## Network clients listener
        self.config_entry.async_on_unload(
            self.update_coordinators[UPDATE_COORDINATOR_CLIENTS].\
                async_add_listener(self._network_clients_listener)
        )

        self.config_entry.async_on_unload(self.close)


    async def close(self) -> None:
        """Close session."""
        await self.api.close()


    async def _auth(self) -> None:
        """Authenticate."""
        auth_ok = await self.api.auth(
            username=self.config_entry.data[CONF_USERNAME],
            password=self.config_entry.data[CONF_PASSWORD]
        )

        if not auth_ok:
            self._authenticated = False
            raise KeeneticAuthFailed
        self._authenticated = True


    async def _fetch_data(self, api_func: callable,
                        try_auth: bool = False, **kwargs) -> dict:
        try:
            if not self._authenticated and try_auth:
                try:
                    await self._auth()
                except KeeneticAuthFailed:
                    raise ConfigEntryAuthFailed(  # noqa: B904
                        f"Credentials expired for {self.config_entry.data[CONF_NAME]}"
                    )

            if self._authenticated:
                return await api_func(**kwargs)

            raise UpdateFailed(
                f"Failed to fetch data from "
                f"{self.api.base_url} ({self.config_entry.data[CONF_NAME]}). Unauthorized."
            )
        except (aiohttp.ClientConnectorError, TimeoutError) as ex:
            # Connection error
            raise UpdateFailed(
                f"Failed to fetch data from "
                f"{self.api.base_url} ({self.config_entry.data[CONF_NAME]}): {ex}"
            ) from ex
        except aiohttp.ClientResponseError as ex:
            if ex.status == 401:
                # Unauthorized
                self._authenticated = False

            raise UpdateFailed(
                f"Failed to fetch data from "
                f"{self.api.base_url} ({self.config_entry.data[CONF_NAME]}): {ex}"
            ) from ex


    async def _get_system_stats(self) -> dict:
        """Fetch Keenetic system statistics."""
        data = await self._fetch_data(self.api.get_system_stats, try_auth=True)

        memory_use = data["memtotal"] - data["memfree"]
        data["memory_usage"] = round(
            memory_use / data["memtotal"] * 100, 0
        )

        return data


    async def _get_interface_stats(self, names: list) -> dict:
        stats = {}
        async with asyncio.TaskGroup() as tg:
            for name in names:
                stats[name] = tg.create_task(
                    self._fetch_data(self.api.get_interface_stats, name=name))
        return {name: r.result() for name, r in stats.items()}


    async def _get_network_clients_rx(self) -> dict:
        """Fetch Network clients RX speed."""
        return await self._fetch_data(self.api.get_clients_speed,
                                      direction="rxspeed")


    async def _get_network_clients_tx(self) -> dict:
        """Fetch Network clients RX speed."""
        return await self._fetch_data(self.api.get_clients_speed,
                                      direction="txspeed")


    async def change_client_registered_setting(self, register: bool, mac: str,
                                               name: str | None = None) -> None:
        """Register/Unregister Network client."""
        await self._fetch_data(
            self.api.set_client_registered_setting,
            register=register,
            mac=mac,
            name=name
        )


    async def change_client_internet_access_setting(self, permit: bool,
                                                    mac: str) -> None:
        """Permit/Deny Network client Internet access."""
        await self._fetch_data(
            self.api.set_client_internet_access_setting,
            permit=permit,
            mac=mac
        )


    @callback
    def _network_clients_listener(self) -> None:
        data = self.get_network_clients_data()

        # New Network client signaling
        current_client_ids = set(data.keys())
        new_clients_ids = current_client_ids.\
            difference(self.tracked_network_client_ids)
        self.tracked_network_client_ids.extend(new_clients_ids)

        if new_clients_ids:
            async_dispatcher_send(
                self.hass, SIGNAL_NEW_NETWORK_CLIENTS, new_clients_ids)

        device_registry = dr.async_get(self.hass)

        # Update Network client device name
        for client_id in data:
            device = device_registry.async_get_device(
                connections={(dr.CONNECTION_NETWORK_MAC, client_id)})

            actual_device_name = self._make_client_device_name(client_id)
            if device and device.name != actual_device_name:
                device_registry.async_update_device(
                    device_id=device.id,
                    name=actual_device_name
                )


    def get_network_clients_data(self) -> dict:
        """Get general Network clients data."""
        return self.update_coordinators[UPDATE_COORDINATOR_CLIENTS].data


    def is_client_registered(self, client_id) -> bool:
        """Get Network client Registered field."""
        return self.get_network_clients_data()[client_id]["registered"]


    @property
    def unique_id(self) -> str:
        """Keenetic router unique_id."""
        return self.config_entry.unique_id


    @property
    def _router_device_identifier(self) -> tuple:
        """Keenetic router identifier for DeviceInfo."""
        return (DOMAIN, self.unique_id)


    @property
    def router_device_info(self) -> dr.DeviceInfo:
        """Return Keenetic router DeviceInfo."""
        fw_data = self.update_coordinators[UPDATE_COORDINATOR_SYS_FW].data
        return dr.DeviceInfo(
            identifiers={self._router_device_identifier},
            manufacturer=fw_data["manufacturer"],
            model=fw_data["model"],
            sw_version=fw_data["title"],
            hw_version=fw_data["hw_version"],
            serial_number=self.config_entry.data["serial"],
            name=f"{self.config_entry.data[CONF_NAME]} Router"
        )


    def _make_client_device_name(self, client_id) -> str:
        client_data = self.get_network_clients_data()[client_id]
        client_name = client_data["mac"]
        if client_data["hostname"]:
            client_name = client_data["hostname"]
        if client_data["name"]:
            client_name = client_data["name"]

        return client_name


    def make_client_device_info(self, client_id) -> dr.DeviceInfo:
        """Return Network client DeviceInfo."""
        return dr.DeviceInfo(
            connections={(dr.CONNECTION_NETWORK_MAC, client_id)},
            name=self._make_client_device_name(client_id),
            via_device=self._router_device_identifier
        )
