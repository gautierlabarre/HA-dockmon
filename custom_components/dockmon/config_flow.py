"""Config flow for DockMon integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_KEY, CONF_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_API_KEY): str,
    }
)


class DockmonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle DockMon config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            api_key = user_input[CONF_API_KEY]

            try:
                # verify_ssl=False tolerates self-signed / local certs
                session = async_get_clientsession(self.hass, verify_ssl=False)
                async with session.get(
                    f"{url}/api/hosts",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    _LOGGER.debug("DockMon /api/hosts returned HTTP %s", resp.status)
                    if resp.status in (401, 403):
                        errors["base"] = "invalid_auth"
                    elif resp.status != 200:
                        errors["base"] = "cannot_connect"
                    else:
                        hosts = await resp.json()
                        host_names = ", ".join(h["name"] for h in hosts)

            except aiohttp.ClientConnectorError as err:
                _LOGGER.error("DockMon connection error: %s", err)
                errors["base"] = "cannot_connect"
            except aiohttp.ClientError as err:
                _LOGGER.error("DockMon client error: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during DockMon setup")
                errors["base"] = "unknown"

            if not errors:
                await self.async_set_unique_id(f"dockmon_{url}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"DockMon ({host_names})",
                    data={CONF_URL: url, CONF_API_KEY: api_key},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
