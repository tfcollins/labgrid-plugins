NetBox Onboarding
=================

``adi-lg netbox add-hardware`` automates the whole of :doc:`onboarding-a-lab-host` Steps 2-4
for a single new board: it registers the board as a device in NetBox, renders and validates its
exporter config, deploys that config to the exporter host as a systemd service and verifies it
comes up, then creates the matching labgrid Place on the coordinator (``create`` /
``add-match`` / ``set-tags``). Run it instead of hand-editing a template and typing
``labgrid-client`` commands.

.. admonition:: What it does NOT do
   :class: note

   It does not physically rack or cable the board, and it does not install ``labgrid-exporter``
   on the host - both are prerequisites, checked below.

Prerequisites
-------------

- Run from within a ``labgrid-plugins`` checkout (``exporter_configs/`` and its templates live
  at the repo root, outside the installed package).
- ``pip install -e ".[netbox]"`` (adds ``pynetbox``, ``jinja2``, ``jsonschema`` - not installed
  by default).
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
  - **``labgrid-exporter`` already installed** there (``pip install labgrid`` on that host) -
    checked up front and failed fast if missing, rather than partially provisioning.

Usage
-----

.. code-block:: console

    $ adi-lg netbox add-hardware
    Available board templates: vcu118_ad9081, zcu102
    Board template: zcu102
    Hardware / place / exporter name (e.g. zcu102-lab3-001): zcu102-lab3-001
    Carrier (board/FPGA, e.g. zcu102, vcu118): zcu102
    Daughter board / chip (e.g. ad9081): ad9081
    Boot strategy [BootFPGASoC/BootFPGASoCSSH/.../BootTickFPGASSH]: BootFPGASoC
    GitHub runner label (hw-zcu102):
    NetBox site slug (must already exist): lab3
    Exporter host SSH target (user@host): labadmin@lab-host-03
    Template fields for zcu102: chip, sdmux_path, serial_port, target_ip
      target_ip (blank = template default): 10.0.0.42
      chip (blank = template default):
      serial_port (blank = template default):
      sdmux_path (blank = template default):

    Plan
      NetBox device: zcu102-lab3-001  (carrier=zcu102, chip=ad9081, site=lab3)
      Exporter: labadmin@lab-host-03 -> systemd unit labgrid-exporter-zcu102-lab3-001
      Coordinator place: zcu102-lab3-001  (tags: daughter-board=ad9081, carrier=zcu102,
      boot-strategy=BootFPGASoC, runner=hw-zcu102)
      Rendered + validated exporter config: /tmp/adi-lg-netbox-xxxxx/zcu102.yaml
      Resource group(s): ZCU102_AD9081

    Proceed? [y/n] (y): y
    ...
    Done. zcu102-lab3-001 tags: {'daughter-board': 'ad9081', 'carrier': 'zcu102', ...}

Use ``--dry-run`` to render and schema-validate the exporter config and print the full plan
without touching NetBox, SSH, or the coordinator - useful for checking your answers before
committing to a real board.

Leaving a template field blank uses that template's own default (see
``exporter_configs/templates/*.yaml``); fields with no default (like ``target_ip``) are
effectively required and the command fails clearly if left blank.

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
