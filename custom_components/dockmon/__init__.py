"""DockMon integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .config_flow import unique_id_for
from .const import (
    CONF_API_KEY,
    CONF_URL,
    CONF_VERIFY_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import DockmonCoordinator, container_key

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


def _migrate_id_keyed_devices(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: DockmonCoordinator
) -> None:
    """Re-key devices that were identified by their (unstable) Docker container ID.

    Up to 1.0.0 a device was identified by `{host_id}_{container_id}`. Since the
    Docker ID changes on every container recreation, each recreation orphaned the
    previous device. Move the still-existing containers onto their name-based key
    so their history survives; the orphans left behind are dropped by
    `_prune_stale_devices`.
    """
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    old_to_new = {
        f"{c['host_id']}_{c['id']}": container_key(c)
        for c in coordinator.data["containers"]
    }

    devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    # Identifiers are only unique *within* a config entry, so track the ones this
    # entry already owns instead of doing a registry-wide `async_get_device` lookup.
    known_ids = {i for device in devices for d, i in device.identifiers if d == DOMAIN}

    for device in devices:
        old_id = next(
            (i for d, i in device.identifiers if d == DOMAIN and i in old_to_new), None
        )
        if old_id is None:
            continue
        new_id = old_to_new[old_id]
        if new_id in known_ids:
            continue  # already migrated; this one is a duplicate, prune will take it

        for ent in er.async_entries_for_device(
            ent_reg, device.id, include_disabled_entities=True
        ):
            new_unique_id = ent.unique_id.replace(old_id, new_id, 1)
            if new_unique_id == ent.unique_id:
                continue
            if ent_reg.async_get_entity_id(ent.domain, DOMAIN, new_unique_id):
                ent_reg.async_remove(ent.entity_id)
            else:
                ent_reg.async_update_entity(ent.entity_id, new_unique_id=new_unique_id)

        dev_reg.async_update_device(device.id, new_identifiers={(DOMAIN, new_id)})
        known_ids.discard(old_id)
        known_ids.add(new_id)
        _LOGGER.info("Re-keyed DockMon device %s -> %s", old_id, new_id)


def _prune_stale_devices(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: DockmonCoordinator
) -> None:
    """Remove devices for hosts/containers DockMon no longer reports."""
    if not coordinator.last_update_success:
        return

    data = coordinator.data
    host_ids = set(data["hosts"])
    container_keys = set(data["containers_by_key"])
    # A host reporting zero containers is far more likely unreachable than truly
    # empty, so leave its devices alone rather than wiping them on a bad poll.
    hosts_with_containers = {c["host_id"] for c in data["containers"]}

    dev_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        ids = {i for d, i in device.identifiers if d == DOMAIN}
        if ids & host_ids or ids & container_keys:
            continue
        owner = next(
            (h for h in host_ids if any(i.startswith(f"{h}_") for i in ids)), None
        )
        if owner is not None and owner not in hosts_with_containers:
            continue  # host is present but silent – don't assume it's empty
        _LOGGER.info("Removing stale DockMon device %s (%s)", device.name, ids)
        dev_reg.async_remove_device(device.id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an entry created by an older version of the integration."""
    if entry.version > 2:
        return False  # downgrade: let HA report the entry as unusable

    if entry.version == 1:
        # v1 always talked to DockMon with TLS verification off. Keep it that way
        # for existing entries — turning it on here would break every self-signed
        # setup on upgrade. New entries verify by default; this can be flipped by
        # removing and re-adding the integration.
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_VERIFY_SSL: False},
            unique_id=unique_id_for(entry.data[CONF_URL]),
            version=2,
        )
        _LOGGER.info("Migrated DockMon config entry %s to version 2", entry.title)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DockMon from a config entry."""
    coordinator = DockmonCoordinator(
        hass,
        url=entry.data[CONF_URL],
        api_key=entry.data[CONF_API_KEY],
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
        config_entry=entry,
    )
    await coordinator.async_config_entry_first_refresh()

    _migrate_id_keyed_devices(hass, entry, coordinator)
    _register_host_devices(hass, entry, coordinator)
    _prune_stale_devices(hass, entry, coordinator)

    @callback
    def _sync_registry() -> None:
        _register_host_devices(hass, entry, coordinator)
        _prune_stale_devices(hass, entry, coordinator)

    entry.async_on_unload(coordinator.async_add_listener(_sync_registry))

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
