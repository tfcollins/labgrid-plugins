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
   Host-side drivers use either labgrid's SSH-backed ``AgentWrapper`` or direct
   SSH command execution. Composite drivers use their exported console,
   command, and file-transfer providers.

**Client LAN path**
   The client opens a connection directly to a target or service.  Registering
   the corresponding resource on an exporter does not tunnel this connection.
   Examples include optional client-to-DUT SSH and libIIO validation paths.

**DUT return path**
   The target opens a connection back to a service. Exporter-backed TFTP uses
   DUT → exporter; the recovery HTTP server remains a DUT → client path.

**Client-local requirement**
   A command, service, cache, or source path exists on the client itself.
   This is different from direct physical access.  The matrices say
   explicitly when USB/JTAG/block-device access must instead be local to the
   exporter or client.

``RemotePlace`` alone is therefore not a transport guarantee.  In particular,
plain plugin resources may contain ``extra["proxy"]`` after coordinator
resolution, but only code which consumes that field relocates its work.

Exporter credentials
~~~~~~~~~~~~~~~~~~~~

Resource parameters and ``extra`` are coordinator-visible. Do not put secrets
in exporter resource YAML. Exporter-executed helpers read credentials only from the exporter environment
or ``~/.config/adi-lg/credentials.env`` on the exporter:

* ``ADI_LG_APC_READ_COMMUNITY`` and ``ADI_LG_APC_WRITE_COMMUNITY``
* ``ADI_LG_HOMEASSISTANT_TOKEN``
* ``ADI_LG_KASA_USERNAME`` and ``ADI_LG_KASA_PASSWORD`` (both optional)
* ``ADI_LG_VESYNC_USERNAME`` and ``ADI_LG_VESYNC_PASSWORD``
* ``CLOUDSMITH_API_TOKEN``

The credential file uses one ``NAME=value`` per line and must have mode 0600.
Set exporter-local ``ADI_LG_CREDENTIAL_FILE`` to select another protected path.
The legacy resource credential fields remain available for local execution,
but exporter execution never sends those values from the client. Protect the
exporter environment with the same controls as other service credentials.

``AgentWrapper`` opens direct SSH/rsync connections. If coordinator metadata
sets ``proxy_required``, these drivers fail before starting an agent; configure
an SSH ``ProxyJump`` for the advertised exporter hostname. The coordinator
proxy metadata alone cannot tunnel ``AgentWrapper``.

Artifact placement at a glance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. container:: editorial-diagram

   .. image:: /_static/diagrams/artifact-handoff-light.svg
      :alt: Location-aware artifact flow from release service through exporter cache and ArtifactRef to JTAG, TFTP, and mass-storage consumers
      :class: diagram-light

   .. image:: /_static/diagrams/artifact-handoff-dark.svg
      :alt: Location-aware artifact flow from release service through exporter cache and ArtifactRef to JTAG, TFTP, and mass-storage consumers
      :class: diagram-dark

.. rst-class:: diagram-caption

Same-host handoffs retain exporter-local paths; compatibility APIs materialize
an explicit client copy. Editorial style adapted from `Diagram Design
<https://github.com/cathrynlavery/diagram-design>`_ (MIT).

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
     - **Yes.** An allowlisted ``AgentWrapper`` helper runs SNMP on the bound resource's exporter.
     - Client → exporter SSH; exporter → APC PDU, UDP/161.
     - ``pysnmp`` must be installed on the exporter. A local resource preserves client-side behavior.
   * - ``VesyncPowerDriver``
     - **Yes.** VeSync login, discovery, and operations run in the exporter helper.
     - Client → exporter SSH; exporter → VeSync cloud service.
     - ``pyvesync`` and outbound Internet access are required on the exporter.
   * - ``MassStorageDriver``
     - **Yes.** ``pmount``, ``pumount``, directory operations, and copies run on the exporter selected by the bound resource; source files are staged there over SSH.
     - Client → exporter SSH. ProxyJump-only exporters are not supported by the current staging helper.
     - The USB block device and mount tools must be local to the exporter. Without remote metadata they must be local to the client instead.
   * - ``ADIShellDriver``
     - Inherited from its ``ConsoleProtocol``. A coordinator-provided network serial console works through the exporter; a local serial resource stays local.
     - Client → exported serial endpoint, or whatever path the bound console requires.
     - No independent transport. Commands and XMODEM transfers use the bound console.
   * - ``KuiperDLDriver``
     - **Yes.** Download, cache, and extraction run in an exporter helper; results are location-aware ``ArtifactRef`` objects.
     - Client → exporter SSH; exporter → Kuiper release host/Internet.
     - Cache and optional ``pytsk3`` extraction support belong on the exporter. Legacy path APIs fetch an explicit client copy.
   * - ``CloudsmithDLDriver``
     - **Yes.** API resolution, downloads, and cache access run in an exporter helper.
     - Client → exporter SSH; exporter → Cloudsmith API/CDN.
     - Download dependencies and cache are exporter-side. Legacy path APIs fetch an explicit client copy.
   * - ``CyberPowerDriver``
     - **Yes.** An allowlisted exporter helper performs SNMP operations.
     - Client → exporter SSH; exporter → CyberPower PDU, UDP/161.
     - ``pysnmp`` and PDU LAN reachability are required on the exporter.
   * - ``XilinxJTAGDriver``
     - **Yes.** ``xsdb`` runs on the exporter selected by ``XilinxDeviceJTAG``; generated Tcl and client-readable xsdb payloads are staged automatically.
     - Client → exporter SSH; ``jtag_url`` is resolved by the exporter-side ``xsdb`` process. ProxyJump-only exporters are not supported by the current Tcl staging helper.
     - Xilinx tools and JTAG/hw_server access must be on the exporter. Prefix a payload with ``exporter:`` when it already exists there. For compatibility, an absolute path absent on the client is also treated as exporter-local. ``dcc_log_path`` is an exporter-side output path and is not copied back to the client.
   * - ``TFTPServerDriver``
     - **Yes.** A stateful ``AgentWrapper`` helper owns the UDP service and root on the resource exporter.
     - Client → exporter SSH; DUT → exporter UDP on the configured port (3069 by default).
     - Configure a DUT-visible address or use exporter-side ``auto`` discovery. Artifact publishing stays on-host when co-located.
   * - ``SoftwareInstallerDriver``
     - Inherited from its bound ``CommandProtocol`` and ``FileTransferProtocol``.
     - Whatever those providers require; with ``SSHDriver`` this is client → DUT LAN.
     - Build tools and packages are installed on the DUT; source files begin on the client and use the bound transfer protocol.
   * - ``HomeAssistantPowerDriver``
     - **Yes.** REST calls run in the exporter helper.
     - Client → exporter SSH; exporter → Home Assistant HTTP(S).
     - ``requests`` and Home Assistant reachability are required on the exporter.
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
     - **Yes.** Discovery and control run in the exporter helper.
     - Client → exporter SSH; exporter → Kasa device on its local LAN.
     - ``python-kasa`` is required on the exporter; a local resource retains client-side execution.

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
     - Image download is exporter → Internet; optional SSH/IP synchronization is client → DUT.
     - Fully exporter-capable for the normal SD-mux + serial boot path. Download→mass-storage artifacts remain on-host.
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
     - **Required for interactive TFTP:** DUT → exporter TFTP. Optional SSH synchronization is client → DUT.
     - Download→TFTP artifacts remain exporter-local. ``sd_autoboot`` skips TFTP but still uses serial and JTAG.
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
     - The alternative update branch requires client → DUT SSH; downloads originate on the exporter.
     - Choose one update topology: exporter-side SD access, or runner-to-DUT LAN. Console access remains required.
   * - ``BootZynq7000JTAGRecovery``
     - JTAG is explicitly exporter-capable; serial and suitable power can use exporter paths.
     - **Required:** DUT → client TFTP and, for automatic SD imaging, DUT → client HTTP.
     - Not transparently exporter-only: recovery files, TFTP root, initramfs build/cache, and HTTP service are client-local.
   * - ``BootNoOSJTAG``
     - JTAG is explicitly exporter-capable; serial and suitable power can use exporter paths.
     - No DUT LAN path is required for firmware load and serial banner validation.
     - Runs through an exporter when the client can SSH to it; caller-local JTAG payloads are staged automatically.
   * - ``ReflashVPK180SD``
     - Both serial consoles and suitable power can use exporter paths.
     - **Required:** recovery DUT → exporter TFTP.
     - Downloaded images and TFTP remain on the same exporter through ``ArtifactRef`` handoff.
   * - ``BootZynqMPJTAG``
     - JTAG is explicitly exporter-capable; serial and suitable power can use exporter paths.
     - No DUT LAN path is required for JTAG/recovery/production boot and serial verification.
     - Runs through an exporter when the client can SSH to it. Xilinx tools and hw_server/JTAG are exporter-side; caller payloads are staged automatically.

Common deployment decisions
---------------------------

* Put USB serial, SD muxes, block devices, JTAG adapters, ``xsdb``, and
  ``hw_server`` on the exporter.  Use exporter-capable resources/drivers for
  them.
* Give the exporter PDU/service reachability for SNMP, Home Assistant, Kasa,
  VeSync, release downloads, and TFTP. Composite drivers follow their bound
  provider; optional SSH and libIIO strategy steps may still require client LAN.
* For TFTP/recovery strategies, allow DUT → exporter UDP and configure a
  DUT-visible exporter address. ``address: auto`` is resolved on the exporter.
* Ensure the client can resolve and SSH to ``resource.host`` or
  ``resource.extra["proxy"]`` for exporter-side mass-storage and JTAG work.
  ``AgentWrapper`` requires direct SSH reachability or an SSH-configured
  ProxyJump. Mass-storage and JTAG inputs are staged; ``ArtifactRef`` avoids
  transfers when producer and consumer use the same exporter.
