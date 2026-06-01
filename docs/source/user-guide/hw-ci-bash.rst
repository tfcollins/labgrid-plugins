Hardware CI for bash / non-Python test drivers (UART + JTAG)
============================================================

The reusable workflow and the :doc:`v2 discovery flow <hw-ci-v2>` both
assume the **test driver is pytest**: a labgrid fixture in the
consumer's ``conftest.py`` owns the board lifecycle and tests reach the
DUT over the network (a libIIO ``ip:<addr>`` URI or SSH).

Some projects don't fit that mold. Their test driver is a **bash /
non-Python harness**, and it drives the board over the **serial console
(UART)** and **JTAG (xsdb)** rather than a network URI. This page
documents a CLI-driven pattern for those projects: a **single CI job**
launches the board as a distinct step, then a separate shell step runs
the external test driver against the booted board.

.. note::

   For pytest-driven projects use :doc:`hw-ci-v2` instead — the labgrid
   fixture owns boot/teardown and there is nothing to hand off. This
   page is only for non-Python drivers that talk UART + JTAG.

When to use this
----------------

* Your tests are a shell script (or any non-Python tool) — there is no
  pytest process for a labgrid fixture to hook into.
* The board is exercised over its **serial console** and/or **xsdb**
  over JTAG, not a libIIO URI or SSH.
* You want board launch (acquire + boot) to be a **separate step** from
  the test run, but within **one job** so the place reservation is held
  for the whole run with no cross-job state handoff.

The launch still reuses the existing discovery tooling
(``adi-lg-hw-ci`` + the ``acquire-place`` action) and the ``adi-lg``
boot commands — only the *handoff* differs.

Architecture
------------

A single job runs these steps in order; the place is reserved from
``acquire-place`` until the final ``release`` (which runs on
``if: always()``):

.. code-block:: text

   ┌─ one GitHub Actions job (place held for the whole job) ───────┐
   │                                                               │
   │  render-env       adi-lg-hw-ci render-env  → env.yaml         │
   │       │                                                       │
   │  acquire-place    reserve + acquire the place via coordinator │
   │       │                                                       │
   │  boot             adi-lg boot-*  --state shell  (env.yaml)    │
   │       │                                                       │
   │  resolve          adi-lg-hw-ci resolve-resources  → LG_* vars │
   │       │             (UART device/host:port, JTAG xsdb+targets)│
   │  test             ./test/run_hw.sh   (reads LG_* env vars)    │
   │       │                                                       │
   │  release          labgrid-client release   (if: always())    │
   └───────────────────────────────────────────────────────────────┘

Exported variables
-------------------

``adi-lg-hw-ci resolve-resources`` reads the booted target and emits
``KEY=VALUE`` lines. **Only the variables that apply to the place are
emitted** — a network-only console produces no ``LG_UART_DEVICE``, a
board with no JTAG produces no ``LG_JTAG_*``.

.. list-table::
   :header-rows: 1
   :widths: 24 30 46

   * - Variable
     - Source resource / attribute
     - Notes
   * - ``LG_UART_DEVICE``
     - ``RawSerialPort`` / ``USBSerialPort`` ``.port``
     - A local ``/dev/ttyUSBx`` path. Set only for a **runner-local**
       exporter.
   * - ``LG_UART_HOST``
     - ``NetworkSerialPort`` ``.host``
     - Coordinator host proxying the console. Set on the
       ``RemotePlace`` (coordinator) path.
   * - ``LG_UART_PORT``
     - ``NetworkSerialPort`` ``.port``
     - TCP socket port on ``LG_UART_HOST`` (an integer, not a device
       path).
   * - ``LG_UART_SPEED``
     - serial ``.speed``
     - Baud rate, if the resource declares one.
   * - ``LG_JTAG_XSDB``
     - ``XilinxVivadoTool`` ``.xsdb_path``
     - Absolute path to ``xsdb`` on the host that will run it.
   * - ``LG_JTAG_ROOT_TARGET``
     - ``XilinxDeviceJTAG`` ``.root_target``
     - JTAG target index for the root device (from xsdb ``targets``).
   * - ``LG_JTAG_MB_TARGET``
     - ``XilinxDeviceJTAG`` ``.microblaze_target``
     - JTAG target index for the MicroBlaze / processor core.

.. note::

   The console arrives via ``RemotePlace`` on the coordinator path, so
   it is usually a ``NetworkSerialPort`` — you get ``LG_UART_HOST`` +
   ``LG_UART_PORT``, **not** ``LG_UART_DEVICE``. A runner-local exporter
   that exposes a raw ``/dev/ttyUSBx`` gets ``LG_UART_DEVICE`` instead.
   Exactly one of the two shapes is populated.

.. important::

   There is **no JTAG cable-serial** in the ADI resource set —
   ``XilinxDeviceJTAG`` carries only target indices, and ``xsdb``
   auto-selects the cable on ``connect``. The JTAG handoff therefore
   exports the ``xsdb`` path plus the target indices (what a bash
   ``xsdb`` invocation actually needs), and nothing more. Don't expect a
   ``LG_JTAG_SERIAL``.

Reaching the board from bash
----------------------------

* **Network console** (``LG_UART_HOST`` / ``LG_UART_PORT``): connect to
  the TCP socket (e.g. ``microcom``/``telnet`` to ``host:port``), or use
  ``labgrid-client -p "$LG_PLACE" console`` if labgrid-client is on the
  runner.
* **Local console** (``LG_UART_DEVICE``): open the ``/dev/ttyUSBx`` path
  directly.
* **JTAG**: invoke ``"$LG_JTAG_XSDB"`` with the exported target indices.
  Raw JTAG access typically requires the harness to run **on the
  exporter host** (where the blaster and ``xsdb`` live), not on an
  arbitrary runner.

CLI reference
-------------

.. code-block:: text

   adi-lg-hw-ci resolve-resources --config <env.yaml> [--target main] [--out stdout|github]

``--config``
    The **rendered env yaml** that ``render-env`` wrote and ``adi-lg
    boot-*`` booted against. ``resolve-resources`` does not re-query the
    coordinator — the place is already acquired and the env file is the
    source of truth.

``--target``
    Target name within the env yaml. Default: ``main``.

``--out``
    ``stdout`` (default) prints the ``KEY=VALUE`` lines. ``github`` also
    appends them to ``$GITHUB_OUTPUT`` (and warns to stderr if that is
    unset). Lines are always printed to stdout so the command is usable
    outside GitHub Actions.

Worked example
--------------

A single-job workflow: render the env, acquire the place, boot to a
Linux shell, resolve the UART/JTAG facts into the job environment, run
the bash test driver, and release the place unconditionally.

.. code-block:: yaml

   name: HW bash test (UART + JTAG)
   on: [workflow_dispatch]

   jobs:
     bash-hw:
       runs-on: [self-hosted, hw-mini2]
       env:
         LG_COORDINATOR: 10.0.0.41:20408
         LG_PLACE: mini2
         VENV: ${{ runner.temp }}/hw-ci/venv
       steps:
         - uses: actions/checkout@v4

         - name: Render env yaml from place tags
           id: render
           run: |
             OUT="${{ runner.temp }}/env-${LG_PLACE}.yaml"
             "$VENV/bin/adi-lg-hw-ci" render-env \
                 --coord "$LG_COORDINATOR" --place "$LG_PLACE" --out "$OUT"
             echo "env_path=$OUT" >> "$GITHUB_OUTPUT"

         - name: Acquire place
           uses: tfcollins/labgrid-plugins/.github/actions/acquire-place@main
           with:
             coordinator: ${{ env.LG_COORDINATOR }}
             place: ${{ env.LG_PLACE }}
             labgrid_client: ${{ env.VENV }}/bin/labgrid-client

         - name: Boot to shell
           run: |
             "$VENV/bin/adi-lg" boot-soc \
                 -c "${{ steps.render.outputs.env_path }}" --state shell

         - name: Resolve UART + JTAG into the job environment
           run: |
             # --out github appends KEY=VALUE to $GITHUB_OUTPUT; the
             # redirect mirrors the same lines into $GITHUB_ENV so later
             # steps see them as plain environment variables.
             "$VENV/bin/adi-lg-hw-ci" resolve-resources \
                 --config "${{ steps.render.outputs.env_path }}" \
                 --out github >> "$GITHUB_ENV"

         - name: Run bash test driver
           run: ./test/run_hw.sh   # reads $LG_UART_HOST / $LG_JTAG_XSDB / …

         - name: Release place
           if: always()
           run: |
             LG="$VENV/bin/labgrid-client"
             "$LG" -x "$LG_COORDINATOR" -p "$LG_PLACE" release || true
             "$LG" -x "$LG_COORDINATOR" cancel-reservation --all 2>/dev/null || true

.. note::

   ``acquire-place`` is a composite action and **cannot** define a
   ``post:`` cleanup, so the unconditional ``Release place`` step is
   required — without it a killed runner leaves the place held. This
   mirrors the release idiom in ``hw-matrix.yml``.
