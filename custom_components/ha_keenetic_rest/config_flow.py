# noqa: D100

import logging
from typing import Any, Mapping  # noqa: UP035

from aiohttp import ClientError, InvalidURL
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    #    CONF_PROTOCOL,
    CONF_USERNAME,
    #    CONF_VERIFY_SSL,
)
from homeassistant.helpers import config_validation as cv

#from homeassistant.helpers import selector
from .api import KeeneticAPI
from .const import (
    ABORT_WRONG_ROUTER,
    DEFAULT_HOST,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_CREDENTIALS,
    ERROR_INVALID_URL,
    ERROR_UNKNOWN,
    ERROR_UNSUPPORTED,
    PROTOCOL_HTTP,
    # PROTOCOL_HTTPS,
)
from .router import KeeneticAuthFailed

_LOGGER = logging.getLogger(__name__)


async def validate_credentials(user_input: dict[str, Any]) -> str:
    """Validate user credentials and return Keenetic router's serial number."""
    api = KeeneticAPI(
        scheme=PROTOCOL_HTTP, #user_input[CONF_PROTOCOL],
        host=user_input[CONF_HOST],
        port=user_input[CONF_PORT],
        ssl_validation=False #user_input[CONF_VERIFY_SSL]
    )

    try:
        if await api.auth(
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD]
        ):
            return (await api.get_system_info()).get("serial", None)
        else:  # noqa: RET505
            raise KeeneticAuthFailed(error_code=ERROR_INVALID_CREDENTIALS)
    except InvalidURL as ex:
        _LOGGER.error("Invalid url: %s", api.base_url)
        raise KeeneticAuthFailed(error_code=ERROR_INVALID_URL) from ex
    except (TimeoutError, ClientError) as ex:
        _LOGGER.error("Failed to connect. %s", ex)
        raise KeeneticAuthFailed(error_code=ERROR_CANNOT_CONNECT) from ex
    finally:
        await api.close()


class KeenticConfigFlow(ConfigFlow, domain=DOMAIN):  # noqa: D101
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                serial = await validate_credentials(user_input)
            except KeeneticAuthFailed as ex:
                errors["base"] = ex.error_code
            except Exception as ex:  # noqa: BLE001
                _LOGGER.error("Unknown error. %s", ex)
                errors["base"] = ERROR_UNKNOWN

            if not errors:
                if not serial:
                    return self.async_abort(reason=ERROR_UNSUPPORTED)

                await self.async_set_unique_id(f"{DOMAIN} {serial}")
                self._abort_if_unique_id_configured()

                user_input["serial"] = serial
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input
                )

        user_input = user_input if user_input else {}

        #! In case of adding Protocol type and SSL validation also edit router.py
        schema = {
            vol.Required(CONF_NAME,
                         default=user_input.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(CONF_HOST,
                         default=user_input.get(CONF_HOST, DEFAULT_HOST)): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_PORT,
                         default=user_input.get(CONF_PORT, DEFAULT_PORT)): cv.port,
            # vol.Required(
            #     CONF_PROTOCOL,
            #     default=user_input.get(CONF_PROTOCOL, PROTOCOL_HTTP)
            # ): selector.SelectSelector(
            #     selector.SelectSelectorConfig(options=[
            #         PROTOCOL_HTTP,
            #         PROTOCOL_HTTPS
            #     ])
            # ),
            # vol.Required(CONF_VERIFY_SSL,
            #              default=user_input.get(CONF_VERIFY_SSL, False)): bool
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            errors=errors
        )


    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauthentication."""
        self._config_data = {
            CONF_HOST: entry_data[CONF_HOST],
            CONF_PORT: entry_data[CONF_PORT],
            # CONF_PROTOCOL: entry_data[CONF_PROTOCOL],
            # CONF_VERIFY_SSL: entry_data[CONF_VERIFY_SSL]
        }
        return await self.async_step_reauth_confirm()


    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauthentication dialog."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input.update(self._config_data)
            try:
                serial = await validate_credentials(user_input)
            except KeeneticAuthFailed as ex:
                errors["base"] = ex.error_code
            except Exception as ex:  # noqa: BLE001
                _LOGGER.error("Unknown error. %s", ex)
                errors["base"] = ERROR_UNKNOWN

            if not errors:
                await self.async_set_unique_id(f"{DOMAIN} {serial}")
                self._abort_if_unique_id_mismatch(reason=ABORT_WRONG_ROUTER)

                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD]
                    }
                )

        schema = {
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
        }

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(schema),
            errors=errors
        )
