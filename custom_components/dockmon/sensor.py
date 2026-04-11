"""Sensor platform for DockMon – CPU%, memory%, status."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfInformation
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DockmonCoordinator


@dataclass
class DockmonSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[dict], float | str | None] = lambda c: None


CONTAINER_SENSORS: tuple[DockmonSensorEntityDescription, ...] = (
    DockmonSensorEntityDescription(
        key="cpu_percent",
        name="CPU",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cpu-64-bit",
        value_fn=lambda c: round(c.get("cpu_percent") or 0, 1),
    ),
    DockmonSensorEntityDescription(
        key="memory_percent",
        name="Memory",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
        value_fn=lambda c: round(c.get("memory_percent") or 0, 1),
    ),
    DockmonSensorEntityDescription(
        key="memory_usage",
        name="Memory Usage",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
        value_fn=lambda c: round((c.get("memory_usage") or 0) / 1024 / 1024, 1),
    ),
    DockmonSensorEntityDescription(
        key="state",
        name="State",
        icon="mdi:docker",
        value_fn=lambda c: c.get("state"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: DockmonCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_container_ids: set[str] = set()
    known_host_ids: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        entities: list = []

        new_hosts = [
            (hid, h)
            for hid, h in coordinator.data["hosts"].items()
            if hid not in known_host_ids
        ]
        if new_hosts:
            known_host_ids.update(hid for hid, _ in new_hosts)
            entities.extend(
                DockmonHostSensor(coordinator, hid) for hid, _ in new_hosts
            )

        new_containers = [
            c for c in coordinator.data["containers"] if c["id"] not in known_container_ids
        ]
        if new_containers:
            known_container_ids.update(c["id"] for c in new_containers)
            entities.extend(
                DockmonContainerSensor(coordinator, c, desc)
                for c in new_containers
                for desc in CONTAINER_SENSORS
            )

        if entities:
            async_add_entities(entities)

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class DockmonHostSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the number of running containers on a host."""

    _attr_has_entity_name = True
    _attr_name = "Running Containers"
    _attr_icon = "mdi:docker"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: DockmonCoordinator, host_id: str) -> None:
        super().__init__(coordinator)
        self._host_id = host_id
        self._attr_unique_id = f"{DOMAIN}_{host_id}_running_containers"

    @property
    def device_info(self) -> DeviceInfo:
        host = self.coordinator.data["hosts"].get(self._host_id, {})
        return DeviceInfo(
            identifiers={(DOMAIN, self._host_id)},
            name=host.get("name", self._host_id),
        )

    @property
    def native_value(self) -> int:
        return sum(
            1
            for c in self.coordinator.data["containers"]
            if c["host_id"] == self._host_id and c.get("state") == "running"
        )


class DockmonContainerSensor(CoordinatorEntity, SensorEntity):
    """A sensor for a container metric."""

    entity_description: DockmonSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DockmonCoordinator,
        container: dict,
        description: DockmonSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._container_id = container["id"]
        self._host_id = container["host_id"]
        self._attr_unique_id = f"{DOMAIN}_{self._host_id}_{self._container_id}_{description.key}"

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
    def native_value(self) -> float | str | None:
        c = self._container
        if c is None:
            return None
        return self.entity_description.value_fn(c)
