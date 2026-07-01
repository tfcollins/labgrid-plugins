Strategies
==========

Schema-level lookup for every strategy registered by ``labgrid-plugins``. For
full prose, state diagrams, and troubleshooting, follow the link on each strategy
name into the :doc:`User Guide <../user-guide/strategies>`.

Schema
------

.. list-table::
   :header-rows: 1
   :widths: 24 34 42

   * - Name
     - Optional attributes (defaults)
     - Required bindings
   * - :ref:`user-guide/strategies:BootFPGASoC Strategy`
     - ``reached_linux_marker`` (``'analog'``), ``update_image`` (False), ``wait_for_linux_prompt_timeout`` (60), ``debug_write_boot_log`` (False)
     - ``PowerProtocol``, ``ADIShellDriver``, ``MassStorageDriver``, ``USBSDMuxDriver`` (+ optional ``KuiperDLDriver``)
   * - :ref:`user-guide/strategies:BootFPGASoCSSH Strategy`
     - ``reached_linux_marker`` (``'analog'``), ``wait_for_linux_prompt_timeout`` (60), ``debug_write_boot_log`` (False)
     - ``ADIShellDriver``, ``SSHDriver`` (+ optional ``PowerProtocol``, ``KuiperDLDriver``)
   * - :ref:`user-guide/strategies:BootFPGASoCTFTP Strategy`
     - ``reached_linux_marker`` (``'analog'``), ``wait_for_linux_prompt_timeout`` (60), ``tftp_root_folder`` (``/var/lib/tftpboot``), ``kernel_addr`` (``0x30000000``), ``dtb_addr`` (``0x2A000000``), ``bootargs``
     - ``ADIShellDriver``, ``TFTPServerResource``, ``TFTPServerDriver`` (+ optional ``PowerProtocol``, ``SSHDriver``, ``KuiperDLDriver``)
   * - :ref:`user-guide/strategies:BootSelMap Strategy`
     - ``reached_linux_marker`` (``'analog'``), ``ethernet_interface``, ``iio_jesd_driver_name`` (``axi-ad9081-rx-hpc``), ``iio_jesd_data_mode`` (``DATA``), ``iio_jesd_link_mode_attr`` (``jesd204_link_mode``), ``pre_boot_boot_files``, ``post_boot_boot_files``
     - Shell, SSH, power, JESD (see User Guide)
   * - :ref:`user-guide/strategies:BootFabric Strategy`
     - ``reached_boot_marker`` (``'login:'``), ``wait_for_boot_timeout`` (120), ``verify_iio_device``, ``trigger_dhcp_reset``, ``power_off_delay``, ``debug_write_boot_log`` (False)
     - ``ADIShellDriver``, ``XilinxJTAGDriver`` (+ optional ``PowerProtocol``)
   * - :ref:`user-guide/strategies:BootRPI Strategy`
     - ``ssh_boot_timeout``, ``power_off_delay``
     - ``SSHDriver`` (+ optional ``PowerProtocol``)
   * - :ref:`user-guide/strategies:SoftwareProvisioningStrategy`
     - ``packages`` ([]), ``repos`` ([]), ``build_steps`` ([]), ``test_steps`` ([])
     - :ref:`user-guide/drivers:SoftwareInstallerDriver`

Minimal YAML
------------

FPGA SoC Boot Variants
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

    # BootFPGASoC — SD-card mux based
    strategies:
      BootFPGASoC:
        reached_linux_marker: 'analog'

    # BootFPGASoCSSH — SSH-based file transfer after initial boot
    strategies:
      BootFPGASoCSSH:
        reached_linux_marker: 'analog'

    # BootFPGASoCTFTP — U-Boot + TFTP kernel/dtb load
    strategies:
      BootFPGASoCTFTP:
        reached_linux_marker: 'analog'
        bootargs: 'console=ttyPS0,115200 root=/dev/mmcblk0p2 rw rootwait'

Dual-FPGA (SelMap)
~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

    strategies:
      BootSelMap:
        reached_linux_marker: 'analog'
        iio_jesd_driver_name: 'axi-ad9081-rx-hpc'

FPGA Fabric (Microblaze / JTAG)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

    strategies:
      BootFabric:
        reached_boot_marker: 'login:'
        wait_for_boot_timeout: 120
        verify_iio_device: 'axi-ad9081-rx-hpc'

Raspberry Pi
~~~~~~~~~~~~

.. code-block:: yaml

    strategies:
      BootRPI: {}

Software Provisioning
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

    strategies:
      SoftwareProvisioningStrategy:
        packages: [git, build-essential]
        repos:
          - {url: 'https://github.com/analogdevicesinc/libiio', dest: '/opt/libiio', branch: 'main'}
        build_steps:
          - {cmd: 'cmake -S . -B build && cmake --build build -j4', dir: '/opt/libiio'}
        test_steps:
          - {cmd: 'ctest --test-dir build', dir: '/opt/libiio'}
