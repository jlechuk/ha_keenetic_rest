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


    async def get_system_stat(self) -> list | dict:
        """Get system statistics."""
        return await self._get_data("rci/show/system")


    async def get_network_clients(self) -> list | dict:
        """Get connected network clients."""
        return (await self._get_data("rci/show/ip/hotspot"))["host"]


    async def get_clients_rx_speed(self) -> list | dict:
        """Get network clients RX speed."""
        return (await self._get_data(
            url="rci/show/ip/hotspot/summary",
            params={'attribute': "rxspeed", "detail": 0}
        ))["host"]


    async def get_clients_tx_speed(self) -> list | dict:
        """Get network clients TX speed."""
        return (await self._get_data(
            url="rci/show/ip/hotspot/summary",
            params={'attribute': "txspeed", "detail": 0}
        ))["host"]


    async def register_network_client(self, mac: str, name: str) -> list | dict:
        """Register network client."""
        return await self._post_data(
            url="rci/known/host",
            params={"name": name, "mac": mac}
        )


    async def unregister_network_client(self, mac: str) -> list | dict:
        """Unregister network client."""
        return await self._post_data(
            url="rci/known/host",
            params={"mac": mac, "no": True}
        )
