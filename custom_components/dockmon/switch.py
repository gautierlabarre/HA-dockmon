"""Switch platform for DockMon – start/stop containers."""
from __future__ import annotations

import logging
from functools import partial
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import CONTAINER_STATE_RUNNING, DOMAIN
from .coordinator import DockmonCoordinator
from .entity import DockmonContainerEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: DockmonCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_keys: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        new = [
            DockmonContainerSwitch(coordinator, c)
            for key, c in coordinator.data["containers_by_key"].items()
            if key not in known_keys
        ]
        if not new:
            return
        known_keys.update(e.key for e in new)
        for entity in new:
            # Let a container that was pruned and later comes back be re-added.
            entity.async_on_remove(partial(known_keys.discard, entity.key))
        async_add_entities(new)

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class DockmonContainerSwitch(DockmonContainerEntity, SwitchEntity):
    """Represents a Docker container as a switch (running = on)."""

    _attr_name = None  # Use device name as entity name
    _attr_icon = "mdi:docker"

    def __init__(self, coordinator: DockmonCoordinator, container: dict) -> None:
        super().__init__(coordinator, container)
        self._attr_unique_id = f"{DOMAIN}_{self.key}_switch"

    @property
    def is_on(self) -> bool:
        c = self._container
        return c is not None and c.get("state") == CONTAINER_STATE_RUNNING

    @property
    def extra_state_attributes(self) -> dict:
        c = self._container or {}
        return {
            "container_id": c.get("id"),
            "image": c.get("image"),
            "host": self._host.get("name", self._host_id),
            "status": c.get("status"),
            "ports": c.get("ports", []),
            "restart_policy": c.get("restart_policy"),
        }

    async def _async_do(self, action: str) -> None:
        container_id = self._container_id
        if container_id is None:
            raise HomeAssistantError(
                f"Container '{self._container_name}' is no longer reported by DockMon"
            )
        await self.coordinator.async_container_action(self._host_id, container_id, action)
        await self.coordinator.async_request_refresh()

        async def _refresh_again(_now) -> None:
            """Docker takes a moment to settle; poll once more after the fact.

            Must stay a coroutine function: `async_call_later` runs a plain
            callable in the executor, and touching hass from there is unsafe.
            """
            await self.coordinator.async_request_refresh()

        async_call_later(self.hass, 4, _refresh_again)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_do("start")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_do("stop")
