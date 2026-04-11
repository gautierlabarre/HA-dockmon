"""DockMon integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_API_KEY, CONF_URL, DOMAIN, PLATFORMS
from .coordinator import DockmonCoordinator

_LOGGER = logging.getLogger(__name__)


def _register_host_devices(hass: HomeAssistant, entry: ConfigEntry, coordinator: DockmonCoordinator) -> None:
    """Register each Docker host as a HA device so containers appear under them."""
    dev_reg = dr.async_get(hass)
    for host in coordinator.data["hosts"].values():
        dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, host["id"])},
            name=host["name"],
            manufacturer="Docker",
            model=host.get("os_version", ""),
            sw_version=host.get("docker_version", ""),
            configuration_url=coordinator.url,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DockMon from a config entry."""
    coordinator = DockmonCoordinator(
        hass,
        url=entry.data[CONF_URL],
        api_key=entry.data[CONF_API_KEY],
    )
    await coordinator.async_config_entry_first_refresh()
    _register_host_devices(hass, entry, coordinator)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
