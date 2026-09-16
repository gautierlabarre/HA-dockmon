"""Tests for the DockMon sensor platform."""
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.helpers import entity_registry as er


def _state(hass, unique_id: str):
    entity_id = er.async_get(hass).async_get_entity_id(
        SENSOR_DOMAIN, "dockmon", unique_id
    )
    return hass.states.get(entity_id)


async def _setup(hass, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_container_metrics_are_rounded(hass, mock_api, config_entry):
    await _setup(hass, config_entry)

    assert _state(hass, "dockmon_h1_nextcloud_cpu_percent").state == "3.1"
    assert _state(hass, "dockmon_h1_nextcloud_memory_percent").state == "12.3"
    # 100 MiB reported in bytes by the Docker API.
    assert _state(hass, "dockmon_h1_nextcloud_memory_usage").state == "100.0"
    assert _state(hass, "dockmon_h1_nextcloud_state").state == "running"


async def test_missing_metrics_default_to_zero(hass, mock_api, config_entry):
    await _setup(hass, config_entry)

    assert _state(hass, "dockmon_h1_jellyfin_cpu_percent").state == "0"
    assert _state(hass, "dockmon_h1_jellyfin_state").state == "exited"


async def test_the_host_sensor_counts_running_containers(hass, mock_api, config_entry):
    await _setup(hass, config_entry)

    # One of the two fixture containers is running.
    assert _state(hass, "dockmon_h1_running_containers").state == "1"
