Execution and Access Topology
=============================

.. role:: topology-exporter-label
   :class: topology-exporter-label

.. role:: topology-network-label
   :class: topology-network-label

.. role:: topology-local-label
   :class: topology-local-label

A coordinator can make a resource *discoverable* without making every driver
operation run on the exporter.  Use this page when deciding where to install a
tool, which host must hold a file, and which network paths must be open.

Terminology
-----------

**Client**
   The process running ``labgrid-client``, pytest, or the hardware CI job.  In
   CI this is the job runner.

**Exporter path**
   An operation is exporter-capable when it follows resource metadata from a
   ``RemotePlace`` and executes on, or connects through, the exporter.  A
   remote serial console is a typical exporter path.  In this package,
   ``MassStorageDriver`` and ``XilinxJTAGDriver`` also explicitly move their
   host-side commands to the exporter over SSH.

**Client LAN path**
   The client opens a connection directly to a target or service.  Registering
   the corresponding resource on an exporter does not tunnel this connection.
   Examples are client-to-DUT SSH, SNMP to a PDU, and HTTP to Home Assistant.

**DUT return path**
   The target opens a connection back to a service running in the client
   process.  TFTP and the recovery HTTP server use this direction.  The DUT
   must be able to route to the advertised client address and port.

**Client-local requirement**
   A command, service, cache, or source path exists on the client itself.
   This is different from direct physical access.  The matrices say
   explicitly when USB/JTAG/block-device access must instead be local to the
   exporter or client.

``RemotePlace`` alone is therefore not a transport guarantee.  In particular,
plain plugin resources may contain ``extra["proxy"]`` after coordinator
resolution, but only code which consumes that field relocates its work.

.. container:: topology-legend

   :topology-exporter-label:`Exporter path` marks work executed on or through
   the exporter. :topology-network-label:`Network path` marks client-to-service
   or DUT-to-client traffic. :topology-local-label:`Local placement` marks
   tools, files, or physical access that must exist on a named host.

.. _driver-transport-matrix:

Driver transport matrix
-----------------------

.. list-table:: Driver transport matrix
   :header-rows: 1
   :widths: 20 20 25 35
   :class: topology-matrix topology-driver-matrix

   * - Driver
     - Exporter path
     - Required network path
     - Client/direct requirements
   * - ``APCDriver``
     - No. The SNMP library runs in the client.
     - Client → APC PDU, UDP/161.
     - No direct hardware access; SNMP credentials and ``pysnmp`` are client-side.
   * - ``VesyncPowerDriver``
     - No. ``pyvesync`` runs in the client.
     - Client → VeSync cloud service, plus the outlet's normal cloud connectivity.
     - VeSync credentials and ``pyvesync`` are client-side.
   * - ``MassStorageDriver``
     - **Yes.** ``pmount``, ``pumount``, directory operations, and copies run on the exporter selected by the bound resource; source files are staged there over SSH.
     - Client → exporter SSH. ProxyJump-only exporters are not supported by the current staging helper.
     - The USB block device and mount tools must be local to the exporter. Without remote metadata they must be local to the client instead.
   * - ``ADIShellDriver``
     - Inherited from its ``ConsoleProtocol``. A coordinator-provided network serial console works through the exporter; a local serial resource stays local.
     - Client → exported serial endpoint, or whatever path the bound console requires.
     - No independent transport. Commands and XMODEM transfers use the bound console.
   * - ``KuiperDLDriver``
     - No. Downloads, cache access, and extraction run in the client.
     - Client → Kuiper release host/Internet.
     - Cache, image extraction dependencies, and resulting boot-file paths are client-local.
   * - ``CloudsmithDLDriver``
     - No. API queries, downloads, and cache access run in the client.
     - Client → Cloudsmith API/CDN/Internet.
     - Cloudsmith credentials and cache paths are client-local.
   * - ``CyberPowerDriver``
     - No. The SNMP library runs in the client.
     - Client → CyberPower PDU, UDP/161.
     - No direct hardware access; ``pysnmp`` is client-side.
   * - ``XilinxJTAGDriver``
     - **Yes.** ``xsdb`` runs on the exporter selected by ``XilinxDeviceJTAG``; only the generated Tcl script is staged automatically.
     - Client → exporter SSH; ``jtag_url`` is resolved by the exporter-side ``xsdb`` process. ProxyJump-only exporters are not supported by the current Tcl staging helper.
     - Xilinx tools and JTAG/hw_server access must be on the exporter. Bitstream, kernel, ELF, and other payload paths embedded in Tcl must already be valid there; they are not uploaded automatically.
   * - ``TFTPServerDriver``
     - No. The Python TFTP server starts in the client process; ``extra["proxy"]`` is not consumed.
     - DUT → client UDP on the configured port (3069 by default, often reached through a port-69 redirect).
     - The TFTP root, files, bind address, and redirect/firewall setup are client-local.
   * - ``SoftwareInstallerDriver``
     - Inherited from its bound ``CommandProtocol`` and ``FileTransferProtocol``.
     - Whatever those providers require; with ``SSHDriver`` this is client → DUT LAN.
     - Build tools and packages are installed on the DUT; source files begin on the client and use the bound transfer protocol.
   * - ``HomeAssistantPowerDriver``
     - No. ``requests`` calls run in the client.
     - Client → Home Assistant REST API over HTTP(S).
     - API token and ``requests`` are client-side; no direct hardware access.
   * - ``TickFpgaManagerDriver``
     - Inherited from its command/file-transfer providers; it has no exporter relocation of its own.
     - With the normal ``SSHDriver`` bindings, client → DUT SSH.
     - The bitstream starts on the client; FPGA manager sysfs access is on the DUT.
   * - ``TickModuleDriver``
     - Inherited from its command/file-transfer providers; it has no exporter relocation of its own.
     - With the normal ``SSHDriver`` bindings, client → DUT SSH.
     - The module starts on the client; ``modinfo``, ``insmod``, and ``iiod`` control run on the DUT.
   * - ``TickOverlayDriver``
     - Inherited from its command/file-transfer providers; it has no exporter relocation of its own.
     - With the normal ``SSHDriver`` bindings, client → DUT SSH.
     - The overlay starts on the client; configfs operations run on the DUT.
   * - ``KasaPowerDriver``
     - No. Discovery and control run in the client.
     - Client → Kasa device on the local LAN.
     - ``python-kasa`` and any device credentials are client-side; no direct hardware access.

The lower-case entry-point aliases have the same behavior as the class names
shown above.  ``XilinxJTAGDriver`` also has an explicit diagnostic escape
hatch: ``LG_FORCE_LOCAL_XSDB=1`` ignores exporter metadata and requires all
Xilinx tools, payload paths, and JTAG/hw_server access on the client.

.. _strategy-transport-matrix:

Strategy transport matrix
-------------------------

A strategy row describes the complete path to its most useful terminal state,
not merely whether one of its component drivers can use an exporter.  Optional
branches are called out explicitly.

.. list-table:: Strategy transport matrix
   :header-rows: 1
   :widths: 20 25 25 30
   :class: topology-matrix topology-strategy-matrix

   * - Strategy
     - Exporter-capable portions
     - LAN/return paths
     - Placement rule
   * - ``BootFPGASoC``
     - Serial, USB SD mux, and mass-storage updates can operate through the exporter.
     - Image download is client → Internet; optional SSH/IP synchronization is client → DUT.
     - Fully exporter-capable for the normal SD-mux + serial boot path, provided the client can SSH to the exporter for mass-storage staging.
   * - ``BootFPGASoCSSH``
     - Initial serial and an exporter-backed power provider can use the exporter.
     - **Required:** client → DUT SSH. Image download is client → release service when enabled.
     - Runner must have DUT LAN reachability; exporter reachability alone is insufficient.
   * - ``BootTickFPGASSH``
     - Initial serial and an exporter-backed power provider can use the exporter.
     - **Required:** client → DUT SSH for boot-file and Tick runtime deployment.
     - Runner must have DUT LAN reachability and local Tick artifact files.
   * - ``BootSelMap``
     - Serial and an exporter-backed power provider can use the exporter.
     - **Required:** client → DUT SSH; JESD validation also opens client → DUT libIIO.
     - Runner must share the DUT network and hold the files being deployed.
   * - ``BootFabric``
     - JTAG is explicitly exporter-capable; serial and suitable power providers can also use exporter paths.
     - Optional SSH/IP synchronization and network IIO verification require client → DUT LAN.
     - JTAG-only programming plus serial verification can be remote-exporter based; network validation cannot.
   * - ``BootFPGASoCTFTP``
     - Serial, suitable power, and optional JTAG bootstrap can use the exporter.
     - **Required for interactive TFTP:** DUT → client TFTP. Optional SSH synchronization is client → DUT.
     - Not transparently exporter-only: TFTP runs in the client and boot files must exist in its local TFTP root. ``sd_autoboot`` skips TFTP but still uses serial and JTAG.
   * - ``SoftwareProvisioningStrategy``
     - Inherited from ``SoftwareInstallerDriver`` command/file providers.
     - Provider-dependent; normally client → DUT SSH.
     - Co-locate only when the selected command/file provider requires it.
   * - ``BootRPI``
     - Optional serial, SD mux, and suitable power providers can use exporter paths.
     - **Required:** client → Raspberry Pi SSH for readiness and the final shell state.
     - Runner must have Pi LAN reachability; exporter access alone is insufficient.
   * - ``BootVPK180``
     - Both serial consoles and the SD-mux + mass-storage update branch can use the exporter.
     - The alternative update branch requires client → DUT SSH; downloads require client → release host.
     - Choose one update topology: exporter-side SD access, or runner-to-DUT LAN. Console access remains required.
   * - ``BootZynq7000JTAGRecovery``
     - JTAG is explicitly exporter-capable; serial and suitable power can use exporter paths.
     - **Required:** DUT → client TFTP and, for automatic SD imaging, DUT → client HTTP.
     - Not transparently exporter-only: recovery files, TFTP root, initramfs build/cache, and HTTP service are client-local.
   * - ``BootNoOSJTAG``
     - JTAG is explicitly exporter-capable; serial and suitable power can use exporter paths.
     - No DUT LAN path is required for firmware load and serial banner validation.
     - Can run through an exporter if the client can SSH to it and every configured JTAG payload path already exists there.
   * - ``ReflashVPK180SD``
     - Both serial consoles and suitable power can use exporter paths.
     - **Required:** recovery DUT → client TFTP.
     - Not transparently exporter-only: the downloaded image and TFTP server/root are client-local.
   * - ``BootZynqMPJTAG``
     - JTAG is explicitly exporter-capable; serial and suitable power can use exporter paths.
     - No DUT LAN path is required for JTAG/recovery/production boot and serial verification.
     - Can run through an exporter if the client can SSH to it. Xilinx tools, hw_server/JTAG, and configured payload paths must all exist exporter-side.

Common deployment decisions
---------------------------

* Put USB serial, SD muxes, block devices, JTAG adapters, ``xsdb``, and
  ``hw_server`` on the exporter.  Use exporter-capable resources/drivers for
  them.
* Give the CI runner routed access to the DUT subnet whenever a strategy uses
  ``SSHDriver``, libIIO, SNMP, Home Assistant, or Kasa.  The coordinator does
  not proxy these application protocols.
* For TFTP/recovery strategies, either run the client on the lab LAN or provide
  explicit routing and firewall rules from the DUT to the client.  Merely
  placing ``TFTPServerResource`` in exporter YAML does not move the server.
* Ensure the client can resolve and SSH to ``resource.host`` or
  ``resource.extra["proxy"]`` for exporter-side mass-storage and JTAG work.
  The current file staging path does not support exporters reachable only
  through ProxyJump.  Mass-storage source files are staged, but JTAG payloads
  referenced by Tcl must already exist on the exporter.
