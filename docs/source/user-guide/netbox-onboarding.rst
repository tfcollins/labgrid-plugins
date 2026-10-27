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
- SSH access to the exporter host as ``user@host``, with:

  - **passwordless sudo** for that user (needed to write under ``/etc`` and run ``systemctl``),
  - ``labgrid-exporter`` **already installed** and on that user's ``PATH`` over SSH -
    checked up front with ``command -v labgrid-exporter``, and the generated systemd unit
    runs the absolute path that resolves to, so a venv or ``~/.local/bin`` install works.

Usage
-----

.. code-block:: console

    $ adi-lg netbox add-hardware
    Available board templates: fabric-jtag, rpi-ssh, soc-sdmux
    Board template: soc-sdmux
    Hardware / place / exporter name (e.g. zcu102-lab3-001): zcu102-lab3-001
    Carrier (board/FPGA, e.g. zcu102, vcu118): zcu102
    Daughter board / chip (e.g. ad9081): ad9081
    Boot strategy [BootFPGASoC/BootFPGASoCSSH/.../BootTickFPGASSH]: BootFPGASoC
    GitHub runner label (hw-zcu102):
    NetBox site slug (must already exist): lab3
    Exporter host SSH target (user@host): labadmin@lab-host-03
    Template fields for soc-sdmux: sdmux_path, serial_port, target_ip
      sdmux_path (blank = template default):
      serial_port (blank = template default):
      target_ip (blank = template default): 10.0.0.42

    Plan
      NetBox device: zcu102-lab3-001  (carrier=zcu102, chip=ad9081, site=lab3)
      Exporter: labadmin@lab-host-03 -> systemd unit labgrid-exporter-zcu102-lab3-001
      Coordinator place: zcu102-lab3-001  (tags: daughter-board=ad9081, carrier=zcu102,
      boot-strategy=BootFPGASoC, runner=hw-zcu102)
      Rendered + validated exporter config: /tmp/adi-lg-netbox-xxxxx/soc-sdmux.yaml
      Resource group(s): ZCU102_AD9081
      Place match(es): zcu102-lab3-001/ZCU102_AD9081/*

    Proceed? [y/n] (y): y
    ...
    Done. zcu102-lab3-001 tags: {'daughter-board': 'ad9081', 'carrier': 'zcu102', ...}

Use ``--dry-run`` to render and schema-validate the exporter config and print the full plan
without touching NetBox, SSH, or the coordinator - useful for checking your answers before
committing to a real board. A dry run never asks for NetBox or coordinator credentials.

Leaving a template field blank uses that template's own default (see
``exporter_configs/templates/*.yaml``); fields with no default (like ``target_ip``) are
effectively required and the command fails clearly if left blank.

The templates name their resource group ``<CARRIER>_<CHIP>`` (e.g. ``ZCU102_AD9081``) from
the ``carrier`` and ``chip`` fields. The command fills those from the *Carrier* and
*Daughter board / chip* answers, so they are not asked again as template fields. Choose the
template by boot path: ``soc-sdmux``, ``fabric-jtag``, or ``rpi-ssh`` (see
:doc:`exporter-setup`).

The boot-strategy prompt only accepts the ADI strategy classes this package registers
(``BootFPGASoC``, ``BootFPGASoCSSH``, ``BootFPGASoCTFTP``, ``BootSelMap``, ``BootFabric``,
``BootRPI``, ``BootVPK180``, ``BootZynqMPJTAG``, ``BootZynq7000JTAGRecovery``,
``BootNoOSJTAG``, ``BootOpenFPGALoader``, ``BootTickFPGASSH``).

Options
~~~~~~~

Every option is optional; anything not supplied is prompted for.

* ``--netbox-url <url>``: NetBox base URL (env: ``NETBOX_URL``).
* ``--netbox-token <token>``: NetBox API token (env: ``NETBOX_TOKEN``).
* ``--coord <host:port>``: coordinator to deploy against and create the place on (default:
  ``$LG_COORDINATOR``).
* ``--coord-user <name>``: coordinator API username (env: ``LG_API_USERNAME``).
* ``--coord-password <password>``: coordinator API password (env: ``LG_API_PASSWORD``).
* ``--exporter-configs-dir <path>``: the ``exporter_configs/`` directory (default: searched
  upward from the current directory for ``exporter_configs/validate.py``).
* ``--dry-run``: render, validate, and print the plan; make no changes.

NetBox and coordinator credentials that are not set by option or environment are prompted for
only *after* you confirm ``Proceed?``, with the token and password entered hidden.

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

Then the **device** itself, named after the hardware name, with that device type and role,
under the existing site. The command prints its URL
(``<netbox>/dcim/devices/<id>/``) when done.

On the exporter host
~~~~~~~~~~~~~~~~~~~~

Files are staged under ``/tmp/adi-lg-netbox-stage/<name>/`` and then moved into place with
``sudo``:

- ``/etc/labgrid/exporters/<name>/resources.yaml`` - the rendered exporter config.
- ``/etc/systemd/system/labgrid-exporter-<name>.service`` - a unit that runs
  ``labgrid-exporter -n <name>`` (the absolute path found by the prerequisite check) as the
  SSH user, pointed at the coordinator, with ``Restart=always``. The exporter registers on the
  coordinator under the hardware name, so one host can run a separate exporter per board.

The unit is enabled and started (``systemctl enable --now``), then polled with
``systemctl is-active`` (10 attempts, 2 s apart). If it never becomes active, the command
fails and prints the last 50 lines of its journal.

On the coordinator
~~~~~~~~~~~~~~~~~~

Through the coordinator REST API (:doc:`coordinator`), authenticated as the coordinator user:

- ``POST /api/places`` - create the place, named after the hardware name.
- ``POST /api/places/<name>/matches`` - one ``<name>/<group>/*`` match per resource group in
  the rendered config (``<name>`` is the exporter name the unit registers).
- ``PUT /api/places/<name>/tags`` - ``daughter-board`` and ``carrier`` (lowercased),
  ``boot-strategy``, and ``runner``, the keys the hardware-CI preflight matches on (see the tag
  table in :doc:`onboarding-a-lab-host`, Step 3).

Finally it re-reads ``/api/places`` and prints the new place's tags, or a warning if the place
is not listed.

Re-running for an existing board
--------------------------------

The command is not fully idempotent; each stage handles an existing board differently:

- **NetBox** - an existing device (matched by name) has its custom fields updated in place.
  Its site and device type are left unchanged.
- **Exporter host** - the config and unit files are overwritten, but
  ``systemctl enable --now`` does not restart a unit that is already running, so the old config
  stays loaded. Restart it yourself:
  ``sudo systemctl restart labgrid-exporter-<name>``.
- **Coordinator** - the coordinator rejects a match that already exists, so a re-run for an
  already-onboarded board stops at the coordinator step with an error, after the NetBox and
  exporter stages have run. Tags are written last, so for a tag-only change use the
  dashboard or ``labgrid-client set-tags`` instead.

Troubleshooting
---------------

``could not find exporter_configs/validate.py above the current directory``
    Run from inside a ``labgrid-plugins`` checkout, or pass ``--exporter-configs-dir``.

``template <name> is missing a required field``
    A template variable with no default (typically ``target_ip``) was left blank.

``rendered exporter config failed validation``
    ``exporter_configs/validate.py`` rejected the rendered file; the listed issues name the
    offending group/resource. Fix the template answers, or the template itself.

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
