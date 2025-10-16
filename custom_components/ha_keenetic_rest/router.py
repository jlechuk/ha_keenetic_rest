"""Setup Keentic router."""

import datetime
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
)

_LOGGER = logging.getLogger(__name__)


UPDATE_INTERVALS = {
    UPDATE_COORDINATOR_FW: datetime.timedelta(minutes=60),
    UPDATE_COORDINATOR_STAT: datetime.timedelta(seconds=30),
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
            UPDATE_COORDINATOR_FW: self._get_system_fw,
            UPDATE_COORDINATOR_STAT: self._get_system_stat,
            UPDATE_COORDINATOR_CLIENTS: self._get_network_clients,
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

        # Signaling
        clients_coordinator: DataUpdateCoordinator = \
            self.update_coordinators[UPDATE_COORDINATOR_CLIENTS]
        self.tracked_network_client_ids = list(clients_coordinator.data.keys())

        ## New network clients signaling
        @callback
        def _new_clients_listener() -> None:
            current_client_ids = list(clients_coordinator.data.keys())
            new_clients_ids = set(current_client_ids).\
                difference(self.tracked_network_client_ids)
            self.tracked_network_client_ids = current_client_ids

            if new_clients_ids:
                async_dispatcher_send(self.hass, SIGNAL_NEW_NETWORK_CLIENTS, new_clients_ids)

        self.config_entry.async_on_unload(
            clients_coordinator.async_add_listener(_new_clients_listener)
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


    async def _get_data(self, api_method: callable, try_auth: bool = False) -> dict:
        try:
            if not self._authenticated and try_auth:
                try:
                    await self._auth()
                except KeeneticAuthFailed:
                    raise ConfigEntryAuthFailed(  # noqa: B904
                        f"Credentials expired for {self.config_entry.data[CONF_NAME]}"
                    )

            if self._authenticated:
                return await api_method()

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


    async def _get_system_fw(self) -> dict:
        """Fetch Keenetic firmware version."""
        return await self._get_data(self.api.get_system_fw)


    async def _get_system_stat(self) -> dict:
        """Fetch Keenetic system statistics."""
        data = await self._get_data(self.api.get_system_stat, try_auth=True)

        memory_use = data["memtotal"] - data["memfree"]
        data["memory_usage"] = round(
            memory_use / data["memtotal"] * 100, 0
        )

        return data


    async def _get_network_clients(self, _ = None) -> None:
        """Fetch Keenetic network clients."""
        data = await self._get_data(self.api.get_network_clients)

        network_clients_data = {}
        for item in data:
            if 'mac' in item:
                network_clients_data[item['mac'].lower()] = item

        return network_clients_data


    async def _get_network_clients_rx(self) -> dict:
        """Fetch Keenetic network clients RX speed."""
        data = await self._get_data(self.api.get_clients_rx_speed)

        net_clients = {}
        for item in data:
            if 'mac' in item:
                net_clients[item['mac'].lower()] = item

        return net_clients


    async def _get_network_clients_tx(self) -> dict:
        """Fetch Keenetic network clients RX speed."""
        data = await self._get_data(self.api.get_clients_tx_speed)

        net_clients = {}
        for item in data:
            if 'mac' in item:
                net_clients[item['mac'].lower()] = item

        return net_clients


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


    def network_client_device_info(self, client_id) -> DeviceInfo:
        """Return Network client DeviceInfo."""
        network_clients = self.update_coordinators[UPDATE_COORDINATOR_CLIENTS].data
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.unique_id}-{client_id}")},
            name=network_clients[client_id]["name"],
            via_device=self.device_identifier
        )
