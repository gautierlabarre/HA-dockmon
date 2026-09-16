"""Tests for the DockMon setup, device migration and pruning."""
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.dockmon.const import DOMAIN

from .conftest import CONTAINERS, HOSTS, URL


async def _setup(hass, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_creates_host_and_container_devices(hass, mock_api, config_entry):
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    dev_reg = dr.async_get(hass)
    host = dev_reg.async_get_device_by_identifier((DOMAIN, "h1"), config_entry.entry_id)
    assert host is not None
    assert host.name == "mini-server"
    assert host.sw_version == "27.1.1"

    container = dev_reg.async_get_device_by_identifier((DOMAIN, "h1_nextcloud"), config_entry.entry_id)
    assert container is not None
    assert container.via_device_id == host.id


async def test_setup_creates_the_expected_entities(hass, mock_api, config_entry):
    await _setup(hass, config_entry)

    ent_reg = er.async_get(hass)
    unique_ids = {e.unique_id for e in ent_reg.entities.values()}

    assert "dockmon_h1_nextcloud_switch" in unique_ids
    assert "dockmon_h1_nextcloud_running" in unique_ids
    assert "dockmon_h1_nextcloud_cpu_percent" in unique_ids
    assert "dockmon_h1_running_containers" in unique_ids
    # One switch + one binary sensor + four sensors per container, one per host.
    assert len(unique_ids) == len(CONTAINERS) * 6 + len(HOSTS)


async def test_unload_removes_the_coordinator(hass, mock_api, config_entry):
    await _setup(hass, config_entry)

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert config_entry.entry_id not in hass.data[DOMAIN]


async def test_id_keyed_devices_are_migrated_to_name_keys(hass, mock_api, config_entry):
    """A device left over from <=1.0.0 keeps its history instead of being orphaned."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    legacy = dev_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "h1_c1")},
        name="mini-server nextcloud",
    )
    legacy_switch = ent_reg.async_get_or_create(
        "switch",
        DOMAIN,
        "dockmon_h1_c1_switch",
        device_id=legacy.id,
        config_entry=config_entry,
    )

    await _setup(hass, config_entry)

    assert dev_reg.async_get_device_by_identifier((DOMAIN, "h1_c1"), config_entry.entry_id) is None
    migrated = dev_reg.async_get_device_by_identifier((DOMAIN, "h1_nextcloud"), config_entry.entry_id)
    assert migrated is not None
    assert migrated.id == legacy.id  # same device row: history is preserved

    entity = ent_reg.async_get(legacy_switch.entity_id)
    assert entity is not None
    assert entity.unique_id == "dockmon_h1_nextcloud_switch"


async def test_devices_of_removed_containers_are_pruned(hass, mock_api, config_entry):
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "h1_deleted-container")},
        name="mini-server deleted-container",
    )

    await _setup(hass, config_entry)

    assert dev_reg.async_get_device_by_identifier((DOMAIN, "h1_deleted-container"), config_entry.entry_id) is None


async def test_a_silent_host_does_not_lose_its_devices(hass, aioclient_mock, config_entry):
    """A host reporting zero containers is probably unreachable, not empty."""
    aioclient_mock.get(f"{URL}/api/hosts", json=HOSTS)
    aioclient_mock.get(f"{URL}/api/containers", json=[])

    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "h1_nextcloud")},
        name="mini-server nextcloud",
    )

    await _setup(hass, config_entry)

    assert dev_reg.async_get_device_by_identifier((DOMAIN, "h1_nextcloud"), config_entry.entry_id) is not None
