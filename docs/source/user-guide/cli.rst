Command Line Interface
======================

The ``adi-lg`` command provides a convenient way to execute boot strategies directly from the terminal. This tool leverages the ``click`` library for a robust CLI and ``rich`` for beautiful, informative output.

Installation
------------

The CLI (``click`` and ``rich`` included) is installed with the package. A few subcommands
need an optional extra:

.. code-block:: bash

    pip install -e .              # adi-lg and every subcommand below
    pip install -e ".[netbox]"    # + adi-lg netbox add-hardware
    pip install -e ".[kuiper]"    # + Kuiper image extraction (pytsk3, needs a C toolchain)

Global Options
--------------

All commands support the following global option:

* ``--debug``: Enable detailed debug logging, including Labgrid internal logs and strategy transitions.

Commands
--------

The CLI provides subcommands for different boot strategies.

request
~~~~~~~

Request a board **by part** — labgrid selects a free matching board, boots it,
hands over its libIIO URI, runs your command, and releases the board. No
strategy/driver/resource config and no place name required.

.. code-block:: bash

    # Boot an ADRV9002 (on any free carrier) and run a pytest selection against it
    adi-lg request --part adrv9002 --run 'pytest test/ -k adrv9002'

    # Narrow to a carrier and pin an image version
    adi-lg request --part adrv9002 --carrier zcu102 --bootfile 2023_R2_P1 \
        --run 'pytest test/ -k adrv9002'

    # Print just the URI (no command) — useful for scripting
    adi-lg request --part adrv9002

Options:

* ``--part`` (required): part / daughter-board, e.g. ``adrv9002``.
* ``--carrier``: optional FPGA carrier filter, e.g. ``zcu102``. Omit to match any free carrier.
* ``--mode`` (default ``uri``): ``uri`` boots Linux and exports ``IIO_URI``; ``flash`` JTAG-flashes a
  no-os ``.elf`` instead of booting Kuiper (see the flash-mode note below); ``reserve`` only
  acquires the board, without booting it, and exports ``LG_ENV`` (the rendered labgrid env
  YAML) so the ``--run`` command drives the board itself, e.g. through the labgrid pytest plugin.
* ``--no-boot``: shortcut for ``--mode reserve``.
* ``--bootfile``: pin an image version. Defaults to the coordinator catalog's default image.
* ``--wait`` (default ``1800``): seconds to queue for a free matching board. ``0`` fails fast.
* ``--power-down``: power the board off after release (default: leave it powered for the next user).
* ``--coord``: coordinator ``host:port`` (default: ``$LG_COORDINATOR``).
* ``--run '<cmd>'``: run ``<cmd>`` with ``IIO_URI``, ``LG_PLACE``, ``LG_CARRIER``,
  ``HW_DAUGHTER`` and ``HW_CARRIER`` (plus ``LG_ENV`` in reserve mode) exported into its
  environment. The command's own exit code is propagated.

Exit codes (so CI can tell an infra problem from a real test failure):

* ``0`` / child's code — success, or the ``--run`` command's own exit code.
* ``10`` — no matching board exists for the part/filters.
* ``11`` — matching boards exist but none became free within ``--wait``.
* ``12`` — the board failed to boot (the console tail is printed for triage).
* ``130`` — interrupted (Ctrl-C or CI job-timeout); the board is still released.

**Flash mode (no-os firmware).** With ``--mode flash`` the board is JTAG-flashed with a no-os
bare-metal ``.elf`` instead of booting Kuiper, and no ``IIO_URI`` is exported. The extra flash
arguments are:

* ``--firmware <elf>``: no-os firmware ``.elf`` to JTAG-load (required for flash mode).
* ``--bitstream <bit>``: optional FPGA bitstream to program before the ``.elf``.
* ``--ps7-init <tcl>``: optional ``ps7_init.tcl`` used for PS initialization.
* ``--validate <banner>``: serial banner to assert after flashing (default: the IIOD server banner).

.. code-block:: bash

    adi-lg request --part adrv9002 --mode flash \
        --firmware build/adrv9002.elf --bitstream build/system.bit \
        --ps7-init build/ps7_init.tcl --validate 'Running' \
        --run 'pytest test/ -k adrv9002'

See :doc:`hw-request` for the request workflow end to end.

setup-runner
~~~~~~~~~~~~

Setup, configure, and service a self-hosted GitHub Actions hardware runner.
Supports both **exporter** (coordinator-backed) and **direct** (locally attached DUT) modes.
When invoked without arguments in an interactive shell, it launches a step-by-step
guided wizard.

.. code-block:: bash

    # Launch interactive setup wizard
    adi-lg setup-runner

    # Check prerequisites only
    adi-lg setup-runner --check-only --mode exporter

    # Non-interactive / headless setup for exporter mode
    adi-lg setup-runner \
        --mode exporter \
        --scope repo:analogdevicesinc/labgrid-plugins \
        --coord 10.0.0.41:20408 \
        --labels hw-lab \
        --non-interactive

    # Direct hardware setup
    adi-lg setup-runner \
        --mode direct \
        --scope repo:analogdevicesinc/labgrid-plugins \
        --env-file /etc/labgrid/direct_env.yaml \
        --labels hw-direct \
        --non-interactive

**Options:**

* ``--mode [exporter|direct]``: Hardware setup mode.
* ``-s, --scope <scope>``: GitHub scope (``repo:OWNER/REPO`` or ``org:ORGNAME``).
* ``-n, --name <name>``: Runner name (defaults to ``<hostname>-<scope-slug>``).
* ``-l, --labels <labels>``: Comma-separated runner labels (e.g. ``hw-lab,zcu102``).
* ``--dir <path>``: Runner installation directory (defaults to ``~/actions-runner-<scope-slug>``).
* ``-c, --coord <host:port>``: Coordinator URL for exporter mode (default: ``$LG_COORDINATOR``).
* ``-e, --env-file <path>``: Labgrid direct environment YAML for direct mode.
* ``-t, --token <token>``: Runner registration token (bypasses automatic ``gh`` auth).
* ``--service / --no-service``: Install and start runner systemd service (default: True).
* ``--non-interactive, --unattended``: Run without interactive prompts.
* ``--dry-run``: Preview planned actions without modifying system files.
* ``--check-only``: Run prerequisite diagnostics and exit.

``adi-lg runner-setup`` is an alias, and the same command is installed as the standalone
``adi-lg-setup-runner`` console script.

netbox add-hardware
~~~~~~~~~~~~~~~~~~~

Onboard one new board in a single interactive pass: register it as a device in NetBox,
cabled to an outlet on its power device and to the ports its serial console and JTAG are
plugged into (each picked from NetBox, or added),
render and validate its exporter config from ``exporter_configs/templates/``, deploy that
config to the exporter host as a ``labgrid-exporter-<name>`` systemd service, and create and
tag the matching place on the coordinator. Requires the ``netbox`` extra and must be run from
a ``labgrid-plugins`` checkout.

.. code-block:: bash

    # Check the plan and the rendered exporter config without changing anything
    adi-lg netbox add-hardware --dry-run

    # Real run, with credentials from the environment instead of prompts
    export NETBOX_URL=https://netbox.example.com NETBOX_TOKEN=<token>
    export LG_API_USERNAME=admin LG_API_PASSWORD=<password>
    adi-lg netbox add-hardware --coord coordinator.example.com:20408

**Options:**

* ``--netbox-url <url>`` / ``--netbox-token <token>``: NetBox API (env: ``NETBOX_URL`` / ``NETBOX_TOKEN``).
* ``--netbox-verify`` / ``--netbox-ca-bundle <path>``: verify NetBox's TLS certificate against Python's CA bundle, or against this one (env: ``NETBOX_CA_BUNDLE``). Not verified by default.
* ``--coord <host:port>``: Coordinator (default: ``$LG_COORDINATOR``).
* ``--coord-user <name>`` / ``--coord-password <password>``: Coordinator API login (env: ``LG_API_USERNAME`` / ``LG_API_PASSWORD``).
* ``--exporter-configs-dir <path>``: ``exporter_configs/`` directory (default: searched upward from the current directory).
* ``--dry-run``: Render, validate, and print the plan; make no changes.

Answers are saved as they are given (never the token or passwords), so a run that fails
can be resumed: the next run offers to pick up where it stopped, skipping steps it already
finished. See :doc:`netbox-onboarding` for prerequisites, exactly what is created in NetBox, on
the exporter host, and on the coordinator, resuming, and re-run behavior.

boot-fabric
~~~~~~~~~~~

Boot an FPGA using the JTAG-based ``BootFabric`` strategy. This is typically used for Microblaze-based systems on Virtex, Artix, or Kintex FPGAs.

.. code-block:: bash

    adi-lg boot-fabric --config soc.yaml --bitstream system.bit --kernel kernel.strip

**Options:**

* ``-c, --config <path>``: (Required) Labgrid configuration file.
* ``--bitstream <path>``: Path to the FPGA bitstream file (.bit). Overrides the path in the config.
* ``--kernel <path>``: Path to the Linux kernel image (.strip). Overrides the path in the config.
* ``-t, --target <name>``: Target name in the configuration (default: ``main``).
* ``--state <name>``: Target state to transition to (default: ``shell``).

boot-soc
~~~~~~~~

Boot an FPGA SoC using the SD Mux-based ``BootFPGASoC`` strategy. This is used for Zynq and ZynqMP based systems.

.. code-block:: bash

    adi-lg boot-soc --config soc.yaml --release 2023_R2_P1 --kernel uImage

**Options:**

* ``-c, --config <path>``: (Required) Labgrid configuration file.
* ``--release <version>``: Kuiper release version to use for boot files.
* ``--kernel <path>``: Path to a custom kernel file.
* ``--bootbin <path>``: Path to a custom BOOT.BIN file.
* ``--devicetree <path>``: Path to a custom devicetree (.dtb) file.
* ``-t, --target <name>``: Target name in the configuration (default: ``main``).
* ``--state <name>``: Target state to transition to (default: ``shell``).
* ``--update-image``: If set, the full SD card image will be flashed before updating boot files.

flash-sd
~~~~~~~~

Write a full SD card image to a mux-attached card, then stop. Unlike ``boot-soc
--update-image``, this does not boot the board afterwards -- it is for resetting a
rig's card to a known image.

The command powers the board down, switches the SD mux to the host, writes the
image with labgrid's ``USBStorageDriver``, switches the mux back to the DUT, and
leaves the board powered off unless told otherwise.

.. warning::

   This is destructive: it overwrites the entire card, not just the boot
   partition.

.. code-block:: bash

    # Flash a published Kuiper release
    adi-lg flash-sd --config soc.yaml --release 2023_R2_P1

    # Flash a locally built image (the .zip adi-kuiper-gen emits is extracted first)
    adi-lg flash-sd --config soc.yaml --image image_2025-03-18-ADI-Kuiper-full.zip

    # Check what would happen without touching hardware
    adi-lg flash-sd --config soc.yaml --image kuiper.img --dry-run

**Options:**

* ``-c, --config <path>``: (Required) Labgrid configuration file.
* ``--image <path>``: SD card image to write -- either a ``.img`` or a ``.zip`` containing one.
* ``--release <version>``: Kuiper release to download and write. Mutually exclusive with ``--image``; exactly one is required.
* ``--cache-path <path>``: Where images are downloaded and extracted (default: ``/tmp/kuiper_cache``).
* ``-t, --target <name>``: Target name in the configuration (default: ``main``).
* ``--mode <dd|bmaptool>``: Write mode (default: ``dd``).
* ``--sd-mode-after <dut|host|off>``: SD mux mode to leave set after writing (default: ``dut``).
* ``--power-off / --no-power-off``: Leave the board powered down afterwards (default: ``--power-off``).
* ``--min-free-gb <n>``: Refuse to download or extract with less free space than this (default: ``24``).
* ``--dry-run``: Resolve the image and print the plan without writing anything.

**Required configuration.** The env YAML must declare a power driver,
``USBSDMuxDriver`` and ``USBStorageDriver``. The last one is easy to miss --
``USBStorageDriver`` binds the ``USBSDMuxDevice`` resource directly and is what
actually performs the write:

.. tab-set::

    .. tab-item:: Exporter

        ``resources.yaml`` (on exporter host):

        .. code-block:: yaml

            mini2_group:
              VesyncOutlet:
                cls: VesyncOutlet
                outlet_names: 'Board Power'
                username: 'user@example.com'
                password: 'password'
              USBSDMuxDevice:
                cls: USBSDMuxDevice
                match:
                  ID_SERIAL_SHORT: '00001234'
              MassStorageDevice:
                cls: MassStorageDevice
                path: '/dev/disk/by-label/BOOT'
                use_with_sdmux: true

        ``target.yaml`` (on client):

        .. code-block:: yaml

            imports:
              - adi_lg_plugins

            targets:
              main:
                resources:
                  RemotePlace:
                    name: mini2
                drivers:
                  VesyncPowerDriver: {}
                  USBSDMuxDriver: {}
                  USBStorageDriver: {}
                  MassStorageDriver:
                    partition: '/dev/disk/by-label/BOOT'

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins

            targets:
              main:
                resources:
                  VesyncOutlet:
                    outlet_names: 'Board Power'
                    username: 'user@example.com'
                    password: 'password'
                  USBSDMuxDevice:
                    match:
                      ID_SERIAL_SHORT: '00001234'
                  MassStorageDevice:
                    path: '/dev/disk/by-label/BOOT'
                    use_with_sdmux: true
                drivers:
                  VesyncPowerDriver: {}
                  USBSDMuxDriver: {}
                  USBStorageDriver: {}
                  MassStorageDriver:
                    partition: '/dev/disk/by-label/BOOT'

**PARTUUIDs change on every flash.** ``adi-kuiper-gen`` runs ``parted mklabel
msdos``, which generates a fresh MBR signature per build, and the partition
UUIDs are derived from it. After writing, the command prints the new
``boot_partuuid`` / ``root_partuuid`` (and appends them to ``$GITHUB_OUTPUT``
when running in CI). Any env YAML that pins ``MassStorageDriver.partition`` to a
``/dev/disk/by-partuuid/...`` path will stop resolving -- use
``/dev/disk/by-label/BOOT`` instead, as above.

These values are read from the **source image**, not read back from the card, so
they describe what a successful write puts there rather than confirming what the
card now holds.

**Expect it to be slow.** ``USBStorageDriver`` syncs the image to the exporter
host before writing it, so a multi-gigabyte image crosses the network first and
is then written to the card.

boot-soc-ssh
~~~~~~~~~~~~

Boot an FPGA SoC using the SSH-based ``BootFPGASoCSSH`` strategy. This is useful when you have network access to the device and want to update boot files without using an SD Mux.

.. code-block:: bash

    adi-lg boot-soc-ssh --config soc.yaml --release 2023_R2_P1 --kernel uImage

**Options:**

* ``-c, --config <path>``: (Required) Labgrid configuration file.
* ``--release <version>``: Kuiper release version to use for boot files.
* ``--kernel <path>``: Path to a custom kernel file.
* ``--bootbin <path>``: Path to a custom BOOT.BIN file.
* ``--devicetree <path>``: Path to a custom devicetree (.dtb) file.
* ``-t, --target <name>``: Target name in the configuration (default: ``main``).
* ``--state <name>``: Target state to transition to (default: ``shell``).

boot-selmap
~~~~~~~~~~~

Boot a dual-FPGA system using the ``BootSelMap`` strategy.

.. code-block:: bash

    adi-lg boot-selmap --config soc.yaml \
        --pre-boot-file local_bitstream.bin:/boot/vu11p.bin \
        --post-boot-file local_dtbo.dtbo:/boot/vu11p.dtbo

**Options:**

* ``-c, --config <path>``: (Required) Labgrid configuration file.
* ``--pre-boot-file <local:remote>``: Files to upload to the Zynq before it reboots. Can be specified multiple times.
* ``--post-boot-file <local:remote>``: Files to upload to the Zynq after it boots, before triggering SelMap. Can be specified multiple times.
* ``-t, --target <name>``: Target name in the configuration (default: ``main``).
* ``--state <name>``: Target state to transition to (default: ``shell``).

The dedicated ``local_bitstream_filename``/``local_overlay_filename``
strategy attributes (or their ``LG_SM_BITSTREAM``/``LG_SM_OVERLAY``
environment variable overrides) are not exposed as CLI flags — set them in
the target YAML, or export the env vars before invoking this command, if
you're not using ``--post-boot-file`` for the Virtex artifacts. See
:doc:`strategies` for the full ``BootSelMap`` attribute reference.

recover
~~~~~~~

Recover a Zynq-7000 board whose SD card no longer boots, using the
``BootZynq7000JTAGRecovery`` strategy: bootstrap U-Boot over JTAG, TFTP-boot a
RAM-rooted recovery Linux, then reflash the SD card from the board itself.

.. warning::

   Destructive: the board's SD card (``/dev/mmcblk0``) is overwritten.

.. code-block:: bash

    adi-lg recover --config zc706.yaml --release 2023_R2_P1

    # Write a specific image instead of the strategy's configured one
    adi-lg recover --config zc706.yaml --sd-image kuiper.img

**Options:**

* ``-c, --config <path>``: (Required) Labgrid configuration file.
* ``--release <version>``: Kuiper release version; overrides the ``KuiperRelease`` resource.
* ``--sd-image <path>``: SD card image to flash, overriding the strategy's configured image.
* ``-t, --target <name>``: Target name in the configuration (default: ``main``).
* ``--state <name>``: Target state to transition to (default: ``sd_flash_done``).

The recovery Linux needs a recovery initramfs on the TFTP server - build it with
``build-recovery-initramfs`` below. See :doc:`strategies` for the full
``BootZynq7000JTAGRecovery`` state machine and configuration.

build-recovery-initramfs
~~~~~~~~~~~~~~~~~~~~~~~~

Build the recovery initramfs that ``BootZynq7000JTAGRecovery`` TFTP-boots: an
``/init`` script, a DHCP hook, and the applet symlinks around a static busybox
you supply, packaged as a U-Boot uImage ready for ``bootm`` (or a raw
``cpio.gz``).

.. code-block:: bash

    adi-lg build-recovery-initramfs \
        --busybox ./busybox-armv7l \
        --out /var/lib/tftpboot/uInitrd.recovery

**Options:**

* ``--busybox <path>``: (Required) Cross-compiled static busybox binary (ARM EABI for Zynq-7000).
* ``-o, --out <path>``: (Required) Destination file, e.g. ``/var/lib/tftpboot/uInitrd.recovery``.
* ``--work-dir <path>``: Staging directory for the cpio and rootfs (default: ``<out>.workdir``).
* ``--image-name <name>``: uImage "Image Name" field (default: ``ZC706-recovery``).
* ``--raw-cpio-gz / --uimage``: Emit a raw ``cpio.gz`` and skip ``mkimage`` (default: ``--uimage``).

generate-config
~~~~~~~~~~~~~~~

Interactively generate a Labgrid YAML configuration file. This wizard scans for available hardware (serial ports) and guides you through setting up strategies, power drivers, and other resources.

.. code-block:: bash

    adi-lg generate-config

**Features:**

* **Interactive:** Prompts for necessary configuration values.
* **Hardware Scanning:** Automatically detects serial ports and local IP addresses.
* **Strategy Support:** Configures ``BootFPGASoC``, ``BootFPGASoCTFTP``, and ``BootFPGASoCSSH``.
* **Resource Configuration:** Sets up Power Drivers (VeSync, CyberPower), Serial/Console, SD Mux, TFTP, and more.
* **Ready to load:** The file starts with ``imports: [adi_lg_plugins]``, which labgrid needs to resolve the ADI drivers and strategies it names.
* **labgrid-ready resources:** Resources use labgrid's class names and parameters (``RawSerialPort``, ``USBSDMuxDevice``, ``MassStorageDevice`` with ``path``, ``KuiperRelease`` with ``release_version``, ...), and the test suite builds every strategy's generated config with labgrid. SSH (``NetworkService``) logs in with the board login from the shell questions. The image writer adds ``USBStorageDriver``, which writes to the SD card through the SD mux. *Skip* (no power control) is offered only for ``BootFPGASoCSSH``; the other strategies need a power driver.

**Example Session:**

.. code-block:: text

    1   BootFPGASoC       SD card through a USB SD mux
    2   BootFPGASoCTFTP   kernel over TFTP from U-Boot
    3   BootFPGASoCSSH    boot files copied over SSH
    Select Strategy (BootFPGASoC): 1
    Target Name (main): zcu102
    Configuring Power Protocol
    1   VesyncPowerDriver   VeSync smart plug
    2   CyberPowerDriver    CyberPower PDU (SNMP)
    3   Skip                no power control
    Select Power Driver (VesyncPowerDriver): 1
    Outlet Names (comma separated): ZCU102
    VeSync Username: user@example.com
    VeSync Password:
    Power Cycle Delay (seconds) (5):
    Configuring Shell / Console
    Detected Serial Ports:
     #   Port           Description
    ─────────────────────────────────────────────────────────────────────────────
     1   /dev/ttyUSB0   FT232R USB UART
     2   Manual Entry   type a device path
    Select Serial Port (/dev/ttyUSB0):
    ...
    Output Filename (config_zcu102.yaml):
    Configuration generated: config_zcu102.yaml

**Resuming:** answers are saved as they are given, one file per target name under
``~/.cache/adi-lg/generate-config/`` (``$XDG_CACHE_HOME/adi-lg/...`` if set; readable only
by you). If a run stops - Ctrl-C, or an output file that can't be written - it says where its
answers are, and the next run offers to pick up from them:

.. code-block:: text

    Saved answers from earlier runs
    #   Target   Strategy      Saved              Answers
    ────────────────────────────────────────────────────────────────
    1   zcu102   BootFPGASoC   2026-10-28 09:32   6 saved
    2   new                                       start a new config
    Resume a saved run (zcu102):

**resume** uses the saved answers and asks only the questions the run never reached;
**review** asks every question again with its saved answer as the default; **new** starts
over. The output filename is always asked again (the saved one is the default), and the
VeSync password is never saved, so it is asked every time. Once the config is written the
saved answers are deleted.

Examples
--------

**Debugging a Boot Failure:**

Use the ``--debug`` flag to see every step of the transition and the output from Labgrid drivers.

.. code-block:: bash

    adi-lg --debug boot-fabric -c soc.yaml --bitstream build/system.bit

**Transitioning to an Intermediate State:**

If you only want to power on the device and flash the bitstream without waiting for Linux to boot:

    adi-lg boot-fabric -c soc.yaml --state flash_fpga

provision-software
~~~~~~~~~~~~~~~~~~

Provision software on a target system using the ``SoftwareProvisioningStrategy``. This command allows you to install packages, clone repositories, build software, and run tests.

.. code-block:: bash

    adi-lg provision-software --config dut.yaml \
        --package htop \
        --repo "https://github.com/my/repo.git,/home/root/repo,main" \
        --build "make,/home/root/repo" \
        --test "pytest,/home/root/repo"

**Options:**

* ``-c, --config <path>``: (Required) Labgrid configuration file.
* ``--package <name>``: Package to install using the system package manager (e.g., apt, dnf). Can be specified multiple times.
* ``--repo <url,dest[,branch]>``: Git repository to clone. Format: URL, destination path, and optional branch/tag. Can be specified multiple times.
* ``--build <cmd,dir>``: Build command to run in a specific directory. Format: command, directory. Can be specified multiple times.
* ``--test <cmd,dir>``: Test command to run in a specific directory. Format: command, directory. Can be specified multiple times.
* ``-t, --target <name>``: Target name in the configuration (default: ``main``).
* ``--state <name>``: Target state to transition to (default: ``tested``).

download-cloudsmith
~~~~~~~~~~~~~~~~~~~

Download a boot artifact (e.g. ``BOOT.BIN``) from a Cloudsmith package
repository. Resolves the latest package matching the FPGA carrier and
daughter card (or an exact pinned version), downloads it into a local
cache with SHA256 verification, and prints the cached path.

Requires the ``CLOUDSMITH_API_TOKEN`` environment variable.

.. code-block:: bash

    adi-lg download-cloudsmith --fpga-carrier zcu102 --daughter-card adrv9009

    # Pin an exact package version and copy the file next to your project
    adi-lg download-cloudsmith \
        --fpga-carrier zcu102 \
        --daughter-card adrv9009 \
        --version "boot_partition/main/2025_06_14-07_18_12/zynqmp-zcu102-rev10-adrv9009/" \
        --out ./BOOT.BIN

**Options:**

* ``--fpga-carrier <name>``: (Required) FPGA carrier, e.g. ``zcu102``.
* ``--daughter-card <name>``: (Required) Daughter card, e.g. ``adrv9009``.
* ``--filename <name>``: Artifact filename (default ``BOOT.BIN``).
* ``--owner <org>``: Cloudsmith owner/org (default ``adi``).
* ``--repo <name>``: Cloudsmith repository (default ``sdg-boot-partition``).
* ``--version <version>``: Pin an exact package version (default: latest).
* ``--cache-path <path>``: Cache directory (default ``~/.labgrid/cloudsmith_releases/``).
* ``--out <path>``: Copy the artifact here after download. If the path is an existing directory the file is copied into it keeping its filename; otherwise the path is used as the destination file.

The standalone ``cloudsmithdl`` console script (below) exposes the same resolution and download, with a different default cache path.

list-hardware
~~~~~~~~~~~~~

List live places on a coordinator along with their attributes (carrier, daughter-board, strategy, hdl-config, status, exporter).

.. code-block:: bash

    adi-lg list-hardware --coord my-coordinator:20408

    # Filter to show only available (unacquired) zcu102 carriers
    adi-lg list-hardware --carrier zcu102 --available-only

    # Output in JSON format for scripting
    adi-lg list-hardware --json

**Options:**

* ``--coord <host:port>``: Coordinator URL (defaults to ``$LG_COORDINATOR`` / ``$ADI_LG_COORDINATOR``).
* ``--carrier <name>``: Filter places by carrier name.
* ``--part <name>`` / ``--daughter-board <name>``: Filter places by daughter board name.
* ``--available-only`` / ``--only-available``: Only list places that are not currently acquired.
* ``--force-cli``: Skip the REST API and query via the ``labgrid-client`` CLI instead.
* ``--json``: Output the places as a JSON list on stdout.

Standalone tools
----------------

In addition to ``adi-lg``, the package installs small standalone
console scripts.

cloudsmithdl
~~~~~~~~~~~~

Resolve and download a boot artifact (e.g. ``BOOT.BIN``) from a
Cloudsmith package repository. By default it resolves the *latest*
package matching the carrier + daughter card; pass ``--version`` to pin
an exact one. Requires ``CLOUDSMITH_API_TOKEN`` in the environment.

.. code-block:: bash

    CLOUDSMITH_API_TOKEN=<token> cloudsmithdl \
        --fpga-carrier zcu102 --daughter-card adrv9009

**Options:**

* ``--fpga-carrier <name>``: (Required) FPGA carrier, e.g. ``zcu102``.
* ``--daughter-card <name>``: (Required) Daughter card, e.g. ``adrv9009``.
* ``--filename <name>``: Artifact filename (default: ``BOOT.BIN``).
* ``--owner <name>``: Cloudsmith owner/org (default: ``adi``).
* ``--repo <name>``: Cloudsmith repo (default: ``sdg-boot-partition``).
* ``--version <str>``: Pin an exact package version (default: latest).
* ``--cache-path <path>``: Download cache (default: ``/tmp/cloudsmith_cache``).

The downloaded file's SHA256 is verified against the Cloudsmith API
checksum. See :doc:`drivers` → CloudsmithDLDriver for using the same
resolution from a boot strategy.

adi-lg-prism-upload
~~~~~~~~~~~~~~~~~~~

Upload a JUnit XML result to a Prism server. This is the
uploader the reusable hardware workflows run for ``prism-upload: true``; it is
stdlib-only, so it also works from any CI job or shell.

.. code-block:: bash

    PRISM_URL=https://prism.example.com PRISM_TOKEN=<token> \
    adi-lg-prism-upload results.xml \
        --project lab-infra --run-name "$GITHUB_RUN_ID" \
        --tag branch=main --tag sha="$GITHUB_SHA" --wait

**Options** (each also reads a ``PRISM_<NAME>`` environment variable):

* ``junit``: (Required, positional) JUnit XML file to upload.
* ``--url <url>``: Prism API base URL (env: ``PRISM_URL``; default ``http://localhost:8000``).
* ``--token <token>``: Bearer API token (env: ``PRISM_TOKEN``), or log in with
  ``--email`` / ``--password`` (env: ``PRISM_EMAIL`` / ``PRISM_PASSWORD``).
* ``--project <slug>``: Target project (env: ``PRISM_PROJECT``).
* ``--auto-create-project``: Create the project if it doesn't exist.
* ``--run-name <name>``: Name for the run (env: ``PRISM_RUN_NAME``).
* ``--tag key=value``: Tag on the run. Repeatable.
* ``--archive <zip>``: ``.zip`` of measurement artifacts to upload with the JUnit.
* ``--measurement name=value[:unit[:min[:max]]]``: Add a numeric measurement, with optional
  limits, to the JUnit's single test case. Repeatable; the JUnit must contain exactly one
  ``<testcase>``.
* ``--wait [SECONDS]``: After uploading, poll until Prism finishes ingesting (60 s if no value).
* ``-q, --quiet`` / ``-v, --verbose``: Print only the result line / every step.

Exit codes: ``0`` success, ``2`` bad argument or missing file, ``3`` authentication failed,
``4`` project not found (pass ``--auto-create-project``), ``5`` upload failed, ``6`` ``--wait``
timed out. See :doc:`prism-reporting` for the workflow integration and enriched pytest
reporting.

``adi-lg-hw-ci`` — Hardware-CI helper
=====================================

``adi-lg-hw-ci`` is the CI-side helper that the reusable workflows call to
discover live boards on the coordinator, render labgrid env YAML for a place,
and build the test/no-os matrices. Most subcommands are invoked by the
workflows, but each works standalone for local debugging. The coordinator URL
defaults to ``$LG_COORDINATOR`` (falling back to ``$ADI_LG_COORDINATOR``) when
``--coord`` is omitted.

Discovery and matrices
----------------------

discover
~~~~~~~~

Query the coordinator for live places, harvest the consumer repo's pytest
markers, and emit the matrix include list as JSON on stdout (plus a
human-readable summary on stderr).

.. code-block:: bash

    adi-lg-hw-ci discover --test-root . --marker iio_hardware

* ``--test-root`` (required): consumer repo root to collect tests from.
* ``--marker`` (default ``iio_hardware``): top-level pytest marker to harvest.
* ``--coord``: coordinator URL (default ``$LG_COORDINATOR`` / ``$ADI_LG_COORDINATOR``).
* ``--timeout`` (default ``15.0``): seconds to wait when listing places.
* ``--force-cli``: skip the REST API and go straight to ``labgrid-client``.
* ``--include-acquired``: (debug) include acquired places in the matrix.
* ``--github-output``: also append ``matrix=`` / ``count=`` to ``$GITHUB_OUTPUT``.

request-matrix
~~~~~~~~~~~~~~

Emit a part-keyed matrix of the parts a repo wants (from its markers) that have
a live board on the coordinator (per ``GET /api/match``). Parts with no live
board are surfaced as ``::warning::`` GitHub annotations. Consumed by the
``hw-request`` workflow.

.. code-block:: bash

    adi-lg-hw-ci request-matrix --test-root test --marker iio_hardware

* ``--test-root`` (required): path to the consumer's test directory.
* ``--marker`` (default ``iio_hardware``): hardware-gating marker name.
* ``--coord``: coordinator ``host:port`` (default ``$LG_COORDINATOR``).
* ``--github-output``: also write ``matrix=`` / ``count=`` to ``$GITHUB_OUTPUT``.

noos-matrix
~~~~~~~~~~~

Emit a no-os project matrix: manifest projects that map to a live,
flash-capable board (per ``GET /api/match?mode=flash``). Each leg carries the
project to build, the part to request, the carrier, and the runner.

.. code-block:: bash

    adi-lg-hw-ci noos-matrix --manifest .github/hw-ci/projects.yaml

* ``--manifest`` (required): path to the no-os hw-ci ``projects.yaml``.
* ``--coord``: coordinator ``host:port`` (default ``$LG_COORDINATOR``).
* ``--github-output``: also write ``matrix=`` / ``count=`` to ``$GITHUB_OUTPUT``.

Env rendering
-------------

render-env
~~~~~~~~~~

Render the labgrid env YAML for a single place (from its coordinator tags) to a
file. Run inside each matrix shard before that shard's pytest invocation.

.. code-block:: bash

    adi-lg-hw-ci render-env --place my-zcu102 --out env.yaml

* ``--place`` (required): place name to render.
* ``--out`` (required): path to write the rendered env YAML to.
* ``--coord``: coordinator URL (default ``$LG_COORDINATOR``).
* ``--force-cli``: skip the REST API and go straight to ``labgrid-client``.

resolve-resources
~~~~~~~~~~~~~~~~~

Read UART + JTAG facts off a booted place and emit ``KEY=VALUE`` lines for a
bash / non-Python test driver to consume (see :doc:`hw-ci-bash`).

.. code-block:: bash

    adi-lg-hw-ci resolve-resources --config env.yaml --target main

* ``--config`` (required): rendered env YAML (from ``render-env``).
* ``--target`` (default ``main``): target name in the env YAML.
* ``--out`` (``stdout`` | ``github``, default ``stdout``): ``github`` also appends
  the ``KEY=VALUE`` lines to ``$GITHUB_OUTPUT``.

list-strategies
~~~~~~~~~~~~~~~

Dump the known boot-strategy class names and which of them have render
templates, as JSON. Exits non-zero if a known strategy is missing its template.

.. code-block:: bash

    adi-lg-hw-ci list-strategies

Infra boot-smoke
----------------

The ``infra-smoke.yml`` reusable workflow boots every live board once, to
check lab health rather than a consumer's code. These three subcommands are its
building blocks.

all-places-matrix
~~~~~~~~~~~~~~~~~

Emit one matrix leg per free live place, with no consumer markers or manifest.
Places whose ``boot-strategy`` boots Linux get a real boot (``mode: uri``);
flash-only places (no-os/JTAG, which need consumer firmware) get an
acquire-only check (``mode: reserve``). Acquired places are skipped with a
``::notice::``, and places tagged ``disabled=<reason>`` with a ``::warning::``.
An unreachable coordinator, or
one with no live places, exits ``3`` so the preflight fails loudly.

.. code-block:: bash

    adi-lg-hw-ci all-places-matrix --check-reachability --github-output

* ``--coord``: coordinator ``host:port`` (default ``$LG_COORDINATOR``).
* ``--check-reachability``: drop places whose exporter host doesn't answer on SSH, so a
  powered-down host doesn't produce a leg that queues forever.
* ``--github-output``: also write ``matrix=`` / ``count=`` to ``$GITHUB_OUTPUT``.

boot-status
~~~~~~~~~~~

Map an ``adi-lg request`` exit code to a boot-smoke status and print it:
``0`` → ``pass``; ``11`` (board busy) → ``skip``; anything else, including
``10`` (no matching board) and ``12`` (boot failed), → ``fail``.

.. code-block:: bash

    status=$(adi-lg-hw-ci boot-status --rc "$rc")

boot-junit
~~~~~~~~~~

Write one boot outcome as a single-test-case JUnit file (suite
``infra-boot-smoke``) for the test-report and Prism upload steps. ``fail``
adds a ``<failure>`` with ``--message``; ``skip`` adds a ``<skipped>``, which
does not fail the run.

.. code-block:: bash

    adi-lg-hw-ci boot-junit --place my-zcu102 --part adrv9002 --carrier zcu102 \
        --status "$status" --seconds 312 --out results-my-zcu102.xml

* ``--place``, ``--part``, ``--status pass|fail|skip``, ``--out``: required.
* ``--carrier``, ``--mode`` (default ``uri``), ``--seconds`` (default ``0``), ``--message``: optional.

Consumer onboarding helpers
---------------------------

``init`` (scaffold a consumer repo's hw-CI files for ``uri`` / ``flash`` /
``matlab`` mode), ``doctor`` (validate the whole onboarding chain in one pass),
``lint-markers`` (flag ``iio_hardware`` / ``iio_carrier`` markers that aren't
string literals), and ``matlab-matrix`` (build the MATLAB CI matrix from a
``board_map.yaml``) are documented step by step in
:doc:`onboarding-a-consumer-repo`. ``adi-lg-hw-ci setup-runner`` (alias
``runner-setup``) is the same command as ``adi-lg setup-runner`` above.

no-os build and XSA
-------------------

build-noos
~~~~~~~~~~

Build a no-os project for HW CI: compose the Vivado environment, source the
board's ``.xsa`` from the Kuiper image, and run ``make``. See
:doc:`hardware-ci-runner-setup` for the runner prerequisites and
:doc:`github-actions` for how the workflow invokes it.

.. code-block:: bash

    adi-lg-hw-ci build-noos --project adrv9009 --carrier zc706 \
        --board adrv9371 --release 2023_R2_P1

* ``--project`` (required): ``projects/<project>`` to build.
* ``--carrier`` (required): FPGA carrier (e.g. ``zc706``).
* ``--board`` (required): canonical daughter-board (e.g. ``adrv9371``).
* ``--release`` (required): Kuiper release for the ``.xsa`` (e.g. ``2023_R2_P1``).
* ``--validate``: on-target banner (informational at build time).
* ``--build-var K=V``: extra ``make`` variable (repeatable).
* ``--noos-root`` (default ``.``): no-os checkout root.
* ``--xsa-dir``: pin the Kuiper boot folder, skipping the FAT search.

fetch-xsa
~~~~~~~~~

Extract a board's ``system_top.xsa`` from the Kuiper image and print its path.
``build-noos`` uses the same source; run this standalone to pre-cache or
inspect the ``.xsa``. See :doc:`hardware-ci-runner-setup` and
:doc:`github-actions`.

.. code-block:: bash

    adi-lg-hw-ci fetch-xsa --release 2023_R2_P1 --board adrv9009 --carrier zc706

* ``--release`` (required): Kuiper release (e.g. ``2023_R2_P1``).
* ``--board`` (required): canonical daughter-board (e.g. ``adrv9009``).
* ``--carrier`` (required): FPGA carrier (e.g. ``zc706``).
* ``--out``: XSA cache dir (default ``~/.labgrid/kuiper_xsa``).
* ``--xsa-dir``: pin the Kuiper boot folder, skipping the FAT search.
