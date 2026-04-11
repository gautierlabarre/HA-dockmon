"""Switch platform for DockMon – start/stop containers."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONTAINER_STATE_RUNNING, DOMAIN
from .coordinator import DockmonCoordinator

_LOGGER = logging.getLogger(__name__)


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
            async_add_entities([DockmonContainerSwitch(coordinator, c) for c in new])

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class DockmonContainerSwitch(CoordinatorEntity, SwitchEntity):
    """Represents a Docker container as a switch (running = on)."""

    _attr_has_entity_name = True
    _attr_name = None  # Use device name as entity name

    def __init__(self, coordinator: DockmonCoordinator, container: dict) -> None:
        super().__init__(coordinator)
        self._container_id = container["id"]
        self._host_id = container["host_id"]
        self._attr_unique_id = f"{DOMAIN}_{self._host_id}_{self._container_id}_switch"

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
            model=c.get("image", ""),
            manufacturer="Docker",
            sw_version=c.get("image", "").split(":")[-1] if c.get("image") else None,
            via_device=(DOMAIN, self._host_id),
            configuration_url=self.coordinator.url,
        )

    @property
    def available(self) -> bool:
        return self._container is not None

    @property
    def is_on(self) -> bool:
        c = self._container
        return c is not None and c.get("state") == CONTAINER_STATE_RUNNING

    @property
    def icon(self) -> str:
        return "mdi:docker" if self.is_on else "mdi:docker"

    @property
    def extra_state_attributes(self) -> dict:
        c = self._container or {}
        host = self.coordinator.data["hosts"].get(self._host_id, {})
        return {
            "container_id": c.get("id"),
            "image": c.get("image"),
            "host": host.get("name", self._host_id),
            "status": c.get("status"),
            "ports": c.get("ports", []),
            "restart_policy": c.get("restart_policy"),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_container_action(self._host_id, self._container_id, "start")
        await self.coordinator.async_request_refresh()
        async_call_later(
            self.hass,
            4,
            lambda _: self.hass.async_create_task(self.coordinator.async_request_refresh()),
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_container_action(self._host_id, self._container_id, "stop")
        await self.coordinator.async_request_refresh()
        async_call_later(
            self.hass,
            4,
            lambda _: self.hass.async_create_task(self.coordinator.async_request_refresh()),
        )
