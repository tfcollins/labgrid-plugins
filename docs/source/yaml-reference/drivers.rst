Drivers
=======

Schema-level lookup for every driver registered by ``adi-labgrid-plugins``. Most drivers
take no YAML-level attributes of their own — configuration lives on the bound resource.
For full prose and troubleshooting, follow the link on each driver name into the
:doc:`User Guide <../user-guide/drivers>`.

Schema
------

.. list-table::
   :header-rows: 1
   :widths: 22 30 26 22

   * - Name
     - Required (driver attrs)
     - Optional (driver attrs / defaults)
     - Required resource(s)
   * - :ref:`user-guide/drivers:VesyncPowerDriver`
     - —
     - —
     - :ref:`user-guide/resources:VesyncOutlet`
   * - :ref:`user-guide/drivers:CyberPowerDriver`
     - —
     - —
     - :ref:`user-guide/resources:CyberPowerOutlet`
   * - :ref:`user-guide/drivers:HomeAssistantPowerDriver`
     - —
     - —
     - :ref:`user-guide/resources:HomeAssistantOutlet`
   * - :ref:`user-guide/drivers:ADIShellDriver`
     - ``prompt``, ``login_prompt``, ``username``
     - ``password`` (``''``), ``keyfile`` (``''``), ``login_timeout`` (60), ``console_ready`` (``''``), ``await_login_timeout`` (2), ``post_login_settle_time`` (0)
     - Serial console (e.g. ``RawSerialPort``)
   * - :ref:`user-guide/drivers:MassStorageDriver`
     - —
     - —
     - :ref:`user-guide/resources:MassStorageDevice`
   * - :ref:`user-guide/drivers:KuiperDLDriver`
     - —
     - —
     - :ref:`user-guide/resources:KuiperRelease`
   * - :ref:`user-guide/drivers:TFTPServerDriver`
     - —
     - —
     - :ref:`user-guide/resources:TFTPServerResource`
   * - :ref:`user-guide/drivers:XilinxJTAGDriver`
     - —
     - —
     - :ref:`user-guide/resources:XilinxDeviceJTAG`, :ref:`user-guide/resources:XilinxVivadoTool`
   * - :ref:`user-guide/drivers:SoftwareInstallerDriver`
     - —
     - —
     - Any ``CommandProtocol`` + ``FileTransferProtocol`` providers (typically :ref:`user-guide/drivers:ADIShellDriver` or ``SSHDriver``)

Minimal YAML
------------

Power Control
~~~~~~~~~~~~~

.. code-block:: yaml

    drivers:
      VesyncPowerDriver: {}        # requires VesyncOutlet
      CyberPowerDriver: {}         # requires CyberPowerOutlet
      HomeAssistantPowerDriver: {} # requires HomeAssistantOutlet

Shell / File Transfer
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

    drivers:
      ADIShellDriver:
        prompt: 'root@analog:.*#'
        login_prompt: 'login:'
        username: 'root'
        password: 'analog'

Storage & Images
~~~~~~~~~~~~~~~~

.. code-block:: yaml

    drivers:
      MassStorageDriver: {}    # requires MassStorageDevice
      KuiperDLDriver: {}       # requires KuiperRelease

Boot / Network Services
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

    drivers:
      TFTPServerDriver: {}     # requires TFTPServerResource

FPGA JTAG
~~~~~~~~~

.. code-block:: yaml

    drivers:
      XilinxJTAGDriver: {}     # requires XilinxDeviceJTAG + XilinxVivadoTool

Provisioning
~~~~~~~~~~~~

.. code-block:: yaml

    drivers:
      SoftwareInstallerDriver: {}  # composes CommandProtocol + FileTransferProtocol
