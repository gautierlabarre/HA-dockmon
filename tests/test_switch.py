"""Tests for the DockMon switch platform."""
from datetime import timedelta

import pytest
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import HOSTS, URL

NEXTCLOUD = "dockmon_h1_nextcloud_switch"
JELLYFIN = "dockmon_h1_jellyfin_switch"


def _entity_id(hass, unique_id: str) -> str:
    return er.async_get(hass).async_get_entity_id(SWITCH_DOMAIN, "dockmon", unique_id)


async def _setup(hass, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_switch_reflects_the_container_state(hass, mock_api, config_entry):
    await _setup(hass, config_entry)

    assert hass.states.get(_entity_id(hass, NEXTCLOUD)).state == "on"
    assert hass.states.get(_entity_id(hass, JELLYFIN)).state == "off"


async def test_switch_exposes_container_attributes(hass, mock_api, config_entry):
    await _setup(hass, config_entry)

    attrs = hass.states.get(_entity_id(hass, NEXTCLOUD)).attributes
    assert attrs["container_id"] == "c1"
    assert attrs["image"] == "nextcloud:29"
    assert attrs["host"] == "mini-server"


@pytest.mark.parametrize(
    ("service", "unique_id", "endpoint"),
    [
        (SERVICE_TURN_ON, JELLYFIN, "start"),
        (SERVICE_TURN_OFF, NEXTCLOUD, "stop"),
    ],
)
async def test_switch_calls_the_api(
    hass, mock_api, config_entry, service, unique_id, endpoint
):
    await _setup(hass, config_entry)
    container_id = "c2" if endpoint == "start" else "c1"
    mock_api.post(f"{URL}/api/hosts/h1/containers/{container_id}/{endpoint}", json={})

    await hass.services.async_call(
        SWITCH_DOMAIN,
        service,
        {ATTR_ENTITY_ID: _entity_id(hass, unique_id)},
        blocking=True,
    )
    await hass.async_block_till_done()

    posted = [call for call in mock_api.mock_calls if call[0] == "POST"]
    assert len(posted) == 1
    assert posted[0][1].path.endswith(f"/{container_id}/{endpoint}")

    # The delayed second refresh must not leave a lingering timer behind.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()


async def test_switch_refuses_to_act_on_a_vanished_container(
    hass, aioclient_mock, config_entry
):
    aioclient_mock.get(f"{URL}/api/hosts", json=HOSTS)
    aioclient_mock.get(f"{URL}/api/containers", json=[])
    await _setup(hass, config_entry)

    entity_id = _entity_id(hass, NEXTCLOUD)
    assert entity_id is None  # nothing was ever created for it
