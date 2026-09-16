"""Config flow for DockMon integration."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_API_KEY,
    CONF_URL,
    CONF_VERIFY_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .coordinator import AUTH_STATUSES, DockmonCoordinator

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
    }
)

STEP_REAUTH_DATA_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})


def normalize_url(url: str) -> str:
    """Normalise a user-typed URL so the same instance yields the same unique id.

    Scheme and host are case-insensitive per RFC 3986; the path is not, so it is
    left alone beyond dropping the trailing slash.
    """
    parts = urlsplit(url.strip().rstrip("/"))
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, "", "")
    )


def unique_id_for(url: str) -> str:
    """Config entry unique id for a DockMon instance."""
    return f"dockmon_{normalize_url(url)}"


async def async_validate(
    hass: HomeAssistant, url: str, api_key: str, verify_ssl: bool
) -> tuple[list[dict], dict[str, str]]:
    """Return (hosts, errors) for the given credentials."""
    coordinator = DockmonCoordinator(
        hass, url=url, api_key=api_key, verify_ssl=verify_ssl
    )
    try:
        return await coordinator.async_validate_connection(), {}
    except aiohttp.ClientResponseError as err:
        _LOGGER.debug("DockMon /api/hosts returned HTTP %s", err.status)
        if err.status in AUTH_STATUSES:
            return [], {"base": "invalid_auth"}
        return [], {"base": "cannot_connect"}
    except aiohttp.ClientSSLError as err:
        _LOGGER.error("DockMon TLS error: %s", err)
        return [], {"base": "invalid_certificate"}
    except (aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.error("DockMon connection error: %s", err)
        return [], {"base": "cannot_connect"}
    except Exception:  # noqa: BLE001 - surfaced to the user as "unknown"
        _LOGGER.exception("Unexpected error talking to DockMon")
        return [], {"base": "unknown"}


class DockmonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle DockMon config flow."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url = normalize_url(user_input[CONF_URL])
            api_key = user_input[CONF_API_KEY]
            verify_ssl = user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)

            hosts, errors = await async_validate(self.hass, url, api_key, verify_ssl)

            if not errors:
                await self.async_set_unique_id(unique_id_for(url))
                self._abort_if_unique_id_configured()
                host_names = ", ".join(h["name"] for h in hosts)
                return self.async_create_entry(
                    title=f"DockMon ({host_names})",
                    data={
                        CONF_URL: url,
                        CONF_API_KEY: api_key,
                        CONF_VERIFY_SSL: verify_ssl,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Triggered when DockMon rejects the stored API key."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask for a fresh API key, keeping the rest of the entry untouched."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            _hosts, errors = await async_validate(
                self.hass,
                entry.data[CONF_URL],
                api_key,
                entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data={**entry.data, CONF_API_KEY: api_key}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"url": entry.data[CONF_URL]},
        )
