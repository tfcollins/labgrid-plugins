"""XilinxJTAGDriver cable selection (serial), hw_server agent_url, xsdb lookup, run/load.

Every xsdb script the driver generates goes through ``_scope_tcl`` in
``_run_xsdb``; these tests run each public method with a fake xsdb that keeps
the scoped script, so a selection the rewrite misses fails here.
"""

import logging
import re
from unittest.mock import MagicMock

import pytest
from labgrid.binding import BindingState
from labgrid.driver.exception import ExecutionError

from adi_lg_plugins.drivers import xilinxjtagdriver as xj
from adi_lg_plugins.drivers.xilinxjtagdriver import XilinxJTAGDriver
from adi_lg_plugins.resources.xilinxdevice import XilinxDeviceJTAG

SERIAL = "210308A474DF"


class _Res:
    """A plain resource stand-in: unset settings are None, like a real XilinxDeviceJTAG."""

    def __init__(self, **kw):
        self.host = None
        self.extra = {}
        self.root_target = 1
        self.microblaze_target = 3
        self.bitstream_path = "/tmp/system_top.bit"
        self.kernel_path = "/tmp/simpleImage.strip"
        self.serial = None
        self.agent_url = None
        self.__dict__.update(kw)


@pytest.fixture
def make_driver():
    def make(**res):
        d = XilinxJTAGDriver.__new__(XilinxJTAGDriver)
        d.target = MagicMock()
        d.target.env = None
        d.name = "jtag"
        d.logger = logging.getLogger("test_xilinx_jtag_connection")
        d.xilinxvivado = MagicMock(xsdb_path="/tools/xsdb")
        d.xilinxdevicejtag = _Res(**res)
        d.state = BindingState.active
        d.scripts = []
        d.reply = ("BOOT_MODE_USER=0x00000100 BOOT_MODE_POR=0x00000eee\n", "", 0)

        def fake_run(tcl_script, timeout=300):
            d.scripts.append(d._scope_tcl(tcl_script))
            return d.reply

        d._run_xsdb = fake_run
        d._stage_payload = lambda path: str(path).removeprefix("exporter:")
        d._stage_file = lambda path: path
        return d

    return make


# --- resource validation -----------------------------------------------------


@pytest.mark.parametrize("serial", ["210308A474DF", "TE0790-03_A"])
def test_resource_accepts_cable_serials(serial):
    assert XilinxDeviceJTAG(None, "jtag", serial=serial).serial == serial


@pytest.mark.parametrize("serial", ['a"b', "a b", "x}; exec rm", ""])
def test_resource_rejects_serials_that_could_break_the_tcl(serial):
    with pytest.raises(ValueError, match="serial"):
        XilinxDeviceJTAG(None, "jtag", serial=serial)


@pytest.mark.parametrize("url", ["tcp::3121", "TCP:10.0.0.79:3121", "tcp:tron.local:3121"])
def test_resource_accepts_agent_urls(url):
    assert XilinxDeviceJTAG(None, "jtag", agent_url=url).agent_url == url


@pytest.mark.parametrize("url", ["10.0.0.79:3121", "tcp:host", "tcp:h:1; exit", "tcp:h:port"])
def test_resource_rejects_malformed_agent_urls(url):
    with pytest.raises(ValueError, match="agent_url"):
        XilinxDeviceJTAG(None, "jtag", agent_url=url)


# --- xsdb executable ---------------------------------------------------------


def test_xsdb_from_vivado_tool(make_driver):
    assert make_driver()._xsdb_bin() == "/tools/xsdb"


def test_xsdb_from_env_tools_without_vivado_tool(make_driver):
    d = make_driver()
    d.xilinxvivado = None
    d.target.env = MagicMock()
    d.target.env.config.get_tool.return_value = "/opt/xsdb"
    assert d._xsdb_bin() == "/opt/xsdb"
    d.target.env.config.get_tool.assert_called_once_with("xsdb")


def test_xsdb_from_path_without_vivado_tool_or_env(make_driver):
    d = make_driver()
    d.xilinxvivado = None
    assert d._xsdb_bin() == "xsdb"


def test_vivado_tool_binding_is_optional():
    assert None in XilinxJTAGDriver.bindings["xilinxvivado"]


# --- agent_url ---------------------------------------------------------------


def test_agent_url_runs_xsdb_on_the_client(make_driver):
    d = make_driver(extra={"proxy": "tron"}, agent_url="tcp:tron.local:3121")
    assert d._exporter_host(d.xilinxdevicejtag) is None


def test_without_agent_url_xsdb_runs_on_the_exporter(make_driver, monkeypatch):
    monkeypatch.setattr("adi_lg_plugins.drivers._remote._resolvable_host", lambda h: h)
    d = make_driver(extra={"proxy": "tron"})
    assert d._exporter_host(d.xilinxdevicejtag) == "tron"


def test_empty_agent_url_host_is_the_exporter(make_driver, monkeypatch):
    monkeypatch.setattr("adi_lg_plugins.drivers._remote._resolvable_host", lambda h: h + ".local")
    d = make_driver(extra={"proxy": "tron"}, agent_url="tcp::3121")
    assert d._agent_url() == "tcp:tron.local:3121"


def test_empty_agent_url_host_on_a_local_resource_is_localhost(make_driver):
    assert make_driver(agent_url="tcp::3121")._agent_url() == "tcp:127.0.0.1:3121"


def test_agent_url_replaces_plain_and_local_connects(make_driver):
    d = make_driver(agent_url="tcp:tron.local:3121")
    tcl = "connect\n  connect -url TCP:127.0.0.1:3121\nconnect -url tcp:localhost:3121\n"
    assert d._scope_tcl(tcl).splitlines() == [
        "connect -url tcp:tron.local:3121",
        "  connect -url tcp:tron.local:3121",
        "connect -url tcp:tron.local:3121",
    ]


def test_agent_url_keeps_an_explicit_other_hw_server(make_driver):
    d = make_driver(agent_url="tcp:tron.local:3121")
    assert d._scope_tcl("connect -url tcp:10.0.0.5:3121\n") == "connect -url tcp:10.0.0.5:3121\n"


def test_without_settings_the_script_is_unchanged(make_driver):
    tcl = 'connect\ntargets 1\ntargets -set -filter {name =~ "PSU"}\n'
    assert make_driver()._scope_tcl(tcl) == tcl


# --- serial ------------------------------------------------------------------


def test_serial_scopes_filter_selections(make_driver):
    d = make_driver(serial=SERIAL)
    out = d._scope_tcl(
        'targets -set -nocase -filter {name =~ "PSU"}\ntargets -set -filter {name == "PL"}\n'
    )
    assert out.splitlines() == [
        f'targets -set -nocase -filter {{(name =~ "PSU") && jtag_cable_serial == "{SERIAL}"}}',
        f'targets -set -filter {{(name == "PL") && jtag_cable_serial == "{SERIAL}"}}',
    ]
    assert "proc lg_cable_target" not in out


def test_serial_maps_index_selections_onto_the_cable(make_driver):
    out = make_driver(serial=SERIAL)._scope_tcl("connect\n        targets 3\n")
    assert out.startswith("proc lg_cable_target")
    assert f'        targets [lg_cable_target "{SERIAL}" 3]' in out.splitlines()


def test_serial_refuses_a_selection_it_cannot_scope(make_driver):
    d = make_driver(serial=SERIAL)
    with pytest.raises(ExecutionError, match="cannot restrict"):
        d._scope_tcl("targets -set 4\n")


def test_target_listing_is_not_a_selection(make_driver):
    tcl = "puts [targets]\nputs [targets -target-properties]\n"
    assert make_driver(serial=SERIAL)._scope_tcl(tcl) == tcl


def _call_every_method(d):
    d.connect_jtag()
    d.flash_bitstream()
    d.program_bitstream("/tmp/other.bit")
    d.download_kernel()
    d.start_execution()
    d.load_bitstream_and_kernel_and_start()
    d.load_and_run_elf("/tmp/app.elf", bitstream_path="/tmp/s.bit", ps7_init_tcl="/tmp/ps7.tcl")
    d.load_zynq_uboot("/tmp/ps7.tcl", "/tmp/u-boot.elf", bitstream_path="/tmp/s.bit")
    d.stop_zynq_cpu()
    d.load_zynqmp_uboot("/tmp/psu.tcl", "/tmp/spl.elf", bitstream_path="/tmp/s.bit")
    d.load_zynqmp_production_uboot(
        "/tmp/psu.tcl", "/tmp/pmufw.bin", "/tmp/u-boot.bin", handoff_bin="/tmp/h.bin"
    )
    d.load_zynqmp_recovery_linux(
        "/tmp/psu.tcl", "/tmp/t.elf", "/tmp/Image", "/tmp/i.cpio.gz", "/tmp/s.dtb"
    )
    d.stop_zynqmp_cpu()
    d.get_zynqmp_boot_mode()
    d.set_zynqmp_boot_mode("jtag")
    d.reply = ("BOOT_MODE_USER=0x00000000 BOOT_MODE_POR=0x00000eee\n", "", 0)
    d.clear_zynqmp_boot_mode_override()
    d.run(['targets -set -filter {name =~ "PSU"}', "mrd 0xff5e0200"])


def test_every_method_restricts_every_selection_to_the_cable(make_driver):
    d = make_driver(serial=SERIAL)
    _call_every_method(d)
    assert len(d.scripts) == 17  # one xsdb script per call above
    for script in d.scripts:
        for line in script.splitlines():
            if re.search(r"\btargets\s+(-set\b|\d|\[)", line):
                assert SERIAL in line, line


def test_every_method_connects_to_the_agent(make_driver):
    d = make_driver(agent_url="tcp:tron.local:3121")
    _call_every_method(d)
    connects = [line.strip() for s in d.scripts for line in s.splitlines() if "connect" in line]
    connects = [c for c in connects if c.startswith("connect")]
    assert connects and set(connects) == {"connect -url tcp:tron.local:3121"}


# --- run / load / program_bitstream ------------------------------------------


def test_run_wraps_commands_in_one_session(make_driver):
    d = make_driver()
    d.reply = ("hello\n", "", 0)
    assert d.run(["puts hello"]) == "hello\n"
    assert d.scripts[-1].splitlines() == ["connect", "puts hello", "disconnect"]


def test_run_accepts_a_single_command_and_interactive(make_driver):
    d = make_driver()
    d.run("puts hi", interactive=True)
    assert d.scripts[-1].splitlines() == ["connect", "puts hi"]


def test_run_raises_on_xsdb_failure(make_driver):
    d = make_driver()
    d.reply = ("", "no targets found", 1)
    with pytest.raises(ExecutionError, match="no targets found"):
        d.run(["targets 99"])


def test_program_bitstream_defaults_to_the_resource_path(make_driver):
    d = make_driver()
    d.program_bitstream()
    assert "fpga -f /tmp/system_top.bit" in d.scripts[-1]
    assert "targets 1" in d.scripts[-1]


def test_program_bitstream_needs_a_file(make_driver):
    d = make_driver(bitstream_path=None)
    with pytest.raises(ExecutionError, match="No bitstream"):
        d.program_bitstream()


@pytest.mark.parametrize("name", ["/tmp/d.bit", "/tmp/D.BIN", "exporter:/srv/s.bit"])
def test_load_programs_bitstreams(make_driver, name):
    d = make_driver()
    d.load(name)
    assert "fpga -f" in d.scripts[-1]


def test_load_without_a_file_uses_the_resource_bitstream(make_driver):
    d = make_driver()
    d.load()
    assert "fpga -f /tmp/system_top.bit" in d.scripts[-1]


def test_load_runs_an_elf_on_the_a9(make_driver):
    d = make_driver()
    d.load("/tmp/app.elf")
    assert "dow /tmp/app.elf" in d.scripts[-1]
    assert "Cortex-A9" in d.scripts[-1]


def test_load_rejects_other_files(make_driver):
    with pytest.raises(ValueError, match="unsupported"):
        make_driver().load("/tmp/image.ub")


# --- force_bootmode_reset ----------------------------------------------------


@pytest.mark.parametrize(
    ("given", "mode"),
    [
        ("ps_jtag", "jtag"),
        ("JTAG", "jtag"),
        ("quad_spi_24", "qspi24"),
        ("qspi", "qspi32"),
        ("sd_0", "sd0"),
        ("sd_1", "sd1"),
        ("sd", "sd1-ls"),
        ("sd_1_ls", "sd1-ls"),
        ("usb", "usb0"),
        ("emmc", "emmc"),
        ("sd1-ls", "sd1-ls"),
        ("0xE100", 0xE),
        ("0x0100", 0x0),
        ("0x5", 0x5),
        (0x2100, 0x2),
        (3, 3),
    ],
)
def test_force_bootmode_reset_maps_onto_set_zynqmp_boot_mode(make_driver, given, mode):
    d = make_driver()
    d.set_zynqmp_boot_mode = MagicMock(return_value={"effective_name": "x"})
    d.force_bootmode_reset(given)
    d.set_zynqmp_boot_mode.assert_called_once_with(mode, reset=True, jtag_url="TCP:127.0.0.1:3121")


@pytest.mark.parametrize("word", ["0x5005", "0xE000", "0x1E100"])
def test_force_bootmode_reset_rejects_words_without_use_alt(make_driver, word):
    d = make_driver()
    d.set_zynqmp_boot_mode = MagicMock()
    with pytest.raises(ValueError, match="BOOT_MODE_USER word"):
        d.force_bootmode_reset(word)
    d.set_zynqmp_boot_mode.assert_not_called()


def test_force_bootmode_reset_end_to_end_writes_the_override(make_driver):
    d = make_driver()
    d.reply = ("BOOT_MODE_USER=0x0000e10e BOOT_MODE_POR=0x00000000\n", "", 0)
    info = d.force_bootmode_reset("sd")
    assert "mwr -force 0xff5e0200 0xe100" in d.scripts[-1]
    assert "rst -system" in d.scripts[-1]
    assert info["effective_name"] == "sd1-ls"


def test_unknown_mle_name_is_rejected(make_driver):
    with pytest.raises(ValueError):
        make_driver().force_bootmode_reset("floppy")


def test_driver_is_a_bootstrap_protocol():
    from labgrid.protocol import BootstrapProtocol

    assert issubclass(XilinxJTAGDriver, BootstrapProtocol)
    assert xj._MLE_BOOT_MODE_ALIASES["sd"] == "sd1-ls"
