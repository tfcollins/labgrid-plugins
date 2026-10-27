Exporter Setup
==============

Exporters run on physical hosts that have access to hardware (serial ports,
JTAG cables, network connections, power control). They register their resources
with the coordinator so that clients can discover and use them.

Resource Configuration
----------------------

Each exporter needs a YAML file defining its resource groups. The group naming
convention is ``<BOARD>_<CHIP>`` to ensure consistency across exporters:

.. code-block:: yaml

   ## resources.yaml for a VCU118+AD9081 setup
   VCU118_AD9081:
     NetworkService:
       cls: NetworkService
       address: "10.0.0.23"
       username: "root"
     RawSerialPort:
       cls: RawSerialPort
       port: "/dev/ttyUSB1"
       speed: 115200
     XilinxDeviceJTAG:
       cls: XilinxDeviceJTAG
       root_target: 1
       microblaze_target: 3
       bitstream_path: "ref/vcu118_ad9081/system_top.bit"
       kernel_path: "ref/vcu118_ad9081/simpleImage.strip"
     XilinxVivadoTool:
       cls: XilinxVivadoTool
       vivado_path: "/tools/Xilinx/2025.1/Vivado"

Using Templates
---------------

Standardized templates are provided in ``exporter_configs/templates/``:

Each is named for the boot path it serves:

.. list-table::
   :header-rows: 1
   :widths: 22 48 30

   * - Template
     - For
     - Boot strategy
   * - ``soc-sdmux.yaml``
     - Zynq / ZynqMP SoC (ZCU102, ZC706, ...) whose SD card is written through a USB SD mux
     - ``BootFPGASoC``, or ``BootFPGASoCSSH``
   * - ``soc-ssh.yaml``
     - Zynq / ZynqMP SoC without an SD mux; boot files copied over SSH into the running Linux
     - ``BootFPGASoCSSH``
   * - ``soc-tftp.yaml``
     - Zynq / ZynqMP SoC (ZC706, ADRV9361, ...) booted over TFTP from U-Boot, with JTAG to
       start U-Boot when needed
     - ``BootFPGASoCTFTP``
   * - ``zynqmp-jtag.yaml``
     - UltraScale+ board strapped for JTAG boot (ADRV9009-ZU11EG, ...)
     - ``BootZynqMPJTAG``
   * - ``fabric-jtag.yaml``
     - FPGA with a MicroBlaze soft CPU (VCU118, ...), bitstream and kernel loaded over JTAG
     - ``BootFabric``
   * - ``rpi-ssh.yaml``
     - Raspberry Pi driven over SSH
     - ``BootRPI``

The resource group is named ``<CARRIER>_<CHIP>`` from the ``carrier`` and ``chip`` fields
(e.g. ``ZCU102_AD9081``); the Raspberry Pi template uses ``RPI_<VARIANT>``. Each template's
``## boot-strategy:`` line names its strategy, and it exports every resource that strategy's
client environment binds - checked in CI by ``tests/test_exporter_templates.py``.

Every template also exports ``NetworkService`` (the board's IP, which ``adi-lg request``
reads for ``IIO_URI``) and a power outlet:

- ``power`` - ``vesync`` (default) or ``homeassistant``. Tag the place
  ``power-driver=VesyncPowerDriver`` or ``power-driver=HomeAssistantPowerDriver`` to match;
  ``render-env`` uses the tag to choose the client's power driver.
- ``power_outlet`` - the VeSync outlet name, or the Home Assistant ``entity_id``
  (e.g. ``switch.lab_outlet_1``).
- Outlet credentials are not written into the file. labgrid reads them from the exporter's
  environment when it starts: ``VESYNC_USERNAME`` / ``VESYNC_PASSWORD``, or
  ``HOMEASSISTANT_URL`` / ``HOMEASSISTANT_TOKEN``. For a systemd service, put them in
  ``/etc/labgrid/exporter.env`` (mode ``600``) and reference it with ``EnvironmentFile=``.

Each template is a single exporter's ``resources.yaml`` with Jinja2 fields
(``{{ target_ip }}``, ``{{ serial_port | default(...) }}``, ...). Fill them in
by hand, or let ``adi-lg netbox add-hardware`` render them
(:doc:`netbox-onboarding`). labgrid does not supply these fields itself — its
loader only provides ``env``, ``hostname``, ``name``, and ``isolated`` — so an
unfilled field renders as an empty string.

.. important::

   labgrid loads every exporter config as a Jinja2 template in which a line
   starting with ``#`` is a *template statement* and ``##`` starts a comment.
   Write comments in exporter configs as ``## ...``; a plain YAML ``# ...``
   line stops ``labgrid-exporter`` from starting with
   ``TemplateSyntaxError: Encountered unknown tag``.

Validating Configurations
-------------------------

Before deploying an exporter, validate the config:

.. code-block:: bash

   python exporter_configs/validate.py resources.yaml

This checks:

- The file parses the way ``labgrid-exporter`` loads it (Jinja2 with ``#``
  line statements and ``##`` comments)
- YAML structure is valid
- All resource classes are recognized
- Every resource declares a ``cls`` (JSON schema)

Running the Exporter
--------------------

.. note::

   Running the exporter reliably requires ``ser2net`` 4.6.1 on ``PATH``
   — the 4.6.0 build shipped in most distributions hangs on the
   RFC2217 ``purge`` option. See :doc:`exporter-deployment` for the
   full host-setup procedure.

.. code-block:: bash

   # Install the plugins on the exporter host
   pip install -e ".[dev]"

   # Start the exporter
   labgrid-exporter \
       -c <coordinator-host>:20408 \
       -n my-lab-host \
       resources.yaml

The exporter name (``-n``) must be unique across all exporters.

Setting Up Places
-----------------

After an exporter registers its resources, create a place and add match
patterns to bind resources to it. This can be done via the web dashboard or
the API:

.. code-block:: bash

   # Via labgrid-client
   labgrid-client -x <coordinator>:20408 create vcu118-lab1
   labgrid-client -x <coordinator>:20408 -p vcu118-lab1 add-match \
       "my-lab-host/VCU118_AD9081/*"
   labgrid-client -x <coordinator>:20408 -p vcu118-lab1 set-tags \
       board=vcu118 chip=ad9081

   # Or via the REST API
   curl -X POST http://localhost:8000/api/places -d '{"name":"vcu118-lab1"}'
   curl -X POST http://localhost:8000/api/places/vcu118-lab1/matches \
       -d '{"pattern":"my-lab-host/VCU118_AD9081/*"}'

Group Naming Convention
-----------------------

Use consistent group names across all exporters:

.. list-table::
   :header-rows: 1

   * - Board
     - Chip
     - Group Name
   * - VCU118
     - AD9081
     - ``VCU118_AD9081``
   * - VCU118
     - AD9084
     - ``VCU118_AD9084``
   * - ZCU102
     - AD9081
     - ``ZCU102_AD9081``
   * - Raspberry Pi CM4
     - (none)
     - ``RPI_CM4``

This enables reliable match patterns like ``*/VCU118_AD9081/*`` that work
regardless of which exporter host the board is connected to.
