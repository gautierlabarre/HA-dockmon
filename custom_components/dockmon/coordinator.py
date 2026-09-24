"""DockMon DataUpdateCoordinator."""
from __future__ import annotations

import logging
import re
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_CONTAINERS,
    API_CONTAINER_RESTART,
    API_CONTAINER_START,
    API_CONTAINER_STOP,
    API_HOSTS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)

AUTH_STATUSES = (401, 403)

_LOGGER = logging.getLogger(__name__)


# DockMon disambiguates colliding container names by prefixing the Docker short
# ID, e.g. `a133bfdc6f16_snapotter`. The prefix it bakes in is whatever short ID
# was current when the collision was resolved, so it neither matches the running
# container nor stays put — it must never reach a name or a key.
_SHORT_ID_PREFIX_RE = re.compile(r"^[0-9a-f]{12}_")

COMPOSE_PROJECT_LABEL = "com.docker.compose.project"
COMPOSE_SERVICE_LABEL = "com.docker.compose.service"


def container_name(container: dict) -> str:
    """Display name of a container, stripped of DockMon's short-ID prefix."""
    raw = (container.get("name") or "").strip().lstrip("/")
    if not raw:
        return container["id"]
    return _SHORT_ID_PREFIX_RE.sub("", raw) or raw


def container_key(container: dict) -> str:
    """Stable identity for a container, independent of ID *and* of name.

    Compose labels come first: `project` + `service` are declared in the compose
    file, so they survive both recreation (which changes the Docker ID) and any
    renaming DockMon does on its side. Only containers started outside compose
    fall back to the name, which is merely the best remaining option.
    """
    labels = container.get("labels") or {}
    project = labels.get(COMPOSE_PROJECT_LABEL)
    service = labels.get(COMPOSE_SERVICE_LABEL)
    if project and service:
        return f"{container['host_id']}_{project}_{service}"
    return f"{container['host_id']}_{container_name(container)}"


def legacy_container_keys(container: dict) -> set[str]:
    """Identifiers this container carried under earlier versions of the integration.

    Used to re-key existing devices in place, which keeps their entity IDs,
    history and customisations — recreating them would not.
    """
    host_id = container["host_id"]
    raw_name = (container.get("name") or "").strip().lstrip("/")
    candidates = {
        f"{host_id}_{container['id']}",  # 1.0.x: keyed on the Docker ID
        f"{host_id}_{raw_name}",  # 1.1.x: keyed on the raw (possibly prefixed) name
        f"{host_id}_{container_name(container)}",  # 1.1.x with an unprefixed name
    }
    return {c for c in candidates if c and c != container_key(container)}


class DockmonCoordinator(DataUpdateCoordinator):
    """Fetch data from DockMon API."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        api_key: str,
        verify_ssl: bool = DEFAULT_VERIFY_SSL,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        self._headers = {"Authorization": f"Bearer {api_key}"}
        super().__init__(
            hass,
            _LOGGER,
            # Needed for ConfigEntryAuthFailed to start the reauth flow.
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    def _session(self) -> aiohttp.ClientSession:
        return async_get_clientsession(self.hass, verify_ssl=self.verify_ssl)

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
            if err.status in AUTH_STATUSES:
                # Asks the user for a new API key instead of failing forever.
                raise ConfigEntryAuthFailed(
                    f"DockMon rejected the API key (HTTP {err.status})"
                ) from err
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
            raise HomeAssistantError(
                f"DockMon action '{action}' failed: {err.status} {err.message}"
            ) from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(
                f"DockMon action '{action}' could not reach {self.url}: {err}"
            ) from err

    async def async_validate_connection(self) -> list[dict]:
        """Validate credentials and return hosts list."""
        session = self._session()
        async with session.get(
            f"{self.url}{API_HOSTS}", headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
