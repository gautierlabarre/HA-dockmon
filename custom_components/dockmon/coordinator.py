"""DockMon DataUpdateCoordinator."""
from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_CONTAINERS,
    API_CONTAINER_RESTART,
    API_CONTAINER_START,
    API_CONTAINER_STOP,
    API_HOSTS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def container_name(container: dict) -> str:
    """Return the container name, falling back to its Docker ID."""
    return (container.get("name") or "").strip().lstrip("/") or container["id"]


def container_key(container: dict) -> str:
    """Stable identity for a container.

    Keyed on the container *name* rather than its Docker ID: the ID changes every
    time the container is recreated (image update, `docker compose up -d`, ...),
    which would otherwise spawn a brand new HA device on each recreation. Names
    are unique per host in Docker, so `host_id + name` is both stable and unique.
    """
    return f"{container['host_id']}_{container_name(container)}"


class DockmonCoordinator(DataUpdateCoordinator):
    """Fetch data from DockMon API."""

    def __init__(self, hass: HomeAssistant, url: str, api_key: str) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self._headers = {"Authorization": f"Bearer {api_key}"}
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    def _session(self) -> aiohttp.ClientSession:
        return async_get_clientsession(self.hass, verify_ssl=False)

    async def _async_update_data(self) -> dict:
        """Fetch hosts and containers."""
        session = self._session()
        try:
            async with session.get(
                f"{self.url}{API_HOSTS}", headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                resp.raise_for_status()
                hosts = await resp.json()

            async with session.get(
                f"{self.url}{API_CONTAINERS}", headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                resp.raise_for_status()
                containers = await resp.json()

        except aiohttp.ClientResponseError as err:
            raise UpdateFailed(f"DockMon API error: {err.status} {err.message}") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Cannot connect to DockMon at {self.url}: {err}") from err

        hosts_by_id = {h["id"]: h for h in hosts}
        containers_by_key: dict[str, dict] = {}
        for container in containers:
            key = container_key(container)
            if key in containers_by_key:
                _LOGGER.warning(
                    "Duplicate DockMon container key %s (ids %s and %s), ignoring the second one",
                    key,
                    containers_by_key[key]["id"],
                    container["id"],
                )
                continue
            containers_by_key[key] = container

        return {
            "hosts": hosts_by_id,
            "containers": containers,
            "containers_by_key": containers_by_key,
        }

    async def async_container_action(self, host_id: str, container_id: str, action: str) -> None:
        """Perform a container action: start, stop, restart."""
        if action == "start":
            path = API_CONTAINER_START
        elif action == "stop":
            path = API_CONTAINER_STOP
        elif action == "restart":
            path = API_CONTAINER_RESTART
        else:
            raise ValueError(f"Unknown action: {action}")

        url = self.url + path.format(host_id=host_id, container_id=container_id)
        session = self._session()
        try:
            async with session.post(url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
        except aiohttp.ClientResponseError as err:
            raise Exception(f"DockMon action '{action}' failed: {err.status} {err.message}") from err

    async def async_validate_connection(self) -> list[dict]:
        """Validate credentials and return hosts list."""
        session = self._session()
        async with session.get(
            f"{self.url}{API_HOSTS}", headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
