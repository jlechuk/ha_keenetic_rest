"""Keenetic API client."""

import hashlib
import logging

from aiohttp import ClientSession, ClientTimeout, CookieJar

from .const import CONNECTION_TIMEOUT

_LOGGER = logging.getLogger(__name__)

# TODO:
# - SSL Validation
# - Bad Request in auth

class KeeneticAPI:
    """API client for Keentic router."""

    def __init__(  # noqa: D107
        self,
        scheme: str,
        host: str,
        port: str,
        ssl_validation: bool
    ) -> None:
        self.base_url = f"{scheme}://{host}:{port}"
        self._session = ClientSession(
            base_url=self.base_url,
            timeout=ClientTimeout(total=CONNECTION_TIMEOUT),
            cookie_jar=CookieJar(unsafe=True)
        )


    async def close(self) -> None:
        """Close session."""
        await self._session.close()


    async def auth(self, username: str, password: str) -> bool:
        """Authenticate."""

        async with self._session.get(url="auth") as resp:
            if resp.status == 200:
                # Already authenticated
                return True
            if resp.status == 401:
                token = resp.headers['X-NDM-Challenge']
                realm = resp.headers['X-NDM-Realm']
            else:
                return False

        md5 = hashlib.md5(f'{username}:{realm}:{password}'.encode())
        sha = hashlib.sha256(f'{token}{md5.hexdigest()}'.encode())

        async with self._session.post(
            url="auth",
            json={
                "login": username,
                "password": sha.hexdigest()
            }
        ) as resp:
            if resp.status == 200:
                self._session.cookie_jar.update_cookies(resp.cookies)
                return True

            return False


    async def _get_data(
            self,
            url: str,
            params: dict | None = None
    ) -> list | dict | None:
        async with self._session.get(url=url, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            resp.raise_for_status()
            return None


    async def _post_data(
            self,
            url: str,
            params: dict | None = None
    ) -> list | dict | None:
        async with self._session.post(url=url, json=params) as resp:
            if resp.status == 200:
                return await resp.json()
            resp.raise_for_status()
            return None


    async def get_system_info(self) -> list | dict:
        """Get system information."""
        return await self._get_data("rci/show/defaults")


    async def get_system_fw(self) -> list | dict:
        """Get firmware version."""
        return await self._get_data("rci/show/version")


    async def get_system_stats(self) -> list | dict:
        """Get system statistics."""
        return await self._get_data("rci/show/system")


    async def get_internet_status(self) -> list | dict:
        """Get Internet status."""
        return await self._get_data("rci/show/internet/status")


    async def get_interface_stats(self, name: str) -> list | dict:
        """Get interface statistics."""
        return await self._get_data(
            url="rci/show/interface/stat",
            params={"name": name}
        )


    async def get_interface_speed(self, name: str, direction: str,
                                  detail: int = 1) -> list | dict:
        """Get interface speed.

        Args:
            name: interface name
            direction: "rxspeed", "txspeed".
            detail: 0 - 3s, 1 - 60s, 2 - 180s, 3 - 1440s
        """
        return await self._get_data(
            url="rci/show/interface/rrd",
            params={"name": name, "attribute": direction, "detail": detail}
        )


    async def get_network_clients(self) -> list | dict:
        """Get connected network clients."""
        data = (await self._get_data("rci/show/ip/hotspot"))["host"]
        return {el["mac"].lower(): el for el in data if "mac" in el}


    async def get_clients_speed(self, direction: str,
                                detail: int = 0) -> list:
        """Get network clients speed.

        Args:
            direction: "rxspeed", "txspeed"
            detail: 0 - 3s, 1 - 60s, 2 - 180s, 3 - 1440s
        """
        data = (await self._get_data(
            url="rci/show/ip/hotspot/summary",
            params={'attribute': direction, "detail": detail}
        ))["host"]

        return {el["mac"].lower(): el for el in data if "mac" in el}


    async def set_client_registered_setting(self, register: bool, mac: str,
                                            name: str | None = None) -> list | dict:
        """Register/Uregister network client."""
        params = {"mac": mac}
        if register:
            params["name"] = name
        else:
            params["no"] = True

        return await self._post_data(url="rci/known/host", params=params)


    async def set_client_internet_access_setting(self, permit: bool,
                                                 mac: str) -> list | dict:
        """Permit/Deny network client internet access."""
        access = "permit" if permit else "deny"
        return await self._post_data(
            url="rci/ip/hotspot/host",
            params={"mac": mac, "access": access}
        )
