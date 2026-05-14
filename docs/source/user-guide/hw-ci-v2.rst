Hardware CI v2 (discovery-driven)
=================================

The ``hw-matrix.yml`` reusable workflow ships in **two versions** that
coexist:

* **v1** (``hw-matrix.yml@v1``) — manifest-first. Each consumer repo
  commits a static ``.github/hw-nodes.json`` + a
  ``test/hw/env/<place>.yaml`` per place. The coordinator is queried
  only to filter dead places out of the manifest. See
  :doc:`hardware-ci` for details. v1 stays supported indefinitely.

* **v2** (``hw-matrix.yml@v2``) — **discovery-driven**. The coordinator
  is the source of truth for live hardware via ``place tags``; the
  consumer repo declares which hardware its tests support via
  ``@pytest.mark.iio_hardware`` markers. No static manifest, no
  per-place env yaml on the consumer side. This page documents v2.

When to use which
-----------------

* Use **v2** when your tests are already marked with
  ``@pytest.mark.iio_hardware`` (the de-facto convention in
  ``pyadi-iio`` and adjacent projects), and the lab admin has tagged
  every place with the v2 schema.
* Use **v1** otherwise — including the transition window while a
  given coordinator's places are being tagged.

The two versions can coexist on the same coordinator with no conflict.

Architecture
------------

.. code-block:: text

   ┌─ labgrid coordinator ─────────────────────────────────────┐
   │  Each live place exposes tags:                            │
   │    carrier: zcu102                                        │
   │    daughter-board: ad9081                                 │
   │    boot-strategy: BootFPGASoC                             │
   │    hdl-config: m8_l4   (optional narrowing)               │
   └─────────────────────┬─────────────────────────────────────┘
                         │   GET /api/places   (REST or labgrid-client fallback)
                         ▼
   ┌─ hw-matrix.yml@v2 ────────────────────────────────────────┐
   │  1. discover:  query coordinator → live places            │
   │  2. validate:  each place conforms to tag schema          │
   │  3. collect:   pytest --collect-only -m iio_hardware in   │
   │                the caller repo                            │
   │  4. intersect: pair tests with places by daughter-board   │
   │  5. render:    per matrix entry, write env.yaml from      │
   │                place tags + boot-strategy template        │
   │  6. emit:      [(place, daughter, marker_filter)] matrix  │
   └─────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
   ┌─ matrix shard (one per (place, daughter-board)) ──────────┐
   │  pytest -m "iio_hardware and <daughter>"  --lg-config …   │
   │  → boot place, run tests, upload JUnit + logs             │
   └───────────────────────────────────────────────────────────┘

Place-tag schema (lab-admin contract)
-------------------------------------

Every place a v2 workflow may dispatch onto must carry these tags.
Set them via ``labgrid-client -p <place> set-tags k=v k2=v2 …``:

.. list-table::
   :header-rows: 1
   :widths: 18 8 32 42

   * - Tag
     - Required
     - Example values
     - Purpose
   * - ``carrier``
     - yes
     - ``zcu102``, ``zc706``, ``vcu118``, ``rpi5``, ``kr260``
     - Matched against ``@pytest.mark.iio_carrier([…])`` for
       optional narrowing.
   * - ``daughter-board``
     - yes
     - ``ad9081``, ``adrv9371``, ``adrv9009``, ``fmcdaq3``, ``pluto``
     - **Primary key.** Matched against
       ``@pytest.mark.iio_hardware([…])``.
   * - ``boot-strategy``
     - yes
     - ``BootFPGASoC``, ``BootFPGASoCSSH``, ``BootFPGASoCTFTP``,
       ``BootFabric``, ``BootRPI``, ``BootSelMap``, ``BootVPK180``,
       ``BootZynq7000JTAGRecovery``
     - Class name of the labgrid strategy. Picks which env-yaml
       template gets rendered. Must be one of the names registered
       under ``adi_lg_plugins.strategies``.
   * - ``hdl-config``
     - no
     - ``m8_l4``, ``m4_l2``
     - Optional further narrowing. Available to tests as an extra
       field on the matrix entry.
   * - ``board-location``
     - no
     - ``mini2``, ``bq``, ``nemo``
     - Operational only — not used for matrix building.

The schema validator (``adi_lg_plugins.hw_ci.schema.validate_place``)
**rejects** places that:

* are missing any required tag, or
* set ``boot-strategy`` to a class name not in the live strategy
  registry (``adi_lg_plugins.hw_ci.KNOWN_STRATEGIES``).

Skipped places are surfaced as a warning annotation in the
``discover`` job — they don't crash the workflow.

Test-marker schema (project-side contract)
------------------------------------------

The ``adi_lg_plugins.pytest_plugin`` module registers two markers via
the ``pytest11`` entry point. Any project that ``pip install``\s
``adi-labgrid-plugins`` gets them auto-registered (no per-project
``conftest.py`` plumbing needed):

.. code-block:: python

   import pytest
   import adi


   @pytest.mark.iio_hardware(["ad9081", "ad9081_tdd"])
   def test_rx_buffer(iio_uri):
       """Runs on any place tagged daughter-board=ad9081
       (or ad9081_tdd)."""
       rx = adi.ad9081(uri=iio_uri)
       assert rx.rx().size > 0


   @pytest.mark.iio_hardware(["ad9081"])
   @pytest.mark.iio_carrier(["zcu102"])
   def test_zcu102_only(iio_uri):
       """Only runs on AD9081 attached to a ZCU102 carrier
       (not VCU118 or any other carrier with ad9081)."""
       …

Single-string shorthand is accepted:
``@pytest.mark.iio_hardware("ad9081")`` is equivalent to
``@pytest.mark.iio_hardware(["ad9081"])``.

.. important::

   The marker argument must be a **string literal** (or a literal
   list/tuple of strings). The discover step harvests markers by
   parsing the AST of every ``test_*.py`` file — it does **not**
   import the modules. Computed arguments (variables, f-strings,
   list comprehensions) cannot be statically harvested and the
   affected test will silently be left out of the matrix. AST harvest
   is what lets the coordinator-adjacent runner stay free of the
   per-DUT toolchain (libiio, ``adi``, etc.) — those only need to be
   present on the per-place ``hw-<place>`` runners.

Consumer setup
--------------

Three things on the consumer side:

1. Install ``adi-labgrid-plugins`` in the test venv (the workflow's
   ``venv_install_cmd`` already needs to do this — the marker plugin
   AND the discover CLI both live in this package):

   .. code-block:: text

      adi-labgrid-plugins @ git+https://github.com/tfcollins/labgrid-plugins.git@v2

2. Mark tests:

   .. code-block:: python

      @pytest.mark.iio_hardware(["ad9081"])
      def test_x(iio_uri): ...

3. Add a thin caller workflow:

   .. code-block:: yaml

      name: Hardware Tests (GHA)
      on:
        workflow_dispatch:
        pull_request:
          types: [labeled, opened, synchronize, reopened]
        schedule:
          - cron: "0 8 * * *"

      jobs:
        hw:
          if: >-
            github.event_name != 'pull_request' ||
            contains(github.event.pull_request.labels.*.name, 'hw-test')
          uses: tfcollins/labgrid-plugins/.github/workflows/hw-matrix.yml@v2
          with:
            venv_install_cmd: |
              uv pip install --quiet --python "$VENV_DIR/bin/python" \
                -r requirements_dev.txt
              uv pip install --quiet --python "$VENV_DIR/bin/python" -e .
              uv pip install --quiet --python "$VENV_DIR/bin/python" \
                "adi-labgrid-plugins @ git+https://github.com/tfcollins/labgrid-plugins.git@v2"
            pytest_cmd_template: >-
              "$VENV_DIR/bin/pytest" -v
              -m "$MARKER_FILTER"
              --lg-config "$LG_ENV"
              --junitxml="$JUNIT"
          secrets: inherit

That is the **entire** consumer surface. No ``.github/hw-nodes.json``,
no ``test/hw/env/*.yaml``, no per-place wiring.

Self-hosted runner contract (lab-admin)
---------------------------------------

The reusable workflow expects two classes of self-hosted runner to be
registered against every consumer repo that calls into ``@v2``:

* **One coordinator-adjacent runner** labeled
  ``[self-hosted, hw-coordinator]``. The ``discover`` job runs here.
  It only needs to be able to reach the coordinator's REST API and
  run ``pytest --collect-only`` against the caller repo — no DUT
  access is required.
* **One runner per coordinator place**, labeled
  ``[self-hosted, hw-<place>]``. The ``hw`` matrix shard for a given
  place pins to ``hw-<place>`` — e.g. shard for place ``mini2`` lands
  on the runner labeled ``hw-mini2``. This runner must be able to
  power-cycle and reach the DUT(s) behind that place.

This convention deliberately **does not** require any extra place
tag: the place name itself drives the routing. To bring up a new
place ``foo``, register a self-hosted runner with labels
``[self-hosted, hw-foo]`` and tag the place per the schema above —
no workflow or repo change is required.

Override the coordinator-runner label with the
``coordinator_runner_label`` input if your lab uses a different
naming scheme. The per-shard ``hw-<place>`` mapping is fixed by the
workflow (it derives from ``matrix.entry.place``).

Migration from v1
-----------------

If you're currently on v1:

1. Tag your places (lab-admin task):

   .. code-block:: shell

      labgrid-client -x $LG_COORDINATOR -p mini2 set-tags \
          carrier=zcu102 daughter-board=ad9081 boot-strategy=BootFPGASoC

2. In the consumer repo:

   .. code-block:: shell

      rm .github/hw-nodes.json
      rm test/hw/env/*.yaml
      rmdir test/hw/env

3. Add ``@pytest.mark.iio_hardware([…])`` to any tests that don't
   already have it. (``pyadi-iio``'s legacy ``test/test_*.py`` already
   has these markers — they keep working without change.)

4. Flip your workflow to ``@v2`` and update the inputs as shown above.

Empty-intersection behaviour
----------------------------

If the project marks tests for hardware that's offline right now, the
matrix is empty. The ``discover`` job emits a clear warning
annotation in the GHA UI:

.. code-block:: text

   hw-ci discovery produced 0 matrix entries — no marked tests
   overlap with live coordinator hardware right now

The job itself succeeds (not failure), so the workflow doesn't block
PR merges purely because the lab is down. Nightly cron runs will
re-trigger as boards come back up.

CLI reference
-------------

The ``adi-lg-hw-ci`` command is what the reusable workflow shells out
to; it's also runnable locally for debugging:

.. code-block:: shell

   # Print the matrix that would be emitted (no GHA $GITHUB_OUTPUT)
   adi-lg-hw-ci discover \
       --coord 10.0.0.41:20408 \
       --test-root . \
       --marker iio_hardware

   # Render the env yaml for one place to a file
   adi-lg-hw-ci render-env \
       --coord 10.0.0.41:20408 \
       --place mini2 \
       --out /tmp/env-mini2.yaml

   # Sanity-check: which strategies have render templates?
   adi-lg-hw-ci list-strategies
