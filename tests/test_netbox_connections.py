"""NetBox records a board's power, serial console, JTAG and SD mux connections as cables.

Power: board power port -> outlet on a power device. Serial console and JTAG:
board console port -> console server port on the device the adapter is
plugged into (usually the exporter host). SD mux: board ``SD`` interface ->
the mux's ``DUT`` interface.

Each test runs against an in-memory stand-in for NetBox, and again against a
real one when ``NETBOX_TEST_URL`` and ``NETBOX_TEST_TOKEN`` name a disposable
instance (every run adds a site of its own and leaves its objects behind).
"""

from __future__ import annotations

import os
import uuid

import pytest
from _fake_netbox import FakeNetBox

from adi_lg_plugins.hw_ci.power import POWER_TYPES
from adi_lg_plugins.tools.netbox import client

APC = {"type": "apc", "address": "10.0.0.50"}


class Lab:
    """A site with a board in it, on a fake or real NetBox."""

    def __init__(self, nb, real: bool):
        self.nb = nb
        self.real = real
        self.tag = uuid.uuid4().hex[:8]
        self.site = self._site(f"site-{self.tag}")
        client.ensure_schema(nb)
        self.board = client.create_or_update_device(
            nb, f"board-{self.tag}", carrier="zcu102", site_slug=self.site.slug, custom_fields={}
        )

    def _site(self, slug):
        if self.real:
            return self.nb.dcim.sites.create(name=slug, slug=slug)
        return self.nb.add_site(slug)

    def name(self, base):
        return f"{base}-{self.tag}"

    def add_device(
        self,
        base,
        *,
        settings=None,
        outlets=(),
        ports=(),
        consoles=(),
        servers=(),
        interfaces=(),
        site=None,
        role=None,
        serial="",
        custom_fields=None,
    ):
        """A device made by hand in NetBox, optionally with power settings.

        ``consoles`` and ``servers`` name its console ports and console server
        ports, ``interfaces`` its interfaces; ``role`` is a role slug.
        """
        site = site or self.site
        custom_fields = custom_fields or ({client.POWER_FIELD: settings} if settings else {})
        if role is not None:
            found = self.nb.dcim.device_roles.get(slug=role)
            role = found or self.nb.dcim.device_roles.create(name=role, slug=role, color="9e9e9e")
        if self.real:
            mfr = self.nb.dcim.manufacturers.get(
                slug="hand-made"
            ) or self.nb.dcim.manufacturers.create(name="Hand made", slug="hand-made")
            dt = self.nb.dcim.device_types.get(
                slug="hand-made"
            ) or self.nb.dcim.device_types.create(
                manufacturer=mfr.id, model="Hand made", slug="hand-made"
            )
            role = (
                role
                or self.nb.dcim.device_roles.get(slug="hand-made")
                or self.nb.dcim.device_roles.create(
                    name="Hand made", slug="hand-made", color="9e9e9e"
                )
            )
            device = self.nb.dcim.devices.create(
                name=self.name(base),
                device_type=dt.id,
                role=role.id,
                site=site.id,
                serial=serial,
                custom_fields=custom_fields,
            )
        else:
            device = self.nb.add_device(
                self.name(base), site, custom_fields=custom_fields, role=role, serial=serial
            )
        for outlet in outlets:
            self.nb.dcim.power_outlets.create(device=device.id, name=outlet)
        for port in ports:
            self.nb.dcim.power_ports.create(device=device.id, name=port)
        for port in consoles:
            self.nb.dcim.console_ports.create(device=device.id, name=port)
        for port in servers:
            self.nb.dcim.console_server_ports.create(device=device.id, name=port)
        for interface in interfaces:
            self.nb.dcim.interfaces.create(device=device.id, name=interface, type="other")
        return device

    _ENDS = {
        "power": ("power_ports", "dcim.powerport", "power_outlets", "dcim.poweroutlet"),
        "console": (
            "console_ports",
            "dcim.consoleport",
            "console_server_ports",
            "dcim.consoleserverport",
        ),
        "sd": ("interfaces", "dcim.interface", "interfaces", "dcim.interface"),
    }

    def cable(self, port_device, port, outlet_device, outlet, kind="power"):
        ports, port_type, outlets, outlet_type = self._ENDS[kind]
        (p,) = getattr(self.nb.dcim, ports).filter(device_id=port_device.id, name=port)
        (o,) = getattr(self.nb.dcim, outlets).filter(device_id=outlet_device.id, name=outlet)
        self.nb.dcim.cables.create(
            a_terminations=[{"object_type": port_type, "object_id": p.id}],
            b_terminations=[{"object_type": outlet_type, "object_id": o.id}],
        )

    def connections(self, device, kind="power"):
        """``{port: "<device> <outlet>"}`` for ``device``'s ports of ``kind``, read afresh."""
        return {
            p.name: " ".join(f"{peer.device.name} {peer.name}" for peer in p.link_peers)
            for p in getattr(self.nb.dcim, self._ENDS[kind][0]).filter(device_id=device.id)
        }

    def server_port(self, device, name):
        (port,) = self.nb.dcim.console_server_ports.filter(device_id=device.id, name=name)
        return port

    def device(self, name):
        found = list(self.nb.dcim.devices.filter(name=name, site_id=self.site.id))
        return found[0] if found else None

    def count(self, endpoint, **filters):
        return len(list(getattr(self.nb.dcim, endpoint).filter(**filters)))


@pytest.fixture(params=["fake", "netbox"])
def lab(request):
    if request.param == "fake":
        return Lab(FakeNetBox(), real=False)
    url, token = os.environ.get("NETBOX_TEST_URL"), os.environ.get("NETBOX_TEST_TOKEN")
    if not (url and token):
        pytest.skip("NETBOX_TEST_URL / NETBOX_TEST_TOKEN not set")
    return Lab(client.connect(url, token, verify=False), real=True)


# --- what the operator picks from ---------------------------------------------


def test_power_devices_lists_devices_with_outlets_at_the_site_and_what_each_outlet_feeds(lab):
    pdu = lab.add_device("pdu", settings=APC, outlets=("1", "2"))
    other = lab.add_device("other", ports=("PSU1",))
    lab.add_device("switch")  # no outlets: not a power device
    elsewhere = lab._site(lab.name("elsewhere"))
    lab.add_device("far-pdu", outlets=("1",), site=elsewhere)
    lab.cable(other, "PSU1", pdu, "2")

    devices = client.power_devices(lab.nb, lab.site.slug)

    assert [d.name for d in devices] == [lab.name("pdu")]
    (found,) = devices
    assert found.settings == APC
    assert [(o.name, o.connected_to) for o in found.outlets] == [
        ("1", None),
        ("2", f"{lab.name('other')} PSU1"),
    ]


def test_power_devices_reads_a_hand_made_device_without_settings(lab):
    lab.add_device("pdu", outlets=("A1",))

    (found,) = client.power_devices(lab.nb, lab.site.slug)

    assert found.settings == {}
    assert found.address == ""


def test_power_device_address_is_its_primary_ip_without_the_prefix_length():
    nb = FakeNetBox()
    site = nb.add_site("lab3")
    pdu = nb.add_device("pdu", site, primary_ip="10.0.0.50/24")
    nb.dcim.power_outlets.create(device=pdu.id, name="1")

    (found,) = client.power_devices(nb, "lab3")

    assert found.address == "10.0.0.50"


def test_sites_are_listed_by_slug_and_name(lab):
    assert (lab.site.slug, lab.site.name) in client.sites(lab.nb)


# --- connecting the board ---------------------------------------------------


def test_a_new_power_device_is_created_with_its_outlet_and_cabled_to_the_board(lab):
    name = lab.name("cyberpower-10.0.0.20")
    settings = {"type": "cyberpower", "address": "10.0.0.20"}

    done = client.connect_power(
        lab.nb, lab.board, site_slug=lab.site.slug, device=name, settings=settings, outlets=["4"]
    )

    pdu = lab.device(name)
    assert pdu.custom_fields[client.POWER_FIELD] == settings
    assert pdu.role.slug == client.POWER_ROLE_SLUG
    assert pdu.device_type.slug == "labgrid-power-cyberpower"
    assert lab.connections(lab.board) == {"power": f"{name} 4"}
    assert any("created power device" in line for line in done)


def test_an_existing_device_and_outlet_are_used_and_empty_settings_filled_in(lab):
    pdu = lab.add_device("pdu", outlets=("1", "2"))

    client.connect_power(
        lab.nb, lab.board, site_slug=lab.site.slug, device=pdu.name, settings=APC, outlets=["2"]
    )

    assert lab.count("devices", name=pdu.name) == 1
    assert lab.count("power_outlets", device_id=pdu.id) == 2
    assert lab.connections(lab.board) == {"power": f"{pdu.name} 2"}
    assert lab.device(pdu.name).custom_fields[client.POWER_FIELD] == APC


def test_settings_already_on_a_device_are_not_overwritten(lab):
    theirs = {"type": "apc", "address": "pdu3.lab"}
    pdu = lab.add_device("pdu", settings=theirs, outlets=("1",))

    done = client.connect_power(
        lab.nb, lab.board, site_slug=lab.site.slug, device=pdu.name, settings=APC, outlets=["1"]
    )

    assert lab.device(pdu.name).custom_fields[client.POWER_FIELD] == theirs
    assert any("differ" in line for line in done)


def test_a_missing_outlet_is_added_to_an_existing_device(lab):
    pdu = lab.add_device("pdu", settings=APC, outlets=("1",))

    client.connect_power(
        lab.nb, lab.board, site_slug=lab.site.slug, device=pdu.name, settings=APC, outlets=["7"]
    )

    assert lab.connections(lab.board) == {"power": f"{pdu.name} 7"}


def test_an_outlet_feeding_another_device_is_refused_and_nothing_is_written(lab):
    pdu = lab.add_device("pdu", settings=APC, outlets=("1",))
    other = lab.add_device("other", ports=("PSU1",))
    lab.cable(other, "PSU1", pdu, "1")

    with pytest.raises(RuntimeError, match=f"already feeds {other.name} PSU1"):
        client.connect_power(
            lab.nb, lab.board, site_slug=lab.site.slug, device=pdu.name, settings=APC, outlets=["1"]
        )

    assert lab.connections(lab.board) == {}
    assert lab.device(pdu.name).custom_fields.get(client.POWER_FIELD) == APC


def test_running_again_changes_nothing(lab):
    pdu = lab.add_device("pdu", settings=APC, outlets=("1",))
    kwargs = dict(site_slug=lab.site.slug, device=pdu.name, settings=APC, outlets=["1"])
    client.connect_power(lab.nb, lab.board, **kwargs)

    done = client.connect_power(lab.nb, lab.board, **kwargs)

    assert lab.connections(lab.board) == {"power": f"{pdu.name} 1"}
    assert lab.count("cables") >= 1
    assert lab.count("power_ports", device_id=lab.board.id) == 1
    assert [line for line in done if "connected" in line and "already" not in line] == []


def test_a_free_power_port_the_board_already_has_is_used(lab):
    board = lab.add_device("board2", ports=("PSU1",))
    pdu = lab.add_device("pdu", settings=APC, outlets=("1",))

    client.connect_power(
        lab.nb, board, site_slug=lab.site.slug, device=pdu.name, settings=APC, outlets=["1"]
    )

    assert lab.connections(board) == {"PSU1": f"{pdu.name} 1"}


def test_a_board_that_moved_outlet_keeps_its_old_cable_and_is_told_about_it(lab):
    pdu = lab.add_device("pdu", settings=APC, outlets=("1", "2"))
    kwargs = dict(site_slug=lab.site.slug, device=pdu.name, settings=APC)
    client.connect_power(lab.nb, lab.board, outlets=["1"], **kwargs)

    done = client.connect_power(lab.nb, lab.board, outlets=["2"], **kwargs)

    assert lab.connections(lab.board) == {"power": f"{pdu.name} 1", "power 2": f"{pdu.name} 2"}
    assert any(f"{pdu.name} 1" in line and "left as is" in line for line in done)


def test_each_listed_outlet_gets_its_own_board_port(lab):
    kwargs = dict(site_slug=lab.site.slug, device=lab.name("strip"))
    settings = {"type": "kasa", "host": "10.0.0.60"}

    client.connect_power(lab.nb, lab.board, settings=settings, outlets=["1", "2"], **kwargs)

    assert sorted(lab.connections(lab.board).values()) == [
        f"{lab.name('strip')} 1",
        f"{lab.name('strip')} 2",
    ]


def test_a_device_of_the_same_name_at_another_site_is_not_used(lab):
    elsewhere = lab._site(lab.name("elsewhere"))
    lab.add_device("pdu", settings=APC, outlets=("1",), site=elsewhere)

    client.connect_power(
        lab.nb,
        lab.board,
        site_slug=lab.site.slug,
        device=lab.name("pdu"),
        settings=APC,
        outlets=["1"],
    )

    assert lab.device(lab.name("pdu")) is not None  # created at the board's site


def test_a_power_role_and_manufacturer_made_by_hand_under_other_slugs_are_reused():
    nb = FakeNetBox()
    nb.add_site("lab3")
    client.ensure_schema(nb)
    board = client.create_or_update_device(
        nb, "b1", carrier="zcu102", site_slug="lab3", custom_fields={}
    )
    nb.dcim.manufacturers.create(name=client.POWER_MANUFACTURER_NAME, slug="generic-hw")
    nb.dcim.device_roles.create(name=client.POWER_ROLE_NAME, slug="power", color="ff9800")

    client.connect_power(nb, board, site_slug="lab3", device="pdu", settings=APC, outlets=["1"])

    (pdu,) = nb.dcim.devices.filter(name="pdu")
    assert pdu.role.slug == "power"
    assert len(list(nb.dcim.manufacturers.filter(name=client.POWER_MANUFACTURER_NAME))) == 1


# --- power answers <-> NetBox -------------------------------------------------


def test_settings_keep_the_type_and_the_fields_that_identify_the_device():
    pdu = POWER_TYPES["cyberpower"]
    context = {"power_host": "10.0.0.20", "power_outlet": "4"}

    assert client.power_settings(pdu, context) == {"type": "cyberpower", "address": "10.0.0.20"}
    assert client.power_answers({"type": "cyberpower", "address": "10.0.0.20"}) == (
        "cyberpower",
        {"power_host": "10.0.0.20"},
    )


@pytest.mark.parametrize(
    "settings",
    [{}, {"type": "no-such-type"}, {"type": "cyberpower"}, "not a mapping"],
)
def test_settings_that_do_not_name_a_type_and_its_fields_are_not_used(settings):
    assert client.power_answers(settings) is None


@pytest.mark.parametrize(
    ("key", "value", "names"),
    [
        ("apc", "4", ["4"]),
        ("kasa", "1, 2", ["1", "2"]),
        ("kasa", "", [client.SINGLE_OUTLET]),
        ("vesync", None, [client.SINGLE_OUTLET]),
    ],
)
def test_outlet_names_follow_the_outlet_answer(key, value, names):
    assert client.outlet_names(POWER_TYPES[key], value) == names


@pytest.mark.parametrize(
    ("key", "outlet", "outlets", "value"),
    [
        ("apc", "4", 8, "4"),
        ("apc", "Outlet 4", 8, None),  # not a number: asked, with 4 offered
        ("kasa", "2", 3, "2"),
        ("kasa", "1", 1, ""),  # a single plug: all of it
        ("sigrok", "CH1", 2, "CH1"),
    ],
)
def test_outlet_answer_from_a_netbox_outlet(key, outlet, outlets, value):
    assert client.outlet_answer(POWER_TYPES[key], outlet, outlets) == value


def test_device_exists_looks_only_at_the_site(lab):
    elsewhere = lab._site(lab.name("elsewhere"))
    lab.add_device("switch", site=elsewhere)

    assert client.device_exists(lab.nb, lab.board.name, lab.site.slug)
    assert not client.device_exists(lab.nb, lab.name("switch"), lab.site.slug)


@pytest.mark.parametrize(
    ("outlet", "label"), [("4", "pdu outlet 4"), ("Outlet 4", "pdu Outlet 4"), ("A1", "pdu A1")]
)
def test_outlets_are_named_without_saying_outlet_twice(outlet, label):
    assert client.outlet_label("pdu", outlet) == label


# --- serial console and JTAG ------------------------------------------------

UART_PATH = "/dev/serial/by-id/usb-Silicon_Labs_CP2108_Quad_USB_to_UART_Bridge_0001-if00-port0"


def _uart(lab, board, host, port, path=UART_PATH):
    return client.connect_console(
        lab.nb, board, kind=client.UART, site_slug=lab.site.slug, device=host, port=port, path=path
    )


def test_console_devices_lists_ports_with_their_path_and_what_they_feed(lab):
    host = lab.add_device("host", servers=("ttyUSB0", "JTAG 1", "spare"))
    other = lab.add_device("other", consoles=("UART", "JTAG"))
    lab.cable(other, "UART", host, "ttyUSB0", kind="console")
    lab.cable(other, "JTAG", host, "JTAG 1", kind="console")
    port = lab.server_port(host, "spare")
    port.custom_fields[client.SERIAL_PATH_FIELD] = "/dev/ttyUSB3"
    port.save()
    lab.add_device("pdu", outlets=("1",))  # no console server ports: not listed

    (found,) = client.console_devices(lab.nb, lab.site.slug)

    assert found.name == lab.name("host")
    assert [(p.name, p.path, p.connected_to, p.jtag) for p in found.ports] == [
        ("JTAG 1", "", f"{other.name} JTAG", True),
        ("spare", "/dev/ttyUSB3", None, False),
        ("ttyUSB0", "", f"{other.name} UART", False),
    ]


def test_a_new_console_server_is_created_with_the_port_and_its_path(lab):
    name = lab.name("lab-host-03")

    done = _uart(lab, lab.board, name, "ttyUSB0")

    host = lab.device(name)
    assert host.role.slug == client.CONSOLE_ROLE_SLUG
    assert lab.server_port(host, "ttyUSB0").custom_fields[client.SERIAL_PATH_FIELD] == UART_PATH
    assert lab.connections(lab.board, "console") == {"UART": f"{name} ttyUSB0"}
    (uart,) = lab.nb.dcim.console_ports.filter(device_id=lab.board.id)
    assert getattr(uart.speed, "value", uart.speed) == 115200  # the templates' baud rate
    assert any("created console server" in line for line in done)


def test_the_exporter_host_already_in_netbox_gets_the_port(lab):
    host = lab.add_device("lab-host-03")  # a plain server, no console server ports yet

    _uart(lab, lab.board, host.name, "ttyUSB0")

    assert lab.count("devices", name=host.name) == 1
    assert lab.connections(lab.board, "console") == {"UART": f"{host.name} ttyUSB0"}


def test_an_empty_serial_path_is_filled_in_and_a_different_one_kept(lab):
    host = lab.add_device("host", servers=("A", "B"))
    port = lab.server_port(host, "B")
    port.custom_fields[client.SERIAL_PATH_FIELD] = "/dev/ttyUSB1"
    port.save()
    board2 = lab.add_device("board2")

    _uart(lab, lab.board, host.name, "A")
    done = _uart(lab, board2, host.name, "B", path="/dev/ttyUSB9")

    assert lab.server_port(host, "A").custom_fields[client.SERIAL_PATH_FIELD] == UART_PATH
    assert lab.server_port(host, "B").custom_fields[client.SERIAL_PATH_FIELD] == "/dev/ttyUSB1"
    assert any("differs" in line for line in done)


def test_a_console_port_feeding_another_board_is_refused_and_nothing_is_written(lab):
    host = lab.add_device("host", servers=("ttyUSB0",))
    other = lab.add_device("other", consoles=("UART",))
    lab.cable(other, "UART", host, "ttyUSB0", kind="console")

    with pytest.raises(RuntimeError, match=f"already feeds {other.name} UART"):
        _uart(lab, lab.board, host.name, "ttyUSB0")

    assert lab.connections(lab.board, "console") == {}
    assert not lab.server_port(host, "ttyUSB0").custom_fields.get(client.SERIAL_PATH_FIELD)


def test_the_board_keeps_uart_and_jtag_on_their_own_console_ports(lab):
    board = lab.add_device("board2", consoles=("JTAG", "Console"))
    host = lab.name("host")

    _uart(lab, board, host, "ttyUSB0")
    done = client.connect_console(
        lab.nb, board, kind=client.JTAG, site_slug=lab.site.slug, device=host, port="JTAG 1"
    )

    assert lab.connections(board, "console") == {
        "Console": f"{host} ttyUSB0",
        "JTAG": f"{host} JTAG 1",
    }
    assert not lab.server_port(lab.device(host), "JTAG 1").custom_fields.get(
        client.SERIAL_PATH_FIELD
    )
    assert not [line for line in done if "also connected" in line]


def test_console_connections_run_again_change_nothing(lab):
    host = lab.name("host")
    _uart(lab, lab.board, host, "ttyUSB0")

    done = _uart(lab, lab.board, host, "ttyUSB0")

    assert lab.connections(lab.board, "console") == {"UART": f"{host} ttyUSB0"}
    assert lab.count("console_ports", device_id=lab.board.id) == 1
    assert any("already connected" in line for line in done)


# --- SD mux: board SD interface -> the mux's DUT interface --------------------

SDMUX = {"sdmux_path": "/dev/sg3", "boot_partition": "/dev/disk/by-id/usb-mux-0:0-part1"}


def _mux(lab, base="mux", *, settings=None, serial="", interfaces=(client.SDMUX_PORT,)):
    custom_fields = {client.SDMUX_FIELD: settings} if settings else None
    return lab.add_device(
        base,
        role=client.SDMUX_ROLE_SLUG,
        serial=serial,
        interfaces=interfaces,
        custom_fields=custom_fields,
    )


def _sdmux(lab, board, device, settings=SDMUX, serial=""):
    return client.connect_sdmux(
        lab.nb, board, site_slug=lab.site.slug, device=device, serial=serial, settings=settings
    )


def test_sd_muxes_lists_the_site_s_muxes_with_their_settings_serial_and_what_they_feed(lab):
    used = _mux(lab, "mux-a", settings=SDMUX, serial="000000001234")
    _mux(lab, "mux-b", interfaces=())  # made by hand: no settings, no DUT interface yet
    usb = _mux(lab, "mux-c", interfaces=(client.SDMUX_PORT, "USB"))
    other = lab.add_device("other", interfaces=(client.SD,))
    lab.cable(other, client.SD, used, client.SDMUX_PORT, kind="sd")
    host = lab.add_device("host", interfaces=("usb1",))
    lab.cable(usb, "USB", host, "usb1", kind="sd")  # its host side: not what it feeds
    lab.add_device("switch", interfaces=(client.SDMUX_PORT,))  # not an SD mux
    elsewhere = lab._site(lab.name("elsewhere"))
    lab.add_device("mux-elsewhere", role=client.SDMUX_ROLE_SLUG, site=elsewhere)

    muxes = client.sd_muxes(lab.nb, lab.site.slug)

    assert [(m.name, m.serial, m.settings, m.connected_to) for m in muxes] == [
        (used.name, "000000001234", SDMUX, f"{other.name} {client.SD}"),
        (lab.name("mux-b"), "", {}, None),
        (usb.name, "", {}, None),
    ]


def test_a_site_without_the_sd_mux_role_has_no_muxes():
    nb = FakeNetBox()
    nb.add_site("lab3")

    assert client.sd_muxes(nb, "lab3") == []


def test_a_new_sd_mux_is_created_with_its_serial_and_settings_and_cabled_to_the_board(lab):
    name = lab.name("b1-sdmux")

    done = _sdmux(lab, lab.board, name, serial="000000001234")

    mux = lab.device(name)
    assert mux.role.slug == client.SDMUX_ROLE_SLUG
    assert mux.device_type.slug == client.SDMUX_ROLE_SLUG
    assert mux.serial == "000000001234"
    assert mux.custom_fields[client.SDMUX_FIELD] == SDMUX
    assert lab.connections(lab.board, "sd") == {client.SD: f"{name} {client.SDMUX_PORT}"}
    assert any("created SD mux" in line for line in done)


def test_a_hand_made_mux_gets_its_dut_interface_its_empty_settings_and_serial(lab):
    mux = _mux(lab, interfaces=())

    done = _sdmux(lab, lab.board, mux.name, serial="000000001234")

    assert lab.count("devices", name=mux.name) == 1
    assert lab.connections(lab.board, "sd") == {client.SD: f"{mux.name} {client.SDMUX_PORT}"}
    found = lab.device(mux.name)
    assert found.custom_fields[client.SDMUX_FIELD] == SDMUX
    assert found.serial == "000000001234"
    assert any("recorded the SD mux settings" in line for line in done)


def test_sd_mux_settings_and_serial_already_in_netbox_are_kept(lab):
    theirs = {"sdmux_path": "/dev/sg1", "boot_partition": "/dev/sdb1"}
    mux = _mux(lab, settings=theirs, serial="000000000001")

    done = _sdmux(lab, lab.board, mux.name, serial="000000009999")

    found = lab.device(mux.name)
    assert found.custom_fields[client.SDMUX_FIELD] == theirs
    assert found.serial == "000000000001"
    assert any("differ" in line for line in done)


def test_an_sd_mux_feeding_another_board_is_refused_and_nothing_is_written(lab):
    mux = _mux(lab)
    other = lab.add_device("other", interfaces=(client.SD,))
    lab.cable(other, client.SD, mux, client.SDMUX_PORT, kind="sd")

    with pytest.raises(RuntimeError, match=f"already feeds {other.name} {client.SD}"):
        _sdmux(lab, lab.board, mux.name)

    assert lab.connections(lab.board, "sd") == {}
    assert not lab.device(mux.name).custom_fields.get(client.SDMUX_FIELD)


def test_the_board_s_network_interface_is_not_used_for_its_sd_card(lab):
    board = lab.add_device("board2", interfaces=("eth0",))

    _sdmux(lab, board, lab.name("mux"))

    assert lab.connections(board, "sd") == {"eth0": "", client.SD: f"{lab.name('mux')} DUT"}


def test_sd_mux_connection_run_again_changes_nothing(lab):
    name = lab.name("mux")
    _sdmux(lab, lab.board, name)

    done = _sdmux(lab, lab.board, name)

    assert lab.connections(lab.board, "sd") == {client.SD: f"{name} {client.SDMUX_PORT}"}
    assert lab.count("interfaces", device_id=lab.board.id) == 1
    assert any("already connected" in line for line in done)
