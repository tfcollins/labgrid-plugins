Command Line Interface
======================

The ``adi-lg`` command provides a convenient way to execute boot strategies directly from the terminal. This tool leverages the ``click`` library for a robust CLI and ``rich`` for beautiful, informative output.

Installation
------------

The CLI is automatically installed when you install ``labgrid-plugins``. Ensure you have the necessary dependencies:

.. code-block:: bash

    pip install labgrid-plugins[cli]  # or just pip install . if you have click and rich

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
  no-os ``.elf`` instead of booting Kuiper (see the flash-mode note below).
* ``--bootfile``: pin an image version. Defaults to the coordinator catalog's default image.
* ``--wait`` (default ``1800``): seconds to queue for a free matching board. ``0`` fails fast.
* ``--power-down``: power the board off after release (default: leave it powered for the next user).
* ``--coord``: coordinator ``host:port`` (default: ``$LG_COORDINATOR``).
* ``--run '<cmd>'``: run ``<cmd>`` with ``IIO_URI``, ``LG_PLACE``, ``LG_CARRIER``,
  ``HW_DAUGHTER`` and ``HW_CARRIER`` exported into its environment. The command's own
  exit code is propagated.

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

**Example Session:**

.. code-block:: text

    Select Strategy [BootFPGASoC]: BootFPGASoC
    Target Name [main]: zcu102
    Configuring Power Protocol
    Select Power Driver [VesyncPowerDriver]: VesyncPowerDriver
    Outlet Names (comma separated): ZCU102
    VeSync Username: user@example.com
    VeSync Password: [hidden]
    Configuring Shell / Console
    Detected Serial Ports: /dev/ttyUSB0, /dev/ttyUSB1
    Select Serial Port [/dev/ttyUSB0]: /dev/ttyUSB0
    ...
    Configuration generated: config_zcu102.yaml

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

Standalone download tools
-------------------------

In addition to ``adi-lg``, the package installs small standalone
download utilities as console scripts.

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
