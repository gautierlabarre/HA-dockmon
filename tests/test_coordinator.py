"""Tests for the DockMon coordinator."""
import aiohttp
import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.dockmon.coordinator import (
    DockmonCoordinator,
    container_key,
    container_name,
)

from .conftest import CONTAINERS, HOSTS, URL


def test_container_name_strips_the_docker_slash():
    assert container_name({"id": "c1", "name": "/nextcloud"}) == "nextcloud"


def test_container_name_falls_back_to_the_id():
    assert container_name({"id": "c1", "name": ""}) == "c1"
    assert container_name({"id": "c1"}) == "c1"


def test_container_key_survives_a_recreation():
    """A new Docker ID for the same name must keep the same key."""
    before = {"id": "aaa", "host_id": "h1", "name": "/nextcloud"}
    after = {"id": "bbb", "host_id": "h1", "name": "/nextcloud"}
    assert container_key(before) == container_key(after) == "h1_nextcloud"


def test_container_key_is_scoped_to_the_host():
    left = {"id": "a", "host_id": "h1", "name": "web"}
    right = {"id": "b", "host_id": "h2", "name": "web"}
    assert container_key(left) != container_key(right)


async def test_update_indexes_hosts_and_containers(hass, mock_api):
    coordinator = DockmonCoordinator(hass, url=f"{URL}/", api_key="s3cret")
    data = await coordinator._async_update_data()

    assert data["hosts"] == {"h1": HOSTS[0]}
    assert data["containers"] == CONTAINERS
    assert set(data["containers_by_key"]) == {"h1_nextcloud", "h1_jellyfin"}


async def test_update_sends_the_api_key(hass, mock_api):
    coordinator = DockmonCoordinator(hass, url=URL, api_key="s3cret")
    await coordinator._async_update_data()

    for _method, _url, _data, headers in mock_api.mock_calls:
        assert headers["Authorization"] == "Bearer s3cret"


async def test_trailing_slash_is_stripped_from_the_url(hass):
    coordinator = DockmonCoordinator(hass, url=f"{URL}///", api_key="s3cret")
    assert coordinator.url == URL


async def test_duplicate_names_keep_the_first_container(hass, aioclient_mock, caplog):
    twins = [
        {"id": "c1", "host_id": "h1", "name": "/web", "state": "running"},
        {"id": "c2", "host_id": "h1", "name": "/web", "state": "running"},
    ]
    aioclient_mock.get(f"{URL}/api/hosts", json=HOSTS)
    aioclient_mock.get(f"{URL}/api/containers", json=twins)

    coordinator = DockmonCoordinator(hass, url=URL, api_key="s3cret")
    data = await coordinator._async_update_data()

    assert data["containers_by_key"]["h1_web"]["id"] == "c1"
    assert "Duplicate DockMon container key" in caplog.text


@pytest.mark.parametrize("status", [500, 502, 404])
async def test_http_errors_surface_as_update_failed(hass, aioclient_mock, status):
    aioclient_mock.get(f"{URL}/api/hosts", status=status)

    coordinator = DockmonCoordinator(hass, url=URL, api_key="s3cret")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.parametrize("status", [401, 403])
async def test_a_rejected_api_key_asks_for_reauth(hass, aioclient_mock, status):
    """ConfigEntryAuthFailed is what makes HA show the "reconfigure" prompt."""
    aioclient_mock.get(f"{URL}/api/hosts", status=status)

    coordinator = DockmonCoordinator(hass, url=URL, api_key="stale")
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_connection_errors_surface_as_update_failed(hass, aioclient_mock):
    aioclient_mock.get(f"{URL}/api/hosts", exc=aiohttp.ClientConnectionError)

    coordinator = DockmonCoordinator(hass, url=URL, api_key="s3cret")
    with pytest.raises(UpdateFailed, match=URL):
        await coordinator._async_update_data()


async def test_timeouts_are_left_to_the_base_coordinator(hass, aioclient_mock):
    """TimeoutError is not a ClientError; DataUpdateCoordinator handles it itself."""
    aioclient_mock.get(f"{URL}/api/hosts", exc=TimeoutError)

    coordinator = DockmonCoordinator(hass, url=URL, api_key="s3cret")
    with pytest.raises(TimeoutError):
        await coordinator._async_update_data()

    await coordinator.async_refresh()
    assert coordinator.last_update_success is False


async def test_container_action_posts_to_the_right_endpoint(hass, aioclient_mock):
    aioclient_mock.post(f"{URL}/api/hosts/h1/containers/c1/restart", json={})

    coordinator = DockmonCoordinator(hass, url=URL, api_key="s3cret")
    await coordinator.async_container_action("h1", "c1", "restart")

    assert len(aioclient_mock.mock_calls) == 1


async def test_a_failed_action_raises_a_home_assistant_error(hass, aioclient_mock):
    """A bare Exception would surface in the UI as an unhandled traceback."""
    aioclient_mock.post(f"{URL}/api/hosts/h1/containers/c1/start", status=409)

    coordinator = DockmonCoordinator(hass, url=URL, api_key="s3cret")
    with pytest.raises(HomeAssistantError, match="start"):
        await coordinator.async_container_action("h1", "c1", "start")


async def test_an_unreachable_action_raises_a_home_assistant_error(hass, aioclient_mock):
    aioclient_mock.post(f"{URL}/api/hosts/h1/containers/c1/stop", exc=TimeoutError)

    coordinator = DockmonCoordinator(hass, url=URL, api_key="s3cret")
    with pytest.raises(HomeAssistantError):
        await coordinator.async_container_action("h1", "c1", "stop")


async def test_tls_verification_is_on_by_default(hass):
    assert DockmonCoordinator(hass, url=URL, api_key="k").verify_ssl is True
    assert (
        DockmonCoordinator(hass, url=URL, api_key="k", verify_ssl=False).verify_ssl
        is False
    )


async def test_unknown_action_is_rejected(hass):
    coordinator = DockmonCoordinator(hass, url=URL, api_key="s3cret")
    with pytest.raises(ValueError):
        await coordinator.async_container_action("h1", "c1", "self-destruct")
