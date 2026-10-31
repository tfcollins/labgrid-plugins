NetBox Onboarding
=================

``adi-lg netbox add-hardware`` automates the whole of :doc:`onboarding-a-lab-host` Steps 2-4
for a single new board: it registers the board as a device in NetBox and records which outlet
powers it, which ports its serial console and JTAG are plugged into and which SD mux its card is
in, renders and validates
its exporter config, deploys that config to the exporter host as a systemd service and verifies
it comes up, then creates the matching labgrid Place on the coordinator (``create`` /
``add-match`` / ``set-tags``). Run it instead of hand-editing a template and typing
``labgrid-client`` commands.

**On this page:**

- `Prerequisites`_
- `Usage`_ — `Board template`_, `Boot strategy`_, `Options`_
- `Power devices`_
- `Serial console and JTAG`_
- `SD mux`_
- `What it creates`_ — `In NetBox`_, `On the exporter host`_, `On the coordinator`_
- `Resuming after a failure`_
- `Re-running for an existing board`_
- `Troubleshooting`_
- `How it maps to the manual procedure`_

.. admonition:: What it does NOT do
   :class: note

   It does not physically rack or cable the board (it records the power, serial, JTAG and SD mux
   cables in NetBox, it doesn't plug them in), and it does not install ``labgrid-exporter`` on the
   host - both are prerequisites, checked below.

Prerequisites
-------------

- Run from within a ``labgrid-plugins`` checkout (``exporter_configs/`` and its templates live
  at the repo root, outside the installed package), or pass ``--exporter-configs-dir``.
- ``pip install -e ".[netbox]"`` (adds ``pynetbox``, ``jinja2``, ``jsonschema`` - not installed
  by default).
- NetBox **4.3 or newer** - custom fields are created with the ``object_types`` key that NetBox
  4.3 introduced (it replaced ``content_types``).
- A NetBox URL and API token with permission to create devices, power ports, power outlets,
  console ports, console server ports, interfaces and cables (plus, the first time, device roles,
  manufacturers, device types and custom fields) (``NETBOX_URL`` / ``NETBOX_TOKEN`` env vars,
  or ``--netbox-url`` / ``--netbox-token``).
- The NetBox **Site** you'll place the device under must already exist - this command creates
  the ``labgrid-target`` device role, its custom fields, and board device types on first run,
  but deliberately never creates a Site (physical-location truth the org manages elsewhere).
- Coordinator API credentials for a user who can create places (``LG_API_USERNAME`` /
  ``LG_API_PASSWORD``, or ``--coord-user`` / ``--coord-password``) - every write endpoint under
  ``/places`` requires an authenticated session, unlike the read-only ``/api/places``.
- Power credentials, for the types that have them, in ``/etc/labgrid/exporter.env`` on the
  exporter host (root-owned, mode ``600``) - e.g. ``VESYNC_USERNAME`` / ``VESYNC_PASSWORD``,
  ``HOMEASSISTANT_URL`` / ``HOMEASSISTANT_TOKEN``, or the optional ``KASA_*`` / ``TASMOTA_*``
  (see :ref:`power-types`). The generated unit loads this file; the deployed config only
  references the variables, so secrets never pass through the command. Missing required
  variables are reported as a warning after deploy.
- SSH access to the exporter host as ``user@host``, with:

  - **passwordless sudo** for that user (needed to write under ``/etc`` and run ``systemctl``),
  - ``labgrid-exporter`` **already installed** and on that user's ``PATH`` over SSH -
    checked up front with ``command -v labgrid-exporter``, and the generated systemd unit
    runs the absolute path that resolves to, so a venv or ``~/.local/bin`` install works.

Usage
-----

.. code-block:: console

    $ adi-lg netbox add-hardware

    A unique name for this board. It names the NetBox device, the coordinator place
    and the exporter service (labgrid-exporter-<name>).
    Board name (e.g. zcu102-ad9081-lab3): zcu102-lab3-001

    The FPGA or SoC board the ADI part is mounted on. Saved in NetBox and as the
    place's carrier tag; most templates also use it in the resource group name.
    Carrier board (e.g. zcu102, zc706, vcu118): zcu102

    The ADI part under test. Saved in NetBox and as the place's daughter-board tag;
    most templates also use it in the resource group name.
    ADI daughter board or chip (e.g. ad9081, adrv9009): ad9081

    The self-hosted GitHub Actions runner that runs this board's hardware-CI jobs
    (the place's runner tag).
    GitHub Actions runner label (hw-zcu102):

    The NetBox instance to register the board in (or set NETBOX_URL).
    NetBox URL (e.g. https://netbox.example.com): https://netbox.example.com

    A NetBox API token that can create devices; create one under your user profile
    in NetBox (or set NETBOX_TOKEN).
    NetBox API token (input hidden):     received 57 characters
    NetBox TLS certificate not verified (--netbox-verify or --netbox-ca-bundle to
    check it)

    The existing NetBox site the board is in (NetBox: Organization > Sites). This
    command never creates sites.
    #   Site   Name
    ────────────────────
    1   lab3   Lab 3
    2   lab4   Lab 4
    NetBox site slug: lab3

    The device that switches this board's power (PDU, smart plug, relay, ...). Pick
    one from NetBox to use its settings, or add a new one; the board's power port is
    cabled to the outlet you choose.

    Power devices in NetBox at lab3
    #   Device      Type         Address     Free outlets
    ──────────────────────────────────────────────────────────────────────────────
    1   pdu-rack3   cyberpower   10.0.0.20   6 of 8
    2   new                                  a power device not in NetBox yet: add it
    Power device: pdu-rack3
      pdu-rack3: CyberPower PDU (SNMP) (cyberpower), settings from NetBox
    #   Outlet     Feeds
    ──────────────────────────────────────────────────
    1   Outlet 1   zc706-lab3-002 PSU1
    2   Outlet 2   zcu102-lab3-000 power
    3   Outlet 3   free
    ...
    9   new        an outlet not in NetBox yet: add it
    Outlet on pdu-rack3: Outlet 3
      Outlet number (3):

    The Linux machine the board's serial, USB and power are connected to. The
    exporter service is installed there over SSH, so this user needs passwordless
    sudo.
    Exporter host SSH login (user@host): labadmin@lab-host-03

    The device the board's serial console (USB-UART) is plugged into - usually the
    exporter host. Pick it from NetBox or add it; the board's UART console port is
    cabled to the port you choose.

    Devices with console server ports in NetBox at lab3
    #   Device        Address     Free ports
    ──────────────────────────────────────────────────────────────────────────────
    1   lab-host-03   10.0.0.40   2 of 4
    2   new                       a device not listed: add it, or add ports to it
    Serial device (lab-host-03):
    #   Port      Serial path                                         Feeds
    ──────────────────────────────────────────────────────────────────────────────
    1   ttyUSB0   /dev/serial/by-id/usb-FTDI_Quad_RS232-HS-if00-...   zcu102-lab3-000 UART
    2   ttyUSB1   /dev/serial/by-id/usb-FTDI_Quad_RS232-HS-if01-...   free
    ...
    5   new                                                           a port not in NetBox yet: add it
    Serial port on lab-host-03: ttyUSB1

    The device the board's JTAG cable (USB-JTAG) is plugged into - usually the
    exporter host. ... none: the board has no JTAG cable, so no JTAG template suits
    it.

    Devices with console server ports in NetBox at lab3
    #   Device        Address     Free ports
    ──────────────────────────────────────────────────────────────────────────────
    1   lab-host-03   10.0.0.40   1 of 4
    2   skip                      it has one: don't record it in NetBox
    3   none                      the board has no JTAG cable
    4   new                       a device not listed: add it, or add ports to it
    JTAG device (lab-host-03): none

    The USB SD mux the board's SD card is in. ... none: its SD card isn't in one, so
    no SD mux template suits it.

    SD muxes in NetBox at lab3
    #   SD mux      Serial         Control device   Feeds
    ──────────────────────────────────────────────────────────────────────────────
    1   mux-rack3   000000001234   /dev/sg3         zcu102-lab3-000 SD
    2   mux-b       000000004321   /dev/sg4         free
    3   none                                        the board's SD card isn't in an SD mux
    4   new                                         an SD mux not in NetBox yet: add it
    SD mux (mux-b):

    Board templates
    #   Template    Fit           Boot strategy    Description
    ──────────────────────────────────────────────────────────────────────────────
    1   soc-sdmux   recommended   BootFPGASoC      SoC booted from an SD card through a
                                                   USB SD mux
    2   rpi-ssh     fits          BootRPI          Raspberry Pi driven over SSH
    3   soc-ssh     fits          BootFPGASoCSSH   SoC whose boot files are updated over SSH
    Not offered: they use hardware the board doesn't have.
      fabric-jtag needs JTAG
      soc-tftp needs JTAG
      zynqmp-jtag needs JTAG
    Board template (soc-sdmux):

    Boot strategies
    #   Strategy          Fit           Description
    ────────────────────────────────────────────────────────────────────────────────
    1   BootFPGASoC       recommended   BootFPGASoC strategy for FPGA SoC devices
                                        using Kuiper releases.
    2   BootFPGASoCSSH    also runs     Strategy to boot an FPGA SoC device using
                                        ShellDriver and SSHDriver.
    ...
    5   BootTickFPGASSH   also runs     BootFPGASoCSSH + runtime Tick deploy
                                        (bitstream, overlay, module).
    Not offered: soc-sdmux doesn't export what they bind.
      BootFabric needs XilinxDeviceJTAG, XilinxVivadoTool
      ...
      BootOpenFPGALoader needs USBDebugger or XilinxDeviceJTAG
    Boot strategy (BootFPGASoC):

    Template fields for soc-sdmux
    Field               Question                             Default
    ──────────────────────────────────────────────────────────────────────────────
    target_ip           Board IP address, for SSH to its     required
                        Linux
    kuiper_bootbin      BOOT.BIN, as release:<path> or a     unset
                        file on the test runner
    ...
    target_password     Board Linux SSH password             analog
    target_username     Board Linux SSH username             root
      Board IP address, for SSH to its Linux (required): 10.0.0.42
      BOOT.BIN, as release:<path> or a file on the test runner (Enter to leave
    unset): release:zynqmp-zcu102-rev10-ad9081/m8_l4/BOOT.BIN
      ...
      Board Linux SSH password (Enter for analog):
      Board Linux SSH username (Enter for root):

    Plan
      NetBox device       zcu102-lab3-001 (site lab3)
      Carrier / chip      zcu102 / ad9081
      Exporter host       labadmin@lab-host-03
      Systemd unit        labgrid-exporter-zcu102-lab3-001
      Exporter config     /tmp/adi-lg-netbox-xxxxxxxx/soc-sdmux.yaml (rendered +
                          validated)
      Resource groups     ZCU102_AD9081
      Coordinator place   zcu102-lab3-001
      Place matches       zcu102-lab3-001/ZCU102_AD9081/*
      Place tags          daughter-board=ad9081
                          carrier=zcu102
                          boot-strategy=BootFPGASoC
                          runner=hw-zcu102
                          power-driver=CyberPowerDriver
      Power               CyberPower PDU (SNMP) (cyberpower)
                          via CyberPowerDriver
      Power in NetBox     zcu102-lab3-001 power port -> pdu-rack3 Outlet 3
      Serial in NetBox    zcu102-lab3-001 UART -> lab-host-03 ttyUSB1
                          serial device /dev/serial/by-id/usb-FTDI_Quad_RS232-HS-if01-port0
      SD mux in NetBox    zcu102-lab3-001 SD -> mux-b DUT
                          control device /dev/sg4
                          boot partition /dev/disk/by-id/usb-LinuxAut_sdmux_HS-SD_MMC_000000004321-0:0-part1

    Proceed? [y/n] (y): y
    NetBox device ready: https://netbox.example.com/dcim/devices/95/
      connected zcu102-lab3-001 power to pdu-rack3 Outlet 3
      connected zcu102-lab3-001 UART to lab-host-03 ttyUSB1
      connected zcu102-lab3-001 SD to mux-b DUT
    ...

The questions go from what the board is (name, carrier, chip, runner), to where it is and what
it is wired to (site, power, exporter host, serial console, JTAG cable, SD mux), to the template
that suits that hardware, its boot strategy and the template's own fields.

Each set of options is listed as a numbered table; answer with the number or the name,
or press Enter for the default shown in parentheses.

Use ``--dry-run`` to render and schema-validate the exporter config and print the full plan
without touching NetBox, SSH, or the coordinator - useful for checking your answers before
committing to a real board. A dry run never asks for NetBox or coordinator credentials and
doesn't read NetBox: the site is typed, the power type and its fields are asked directly,
*Does the board have a JTAG cable?* and *Is the board's SD card in a USB SD mux?* stand in for
the JTAG and SD mux picks to recommend the template, the serial console device and the SD mux's
devices are asked as template fields, and the plan says the power device, serial port, JTAG port
and SD mux are chosen when run without ``--dry-run``.

Each question says what the answer is used for. Template fields are asked by what they are
(*Board IP address*, *Board Linux SSH password*, ...), after a table of the
template's fields with each one's default. Fields with no default (``target_ip`` in every
template, plus ``bitstream_path`` and ``kernel_path`` in ``fabric-jtag``) are asked first,
marked *(required)*, and asked again if left blank; the same applies to a power type's
required fields. Pressing Enter on any other field keeps the template's default (see
``exporter_configs/templates/*.yaml``). Malformed answers are asked again on the spot: the
board name, carrier and daughter board take letters, digits, ``.``, ``_`` and ``-`` only,
the site must be a slug, the SSH login must be ``user@host``, and the NetBox URL must start
with ``http://`` or ``https://``.

The templates name their resource group ``<CARRIER>_<CHIP>`` (e.g. ``ZCU102_AD9081``) from
the ``carrier`` and ``chip`` fields. The command fills those from the *Carrier board* and
*ADI daughter board or chip* answers, so they are not asked again as template fields. The
*Board template* list recommends the templates that use the board's hardware (see
`Board template`_); the *Boot strategy* prompt then offers only the strategies that can run on
what the chosen template exports (see `Boot strategy`_), the one the template declares first and
as the default. The power type - picked from NetBox's power device, or asked
as *Power category* and *Power type* (see `Power devices`_) - chooses the template's
``power`` fragment: any of the types in :ref:`power-types`, covering this package's outlets
and all of labgrid's power options. The command sets the place's ``power-driver`` tag, plus
``power-output-driver`` for relay types. Credentials, reachability notes (e.g. ``tasmota``
and ``laa`` connect from the client) and required host tools are printed in the plan.

Board template
~~~~~~~~~~~~~~

A template (``exporter_configs/templates/*.yaml``) is the set of resources the board's exporter
publishes. Beyond the serial console and network every board has, some use hardware only some
boards have: ``fabric-jtag``, ``soc-tftp`` and ``zynqmp-jtag`` program the board over a JTAG
cable (``XilinxDeviceJTAG``, ``XilinxVivadoTool``), and ``soc-sdmux`` boots it from an SD card in
a USB SD mux (``USBSDMuxDevice``, ``MassStorageDevice``). The *JTAG device* and *SD mux* answers
say which of these the board has (*none* for one it hasn't), so the *Board template* list:

- marks *recommended* the templates that use the most of the board's hardware, and lists them
  first; the first is the default. With a JTAG cable that is all three JTAG templates, with an
  SD mux ``soc-sdmux``, with neither ``rpi-ssh`` and ``soc-ssh``. A tie stays a tie, in name
  order - the carrier name isn't used to guess - so pick the one for the board's boot flow (see
  :doc:`exporter-setup`);
- marks *fits* the other templates the board can use (``soc-ssh`` needs only the serial console
  and network, so one always fits);
- lists under the table the templates that use hardware the board doesn't have, with what each
  needs (``soc-sdmux needs SD mux``); they can't be picked.

What hardware a template uses is read from the resource classes it exports, so a new template
needs no change here. A template saved by an earlier run that the board's hardware no longer
suits - a dry run was told the board has a JTAG cable, and the real run's *JTAG device* is
*none* - is asked again.

Boot strategy
~~~~~~~~~~~~~

The place's ``boot-strategy`` tag makes render-env emit that strategy's labgrid config (see
:doc:`hardware-ci`), and every driver in it must find the resources it binds among the ones
the board's exporter publishes. So the *Boot strategy* prompt lists only the ADI strategies
(``BootFPGASoC``, ``BootFPGASoCSSH``, ``BootFPGASoCTFTP``, ``BootSelMap``, ``BootFabric``,
``BootRPI``, ``BootVPK180``, ``BootZynqMPJTAG``, ``BootZynq7000JTAGRecovery``,
``BootNoOSJTAG``, ``BootOpenFPGALoader``, ``BootTickFPGASSH``) whose config binds to what
the template exports:

- the strategy the template is written for (its ``## boot-strategy:`` line) comes first,
  marked *recommended*, and is the default;
- the others that also bind are marked *also runs* - ``soc-sdmux``, for example, also serves
  ``BootFPGASoCSSH``;
- the rest are listed under the table with what they need that the template doesn't export
  (``BootFPGASoC`` needs the SD mux's ``USBSDMuxDevice`` and ``MassStorageDevice``, for
  example), and can't be picked.

What each strategy needs is read from its render-env config
(``adi_lg_plugins/hw_ci/templates/<strategy>.yaml``) and the labgrid ``bindings`` of the drivers
it lists, so a new template or strategy needs no change here. Resources a config defines itself,
like ``BootFPGASoCTFTP``'s TFTP server on the test runner, aren't needed from the exporter.
A strategy saved by an earlier run that the template can't run is asked again on resume.

Options
~~~~~~~

Every option is optional; anything not supplied is prompted for.

* ``--netbox-url <url>``: NetBox base URL (env: ``NETBOX_URL``).
* ``--netbox-token <token>``: NetBox API token (env: ``NETBOX_TOKEN``).
* ``--netbox-verify``: verify NetBox's TLS certificate against Python's CA bundle. Off by
  default: lab NetBox instances often sit behind an internal CA, so the certificate is not
  checked unless you ask.
* ``--netbox-ca-bundle <path>``: verify NetBox's TLS certificate against this CA bundle, for a
  NetBox behind an internal CA (env: ``NETBOX_CA_BUNDLE``).
* ``--coord <host:port>``: coordinator to deploy against and create the place on (default:
  ``$LG_COORDINATOR``).
* ``--coord-user <name>``: coordinator API username (env: ``LG_API_USERNAME``).
* ``--coord-password <password>``: coordinator API password (env: ``LG_API_PASSWORD``).
* ``--exporter-configs-dir <path>``: the ``exporter_configs/`` directory (default: searched
  upward from the current directory for ``exporter_configs/validate.py``).
* ``--dry-run``: render, validate, and print the plan; make no changes.

NetBox credentials that are not set by option or environment are asked for before the site,
because the site, the board's power device, its serial and JTAG ports and its SD mux are picked
from what NetBox holds; nothing is written to NetBox until you confirm ``Proceed?``. Coordinator credentials are asked for after
``Proceed?``. The token and password prompts hide what you type or paste, so nothing appears
on screen; after each one the command prints how many characters it received. Blank answers
are asked again.

Power devices
-------------

NetBox records a board's power the standard way: a cable from a **power port** on the board to
an **outlet** on the **power device** that switches it - a PDU, smart plug, relay card, USB hub
or bench supply. The command lists the devices with power outlets that NetBox has at the
board's site, with their labgrid power type, address and how many outlets are free:

- **Pick one** and its labgrid settings come from NetBox: only the outlet is asked, from a
  table of the device's outlets and what each one feeds. An outlet that already feeds another
  device can't be picked (one that feeds this board can, when you run the command again).
  When the outlet's name isn't the number labgrid needs (``Outlet 3``), the number is asked,
  with the one in the name as its default. *new* adds an outlet the device doesn't have in
  NetBox yet.

  A device added to NetBox by hand has no labgrid settings, so the first board on it asks its
  *Power category*, *Power type* and the fields that identify it (its primary IP is offered as
  the address); they are saved on the device, and the next board on it asks only the outlet.
- **Pick new** for a power device NetBox doesn't have: *Power category*, *Power type* and the
  type's fields are asked, then the device's name in NetBox, suggested from the type and its
  address (``cyberpower-10.0.0.20``). With no power devices at the site, this is where the
  command starts.

.. code-block:: console

    Power device: new

    Power control
    #   Category                       Types
    ...
    Power type (apc): cyberpower
      PDU hostname or IP: 10.0.0.20
      Outlet number: 4

    The new power device is added to NetBox under this name, at the board's site.
    Power device name in NetBox (cyberpower-10.0.0.20):

A few types have no outlet field: a VeSync, Home Assistant or Tasmota plug, an HTTP output and
an LAA each switch one thing, so their power device has a single outlet, ``1`` - as does a Kasa
strip used whole (blank socket answer). A comma-separated Kasa socket list cables the board to
each socket. Settings that belong to the board's connection rather than the device (a relay's
*Invert output*, an LAA's switch-on and switch-off states) are asked for every board. Manual
power (the ``manual`` type) is not recorded in NetBox.

Serial console and JTAG
-----------------------

The board's serial console is recorded the same way, with NetBox's console components: a
``UART`` **console port** on the board, cabled to a **console server port** on the device its
USB-UART is plugged into - usually the exporter host, or a USB-serial adapter box. After the
*Exporter host SSH login*, the command lists the site's devices that have console server
ports, with how many ports are free; the exporter host (matched by name, short name or primary
IP) is the default.

- **Pick a device**, then a port from a table of its ports, each with its serial path and what
  it feeds. A port that feeds another board can't be picked, and one recorded as a JTAG cable
  isn't offered. The port's serial path - its ``labgrid_serial_path`` custom field - answers the
  template's *Serial console device on the exporter host*, so that question isn't asked. A port
  made by hand has no path yet: it is asked (``/dev/ttyUSB2`` for a port named ``ttyUSB2``) and
  saved on the port. *new* adds a port: its path is asked, and the port is named after the
  device file (a name over NetBox's 64 characters keeps its end, where a multi-port adapter's
  ``-if01-port0`` tells its ports apart).
- **Pick new** for a device the list doesn't have - for example the exporter host, when NetBox
  has it as a plain server without console server ports. Its name is asked (default: the
  exporter host's short name). A device of that name at the site gets the new port; otherwise
  the device is created. With no console server ports at the site, this is where the command
  starts.

The serial path is the device on the *exporter host*, the same as the template field: prefer a
stable ``/dev/serial/by-id/...`` path over ``/dev/ttyUSB0``, which can change on reboot.

**JTAG**: every board is asked where its JTAG cable is plugged in, before its template, which
the answer helps pick (see `Board template`_). NetBox has no JTAG (or USB) port type, so the
cable is recorded as a ``JTAG`` console port on the board, cabled to a console server port - by
default on the same device as the serial console - whatever template is picked. It is a record
of the wiring only: labgrid's JTAG settings (the xsdb ``root_target``) don't depend on it. The
*JTAG device* list adds *none*, for a board without a JTAG cable (the JTAG templates aren't
offered then), and *skip*, to leave out of NetBox a cable the board has. Ports with a serial path, or that feed a serial console, aren't offered for JTAG; a new
JTAG port's name is asked (default ``JTAG``, or ``JTAG 2``, ... if taken).

.. code-block:: console

    JTAG device (lab-host-03):
    JTAG port name on lab-host-03 in NetBox (JTAG):

SD mux
------

A USB SD mux switches a board's SD card between the board and the exporter host, so a template
that exports one (``USBSDMuxDevice``, today ``soc-sdmux``) can write the boot files to the card.
NetBox has no SD card component, so the card slot is recorded the way JTAG is: an ``SD``
**interface** on the board, cabled to the ``DUT`` interface of the **SD mux**, a device with the
``labgrid-sd-mux`` role. After the serial console and JTAG, every board is asked about its SD
mux, before its template: the command lists the site's SD muxes, with each one's serial number,
control device and what it feeds:

- **Pick one** and its ``labgrid_sdmux`` custom field - its control device (``/dev/sg*``) and
  the card's boot partition on the exporter host - answers the template's two SD mux questions,
  so they aren't asked. A mux that feeds another board can't be picked; with one free mux, it
  is the default. A mux added to NetBox by hand (give it the ``Labgrid SD Mux`` role, slug
  ``labgrid-sd-mux``, to have it listed) has no settings yet: the two devices are asked, with
  the template's defaults, and saved on it.
- **Pick new** for a mux NetBox doesn't have: its name (default ``<board>-sdmux``) and its USB
  serial number (``usbsdmux /dev/sg0 info``, or the label; Enter leaves it unset) are asked,
  then the two devices.
- **Pick none** if the board's SD card isn't in a mux: ``soc-sdmux`` isn't offered then. It is
  the default when the site has no free mux.

A board's mux is recorded in NetBox whatever template is picked; only ``soc-sdmux`` uses its
devices.

.. code-block:: console

    SD muxes in NetBox at lab3
    #   SD mux      Serial         Control device   Feeds
    ──────────────────────────────────────────────────────────────────────────────
    1   mux-rack3   000000001234   /dev/sg3         zcu102-lab3-000 SD
    2   mux-b       000000004321   /dev/sg4         free
    3   none                                        the board's SD card isn't in an SD mux
    4   new                                         an SD mux not in NetBox yet: add it
    SD mux (mux-b):

As with the serial path, prefer stable ``/dev/disk/by-id/...`` paths for the boot partition:
``/dev/sg*`` and ``/dev/sd*`` numbers can change when USB devices are replugged.

What it creates
---------------

In NetBox
~~~~~~~~~

Schema objects are created only if missing, so the first run against a fresh NetBox sets them
up and later runs reuse them:

- **Device role** ``labgrid-target`` ("Labgrid Target").
- **Manufacturer** ``adi-lab`` ("Analog Devices, Inc. (lab hardware)").
- **Device type** per carrier: slug is the carrier lowercased with ``_`` → ``-``, model is the
  carrier uppercased (``zcu102`` → slug ``zcu102``, model ``ZCU102``).
- **Custom fields** on ``dcim.device`` (all text, except ``labgrid_power`` and ``labgrid_sdmux``):

  .. list-table::
     :header-rows: 1
     :widths: 25 35 40

     * - Field
       - Label
       - Value written
     * - ``carrier``
       - Carrier
       - the carrier you entered
     * - ``daughter_board``
       - Daughter board / chip
       - the daughter board you entered
     * - ``boot_strategy``
       - Boot strategy
       - the chosen strategy class
     * - ``exporter_host``
       - Exporter SSH target
       - ``user@host``
     * - ``runner_label``
       - GitHub runner label
       - the runner label
     * - ``labgrid_power``
       - Labgrid power control
       - on power devices only (JSON): the labgrid power type and the settings that identify
         the device, e.g. ``{"type": "cyberpower", "address": "10.0.0.20"}``

     * - ``labgrid_sdmux``
       - Labgrid SD mux
       - on SD muxes only (JSON): its control device and the card's boot partition on the
         exporter host, e.g. ``{"sdmux_path": "/dev/sg3", "boot_partition": "/dev/sda1"}``

- **Custom field** ``labgrid_serial_path`` ("Labgrid serial device path", text) on
  ``dcim.consoleserverport``: a serial port's device path on the exporter host.

Then the **device** itself, named after the board name, with that device type and role,
under the existing site. The command prints its URL
(``<netbox>/dcim/devices/<id>/``) when done.

Then its power (see `Power devices`_):

- The **power device** picked, or a new one at the board's site with role ``labgrid-power``
  ("Labgrid Power Control"), manufacturer ``generic`` ("Generic") and a device type per power
  type (slug ``labgrid-power-<type>``, model the type's description), each created if missing.
  An empty ``labgrid_power`` field is filled in from your answers; one that is already set is
  never replaced, and the command says so if it differs from this board's answers.
- The **outlet** picked, or a new one named after the outlet answer (``4``).
- A **power port** on the board: a free one it already has (e.g. from its device type), or a
  new one named ``power`` (``power 2``, ... if it has more).
- A **cable** from the port to the outlet. An outlet that already feeds another device is
  refused before anything is written. Cables already there are kept: if the board was on
  another outlet before, that cable is left in place and reported, for you to remove in NetBox.

Then its serial console and JTAG (see `Serial console and JTAG`_):

- The **device** picked, or the one named: an existing device at the site is used as it is;
  a missing one is created with role ``labgrid-console-server`` ("Labgrid Console Server"),
  manufacturer ``generic`` and device type ``labgrid-console-server``.
- The **console server port** picked, or a new one. A new serial port gets your path in
  ``labgrid_serial_path``; an existing port's empty path is filled in, and one already set is
  never replaced (the command says so if it differs).
- A **console port** on the board: a free one of the right kind it already has (``UART``,
  ``Console`` or ``Serial...`` for the serial console, ``JTAG...`` for JTAG), or a new one named
  ``UART`` (at 115200 baud, the templates' speed) or ``JTAG``.
- A **cable** from each console port to its console server port, with the same rules as the
  power cable.

Then its SD mux (see `SD mux`_):

- The **SD mux** picked, or a new one at the board's site with role ``labgrid-sd-mux``
  ("Labgrid SD Mux"), manufacturer ``generic`` and device type ``labgrid-sd-mux``, and the
  serial number you gave in its ``serial`` field. An empty ``labgrid_sdmux`` field or serial
  number is filled in; one already set is never replaced (the command says so if the settings
  differ).
- Its ``DUT`` **interface** (type *Other*), added if missing.
- An ``SD`` **interface** (type *Other*) on the board: a free ``SD...`` one it already has, or a
  new one. Its network interfaces are never used.
- A **cable** from ``SD`` to ``DUT``, with the same rules as the power cable.

Each change is printed under the device URL. The NetBox step counts as done only when the
board is registered *and* every cable is added, so a failure in any is redone on resume.

On the exporter host
~~~~~~~~~~~~~~~~~~~~

Files are staged under ``/tmp/adi-lg-netbox-stage/<name>/`` and then moved into place with
``sudo``:

- ``/etc/labgrid/exporters/<name>/resources.yaml`` - the rendered exporter config.
- ``/etc/systemd/system/labgrid-exporter-<name>.service`` - a unit that runs
  ``labgrid-exporter -n <name>`` (the absolute path found by the prerequisite check) as the
  SSH user, pointed at the coordinator, with ``Restart=always`` and
  ``EnvironmentFile=-/etc/labgrid/exporter.env`` (optional, for outlet credentials). The exporter registers on the
  coordinator under the hardware name, so one host can run a separate exporter per board.

The unit is enabled and (re)started (``systemctl enable`` then ``systemctl restart``), then
polled with ``systemctl is-active`` (10 attempts, 2 s apart). If it never becomes active, the command
fails and prints the last 50 lines of its journal.

On the coordinator
~~~~~~~~~~~~~~~~~~

Through the coordinator REST API (:doc:`coordinator`), authenticated as the coordinator user:

- ``POST /api/places`` - create the place, named after the board name, unless
  ``GET /api/places/<name>`` shows it already exists.
- ``POST /api/places/<name>/matches`` - one ``<name>/<group>/*`` match per resource group in
  the rendered config (``<name>`` is the exporter name the unit registers), skipping any the
  place already has.
- ``PUT /api/places/<name>/tags`` - ``daughter-board`` and ``carrier`` (lowercased),
  ``boot-strategy``, ``runner``, ``power-driver``, and (relay types) ``power-output-driver``, the keys the hardware-CI preflight matches on (see the tag
  table in :doc:`onboarding-a-lab-host`, Step 3).

Finally it re-reads ``/api/places`` and prints the new place's tags, or a warning if the place
is not listed.

Resuming after a failure
------------------------

Answers are saved as you give them, one file per board name, under
``~/.cache/adi-lg/netbox-add-hardware/`` (``$XDG_CACHE_HOME/adi-lg/...`` if that is set). If a
run stops - a site slug NetBox doesn't know, an exporter host without passwordless sudo, a
rejected token, Ctrl-C - the error says where its answers are:

Never hand-edit one of these JSON files to fix a wrong answer. The *done* steps it records
(*NetBox device done*, *exporter running*, ...) are only cleared when an answer changes through
**review** (see below); editing the file directly leaves them marked done with a value NetBox
and the exporter were never updated with, so a later ``resume`` silently skips re-registering
them. Pick **review** instead and retype the answer at its prompt.

.. code-block:: console

    Error: NetBox site 'lab4' does not exist - this tool only references existing sites, it does not create them
    Answers saved to /home/you/.cache/adi-lg/netbox-add-hardware/zcu102-lab3-001.json - run `adi-lg netbox add-hardware` again and pick zcu102-lab3-001 to resume.

The next run lists the saved runs before anything else:

.. code-block:: console

    $ adi-lg netbox add-hardware
    Saved answers from earlier runs
    #   Board             Template    Saved              Progress
    ──────────────────────────────────────────────────────────────────────
    1   zcu102-lab3-001   soc-sdmux   2026-10-28 08:29   plan checked
    2   new                                              start a new board
    Resume a saved run (zcu102-lab3-001):

    Saved answers for zcu102-lab3-001
    Question                                  Answer
    ────────────────────────────────────────────────────────────────────────────────
    Board name                                zcu102-lab3-001
    ...
    NetBox site slug                          lab4
    Exporter host SSH login                   labadmin@lab-host-03
    Board has a JTAG cable                    no
    Board's SD card in an SD mux              yes
    Board template                            soc-sdmux
    Boot strategy                             BootFPGASoC
    Board IP address, for SSH to its Linux    10.0.0.42
    BOOT.BIN, as release:<path> or a file     release:zynqmp-zcu102-rev10-ad9081/m8_
    on the test runner                        l4/BOOT.BIN
    ...
    1   resume   as they are: ask only what is still unanswered
    2   review   ask every question again, with the saved answer as its default
    Use the saved answers (resume):

- **resume** uses the saved answers as they are and goes straight to the plan. Only questions
  the saved run never reached are asked.
- **review** asks every question again with its saved answer as the default: press Enter to
  keep it or type a new one. For an optional template field, ``-`` drops the saved answer and
  goes back to the template's default.
- **new** starts over. The saved run stays listed until a run for that board name finishes.

The *Progress* column shows how far a run got: *plan checked* (the exporter config rendered
and validated), *NetBox device done*, or *exporter running*. A resumed run skips the steps it
finished, as long as no answer changed, and does not ask for their credentials again.
Changing any answer in **review** runs every step again; each one is safe to repeat (see
`Re-running for an existing board`_). Once the coordinator step succeeds the saved answers
are deleted.

A resumed run asks for the NetBox URL and coordinator username again when it needs them, with
the saved ones as defaults - a wrong URL or login is the usual reason a run stops, so press Enter
to keep them or type the right one. The power device and outlet, the serial and JTAG
devices and ports, and the SD mux are saved answers too, so a resumed run reads NetBox before the plan only
if one of them is missing - for example in a run saved by a version without them, which asks
for the NetBox URL and token, then only the missing ones. Answering a question a saved run
didn't have runs every step again, so the new cables are added. A saved site NetBox no longer
has is asked again. It deploys to the same coordinator as the saved run, so
``--coord`` need not be given again; naming a different one (``--coord`` or ``LG_COORDINATOR``)
runs every step again, because the exporter already deployed points at the first.

A run saved before templates were recommended from the board's hardware already has its
template. Resuming it keeps that template and takes the board's hardware from it, so JTAG and
the SD mux are asked only if the template uses them and NetBox has no answer saved for them -
a ``soc-ssh`` run asks nothing new. **review** asks every question, in the new order.

A dry run saves its answers too, with the plan marked as checked, so you can check the plan
with ``--dry-run`` and then run for real, picking **resume**: it asks only for the NetBox
devices a dry run doesn't pick (power device, serial and JTAG ports, SD mux), then goes to
``Proceed?`` - unless those picks show the board's hardware isn't what the dry run was told,
and the saved template no longer suits it: then the template is asked again.

The NetBox API token and the coordinator password are never saved. The NetBox URL, the
coordinator username and every other answer are, including template fields such as the
board's Linux SSH password, which the rendered exporter config holds in plain text anyway.
The files can be read only by you (mode 0600). To discard saved runs, delete the files.

Re-running for an existing board
--------------------------------

Every stage is safe to run again for a board that is already (or partly) onboarded:

- **NetBox** - an existing device (matched by name) has its custom fields updated in place.
  Its site and device type are left unchanged. A board already cabled to the outlet is left
  as it is.
- **Exporter host** - the config and unit files are overwritten and the unit is restarted, so
  the new config is loaded.
- **Coordinator** - an existing place is kept and only the matches it lacks are added. The
  tags this command writes are set to this run's values; any other tags on the place are kept.

Troubleshooting
---------------

``could not find exporter_configs/validate.py above the current directory``
    Run from inside a ``labgrid-plugins`` checkout, or pass ``--exporter-configs-dir``.

``template <name> is missing a required field``
    A template variable with no default (typically ``target_ip``) was left blank.

``rendered exporter config failed validation``
    ``exporter_configs/validate.py`` rejected the rendered file; the listed issues name the
    offending group/resource. Fix the template answers, or the template itself.

``TLS verification failed for <url>`` (``certificate verify failed: self-signed certificate in certificate chain``)
    Only with ``--netbox-verify`` or ``--netbox-ca-bundle``. NetBox's certificate is signed by
    a CA that Python doesn't trust. A pip-installed ``requests`` checks certificates against its
    own bundle (``certifi``), not the host's trust store, so an internal CA installed on the
    host still fails. Pass that CA with ``--netbox-ca-bundle`` (on Debian/Ubuntu,
    ``/etc/ssl/certs/ca-certificates.crt`` is the host's trust store), or drop both options to
    skip the check. With ``--netbox-verify`` alone, a ``REQUESTS_CA_BUNDLE`` or
    ``CURL_CA_BUNDLE`` environment variable replaces Python's bundle; the other two settings
    ignore them.

``NetBox rejected the request: ... 403 Forbidden``
    The API token is wrong, expired, or lacks write permission. Create a token in NetBox under
    your user profile and pass it with ``--netbox-token`` or ``NETBOX_TOKEN``.

``Invalid authorization header: Must be in the form "Bearer <key>.<token>" or "Token <token>"``
    The token had a space in it - usually a copied ``Authorization: Bearer nbt_...`` header
    line rather than the token alone. Give just the token: ``nbt_<key>.<token>`` on NetBox
    4.5+, or a 40-character v1 token; the command adds the ``Bearer``/``Token`` keyword. It now
    removes a pasted ``Authorization:``/``Bearer``/``Token`` prefix and surrounding quotes
    itself, and refuses a token that still has a space in it, or that is only the
    ``nbt_<key>`` half of a v2 token (NetBox shows the full token once, when it is created).
    A bad ``--netbox-token`` / ``NETBOX_TOKEN`` stops the command before any question; a bad
    answer at the prompt is asked again.

``NetBox site '<slug>' does not exist`` / ``NetBox has no sites``
    Create the site in NetBox first (or use an existing slug); the command never creates sites.

``<device> Outlet 3 already feeds <device> <port>`` / ``<device> ttyUSB1 already feeds <device> UART``
    The outlet or console server port is cabled to another device in NetBox. Pick a free one -
    or, if that device was unplugged, remove its cable in NetBox (*Cables*) and run again.

``<device> keeps its labgrid_power settings in NetBox (...), which differ from this board's (...)``
    Not an error: the power device was set up by an earlier board (or by hand) with other
    settings, and the command never replaces them. If the device's address really changed,
    edit its *Labgrid power control* field in NetBox.

``<board> power is also connected to <device> <outlet> - left as is``
    Not an error: the board was cabled to another outlet (or, for ``UART`` / ``JTAG``, another
    port) before. If it was moved, remove the old cable in NetBox.

``<device> <port> keeps its serial path in NetBox (...), which differs from this board's (...)``
    Not an error: the port's ``labgrid_serial_path`` was set by an earlier board (or by hand)
    and is never replaced; the exporter config uses your answer. If the adapter really moved,
    edit the port's *Labgrid serial device path* in NetBox.

``cannot SSH to <host>``
    The exporter host's name doesn't resolve, or its SSH key isn't accepted without a
    password. Check the *Exporter host SSH login* answer (pick **review** to change it) and
    that ``ssh user@host`` works without a prompt.

``labgrid-exporter not found on <host>``
    Install labgrid on the exporter host (``pip install labgrid``) so ``labgrid-exporter`` is
    on the SSH user's ``PATH`` for non-interactive SSH commands.

``failed to install/start labgrid-exporter-<name>``
    Usually missing passwordless sudo for the SSH user.

``labgrid-exporter-<name> did not become active``
    Read the journal lines printed with the error, or run
    ``journalctl -u labgrid-exporter-<name>`` on the host. Common causes are a wrong
    coordinator address, or a serial port / device path in the config that doesn't exist on
    the host.

``Warning: ... not set in /etc/labgrid/exporter.env``
    The exporter is running, but the outlet credentials are empty, so power operations will
    fail. Add the listed variables to the file and run
    ``sudo systemctl restart labgrid-exporter-<name>``.

How it maps to the manual procedure
------------------------------------

.. code-block:: text

    adi-lg netbox add-hardware                  manual equivalent (onboarding-a-lab-host.rst)
    ───────────────────────────────────────────  ──────────────────────────────────────────────
    NetBox device + power/serial/JTAG/SD cables  (no manual equivalent - new)
    render + validate exporter_configs/*.yaml     Step 2: copy template, fill in, validate.py
    SSH deploy + systemd install/start/verify     Step 2: run labgrid-exporter (foreground/nohup)
    POST /places, /places/{name}/matches          Step 3: labgrid-client create / add-match
    PUT /places/{name}/tags                        Step 3: labgrid-client set-tags

Step 4 (board-catalog entry) is only partially covered: tagging a place with a
``daughter-board`` (+ ``carrier``) tag auto-seeds a minimal catalog stub on the coordinator, but
that stub lives in the running container's filesystem, not the git-tracked
``coordinator/api/board_catalog.yaml`` - it's lost on the next redeploy. Setting a non-default
Kuiper ``image``, ``flash`` config, or ``aliases`` still requires hand-editing
``board_catalog.yaml`` and redeploying, per Step 4.
