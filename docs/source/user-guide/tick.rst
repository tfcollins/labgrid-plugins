Tick runtime deploy (ZCU102 + AD9081)
=====================================

The Tick classes deploy the ``axi_timed_command_scheduler`` IP onto a board
that already booted its pre-baked Kuiper SD image, at runtime over SSH.

Components
----------

- ``TickArtifacts`` (resource) -- paths to the bitstream, prebuilt ``.dtbo``
  overlay, and kernel module, plus target-side naming.
- ``TickFpgaManagerDriver`` -- programs the FPGA via the ``fpga_manager`` sysfs.
- ``TickOverlayDriver`` -- applies/removes the DT overlay via configfs.
- ``TickModuleDriver`` -- ``insmod``\ s the module and (optionally) restarts
  ``iiod`` so the IIO device is network-discoverable.
- ``BootTickFPGASSH`` -- subclasses ``BootFPGASoCSSH``; boots to a shell, then
  runs the three deploy steps. States:
  ``tick_fpga_loaded -> tick_overlay_applied -> tick_module_loaded``; ``tick_off``
  reverses the deploy and powers down.

Example environment
-------------------

.. tab-set::

    .. tab-item:: Exporter

        ``resources.yaml`` (on exporter host):

        .. code-block:: yaml

            mini2_group:
              VesyncOutlet:
                cls: VesyncOutlet
                outlet_names: 'ZCU102 Power'
                username: 'user@example.com'
                password: 'password'
              RawSerialPort:
                cls: RawSerialPort
                port: '/dev/ttyUSB0'
                speed: 115200
              NetworkService:
                cls: NetworkService
                address: '10.0.0.50'
                username: 'root'
                password: 'analog'
              TickArtifacts:
                cls: TickArtifacts
                bitstream_path: /run/tick/ad9081_fmca_ebz_zcu102.bit
                overlay_dtbo_path: /run/tick/tick.dtbo
                module_ko_path: /run/tick/axi_timed_command_scheduler.ko

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
                  SerialDriver: {}
                  ADIShellDriver:
                    prompt: 'root@.*#'
                    login_prompt: 'analog login: '
                    username: root
                    password: analog
                  SSHDriver@runtime-ssh: {}
                  TickFpgaManagerDriver:
                    bindings: {command: runtime-ssh, fs: runtime-ssh}
                  TickOverlayDriver:
                    bindings: {command: runtime-ssh, fs: runtime-ssh}
                  TickModuleDriver:
                    bindings: {command: runtime-ssh, fs: runtime-ssh}
                  BootTickFPGASSH:
                    bindings: {ssh: runtime-ssh}

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  VesyncOutlet:
                    outlet_names: 'ZCU102 Power'
                    username: 'user@example.com'
                    password: 'password'
                  RawSerialPort:
                    port: '/dev/ttyUSB0'
                    speed: 115200
                  NetworkService:
                    address: '10.0.0.50'
                    username: 'root'
                    password: 'analog'
                  TickArtifacts:
                    bitstream_path: /run/tick/ad9081_fmca_ebz_zcu102.bit
                    overlay_dtbo_path: /run/tick/tick.dtbo
                    module_ko_path: /run/tick/axi_timed_command_scheduler.ko
                drivers:
                  VesyncPowerDriver: {}
                  SerialDriver: {}
                  ADIShellDriver:
                    prompt: 'root@.*#'
                    login_prompt: 'analog login: '
                    username: root
                    password: analog
                  SSHDriver@runtime-ssh: {}
                  TickFpgaManagerDriver:
                    bindings: {command: runtime-ssh, fs: runtime-ssh}
                  TickOverlayDriver:
                    bindings: {command: runtime-ssh, fs: runtime-ssh}
                  TickModuleDriver:
                    bindings: {command: runtime-ssh, fs: runtime-ssh}
                  BootTickFPGASSH:
                    bindings: {ssh: runtime-ssh}

.. note::

   The Tick drivers bind the ``CommandProtocol`` + ``FileTransferProtocol``
   pair. When the env also defines a console-based shell that satisfies those
   protocols, name the intended SSH driver explicitly so binding is
   unambiguous.
