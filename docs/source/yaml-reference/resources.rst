Resources
=========

Schema-level lookup for every resource registered by ``adi-labgrid-plugins``. For full
prose, troubleshooting, and examples, follow the link on each resource name into the
:doc:`User Guide <../user-guide/resources>`.

Schema
------

.. list-table::
   :header-rows: 1
   :widths: 22 26 30 22

   * - Name
     - Required
     - Optional (defaults)
     - Pairs with
   * - :ref:`user-guide/resources:VesyncOutlet`
     - ``outlet_names``, ``username``, ``password``
     - ``delay`` (5.0)
     - :ref:`user-guide/drivers:VesyncPowerDriver`
   * - :ref:`user-guide/resources:CyberPowerOutlet`
     - ``address``, ``outlet``
     - ``delay`` (5.0)
     - :ref:`user-guide/drivers:CyberPowerDriver`
   * - :ref:`user-guide/resources:HomeAssistantOutlet`
     - ``url``, ``token``, ``entity_id``
     - ``delay`` (5.0)
     - :ref:`user-guide/drivers:HomeAssistantPowerDriver`
   * - :ref:`user-guide/resources:MassStorageDevice`
     - ``device``, ``partition``
     - —
     - :ref:`user-guide/drivers:MassStorageDriver`
   * - :ref:`user-guide/resources:KuiperRelease`
     - ``release``, ``cache_dir``
     - —
     - :ref:`user-guide/drivers:KuiperDLDriver`
   * - :ref:`user-guide/resources:TFTPServerResource`
     - —
     - ``address`` (``'auto'``), ``port`` (3069), ``root`` (``/var/lib/tftpboot``)
     - :ref:`user-guide/drivers:TFTPServerDriver`, :ref:`user-guide/strategies:BootFPGASoCTFTP Strategy`
   * - :ref:`user-guide/resources:XilinxVivadoTool`
     - —
     - ``vivado_path``, ``version``, ``xsdb_path`` (derived)
     - :ref:`user-guide/drivers:XilinxJTAGDriver`
   * - :ref:`user-guide/resources:XilinxDeviceJTAG`
     - —
     - ``root_target`` (1), ``microblaze_target`` (3), ``bitstream_path``, ``kernel_path``, ``devicetree_path``
     - :ref:`user-guide/drivers:XilinxJTAGDriver`, :ref:`user-guide/strategies:BootFabric Strategy`

Minimal YAML
------------

Power Control
~~~~~~~~~~~~~

.. code-block:: yaml

    # VesyncOutlet
    resources:
      VesyncOutlet:
        outlet_names: 'Device Power'
        username: 'user@example.com'
        password: 'secret'

    # CyberPowerOutlet
    resources:
      CyberPowerOutlet:
        address: '192.168.1.100'
        outlet: 3

    # HomeAssistantOutlet
    resources:
      HomeAssistantOutlet:
        url: 'http://homeassistant.local:8123'
        token: 'eyJhbGciOiJI...'
        entity_id: 'switch.lab_outlet_1'

Storage & Images
~~~~~~~~~~~~~~~~

.. code-block:: yaml

    # MassStorageDevice
    resources:
      MassStorageDevice:
        device: '/dev/sdb'
        partition: 1

    # KuiperRelease
    resources:
      KuiperRelease:
        release: '2023_R2_P1'
        cache_dir: '/var/cache/kuiper'

Boot / Network Services
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

    # TFTPServerResource — all fields optional
    resources:
      TFTPServerResource: {}

FPGA JTAG
~~~~~~~~~

.. code-block:: yaml

    # XilinxVivadoTool
    resources:
      XilinxVivadoTool:
        vivado_path: '/tools/Xilinx/2025.1/Vivado'

    # XilinxDeviceJTAG
    resources:
      XilinxDeviceJTAG:
        bitstream_path: '/builds/system_top.bit'
        kernel_path:    '/builds/simpleImage.vcu118.strip'
