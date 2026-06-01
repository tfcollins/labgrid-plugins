"""Tests for adi_lg_plugins.hw_ci.resolve and the resolve-resources CLI."""

from __future__ import annotations

from unittest.mock import MagicMock

from adi_lg_plugins.hw_ci import cli
from adi_lg_plugins.hw_ci.resolve import (
    ResolvedResources,
    render_github_output,
    resolve_from_env,
    resolve_resources,
)


def _target(resources):
    """Fake labgrid target whose get_resource(name) maps from a dict.

    Unknown names raise (mirroring labgrid's behaviour), so the resolver's
    try/each-candidate logic is exercised.
    """
    tg = MagicMock()

    def _get(name, *_args, **_kwargs):
        if name in resources:
            return resources[name]
        raise KeyError(name)

    tg.get_resource.side_effect = _get
    return tg


def test_resolve_reads_rawserialport_local_device():
    serial = MagicMock(spec=["port", "speed"])
    serial.port = "/dev/ttyUSB1"
    serial.speed = 115200
    r = resolve_resources(_target({"RawSerialPort": serial}))
    assert r.uart_device == "/dev/ttyUSB1"
    assert r.uart_speed == 115200
    assert r.uart_host is None
    assert r.uart_port is None


def test_resolve_reads_networkserialport_host_port():
    serial = MagicMock(spec=["host", "port", "speed"])
    serial.host = "10.0.0.41"
    serial.port = 4001
    serial.speed = 115200
    r = resolve_resources(_target({"NetworkSerialPort": serial}))
    assert r.uart_host == "10.0.0.41"
    assert r.uart_port == 4001
    assert r.uart_speed == 115200
    assert r.uart_device is None


def test_resolve_reads_jtag_fields():
    jtag = MagicMock(spec=["root_target", "microblaze_target"])
    jtag.root_target = 1
    jtag.microblaze_target = 3
    tool = MagicMock(spec=["xsdb_path"])
    tool.xsdb_path = "/tools/Xilinx/2025.1/Vitis/bin/xsdb"
    r = resolve_resources(_target({"XilinxDeviceJTAG": jtag, "XilinxVivadoTool": tool}))
    assert r.jtag_root_target == 1
    assert r.jtag_mb_target == 3
    assert r.jtag_xsdb == "/tools/Xilinx/2025.1/Vitis/bin/xsdb"


def test_resolve_no_resources_is_all_none():
    r = resolve_resources(_target({}))
    assert r == ResolvedResources()


def test_render_github_output_omits_none_fields():
    r = ResolvedResources(
        uart_host="10.0.0.41",
        uart_port=4001,
        jtag_xsdb="/x/xsdb",
        jtag_root_target=1,
    )
    out = render_github_output(r)
    assert "LG_UART_HOST=10.0.0.41\n" in out
    assert "LG_UART_PORT=4001\n" in out
    assert "LG_JTAG_XSDB=/x/xsdb\n" in out
    assert "LG_JTAG_ROOT_TARGET=1\n" in out
    # Unset fields must not appear at all.
    assert "LG_UART_DEVICE" not in out
    assert "LG_UART_SPEED" not in out
    assert "LG_JTAG_MB_TARGET" not in out


def test_render_github_output_emits_zero_valued_target():
    # root_target=0 is a real value, not "unset" — must still be emitted.
    out = render_github_output(ResolvedResources(jtag_root_target=0))
    assert "LG_JTAG_ROOT_TARGET=0\n" in out


def test_resolve_from_env_uses_injected_factory():
    serial = MagicMock(spec=["port", "speed"])
    serial.port = "/dev/ttyUSB0"
    serial.speed = 115200
    target = _target({"RawSerialPort": serial})
    fake_env = MagicMock()
    fake_env.get_target.return_value = target

    r = resolve_from_env("env.yaml", env_factory=lambda cfg: fake_env)

    fake_env.get_target.assert_called_once_with("main")
    assert r.uart_device == "/dev/ttyUSB0"


def test_cmd_resolve_resources_writes_github_output(tmp_path, monkeypatch):
    gh_file = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_file))
    # _cmd_resolve_resources imports the module lazily, so patch the source.
    import adi_lg_plugins.hw_ci.resolve as resolve_mod

    monkeypatch.setattr(
        resolve_mod,
        "resolve_from_env",
        lambda *a, **k: ResolvedResources(uart_device="/dev/ttyUSB2", uart_speed=115200),
    )

    rc = cli.main(["resolve-resources", "--config", "env.yaml", "--out", "github"])

    assert rc == 0
    contents = gh_file.read_text()
    assert "LG_UART_DEVICE=/dev/ttyUSB2\n" in contents
    assert "LG_UART_SPEED=115200\n" in contents
