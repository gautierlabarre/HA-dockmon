"""Constants for the DockMon integration."""

DOMAIN = "dockmon"
PLATFORMS = ["switch", "sensor", "binary_sensor"]

CONF_URL = "url"
CONF_API_KEY = "api_key"
CONF_HOST_FILTER = "host_filter"

DEFAULT_SCAN_INTERVAL = 30  # seconds

API_HOSTS = "/api/hosts"
API_CONTAINERS = "/api/containers"
API_CONTAINER_START = "/api/hosts/{host_id}/containers/{container_id}/start"
API_CONTAINER_STOP = "/api/hosts/{host_id}/containers/{container_id}/stop"
API_CONTAINER_RESTART = "/api/hosts/{host_id}/containers/{container_id}/restart"

CONTAINER_STATE_RUNNING = "running"
CONTAINER_STATE_STOPPED = "exited"
CONTAINER_STATE_PAUSED = "paused"
