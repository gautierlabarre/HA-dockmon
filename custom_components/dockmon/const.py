"""Constants for the DockMon integration."""

DOMAIN = "dockmon"
PLATFORMS = ["switch", "sensor", "binary_sensor"]

CONF_URL = "url"
CONF_API_KEY = "api_key"
CONF_HOST_FILTER = "host_filter"
CONF_VERIFY_SSL = "verify_ssl"

DEFAULT_SCAN_INTERVAL = 30  # seconds
# Entries created before config-entry version 2 were always unverified; only new
# entries get TLS verification on by default.
DEFAULT_VERIFY_SSL = True

API_HOSTS = "/api/hosts"
API_CONTAINERS = "/api/containers"
API_CONTAINER_START = "/api/hosts/{host_id}/containers/{container_id}/start"
API_CONTAINER_STOP = "/api/hosts/{host_id}/containers/{container_id}/stop"
API_CONTAINER_RESTART = "/api/hosts/{host_id}/containers/{container_id}/restart"

CONTAINER_STATE_RUNNING = "running"
CONTAINER_STATE_STOPPED = "exited"
CONTAINER_STATE_PAUSED = "paused"
