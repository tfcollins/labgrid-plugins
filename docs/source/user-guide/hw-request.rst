Hardware CI by part (hw-request)
================================

``hw-request.yml`` is a reusable workflow that runs a consumer repo's hardware
tests **by part**. A consumer repo marks its tests with
``@pytest.mark.iio_hardware([...])`` and calls the workflow; labgrid selects a
free matching board, boots it, runs the tests, and releases it — one
independent job per board, with **no** place names, env yaml, or board maps in
the consumer repo.

How it differs from ``hw-matrix.yml``
-------------------------------------

``hw-matrix.yml`` (v1/v2) fans out per *place* and each leg does
acquire-place + render-env + board_map + ``pytest --lg-config``.
``hw-request.yml`` fans out per *part* and each leg is a single
``adi-lg request`` call that does all of that internally. Both coexist.

Calling it
----------

.. code-block:: yaml

   # .github/workflows/hw.yml in the consumer repo (e.g. pyadi-iio)
   name: HW
   on: [pull_request]
   jobs:
     hw:
       uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@main
       with:
         coordinator: "10.0.0.41:8000"
         test-root: "test"
         # marker: iio_hardware        # default
         # wait: 1800                   # seconds to queue for a busy board
         # runner-label: hw-lab         # self-hosted label for the per-board legs
         # pytest-args: "-v"

What happens
------------

#. **preflight** harvests the parts the suite wants from its
   ``iio_hardware`` markers (statically, via ``adi-lg-hw-ci request-matrix`` —
   it never imports test modules), probes ``GET /api/match`` for each, and
   emits a matrix of the parts that have a live board. A wanted part with no
   live board is **skipped** with a ``::warning::`` annotation.
#. **hw-request** runs one job per available part:
   ``adi-lg request --part <p> --wait <N> --run 'pytest -m iio_hardware …'``.
   The reservation **queues** if every matching board is busy (bounded by
   ``wait``). ``HW_DAUGHTER=<p>`` narrows the run to that board's tests.
#. **report** aggregates the per-leg JUnit into a single PR check.

Boot verification and failure semantics
---------------------------------------

``adi-lg request`` (uri mode) verifies the booted board before handing it to
the child command: after the boot strategy reaches shell and the URI is
resolved, the request layer polls a TCP connect to iiod (port 30431) for up
to 60 s. A board that boots to shell with a dead iiod is a **boot failure**,
not a test failure.

* One bounded retry: a failed attempt (strategy error or iiod never up) gets
  exactly one cold-boot retry (power-off, reboot) before failing the leg.
* Exit codes: ``10`` no matching board, ``11`` none free in the wait window,
  ``12`` provisioning/boot failed. Test failures pass the child's own exit
  code through — CI can always tell infra from tests. The full exit-code
  list lives in :doc:`cli`.
* On GitHub Actions a boot failure additionally emits
  ``::error title=boot-failure::part=<part> place=<place> reason=<…>`` —
  count these annotations to track boot success rate.
* The place is **always released**, including on Ctrl-C/SIGTERM and after
  failed retries.

Child environment: ``IIO_URI``, ``LG_PLACE``, ``LG_CARRIER``, plus
``HW_DAUGHTER`` / ``HW_CARRIER`` for the pytest plugin's per-shard test
narrowing.

Requirements
------------

* Self-hosted runners: one reachable by the coordinator REST API
  (``preflight-runner-label``) and a pool that can reach the coordinator and
  actuate the lab (``runner-label``).
* The coordinator must serve the Plan-1 board catalog (``GET /api/match``).

Flash mode (no-os)
------------------

``adi-lg request`` supports a ``--mode flash`` path for bare-metal no-os
firmware. Instead of booting Linux and exporting an IIO URI, the request
JTAG-loads an ``.elf`` directly onto the target and asserts a serial banner:

.. code-block:: bash

   adi-lg request \
       --part adrv9009 --carrier zc706 \
       --mode flash \
       --firmware projects/adrv9009/build/adrv9009.elf \
       --bitstream projects/adrv9009/build_hw/system_top.bit \
       --ps7-init projects/adrv9009/build_hw/ps7_init.tcl \
       --validate "Successfully initialized" \
       --wait 1800

``--firmware <elf>`` (required in flash mode)
    Path to the no-os ``.elf`` to JTAG-load.

``--bitstream <bit>`` (optional)
    FPGA bitstream to program before loading the ``.elf``.

``--ps7-init <tcl>`` (optional)
    ``ps7_init.tcl`` for PS initialisation on Zynq-7000 targets.

``--validate <banner>``
    Serial string to assert on-target after flash. Defaults to the IIOD
    server banner if omitted; for no-os use ``"Successfully initialized"``
    or the project's own startup message.

``adi-lg-hw-ci build-noos`` produces the matching artifacts: the ``.elf``
lands in ``projects/<project>/build/`` and the ``system_top.bit`` plus
``ps7_init.tcl`` land in ``projects/<project>/build_hw/``.

The full automated flow — manifest → discovery → build → JTAG-flash → serial
validation — is driven by the ``noos-hw-request.yml`` reusable workflow. See
:doc:`hardware-ci-runner-setup` for runner requirements, the manifest schema,
and per-leg troubleshooting.
