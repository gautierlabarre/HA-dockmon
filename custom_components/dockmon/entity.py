"""Shared entity base for DockMon container entities."""
from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DockmonCoordinator, container_key, container_name


class DockmonContainerEntity(CoordinatorEntity[DockmonCoordinator]):
    """Base class for entities backed by a single Docker container."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DockmonCoordinator, container: dict) -> None:
        super().__init__(coordinator)
        self._host_id = container["host_id"]
        self._container_name = container_name(container)
        self.key = container_key(container)

    @property
    def _container(self) -> dict | None:
        return self.coordinator.data["containers_by_key"].get(self.key)

    @property
    def _container_id(self) -> str | None:
        """Current Docker ID – re-read every time, it changes on recreation."""
        c = self._container
        return c["id"] if c else None

    @property
    def _host(self) -> dict:
        return self.coordinator.data["hosts"].get(self._host_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        image = (self._container or {}).get("image") or ""
        return DeviceInfo(
            identifiers={(DOMAIN, self.key)},
            name=f"{self._host.get('name') or 'unknown'} {self._container_name}",
            manufacturer="Docker",
            model=image,
            sw_version=image.split(":")[-1] if ":" in image else None,
            via_device=(DOMAIN, self._host_id),
            configuration_url=self.coordinator.url,
        )

    @property
    def available(self) -> bool:
        return super().available and self._container is not None
