"""Setup Keentic router."""

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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KeeneticAPI
from .const import (
    DOMAIN,
    PROTOCOL_HTTP,
    SIGNAL_NEW_NETWORK_CLIENTS,
    UPDATE_COORDINATOR_CLIENTS,
    UPDATE_COORDINATOR_FW,
    UPDATE_COORDINATOR_RX,
    UPDATE_COORDINATOR_STAT,
    UPDATE_COORDINATOR_TX,
    UPDATE_COORDINATOR_WAN_SPEED,
    UPDATE_COORDINATOR_WAN_STATUS,
)

_LOGGER = logging.getLogger(__name__)


UPDATE_INTERVALS = {
    UPDATE_COORDINATOR_FW: datetime.timedelta(minutes=60),
    UPDATE_COORDINATOR_STAT: datetime.timedelta(seconds=30),
    UPDATE_COORDINATOR_WAN_STATUS: datetime.timedelta(seconds=30),
    UPDATE_COORDINATOR_WAN_SPEED: datetime.timedelta(seconds=30),
    UPDATE_COORDINATOR_CLIENTS: datetime.timedelta(seconds=30),
    UPDATE_COORDINATOR_RX: datetime.timedelta(seconds=30),
    UPDATE_COORDINATOR_TX: datetime.timedelta(seconds=30)
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

        self._authenticated = False

        self.api = KeeneticAPI(
            scheme=PROTOCOL_HTTP, #config_entry.data[CONF_PROTOCOL],
            host=config_entry.data[CONF_HOST],
            port=config_entry.data[CONF_PORT],
            ssl_validation=False #config_entry.data[CONF_VERIFY_SSL]
        )


    async def async_setup(self) -> None:
        """Create update coordinators to fetch data using Keenetic api."""
        await self._auth()

        # Create update coordinators
        update_methods = {
            UPDATE_COORDINATOR_FW: partial(self._fetch_data, self.api.get_system_fw),
            UPDATE_COORDINATOR_WAN_STATUS: partial(self._fetch_data, self.api.get_internet_status),
            UPDATE_COORDINATOR_CLIENTS: partial(self._fetch_data, self.api.get_network_clients),
            UPDATE_COORDINATOR_STAT: self._get_system_stat,
            UPDATE_COORDINATOR_RX: self._get_network_clients_rx,
            UPDATE_COORDINATOR_TX: self._get_network_clients_tx
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

        # Internet speed
        wan_interface_name = \
            self.update_coordinators[UPDATE_COORDINATOR_WAN_STATUS].\
                data.get("gateway", {}).get("interface")

        if wan_interface_name:
            self.update_coordinators[UPDATE_COORDINATOR_WAN_SPEED] = \
                DataUpdateCoordinator(
                    self.hass, _LOGGER,
                    name=f"{UPDATE_COORDINATOR_WAN_SPEED}",
                    update_method=partial(self._get_interface_rx,
                                          name=wan_interface_name),
                    update_interval=UPDATE_INTERVALS[UPDATE_COORDINATOR_WAN_SPEED]
                )
            await self.update_coordinators[UPDATE_COORDINATOR_WAN_SPEED].\
                async_config_entry_first_refresh()

        # Signaling
        self.tracked_network_client_ids = list(
            self.get_network_clients_data().keys()
        )

        ## New network clients signaling
        @callback
        def _new_clients_listener() -> None:
            current_client_ids = set(self.get_network_clients_data().keys())
            new_clients_ids = current_client_ids.\
                difference(self.tracked_network_client_ids)
            self.tracked_network_client_ids.extend(new_clients_ids)

            if new_clients_ids:
                async_dispatcher_send(self.hass, SIGNAL_NEW_NETWORK_CLIENTS, new_clients_ids)

        self.config_entry.async_on_unload(
            self.update_coordinators[UPDATE_COORDINATOR_CLIENTS].\
                async_add_listener(_new_clients_listener)
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


    async def _get_system_stat(self) -> dict:
        """Fetch Keenetic system statistics."""
        data = await self._fetch_data(self.api.get_system_stat, try_auth=True)

        memory_use = data["memtotal"] - data["memfree"]
        data["memory_usage"] = round(
            memory_use / data["memtotal"] * 100, 0
        )

        return data


    async def _get_interface_rx(self, name: str) -> dict:
        """Get Router interface speed."""
        data = await self._fetch_data(partial(self.api.get_interface_speed,
                                              name=name, direction="rxspeed"))
        return {"rxspeed": data["data"][0]["v"]}


    async def _get_network_clients_rx(self) -> dict:
        """Fetch Network clients RX speed."""
        return await self._fetch_data(partial(self.api.get_clients_speed,
                                              direction="rxspeed"))


    async def _get_network_clients_tx(self) -> dict:
        """Fetch Network clients RX speed."""
        return await self._fetch_data(partial(self.api.get_clients_speed,
                                              direction="txspeed"))


    async def change_client_registered_setting(self, mac: str,
                                               name: str | None = None,
                                               register: bool = True) -> None:
        """Register/Unregister Network client."""
        if register:
            await self._fetch_data(self.api.register_client,
                                 mac=mac, name=name)
        else:
            await self._fetch_data(self.api.unregister_client,
                                 mac=mac)


    async def change_client_internet_access_setting(self, mac: str,
                                                    permit: bool = True) -> None:
        """Permit/Deny Network client Internet access."""
        if permit:
            await self._fetch_data(self.api.permit_client_internet_access,
                                 mac=mac)
        else:
            await self._fetch_data(self.api.deny_client_internet_access,
                                 mac=mac)


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
    def device_identifier(self) -> tuple:
        """Keenetic router identifier for DeviceInfo."""
        return (DOMAIN, self.unique_id)


    @property
    def device_info(self) -> DeviceInfo:
        """Return Keenetic router DeviceInfo."""
        fw_data = self.update_coordinators[UPDATE_COORDINATOR_FW].data
        return DeviceInfo(
            identifiers={self.device_identifier},
            manufacturer=fw_data["manufacturer"],
            model=fw_data["model"],
            sw_version=fw_data["title"],
            hw_version=fw_data["hw_version"],
            serial_number=self.config_entry.data["serial"],
            name=f"{self.config_entry.data[CONF_NAME]}"
        )


    def get_network_client_device_info(self, client_id) -> DeviceInfo:
        """Return Network client DeviceInfo."""
        client_data = self.get_network_clients_data()[client_id]
        client_name = client_data["mac"]
        if client_data["hostname"]:
            client_name = client_data["hostname"]
        if client_data["name"]:
            client_name = client_data["name"]

        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.unique_id}-{client_id}")},
            name=client_name,
            via_device=self.device_identifier
        )
