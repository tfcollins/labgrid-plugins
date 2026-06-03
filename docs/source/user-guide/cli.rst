Command Line Interface
======================

The ``adi-lg`` command provides a convenient way to execute boot strategies directly from the terminal. This tool leverages the ``click`` library for a robust CLI and ``rich`` for beautiful, informative output.

Installation
------------

The CLI is automatically installed when you install ``adi-labgrid-plugins``. Ensure you have the necessary dependencies:

.. code-block:: bash

    pip install adi-labgrid-plugins[cli]  # or just pip install . if you have click and rich

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
* ``--bootfile``: pin an image version. Defaults to the coordinator catalog's default image.
* ``--wait`` (default ``1800``): seconds to queue for a free matching board. ``0`` fails fast.
* ``--power-down``: power the board off after release (default: leave it powered for the next user).
* ``--coord``: coordinator ``host:port`` (default: ``$LG_COORDINATOR``).
* ``--run '<cmd>'``: run ``<cmd>`` with ``IIO_URI``, ``LG_PLACE`` and ``LG_CARRIER`` exported into
  its environment. The command's own exit code is propagated.

Exit codes (so CI can tell an infra problem from a real test failure):

* ``0`` / child's code — success, or the ``--run`` command's own exit code.
* ``10`` — no matching board exists for the part/filters.
* ``11`` — matching boards exist but none became free within ``--wait``.
* ``12`` — the board failed to boot (the console tail is printed for triage).
* ``130`` — interrupted (Ctrl-C or CI job-timeout); the board is still released.

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
