"""Tests for the DockMon setup, device migration and pruning."""
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components import dockmon
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


def _stale_device(hass, config_entry, identifier="h1_deleted-container"):
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, identifier)},
        name=f"mini-server {identifier}",
    )


async def test_devices_of_removed_containers_are_pruned(
    hass, mock_api, config_entry, monkeypatch
):
    monkeypatch.setattr(dockmon, "STALE_GRACE", 0)
    _stale_device(hass, config_entry)

    await _setup(hass, config_entry)

    dev_reg = dr.async_get(hass)
    assert dev_reg.async_get_device_by_identifier((DOMAIN, "h1_deleted-container"), config_entry.entry_id) is None


async def test_a_briefly_absent_container_is_not_pruned(hass, mock_api, config_entry):
    """Recreating a container makes it vanish for a while – that must not delete it.

    Removing the device deletes its entities from the registry, frees their entity
    IDs and breaks every dashboard and automation pointing at them.
    """
    _stale_device(hass, config_entry)

    await _setup(hass, config_entry)

    dev_reg = dr.async_get(hass)
    assert dev_reg.async_get_device_by_identifier((DOMAIN, "h1_deleted-container"), config_entry.entry_id) is not None


async def test_an_empty_payload_never_prunes(hass, aioclient_mock, config_entry, monkeypatch):
    """DockMon answers 200 with [] while starting up; that is not a deletion."""
    monkeypatch.setattr(dockmon, "STALE_GRACE", 0)
    aioclient_mock.get(f"{URL}/api/hosts", json=[])
    aioclient_mock.get(f"{URL}/api/containers", json=[])
    _stale_device(hass, config_entry, "h1_nextcloud")

    await _setup(hass, config_entry)

    dev_reg = dr.async_get(hass)
    assert dev_reg.async_get_device_by_identifier((DOMAIN, "h1_nextcloud"), config_entry.entry_id) is not None


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


async def test_v1_entries_keep_tls_verification_off(hass, mock_api):
    """Turning verification on during a migration would break self-signed setups."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.dockmon.const import (
        CONF_API_KEY,
        CONF_URL,
        CONF_VERIFY_SSL,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        data={CONF_URL: URL, CONF_API_KEY: "s3cret"},
        unique_id=f"dockmon_{URL}/",
    )
    entry.add_to_hass(hass)

    await _setup(hass, entry)

    assert entry.version == 2
    assert entry.data[CONF_VERIFY_SSL] is False
    assert hass.data[DOMAIN][entry.entry_id].verify_ssl is False
    # The trailing slash is normalised away at the same time.
    assert entry.unique_id == f"dockmon_{URL}"


async def test_new_entries_verify_tls(hass, mock_api, config_entry):
    """A v2 entry is left as-is: no migration, verification stays on."""
    await _setup(hass, config_entry)

    assert config_entry.version == 2

    assert hass.data[DOMAIN][config_entry.entry_id].verify_ssl is True


# --- The 1.1.x regression: DockMon renaming a container ----------------------

LABELLED = [
    {
        "id": "a133bfdc6f16",
        "host_id": "h1",
        "name": "snapotter",
        "state": "running",
        "status": "Up 2 days",
        "image": "snapotter/snapotter:latest",
        "cpu_percent": 1.0,
        "memory_percent": 2.0,
        "memory_usage": 1024,
        "labels": {
            "com.docker.compose.project": "infra",
            "com.docker.compose.service": "snapotter",
        },
    }
]


def _serve(aioclient_mock, containers):
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/hosts", json=HOSTS)
    aioclient_mock.get(f"{URL}/api/containers", json=containers)


def _dockmon_entity_ids(hass):
    return {e.entity_id for e in er.async_get(hass).entities.values() if e.platform == DOMAIN}


async def test_a_container_renamed_by_dockmon_keeps_its_entity_ids(
    hass, aioclient_mock, config_entry
):
    """DockMon rewrites `name` to `<short_id>_<name>` when it disambiguates.

    Keying on the name made that look like a different container: HA built a second
    device and the original entity IDs disappeared from every dashboard.
    """
    _serve(aioclient_mock, LABELLED)
    await _setup(hass, config_entry)
    before = _dockmon_entity_ids(hass)
    assert "switch.mini_server_snapotter" in before

    renamed = [{**LABELLED[0], "id": "243541a5f151", "name": "a133bfdc6f16_snapotter"}]
    _serve(aioclient_mock, renamed)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert _dockmon_entity_ids(hass) == before
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device_by_identifier(
        (DOMAIN, "h1_infra_snapotter"), config_entry.entry_id
    )
    assert device is not None
    assert device.name == "mini-server snapotter"  # prefix never reaches the name


async def test_name_keyed_devices_are_migrated_to_compose_keys(
    hass, aioclient_mock, config_entry
):
    """A 1.1.x device is re-keyed in place, keeping its entity ID and history."""
    _serve(aioclient_mock, LABELLED)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    legacy = dev_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "h1_snapotter")},
        name="mini-server snapotter",
    )
    legacy_switch = ent_reg.async_get_or_create(
        "switch",
        DOMAIN,
        "dockmon_h1_snapotter_switch",
        device_id=legacy.id,
        config_entry=config_entry,
    )

    await _setup(hass, config_entry)

    migrated = dev_reg.async_get_device_by_identifier(
        (DOMAIN, "h1_infra_snapotter"), config_entry.entry_id
    )
    assert migrated is not None
    assert migrated.id == legacy.id
    entity = ent_reg.async_get(legacy_switch.entity_id)
    assert entity is not None
    assert entity.unique_id == "dockmon_h1_infra_snapotter_switch"
