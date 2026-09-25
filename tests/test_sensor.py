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


async def test_a_real_zero_is_reported_as_zero(hass, mock_api, config_entry):
    """An idle container measured at 0% is not the same as no measurement."""
    await _setup(hass, config_entry)

    assert _state(hass, "dockmon_h1_jellyfin_cpu_percent").state == "0"
    assert _state(hass, "dockmon_h1_jellyfin_state").state == "exited"


async def test_absent_metrics_are_unknown_not_zero(hass, aioclient_mock, config_entry):
    """DockMon streams stats only while someone is watching, unless persistence
    is enabled, so null is the normal answer for a local or mTLS host. Reporting
    0.0 would claim the container is idle and read like a broken integration."""
    from .conftest import ALL_CAPABILITIES, HOSTS, URL

    unmeasured = [
        {
            "id": "c1",
            "host_id": "h1",
            "name": "/nextcloud",
            "state": "running",
            "status": "Up 3 days",
            "image": "nextcloud:29",
            "cpu_percent": None,
            "memory_percent": None,
            "memory_usage": None,
        }
    ]
    aioclient_mock.get(f"{URL}/api/hosts", json=HOSTS)
    aioclient_mock.get(f"{URL}/api/containers", json=unmeasured)
    aioclient_mock.get(f"{URL}/api/v2/auth/me", json=ALL_CAPABILITIES)

    await _setup(hass, config_entry)

    for key in ("cpu_percent", "memory_percent", "memory_usage"):
        assert _state(hass, f"dockmon_h1_nextcloud_{key}").state == "unknown", key
    # The container itself is still fine — only the measurements are missing.
    assert _state(hass, "dockmon_h1_nextcloud_state").state == "running"


async def test_the_host_sensor_counts_running_containers(hass, mock_api, config_entry):
    await _setup(hass, config_entry)

    # One of the two fixture containers is running.
    assert _state(hass, "dockmon_h1_running_containers").state == "1"


async def test_the_host_sensor_is_unavailable_when_the_host_is_offline(
    hass, aioclient_mock, config_entry
):
    """DockMon omits an offline host's containers, so counting them would
    report a confident 0 where the truthful answer is "unknown"."""
    from .conftest import CONTAINERS, HOSTS, URL

    offline = [{**HOSTS[0], "status": "offline"}]
    aioclient_mock.get(f"{URL}/api/hosts", json=offline)
    # Exactly what DockMon does for an offline host: the host is still listed,
    # its containers are not.
    aioclient_mock.get(f"{URL}/api/containers", json=[])

    await _setup(hass, config_entry)

    assert _state(hass, "dockmon_h1_running_containers").state == "unavailable"


async def test_the_host_sensor_counts_again_once_the_host_is_online(
    hass, aioclient_mock, config_entry
):
    from .conftest import CONTAINERS, HOSTS, URL

    aioclient_mock.get(f"{URL}/api/hosts", json=[{**HOSTS[0], "status": "online"}])
    aioclient_mock.get(f"{URL}/api/containers", json=CONTAINERS)

    await _setup(hass, config_entry)

    assert _state(hass, "dockmon_h1_running_containers").state == "1"
