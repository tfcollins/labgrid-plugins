<p align="center">
  <img src="docs/source/_static/lg_adi_light.svg" alt="labgrid-plugins" width="400">
</p>

<p align="center">
  <a href="https://github.com/tfcollins/labgrid-plugins/actions/workflows/tests.yml"><img src="https://github.com/tfcollins/labgrid-plugins/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="https://labgrid-plugins.readthedocs.io/"><img src="https://readthedocs.org/projects/labgrid-plugins/badge/?version=latest" alt="Documentation"></a>
  <a href="https://github.com/tfcollins/labgrid-plugins/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

**labgrid-plugins** is a [labgrid](https://labgrid.readthedocs.io/) plugin package providing Analog Devices specific drivers, resources, and strategies for automated hardware testing and device control of FPGA SoC systems.

## Features

- **Power Control** -- VeSync smart outlets and CyberPower PDU support
- **Shell Access** -- XMODEM file transfer over serial console
- **Boot Strategies** -- Automated FPGA SoC, Fabric, SelMap, TFTP, SSH, and Raspberry Pi boot workflows
- **Mass Storage** -- SD card file management via USB SD-Mux
- **Kuiper Linux** -- Download and manage ADI Kuiper releases
- **MCP Server** -- FastMCP interface for LLM-driven hardware control with coordinator support
- **Coordinator** -- Docker-based labgrid coordinator with REST API and React web dashboard

## Quick Start

### Install

```bash
pip install git+https://github.com/tfcollins/labgrid-plugins.git
```

Or for development:

```bash
git clone https://github.com/tfcollins/labgrid-plugins.git
cd labgrid-plugins
pip install -e ".[dev]"
```

### Control a VeSync Outlet

```yaml
# target.yaml
targets:
  my_device:
    resources:
      VesyncOutlet:
        outlet_names: "Device Power"
        username: "user@example.com"
        password: "password"
    drivers:
      VesyncPowerDriver: {}
```

```python
from labgrid import Environment

env = Environment("target.yaml")
target = env.get_target("my_device")
power = target.get_driver("VesyncPowerDriver")

power.on()
power.off()
```

### Start the Coordinator

```bash
cd coordinator
docker compose up -d
```

This starts the labgrid coordinator (`:20408`), REST API (`:8000`), and web dashboard (`:3000`).

### Run the MCP Server

```bash
adi-lg-mcp
```

Set `LG_COORDINATOR` to enable remote hardware discovery:

```bash
export LG_COORDINATOR=10.0.0.41:20408
adi-lg-mcp
```

## Documentation

Full documentation is available at **[labgrid-plugins.readthedocs.io](https://labgrid-plugins.readthedocs.io/)**.

Key sections:

- [Getting Started](https://labgrid-plugins.readthedocs.io/en/latest/getting-started/index.html)
- [User Guide](https://labgrid-plugins.readthedocs.io/en/latest/user-guide/index.html) -- drivers, strategies, CLI, MCP, coordinator
- [API Reference](https://labgrid-plugins.readthedocs.io/en/latest/api/index.html)
- [Exporter Deployment](https://labgrid-plugins.readthedocs.io/en/latest/user-guide/exporter-deployment.html)
- [Running Coordinator Tests](https://labgrid-plugins.readthedocs.io/en/latest/user-guide/coordinator-testing.html)

## License

[Apache License 2.0](LICENSE)
