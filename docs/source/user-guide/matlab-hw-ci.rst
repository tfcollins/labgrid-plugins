MATLAB Hardware CI (adi-lg-matlab)
==================================

``adi-lg-matlab`` is a generic bridge that lets a **MATLAB** toolbox run
its hardware tests against a board provisioned by labgrid — the MATLAB
analogue of the pytest-oriented :doc:`hw-ci-v2` flow.

MATLAB stays decoupled from labgrid. Toolboxes such as TransceiverToolbox
already honour the ``IIO_URI`` environment variable (its
``test/HardwareTests.m`` overrides the device URI from ``IIO_URI`` at test
setup). So the integration only has to **boot the board, resolve its URI,
set IIO_URI, and launch MATLAB** — no MATLAB-side labgrid coupling.

How it differs from the pytest path
-----------------------------------

The :doc:`hw-ci-v2` ``hw-matrix.yml`` workflow discovers tests by
AST-harvesting ``@pytest.mark.iio_hardware`` markers. MATLAB tests carry
no such markers, and labgrid place tags use chip/carrier names
(``adrv9002`` / ``zcu102``) while MATLAB ``runHWTests`` keys on long HDL
reference names (``zynqmp-zcu102-rev10-adrv9002-vcmos``). ``adi-lg-matlab``
bridges that gap with a consumer-supplied **board map**.

Board map
---------

A YAML file mapping place tags to a MATLAB board reference name:

.. code-block:: yaml

   boards:
     - {carrier: zcu102, daughter-board: adrv9002, matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}
     - {carrier: zcu102, daughter-board: adrv9002, hdl-config: lvds, matlab_board: zynqmp-zcu102-rev10-adrv9002-vlvds}
     - {daughter-board: pluto, matlab_board: pluto}

``daughter-board`` and ``matlab_board`` are required per row. ``carrier``
and ``hdl-config`` are optional narrowing keys; the most specific matching
row wins, and a row without ``carrier`` is a carrier-agnostic fallback.

CLI
---

.. code-block:: shell

   # Emit the GHA matrix of (place -> matlab_board) for live, mapped places
   adi-lg-matlab discover \
       --coord 10.0.0.41:20408 \
       --board-map test/hw_ci/board_map.yaml

   # Place mode: render env from the place's tags, boot it, run MATLAB,
   # acquire/release the place around the run
   adi-lg-matlab run \
       --coord 10.0.0.41:20408 --place mini2 \
       --board-map test/hw_ci/board_map.yaml \
       --repo-dir . --matlab /opt/MATLAB/R2025b/bin/matlab \
       --junit junit-mini2.xml --acquire

   # Config mode: skip the coordinator, run against a labgrid yaml you supply
   adi-lg-matlab run \
       --config env.yaml --matlab-board zynqmp-zcu102-rev10-adrv9002-vcmos \
       --boot-strategy BootFPGASoC --repo-dir . --matlab /opt/MATLAB/R2025b/bin/matlab

``run`` boots the place's ``boot-strategy`` to ``--reached-state`` (default
``shell``), resolves the booted board's address from its ``NetworkService``
resource into ``ip:<addr>``, launches ``matlab -batch "addpath(genpath('test'));
runHWTests(getenv('board'))"`` with ``IIO_URI`` and ``board`` exported, and
copies MATLAB's ``<board>_HWTestResults.xml`` to ``--junit``.

.. note::

   In CI, prefer the ``acquire-place`` composite action to own the
   reservation (it uses labgrid's reservation queue with ``--wait``) and do
   **not** pass ``--acquire``. ``--acquire`` is for local runs, where it
   does a plain ``labgrid-client acquire``/``release`` around the run.

GitHub Actions
--------------

There is no reusable MATLAB workflow; the consumer repo owns a bespoke
workflow (MATLAB licensing and install are per-runner concerns). The shape:

* a ``discover`` job on ``[self-hosted, hw-coordinator]`` running
  ``adi-lg-matlab discover --github-output`` to build the matrix;
* an ``hw`` matrix job, one shard per place pinned to
  ``[self-hosted, hw-<place>]`` (which must have MATLAB + libiio), that
  acquires the place (``acquire-place`` action), runs ``adi-lg-matlab run``,
  releases the place with ``if: always()``, and uploads the JUnit.

See ``TransceiverToolbox/.github/workflows/hw-matlab.yml`` for a complete
example. The lab-admin place-tag and self-hosted-runner contracts are the
same as :doc:`hw-ci-v2`.
