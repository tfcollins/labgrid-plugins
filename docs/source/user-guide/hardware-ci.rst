Hardware CI (v1, manifest-first)
================================

.. note::

   A discovery-driven successor (``hw-matrix.yml@v2``) is also
   available — see :doc:`hw-ci-v2`. Both versions coexist; v1 stays
   supported for projects that haven't migrated their tests to
   ``@pytest.mark.iio_hardware`` markers yet.

This repo ships a **reusable GitHub Actions workflow** that drives
``@pytest.mark.hardware`` tests against real boards. Sibling repos
(pyadi-dt, pyadi-iio, vrt49) consume it via ``uses:`` and ship a small
node manifest; the workflow handles preflight discovery, per-place
matrix expansion, place reservation with bounded waiting, JUnit
aggregation into a PR comment, and an optional upload to a Prism
results dashboard.

Architecture overview
---------------------

.. code-block:: text

   consumer-repo/.github/workflows/hardware-test.yml  (≈25 lines)
                 │
                 │   uses: tfcollins/labgrid-plugins/
                 ▼              .github/workflows/hw-matrix.yml@v1
   ┌────────────────────────────────────────────────────────┐
   │ preflight     (probes coordinator via labgrid-client)  │
   │   │                                                    │
   │   ├─► hw-direct matrix  (one job per place × direct)   │
   │   └─► hw-coord  matrix  (one job per place × coord)    │
   │             │                                          │
   │             ▼                                          │
   │ publish-pr-test-summary  (EnricoMi JUnit aggregator)   │
   └────────────────────────────────────────────────────────┘

Each leg acquires its place through the ``acquire-place`` composite
action (reservation queue, bounded ``place_wait_minutes`` timeout) and
releases on job exit. JUnit XML is uploaded as artifacts and
optionally posted to Prism.

Onboarding a new consumer repo
------------------------------

Three files in your repo. Adapt the ``pytest_cmd_template`` to whatever
your suite expects.

1. ``.github/hw-nodes.json`` — the per-place manifest. One entry per
   labgrid place you want to fan out to:

   .. code-block:: json

      [
        {
          "place": "mini2",
          "runner_label": "hw-mini2",
          "env_remote": "test/hw/env/mini2.yaml",
          "tests": ["test/hw/test_mini2_hw.py"],
          "legs": ["coord"]
        }
      ]

   The schema lives at ``exporter_configs/schemas/hw-nodes.schema.json``
   in this repo; the preflight step validates the manifest before
   building the matrix.

2. ``.github/workflows/hardware-test.yml`` — the thin caller:

   .. code-block:: yaml

      name: Hardware Tests
      on:
        pull_request:
        workflow_dispatch:
        schedule: [{cron: "0 7 * * *"}]
      permissions: {contents: read, checks: write, pull-requests: write}
      jobs:
        hw:
          uses: tfcollins/labgrid-plugins/.github/workflows/hw-matrix.yml@v1
          with:
            manifest_path: .github/hw-nodes.json
            venv_install_cmd: 'uv pip install --python "$VENV_DIR/bin/python" -e ".[dev]"'
            pytest_cmd_template: '"$VENV_DIR/bin/pytest" -v $TESTS --junitxml="$JUNIT"'
            prism_project: my-project
          secrets: inherit

3. ``test/hw/`` — your hardware tests. Marked ``@pytest.mark.hardware``;
   they consume ``$LG_ENV``, ``$LG_COORDINATOR``, and ``$LG_PLACE``
   from the environment.

Reusable workflow inputs
------------------------

See the ``inputs:`` block of ``.github/workflows/hw-matrix.yml``. The
load-bearing ones:

``coordinator``
    Coordinator ``host:port``. Defaults to ``vars.ADI_LG_COORDINATOR``
    (set at the org level on ``analogdevicesinc``, and per-repo on the
    ``tfcollins/*`` consumers).

``manifest_path``
    Path to ``hw-nodes.json``. Default: ``.github/hw-nodes.json``.

``venv_install_cmd`` (required)
    Shell command run with ``$VENV_DIR`` exported. Installs your test
    deps into the persistent venv. The composite action ensures uv is
    on PATH first.

``pre_pytest_cmd``
    Shell command run before pytest in each matrix leg's workspace.
    Use for cmake builds, cross-compilation, or fixture pre-staging.

``pytest_cmd_template`` (required)
    Shell command run after ``pre_pytest_cmd``. Reads
    ``$TESTS``, ``$JUNIT``, ``$LG_ENV``, ``$LG_COORDINATOR``,
    ``$LG_PLACE``, and ``$VENV_DIR``.

``legs``
    ``direct,coord`` (default), or just one of them. Per-place
    ``legs`` in the manifest narrows further.

``place_wait_minutes``
    How long the acquire-place composite waits for a busy place
    before failing the leg. Default: 30. Bounds the runner idle time
    when the place is held by another job or a manual session.

``prism_upload`` / ``prism_url`` / ``prism_project``
    Gate and configure post-pytest run upload to Prism. ``prism_url``
    defaults to ``vars.PRISM_URL``; ``prism_upload`` to
    ``vars.PRISM_UPLOAD_ENABLED``.

Dynamic mode (tag-driven matrix allocation)
-------------------------------------------

The default (static) flow requires each consumer to pre-declare every
labgrid place in ``hw-nodes.json`` and commit a per-place LG_ENV yaml.
**Dynamic mode** flips that around: the consumer publishes the set of
boards it *supports* and the workflow queries the coordinator at
preflight to discover which of those boards are currently registered.
A matrix leg is generated for each match.

Enable it from the caller:

.. code-block:: yaml

   jobs:
     hw:
       uses: tfcollins/labgrid-plugins/.github/workflows/hw-matrix.yml@v<tag>
       with:
         dynamic_mode: true
         supported_boards_path: .github/supported-boards.yml
         venv_install_cmd: 'uv pip install --python "$VENV_DIR/bin/python" -e ".[dev]"'
         # $BOARD is substituted with the matched tag for each leg.
         pytest_cmd_template: '"$VENV_DIR/bin/pytest" -v --board="$BOARD" --junitxml="$JUNIT" test/'
         prism_project: my-project
       secrets: inherit

In dynamic mode, ``manifest_path``, ``legs``, ``hw-direct`` and
``hw-coord`` are not used.

``supported-boards.yml`` shape
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   boards:
     - ad9081
     - ad9084
     - adrv9002

The strings here are matched against each coordinator place's
``daughter-board`` tag (override with ``board_tag_key`` if your lab
uses a different key). Anything not in the list is ignored, anything
not registered on the coordinator at preflight time is skipped
without failing the workflow.

Coordinator-side requirement: ``daughter-board=`` tag on each place
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Dynamic mode relies on the coordinator answering ``GET /api/places``
with each place's ``tags`` populated. Labgrid exporters register
*resources* (groups), not place tags — tags are set on the place
itself via labgrid-client. The existing lab convention is
``daughter-board=<chip>`` for the IC under test and ``carrier=<fpga>``
for the FPGA carrier board:

.. code-block:: bash

   labgrid-client -x 10.0.0.41:20408 -p mini2 set-tags \
       daughter-board=ad9081 carrier=zcu102

The optional ``runner`` tag overrides the GH Actions runner label
that the matrix leg targets; without it the leg falls back to
``inputs.dynamic_runner_label_default`` (default ``hw-coordinator``).

A one-shot helper applies tags from a yaml manifest:

.. code-block:: bash

   # exporter_configs/scripts/place-tags.example.yaml
   places:
     mini2:
       daughter-board: ad9081
       carrier: zcu102
       runner: hw-mini2

   exporter_configs/scripts/seed-place-tags.sh \
       --coordinator 10.0.0.41:20408 \
       --manifest exporter_configs/scripts/place-tags.example.yaml

Each board-specific template under ``exporter_configs/templates/``
documents the expected ``set-tags`` invocation in its header.

How a dynamic leg runs
~~~~~~~~~~~~~~~~~~~~~~

1. **Preflight** hits ``GET <coordinator_api_url>/api/places``
   (default ``http://<coord_host>:8000``; override with
   ``coordinator_api_url``). Places whose ``tags.<board_tag_key>`` is
   in ``supported-boards.yml`` become matrix entries
   ``{place, board, runner_label}``. The key defaults to
   ``daughter-board`` to match the existing lab convention; override
   via the ``board_tag_key`` input.
2. Each matrix leg fetches the LG_ENV yaml on demand from
   ``GET <coordinator_api_url>/api/places/<place>/env-yaml``. The
   coordinator generates it from the place's matched resources, so
   IP, UART and any other resources registered by the exporter flow
   through automatically. No env yaml is committed to the consumer
   repo.
3. The leg acquires the place through the same ``acquire-place``
   composite (reservation queue, ``place_wait_minutes`` wait).
4. ``pytest_cmd_template`` runs with ``$BOARD`` set to the matched
   tag. Consumers should pass this as a pytest argument and have
   their conftest filter tests accordingly (pyadi-iio: ``--board=$BOARD``
   deselects tests whose ``@pytest.mark.iio_hardware`` arg list
   does not contain the board).
5. JUnit XML + artifacts upload the same way as the static legs.
   ``publish-pr-test-summary`` aggregates all three legs.

The smoke job in this repo
--------------------------

``.github/workflows/hardware-smoke.yml`` calls the reusable workflow
locally (``uses: ./.github/workflows/hw-matrix.yml``) to dogfood the
boot strategies in ``adi_lg_plugins.strategies``. It runs nightly at
06:00 UTC and on ``workflow_dispatch``, targeting one place
(``mini2``) with a minimal "boot to shell and ``uname -r``" test.
Extend by adding entries to ``.github/hw-nodes.json`` and new files
under ``tests/hw/``.

Carrier-keyed nightly dispatch
------------------------------

Alongside the manifest/dynamic ``hw-matrix.yml`` legs, this repo runs a
**carrier-keyed** path that dogfoods the boot strategies against the
lab's own boards: ``.github/workflows/hardware-tests.yml`` →
``ci/discover_places.py`` → ``ci/hardware_targets.yml``. It queries the
coordinator's ``/api/places``, and for every live place emits one job
keyed on the place's ``carrier`` tag.

``ci/hardware_targets.yml`` maps a ``carrier`` value to *how* to test it
— no code change is needed to cover a new carrier, just an entry plus a
tagged place on the coordinator:

.. code-block:: yaml

   boards:
     zcu102:
       lg_env: examples/lg_ad9081_zcu102_exporter.yaml
       tests:
         - tests/coordinator/test_soc_strat_coordinator.py
       runner_labels: [self-hosted, lab, zcu102]
     zc706:
       lg_env: tests/coordinator/env_remote_zc706.yaml
       tests:
         - tests/coordinator/test_zc706_recovery_coordinator.py
       runner_labels: [self-hosted, lab, zc706]

Because ``discover_places.py`` iterates over *places* (not carriers),
**every** live place tagged ``carrier=zc706`` gets its own job from the
single ``zc706`` entry. The per-place job substitutes ``${LG_PLACE}``
into ``lg_env`` (so one committed env covers all places of that
carrier) and the ``hw_targets`` fixture in ``tests/coordinator/`` does
the coordinator acquire/release.

``zc706`` coverage is intentionally a **lightweight, non-destructive
smoke** (``tests/coordinator/test_zc706_recovery_coordinator.py``): it
acquires the place over the coordinator and confirms its
``SerialDriver`` resolves. The lab's zc706 boards are tagged
``boot-strategy=BootZynq7000JTAGRecovery`` — a **destructive** flow
(it reflashes the SD over JTAG) that is JTAG/serial-local, so it is
**not** driven over the coordinator in nightly CI. The committed env
(``tests/coordinator/env_remote_zc706.yaml``) therefore binds only a
``RemotePlace`` + ``SerialDriver`` (no power/boot bindings, so it can't
fail on a power-driver mismatch). The full recovery flow is exercised
separately by ``tests/test_zynq7000_recovery_hw.py`` on a host wired to
the JTAG cable.

Cross-org runner topology
-------------------------

The consumer repos live across two GitHub scopes:

* **``analogdevicesinc`` org** — ``pyadi-dt``, ``pyadi-iio``
* **``tfcollins`` personal account** — ``labgrid-plugins``, ``vrt49``

GH Actions self-hosted runners are scope-bound. To make one physical
lab host serve all four consumer repos, register the host as **three
separate runner services**, sharing the same labgrid lab YAML via the
same ``LG_DIRECT_ENV`` path. Use the same runner label on all three
services (e.g. ``hw-bq``) so a single ``hw-nodes.json`` entry routes
correctly regardless of which scope the caller lives in.

The parameterized helper at ``.github/scripts/register-hw-runners.sh``
handles this:

.. code-block:: bash

   ./.github/scripts/register-hw-runners.sh \
       --hosts-file ./hosts.tsv \
       --scopes org:analogdevicesinc,repo:tfcollins/labgrid-plugins,repo:tfcollins/vrt49

The operator running this needs ``admin:org`` on the org scope and
``repo`` on each repo scope. The script writes
``LG_DIRECT_ENV=<path>`` into each ``actions-runner-<scope-slug>/.env``
so direct-mode legs find their config.

Reusable workflow visibility — public for a reason
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``tfcollins/labgrid-plugins`` is public, which is what lets
``analogdevicesinc/pyadi-dt`` (for example) call
``uses: tfcollins/labgrid-plugins/.github/workflows/hw-matrix.yml@v1``
without an allowlist. GitHub's "Allow specified actions and reusable
workflows" gate only applies to *private* sources. Keep this repo
public, or migrate it into the ``analogdevicesinc`` org if visibility
needs to change.

Place contention
----------------

Two layers of serialization protect a place from simultaneous
acquisition:

1. **GHA-level concurrency.** Each matrix leg declares
   ``concurrency: hw-place-<coord>-<place>``. Two workflow runs
   targeting the same place + coordinator queue at GH; the second
   never picks a runner until the first releases.

2. **Action-level reservation wait.** The ``acquire-place`` composite
   uses ``labgrid-client reserve --wait`` (falling back to polling on
   older labgrid). A *non-CI* holder (developer laptop, manual debug
   session) is the typical reason a place is busy at action time.
   ``place_wait_minutes`` caps the wait; on timeout the leg fails
   with the current reservation queue depth in the error message.

Place release runs ``if: always()`` after pytest so a failed test
still frees the place. **Composite actions cannot define ``post:``
steps**, so if the *runner* is killed mid-job (network drop, kernel
panic), the release never fires — the place stays held until manual
intervention. Fix is ``labgrid-client release`` from any lab host.
A future hardening could rewrite ``acquire-place`` as a JavaScript
action to gain ``post:`` cleanup.

Coordinator URL — one source of truth
-------------------------------------

The reusable workflow defaults ``inputs.coordinator`` to
``vars.ADI_LG_COORDINATOR`` (currently ``10.0.0.41:20408``). Setting
this once at the org / repo variable level means lab moves don't
require code edits.

Historic note: vrt49's ``vcu118-lab1`` place lived on a separate
coordinator at ``10.0.0.156:20408`` before this consolidation; if you
find a stale reference to that host in code or docs, replace it with
``vars.ADI_LG_COORDINATOR``.

Prism integration
-----------------

When ``vars.PRISM_UPLOAD_ENABLED=true`` and ``vars.PRISM_URL`` is set
at the consumer's org/repo level, each matrix leg appends a step that
posts JUnit + artifact bundle to Prism. The step is
``continue-on-error: true`` so a Prism outage does not redden an
otherwise-green HW workflow.

Per-test enrichment (waveform PNGs, DTS diffs, etc.) is the consumer
repo's responsibility: add ``pytest-prism`` to dev deps, pass
``--prism-labgrid-place "$LG_PLACE"`` in the pytest template, and
register setuptools entry points for repo-specific renderers. The
plugin's design supports this — see
``prism/clients/python-pytest/README.md`` in the prism repo.

Local debugging
---------------

The composite actions and scripts work standalone:

.. code-block:: bash

   # Validate a manifest before pushing
   python exporter_configs/validate.py --hw-nodes .github/hw-nodes.json

   # Reservation-wait acquire / release outside of CI
   labgrid-client -x 10.0.0.41:20408 -p mini2 reserve --shell --wait "name=mini2"
   labgrid-client -x 10.0.0.41:20408 -p mini2 acquire
   # ... work ...
   labgrid-client -x 10.0.0.41:20408 -p mini2 release

   # Inspect what's currently reserved
   labgrid-client -x 10.0.0.41:20408 reservations

Worked examples
---------------

Three consumer repos exercise the workflow at varying complexity:

``pyadi-dt``
    Largest deployment: 3 places, both ``direct`` and ``coord`` legs,
    Vivado sourcing, XSA-pipeline test artifacts uploaded.

``vrt49``
    Adds a ``pre_pytest_cmd`` for a cmake build before pytest.
    Custom pytest flags (``--vrt49-coordinator``, ``--vrt49-place``)
    flow through the template from ``LG_*`` env vars.

``pyadi-iio``
    Net-new HW pipeline added alongside an existing Jenkins job.
    Translates labgrid place → IIO URI in ``test/hw/conftest.py``,
    uses minimal smoke tests independent of the legacy
    ``test/test_*.py`` suite.
