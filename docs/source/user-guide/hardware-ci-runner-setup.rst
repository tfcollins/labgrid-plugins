Hardware-CI Runner Setup (no-os flash mode)
===========================================

A no-os DUT repo opts into on-hardware CI with a project manifest and four
workflow inputs. The lab/toolchain logic (Vivado sourcing, the libtinfo shim,
the ``.xsa`` fetch from the Kuiper image) lives entirely in
``labgrid-plugins`` — the runner's only hard requirement is a Vivado/Vitis
install.

Runner requirements
-------------------

The per-project build+flash legs run on a **self-hosted runner** that must:

* Have **Vivado/Vitis** installed (``/opt/Xilinx/Vivado/*/settings64.sh`` or
  ``/tools/Xilinx/*/Vivado/settings64.sh``). ``build-noos`` auto-detects the
  newest version. Override with ``VITIS_SETTINGS=<path/to/settings64.sh>`` if
  you have a non-standard install location.
* Be able to **reach the JTAG cable** wired to the target board (the runner is
  typically co-located on the exporter host, or uses the place's ``runner``
  tag to route each leg to the right host).
* Have ``labgrid-plugins`` installed (the workflow installs it per leg via
  ``uv``; no manual prep required).

Register the runner with ``.github/scripts/register-hw-runners.sh``. Use
``--scopes`` to register one physical host across multiple GitHub scopes so a
single lab machine can serve both org and personal-account consumer repos:

.. code-block:: bash

   ./.github/scripts/register-hw-runners.sh \
       --hosts-file ./hosts.tsv \
       --scopes org:analogdevicesinc,repo:tfcollins/labgrid-plugins

The manifest
------------

A no-os consumer repo places a project manifest at
``tools/hw_ci/projects.yaml`` (override with the ``manifest`` workflow input):

.. code-block:: yaml

   projects:
     - noos_project: adrv9009
       part: adrv9009
       carriers: [zc706]
       validate_banner: "Successfully initialized"   # optional; default shown
       build_vars: {}                                 # optional extra make vars

Each entry in the ``projects`` list accepts:

``noos_project`` (required)
    The no-os project directory name under ``projects/`` (e.g.
    ``adrv9009``). Also used as the ``.elf`` stem.

``part`` (required)
    The canonical daughter-board part name, matched against the coordinator's
    board catalog (same value used in ``@pytest.mark.iio_hardware``).

``carriers`` (required, >=1 entry)
    FPGA carrier boards to test against. One build+flash leg is generated per
    ``(noos_project, carrier)`` pair that has a live flash-capable board on the
    coordinator.

``validate_banner`` (optional)
    Serial string the firmware must print after JTAG-flash; matched on the
    console as a pexpect pattern (an unanchored regex/substring search).
    Defaults to ``"Successfully initialized"`` if omitted.

``build_vars`` (optional)
    Extra ``make`` variables forwarded to the no-os build as ``KEY=VALUE``
    pairs.

The consumer workflow
---------------------

Four inputs wire your no-os repo into the reusable ``noos-hw-request.yml``
workflow:

.. code-block:: yaml

   jobs:
     noos-hw-request:
       uses: tfcollins/labgrid-plugins/.github/workflows/noos-hw-request.yml@main
       with:
         coordinator: ${{ vars.LG_COORDINATOR }}
         manifest: "tools/hw_ci/projects.yaml"
         runner-label: ${{ vars.HW_REQUEST_RUNNER }}
         preflight-runner-label: ${{ vars.HW_PREFLIGHT_RUNNER }}

``coordinator``
    Coordinator ``host:port`` for ``GET /api/match?mode=flash``. Set once as
    a repo or org variable.

``manifest``
    Path to the projects manifest inside the consumer checkout. Default:
    ``tools/hw_ci/projects.yaml``.

``runner-label``
    Fallback runner label for the per-project build+flash legs. Each leg
    prefers the runner co-located with its board (from the place's ``runner``
    tag); this is the fallback.

``preflight-runner-label``
    Runner label for the discovery preflight step. Must be able to reach the
    coordinator REST API.

What happens per leg
--------------------

#. **Discovery** (preflight). ``adi-lg-hw-ci noos-matrix`` intersects the
   manifest's ``(noos_project, part, carriers)`` entries with the
   coordinator's live flash-capable boards (``GET /api/match?mode=flash``).
   Each matching ``(project, carrier)`` pair becomes one matrix leg. A project
   with no live board emits a ``::warning::`` annotation and is skipped.

#. **Build** (``adi-lg-hw-ci build-noos``). The build step runs on the
   leg's assigned runner:

   * Sources Vivado automatically from the system-wide install (or
     ``$VITIS_SETTINGS``).
   * Creates the libtinfo ``.so.5`` → ``.so.6`` shim under
     ``~/.local/xlnxshim`` so Vitis works on Ubuntu 22.04/24.04 without
     system-level package installs.
   * Downloads the Kuiper Linux image (~3.5 GB) for the board's release,
     cached once per release under ``~/.labgrid/kuiper_releases``.
   * Extracts the board's ``system_top.xsa`` from the Kuiper boot FAT
     partition, cached under ``~/.labgrid/kuiper_xsa``.
   * Sets ``NOOS_VITIS_HSI_FLOW=1`` (the pure-HSI flow avoids the "Channel
     closed" crash that affects the default Vitis HWH flow) and runs
     ``make`` in ``projects/<noos_project>/``.
   * Artifacts: ``.elf`` in ``projects/<noos_project>/build/``, plus
     ``system_top.bit`` and ``ps7_init.tcl`` in
     ``projects/<noos_project>/build_hw/``.

#. **Flash + validate** (``adi-lg request --mode flash``). After the build
   completes, the leg reserves a matching flash-capable board on the
   coordinator (queuing up to ``wait`` seconds if the board is busy), then
   uses the ``BootNoOSJTAG`` strategy to:

   * JTAG-program the bitstream (``system_top.bit``) onto the FPGA.
   * Initialize the PS via ``ps7_init.tcl``.
   * Download and run the ``<project>.elf``.
   * Assert the ``validate_banner`` string on the serial console.
   * Release the board on exit (even on failure).

Troubleshooting
---------------

**"Channel closed" crash during ``make``**
    This is a known Vitis bug in the default HWH-based HSI flow. ``build-noos``
    sets ``NOOS_VITIS_HSI_FLOW=1`` automatically to use the pure-HSI flow,
    which avoids this crash. No manual workaround is needed.

**libtinfo.so.5 / libncurses.so.5 not found**
    Vitis requires these legacy libraries that are absent on Ubuntu 22.04+.
    ``build-noos`` creates symlinks ``*.so.5 → *.so.6`` under
    ``~/.local/xlnxshim`` and prepends that directory to ``LD_LIBRARY_PATH``
    automatically. No system-level package installs are required.

**Ambiguous Kuiper boot folder (multiple board matches in the FAT partition)**
    ``build-noos`` searches the Kuiper image's FAT boot partition for a
    subdirectory matching the board name. If more than one folder matches, set
    ``flash.kuiper_xsa_dir`` in the coordinator board catalog for the relevant
    place, or pass ``--xsa-dir <path>`` to ``adi-lg-hw-ci build-noos`` directly
    to pin the exact folder path.

**Flash fails with "board busy"**
    The default wait is 1800 s. Increase the ``wait`` input on the reusable
    workflow, or check whether a previous run left the board reserved:
    ``labgrid-client -x <coordinator> reservations``.

See also
--------

* :doc:`hw-request` — the ``adi-lg request`` command and URI mode (Linux boot +
  IIO URI export).
* :doc:`hardware-ci` — the v1/v2 pytest-driven workflows (for repos whose tests
  talk the board over a libIIO network URI rather than direct JTAG).
