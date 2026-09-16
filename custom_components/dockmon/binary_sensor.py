"""Binary sensor platform for DockMon – container running state."""
from __future__ import annotations

from functools import partial

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONTAINER_STATE_RUNNING, DOMAIN
from .coordinator import DockmonCoordinator
from .entity import DockmonContainerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: DockmonCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_keys: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        new = [
            DockmonContainerBinarySensor(coordinator, c)
            for key, c in coordinator.data["containers_by_key"].items()
            if key not in known_keys
        ]
        if not new:
            return
        known_keys.update(e.key for e in new)
        for entity in new:
            entity.async_on_remove(partial(known_keys.discard, entity.key))
        async_add_entities(new)

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class DockmonContainerBinarySensor(DockmonContainerEntity, BinarySensorEntity):
    """Binary sensor: True when container is running."""

    _attr_name = "Running"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: DockmonCoordinator, container: dict) -> None:
        super().__init__(coordinator, container)
        self._attr_unique_id = f"{DOMAIN}_{self.key}_running"

    @property
    def is_on(self) -> bool:
        c = self._container
        return c is not None and c.get("state") == CONTAINER_STATE_RUNNING
