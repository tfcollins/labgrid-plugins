NetBox Onboarding
=================

``adi-lg netbox add-hardware`` automates the whole of :doc:`onboarding-a-lab-host` Steps 2-4
for a single new board: it registers the board as a device in NetBox, renders and validates its
exporter config, deploys that config to the exporter host as a systemd service and verifies it
comes up, then creates the matching labgrid Place on the coordinator (``create`` /
``add-match`` / ``set-tags``). Run it instead of hand-editing a template and typing
``labgrid-client`` commands.

**On this page:**

- `Prerequisites`_
- `Usage`_ — `Options`_
- `What it creates`_ — `In NetBox`_, `On the exporter host`_, `On the coordinator`_
- `Resuming after a failure`_
- `Re-running for an existing board`_
- `Troubleshooting`_
- `How it maps to the manual procedure`_

.. admonition:: What it does NOT do
   :class: note

   It does not physically rack or cable the board, and it does not install ``labgrid-exporter``
   on the host - both are prerequisites, checked below.

Prerequisites
-------------

- Run from within a ``labgrid-plugins`` checkout (``exporter_configs/`` and its templates live
  at the repo root, outside the installed package), or pass ``--exporter-configs-dir``.
- ``pip install -e ".[netbox]"`` (adds ``pynetbox``, ``jinja2``, ``jsonschema`` - not installed
  by default).
- NetBox **4.3 or newer** - custom fields are created with the ``object_types`` key that NetBox
  4.3 introduced (it replaced ``content_types``).
- A NetBox URL and API token with permission to create devices (``NETBOX_URL`` /
  ``NETBOX_TOKEN`` env vars, or ``--netbox-url`` / ``--netbox-token``).
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
    Board templates
    #   Template      Boot strategy     Description
    ──────────────────────────────────────────────────────────────────────────────
    1   fabric-jtag   BootFabric        FPGA fabric loaded over JTAG
    2   rpi-ssh       BootRPI           Raspberry Pi driven over SSH
    3   soc-sdmux     BootFPGASoC       SoC booted from an SD card through a USB SD mux
    4   soc-ssh       BootFPGASoCSSH    SoC whose boot files are updated over SSH
    5   soc-tftp      BootFPGASoCTFTP   SoC booted over TFTP from U-Boot
    6   zynqmp-jtag   BootZynqMPJTAG    ZynqMP board strapped for JTAG boot
    Board template (fabric-jtag): 3

    A unique name for this board. It names the NetBox device, the coordinator place
    and the exporter service (labgrid-exporter-<name>).
    Board name (e.g. zcu102-ad9081-lab3): zcu102-lab3-001

    The FPGA or SoC board the ADI part is mounted on. Saved in NetBox and as the
    place's carrier tag; most templates also use it in the resource group name.
    Carrier board (e.g. zcu102, zc706, vcu118): zcu102

    The ADI part under test. Saved in NetBox and as the place's daughter-board tag;
    most templates also use it in the resource group name.
    ADI daughter board or chip (e.g. ad9081, adrv9009): ad9081

    Boot strategies
     #   Strategy                   Description
    ──────────────────────────────────────────────────────────────────────────────
     1   BootFPGASoC                BootFPGASoC strategy for FPGA SoC devices using
                                    Kuiper releases.
     ...
    12   BootTickFPGASSH            BootFPGASoCSSH + runtime Tick deploy (bitstream,
                                    overlay, module).
    Boot strategy (BootFPGASoC):

    Power control
    #   Category                       Types
    ──────────────────────────────────────────────────────────────────────────────
    1   Network PDU                    apc, cyberpower, network-pdu, pdudaemon
    2   Smart plug / home automation   vesync, kasa, homeassistant, tasmota
    ...
    Power category (Smart plug / home automation): 1
    #   Type          Description                                 Driver
    ──────────────────────────────────────────────────────────────────────────────
    1   apc           APC PDU (SNMP)                              APCDriver
    2   cyberpower    CyberPower PDU (SNMP)                       CyberPowerDriver
    ...
    Power type (apc): cyberpower
      PDU hostname or IP: 10.0.0.20
      Outlet number: 4

    The self-hosted GitHub Actions runner that runs this board's hardware-CI jobs
    (the place's runner tag).
    GitHub Actions runner label (hw-zcu102):

    The existing NetBox site the board is in (NetBox: Organization > Sites). This
    command never creates sites.
    NetBox site slug (e.g. lab3): lab3

    The Linux machine the board's serial, USB and power are connected to. The
    exporter service is installed there over SSH, so this user needs passwordless
    sudo.
    Exporter host SSH login (user@host): labadmin@lab-host-03

    Template fields for soc-sdmux
    Field               Question                             Default
    ──────────────────────────────────────────────────────────────────────────────
    target_ip           Board IP address, for SSH to its     required
                        Linux
    boot_partition      SD card boot partition on the        /dev/disk/by-label/BOOT
                        exporter host, through the SD mux
    kuiper_bootbin      BOOT.BIN, as release:<path> or a     unset
                        file on the test runner
    ...
    serial_port         Serial console device on the         /dev/ttyUSB0
                        exporter host
    target_password     Board Linux SSH password             analog
    target_username     Board Linux SSH username             root
      Board IP address, for SSH to its Linux (required): 10.0.0.42
      SD card boot partition on the exporter host, through the SD mux (Enter for
    /dev/disk/by-label/BOOT):
      BOOT.BIN, as release:<path> or a file on the test runner (Enter to leave
    unset): release:zynqmp-zcu102-rev10-ad9081/m8_l4/BOOT.BIN
      ...
      Serial console device on the exporter host (Enter for /dev/ttyUSB0):
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

    Proceed? [y/n] (y): y
    ...

Each set of options is listed as a numbered table; answer with the number or the name,
or press Enter for the default shown in parentheses.

Use ``--dry-run`` to render and schema-validate the exporter config and print the full plan
without touching NetBox, SSH, or the coordinator - useful for checking your answers before
committing to a real board. A dry run never asks for NetBox or coordinator credentials.

Each question says what the answer is used for. Template fields are asked by what they are
(*Board IP address*, *Serial console device on the exporter host*, ...), after a table of the
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
*ADI daughter board or chip* answers, so they are not asked again as template fields. Choose the
template by boot strategy (see :doc:`exporter-setup`); the *Boot strategy* prompt defaults to
the one the template declares. *Power category* and *Power type* choose the template's
``power`` fragment - any of the types in :ref:`power-types`, covering this package's outlets
and all of labgrid's power options - and that type's own fields follow. The command sets the
place's ``power-driver`` tag, plus ``power-output-driver`` for relay types. Credentials,
reachability notes (e.g. ``tasmota`` and ``laa`` connect from the client) and required host
tools are printed in the plan.

The boot-strategy prompt only accepts the ADI strategy classes this package registers
(``BootFPGASoC``, ``BootFPGASoCSSH``, ``BootFPGASoCTFTP``, ``BootSelMap``, ``BootFabric``,
``BootRPI``, ``BootVPK180``, ``BootZynqMPJTAG``, ``BootZynq7000JTAGRecovery``,
``BootNoOSJTAG``, ``BootOpenFPGALoader``, ``BootTickFPGASSH``).

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

NetBox and coordinator credentials that are not set by option or environment are prompted for
only *after* you confirm ``Proceed?``. The token and password prompts hide what you type or
paste, so nothing appears on screen; after each one the command prints how many characters it
received. Blank answers are asked again.

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
- **Custom fields** on ``dcim.device`` (all text):

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

Then the **device** itself, named after the board name, with that device type and role,
under the existing site. The command prints its URL
(``<netbox>/dcim/devices/<id>/``) when done.

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
    Board template                            soc-sdmux
    Board name                                zcu102-lab3-001
    ...
    NetBox site slug                          lab4
    Exporter host SSH login                   labadmin@lab-host-03
    Board IP address, for SSH to its Linux    10.0.0.42
    BOOT.BIN, as release:<path> or a file     release:zynqmp-zcu102-rev10-ad9081/m8_
    on the test runner                        l4/BOOT.BIN
    ...
    1   resume   as they are: ask only what is still unanswered, then show the plan
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

After ``Proceed?`` a resumed run asks for the NetBox URL and coordinator username again, with
the saved ones as defaults - a wrong URL or login is the usual reason a run stops, so press Enter
to keep them or type the right one. It deploys to the same coordinator as the saved run, so
``--coord`` need not be given again; naming a different one (``--coord`` or ``LG_COORDINATOR``)
runs every step again, because the exporter already deployed points at the first.

A dry run saves its answers too, with the plan marked as checked, so you can check the plan
with ``--dry-run`` and then run for real, picking **resume** to go straight to
``Proceed?``.

The NetBox API token and the coordinator password are never saved. The NetBox URL, the
coordinator username and every other answer are, including template fields such as the
board's Linux SSH password, which the rendered exporter config holds in plain text anyway.
The files can be read only by you (mode 0600). To discard saved runs, delete the files.

Re-running for an existing board
--------------------------------

Every stage is safe to run again for a board that is already (or partly) onboarded:

- **NetBox** - an existing device (matched by name) has its custom fields updated in place.
  Its site and device type are left unchanged.
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

``NetBox site '<slug>' does not exist``
    Create the site in NetBox first (or use an existing slug); the command never creates sites.

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
    NetBox device create/update                  (no manual equivalent - new)
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
