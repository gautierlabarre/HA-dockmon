"""Constants for the DockMon integration."""

DOMAIN = "dockmon"
PLATFORMS = ["switch", "sensor", "binary_sensor"]

CONF_URL = "url"
CONF_API_KEY = "api_key"
CONF_HOST_FILTER = "host_filter"
CONF_VERIFY_SSL = "verify_ssl"

# DockMon walks its hosts one at a time and gives each agent host up to 30s to
# answer a container listing, so a couple of hosts — or one slow but healthy
# agent — can legitimately push /api/containers well past a few seconds.
POLL_TIMEOUT = 30  # seconds, per polled endpoint
ACTION_TIMEOUT = 30  # seconds, for start/stop/restart

# Two sequential polls at POLL_TIMEOUT each must fit inside one interval, or a
# slow update overlaps the next and HA warns about it.
DEFAULT_SCAN_INTERVAL = 2 * POLL_TIMEOUT  # seconds
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
