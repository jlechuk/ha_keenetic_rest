# noqa: D104

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .router import KeeneticAuthFailed, KeeneticRouter

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.BINARY_SENSOR,
    Platform.SWITCH
]


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Setup up Keenetic from config entry."""

    router = KeeneticRouter(
        hass=hass,
        config_entry=config_entry
    )
    try:
        await router.async_setup()
    except (aiohttp.ClientError, TimeoutError) as ex:
        await router.close()
        raise ConfigEntryNotReady(
            f"Failed to setup '{config_entry[CONF_NAME]}': {ex}"
        ) from ex
    except KeeneticAuthFailed:
        await router.close()
        raise ConfigEntryAuthFailed(  # noqa: B904
            f"Credentials expired for '{config_entry.data[CONF_NAME]}'"
        )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = router

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Unload Keenetic config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    if unload_ok:
        router: KeeneticRouter = hass.data[DOMAIN][config_entry.entry_id]
        await router.close()
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_entry: dr.DeviceEntry
) -> bool:
    """Remove Keentic Router or Network client device manually."""
    return any(
        identifier
        for identifier in device_entry.identifiers
        if identifier[0] == DOMAIN
        and len(identifier) > 2
        and identifier[2] == "network_client"
    )
