"""Sensor platform for DockMon – CPU%, memory%, status."""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
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
from .entity import DockmonContainerEntity


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
    known_container_keys: set[str] = set()
    known_host_ids: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        entities: list = []

        for host_id in coordinator.data["hosts"]:
            if host_id in known_host_ids:
                continue
            known_host_ids.add(host_id)
            sensor = DockmonHostSensor(coordinator, host_id)
            sensor.async_on_remove(partial(known_host_ids.discard, host_id))
            entities.append(sensor)

        for key, container in coordinator.data["containers_by_key"].items():
            if key in known_container_keys:
                continue
            known_container_keys.add(key)
            for desc in CONTAINER_SENSORS:
                sensor = DockmonContainerSensor(coordinator, container, desc)
                entities.append(sensor)
            # One discard is enough: all four sensors share the same key and are
            # added and removed together.
            entities[-1].async_on_remove(partial(known_container_keys.discard, key))

        if entities:
            async_add_entities(entities)

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class DockmonHostSensor(CoordinatorEntity[DockmonCoordinator], SensorEntity):
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
    def available(self) -> bool:
        return super().available and self._host_id in self.coordinator.data["hosts"]

    @property
    def native_value(self) -> int:
        return sum(
            1
            for c in self.coordinator.data["containers"]
            if c["host_id"] == self._host_id and c.get("state") == "running"
        )


class DockmonContainerSensor(DockmonContainerEntity, SensorEntity):
    """A sensor for a container metric."""

    entity_description: DockmonSensorEntityDescription

    def __init__(
        self,
        coordinator: DockmonCoordinator,
        container: dict,
        description: DockmonSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, container)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{self.key}_{description.key}"

    @property
    def native_value(self) -> float | str | None:
        c = self._container
        if c is None:
            return None
        return self.entity_description.value_fn(c)
