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

Reserve mode (consumer-driven boot)
-----------------------------------

Some suites must drive board boot **themselves** — pyadi-dt's hardware tests,
for example, use the labgrid pytest plugin to flash and boot a different DTB
per test, so the boot-then-hand-off contract of uri mode cannot serve them.
``--mode reserve`` covers this: the request layer acquires a matching place
and renders its labgrid env yaml, but performs **no boot and no iiod
verification**, then runs the child with the env contract:

* ``LG_ENV`` — the rendered labgrid env yaml for the acquired place; the
  labgrid pytest plugin reads it directly.
* ``LG_COORDINATOR`` — the coordinator address (set by the workflow).
* ``LG_PLACE`` — the acquired place name.
* ``HW_DAUGHTER`` / ``HW_CARRIER`` — the pytest plugin's per-shard test
  narrowing, exactly as in uri mode.

``IIO_URI`` is **not** exported (nothing is booted). There is **no boot
gate** in this mode: a board that fails to boot is the suite's own failure
to detect and report — the ``::error title=boot-failure::`` annotation and
exit code 12 only cover provisioning up to the acquire/render step. The
place is still always released on exit, and the rendered env directory is
removed.

In the reusable workflow, select it per caller with the ``request-mode``
input:

.. code-block:: yaml

   jobs:
     hw:
       uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@main
       with:
         coordinator: ${{ vars.ADI_LG_COORDINATOR }}
         test-root: "tests"
         request-mode: "reserve"
       secrets:
         # Only needed when test deps live in private git repos
         # (e.g. pyadi-dt's pyadi-build):
         INSTALL_GIT_TOKEN: ${{ secrets.INSTALL_GIT_TOKEN }}

``INSTALL_GIT_TOKEN`` (optional) is exposed as a ``github.com`` ``insteadOf``
credential only during the per-leg venv install, letting ``uv pip install``
resolve private git dependencies; it never persists in the runner's git
config.

Requirements
------------

* Self-hosted runners: one reachable by the coordinator REST API
  (``preflight-runner-label``) and a pool that can reach the coordinator and
  actuate the lab (``runner-label``).
* The coordinator must serve the Plan-1 board catalog (``GET /api/match``).

Uploading results to Prism
--------------------------

Both ``hw-request.yml`` and ``matlab-hw-request.yml`` can post each leg's
JUnit to a Prism instance, tagged with the leg's place/board/carrier. Enable
it with ``prism-upload: true`` plus a ``prism-project`` slug, set the Prism
base URL as a repo variable ``vars.PRISM_URL`` (or pass it via the
``prism-url`` input), and pass the three Prism secrets **explicitly** in the
caller — cross-org ``secrets: inherit`` does **not** work:

.. code-block:: yaml

   jobs:
     hw:
       uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@main
       with:
         coordinator: ${{ vars.LG_COORDINATOR }}
         test-root: "test"
         prism-upload: true
         prism-project: "my-project"
         # prism-url: "https://prism.example.com"   # default: vars.PRISM_URL
       secrets:
         PRISM_API_TOKEN: ${{ secrets.PRISM_API_TOKEN }}
         PRISM_EMAIL: ${{ secrets.PRISM_EMAIL }}
         PRISM_PASSWORD: ${{ secrets.PRISM_PASSWORD }}

By default each leg installs the ``prism-uploader`` package into the per-leg
venv via uv and uploads the leg's JUnit. Consumers with a **vendored
uploader** (e.g. pyadi-dt's private-Prism-repo uploader script) can replace
the built-in one with the ``prism-upload-cmd`` escape hatch — a shell
command run instead of the built-in uploader, with ``PRISM_URL``,
``PRISM_API_TOKEN``, ``PRISM_EMAIL``, ``PRISM_PASSWORD``, ``PRISM_PROJECT``,
``PRISM_JUNIT``, ``PRISM_RUN_NAME``, ``PRISM_BOARD``, ``PRISM_CARRIER``, and
``PRISM_PLACE`` exported:

.. code-block:: yaml

       with:
         prism-upload: true
         prism-project: "my-project"
         prism-upload-cmd: "python tools/upload_to_prism.py"

The upload step runs with ``continue-on-error`` and surfaces failures as
``::warning::`` annotations — a Prism outage (or a missing uploader) never
fails a hardware leg.

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
