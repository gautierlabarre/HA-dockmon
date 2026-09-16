"""Fixtures shared by the DockMon tests."""
import pytest

from custom_components.dockmon.const import CONF_API_KEY, CONF_URL, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

URL = "https://dockmon.test"

HOSTS = [
    {
        "id": "h1",
        "name": "mini-server",
        "docker_version": "27.1.1",
        "os_version": "Debian 12",
    }
]

CONTAINERS = [
    {
        "id": "c1",
        "host_id": "h1",
        "name": "/nextcloud",
        "state": "running",
        "status": "Up 3 days",
        "image": "nextcloud:29",
        "cpu_percent": 3.14159,
        "memory_percent": 12.34,
        "memory_usage": 100 * 1024 * 1024,
    },
    {
        "id": "c2",
        "host_id": "h1",
        "name": "/jellyfin",
        "state": "exited",
        "status": "Exited (0) 2 hours ago",
        "image": "jellyfin/jellyfin:latest",
        "cpu_percent": 0,
        "memory_percent": 0,
        "memory_usage": 0,
    },
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load `custom_components/` in every test."""
    yield


@pytest.fixture
def mock_api(aioclient_mock):
    """Mock a healthy DockMon API."""
    aioclient_mock.get(f"{URL}/api/hosts", json=HOSTS)
    aioclient_mock.get(f"{URL}/api/containers", json=CONTAINERS)
    return aioclient_mock


@pytest.fixture
def config_entry(hass) -> MockConfigEntry:
    """A config entry registered against hass."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="DockMon (mini-server)",
        data={CONF_URL: URL, CONF_API_KEY: "s3cret"},
        unique_id=f"dockmon_{URL}",
    )
    entry.add_to_hass(hass)
    return entry
