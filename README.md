# DockMon for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant integration to monitor and control Docker containers via [DockMon](https://github.com/darthnorse/dockmon).

## Features

- **Switch** – Start/stop each container directly from HA
- **Binary sensor** – Running state of each container
- **Sensors** – CPU %, Memory %, Memory usage (MB), container state
- Automatic discovery of all hosts and containers
- Devices survive container recreation (identified by host + container name, not by the Docker ID)
- Devices of removed containers/hosts are cleaned up automatically
- Supports multiple DockMon instances

## Requirements

- A running [DockMon](https://github.com/darthnorse/dockmon) instance
- An API key (DockMon Settings → API Keys)

## Installation via HACS

1. In HACS, click **Integrations** → **+ Explore & download repositories**
2. Search for **DockMon** and click **Download**
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration**
5. Search for **DockMon** and follow the setup steps

## Manual Installation

1. Copy the `custom_components/dockmon` folder into your HA `config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration via **Settings → Devices & Services**

## Configuration

| Field           | Description                                                            |
| --------------- | ---------------------------------------------------------------------- |
| **DockMon URL** | Base URL of your DockMon instance (e.g. `https://dockmon.example.com`) |
| **API Key**     | API key with read + write permissions                                  |

## Entities

For each Docker container, the integration creates a **device** with the following entities:

| Entity        | Type          | Description                               |
| ------------- | ------------- | ----------------------------------------- |
| (device name) | Switch        | Start / stop the container                |
| Running       | Binary sensor | `on` when container is running            |
| CPU           | Sensor        | CPU usage (%)                             |
| Memory        | Sensor        | Memory usage (%)                          |
| Memory Usage  | Sensor        | Memory usage (MB)                         |
| State         | Sensor        | Raw Docker state (`running`, `exited`, …) |

## Contributing

Issues and pull requests are welcome on [GitHub](https://github.com/gautierlabarre/HA-dockmon/issues).

## License

Released under the [MIT License](LICENSE).

This project is an independent Home Assistant integration and is not affiliated
with, endorsed by, or maintained by the [DockMon](https://github.com/darthnorse/dockmon)
project.
