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

- ``vcu118_ad9081.yaml`` - VCU118 with AD9081 transceiver
- ``rpi.yaml`` - Raspberry Pi
- ``zcu102.yaml`` - ZCU102 SoC

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
