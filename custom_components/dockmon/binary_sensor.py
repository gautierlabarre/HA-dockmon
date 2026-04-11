"""Binary sensor platform for DockMon – container running state."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONTAINER_STATE_RUNNING, DOMAIN
from .coordinator import DockmonCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: DockmonCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_ids: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        new = [c for c in coordinator.data["containers"] if c["id"] not in known_ids]
        if new:
            known_ids.update(c["id"] for c in new)
            async_add_entities([DockmonContainerBinarySensor(coordinator, c) for c in new])

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class DockmonContainerBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor: True when container is running."""

    _attr_has_entity_name = True
    _attr_name = "Running"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: DockmonCoordinator, container: dict) -> None:
        super().__init__(coordinator)
        self._container_id = container["id"]
        self._host_id = container["host_id"]
        self._attr_unique_id = f"{DOMAIN}_{self._host_id}_{self._container_id}_running"

    @property
    def _container(self) -> dict | None:
        for c in self.coordinator.data["containers"]:
            if c["id"] == self._container_id:
                return c
        return None

    @property
    def device_info(self) -> DeviceInfo:
        c = self._container or {}
        host = self.coordinator.data["hosts"].get(self._host_id, {})
        host_name = host.get("name", "unknown")
        container_name = c.get("name", self._container_id)
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._host_id}_{self._container_id}")},
            name=f"{host_name} {container_name}",
        )

    @property
    def available(self) -> bool:
        return self._container is not None

    @property
    def is_on(self) -> bool:
        c = self._container
        return c is not None and c.get("state") == CONTAINER_STATE_RUNNING
