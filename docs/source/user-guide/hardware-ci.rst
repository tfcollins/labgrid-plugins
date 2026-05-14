Hardware CI
===========

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

The smoke job in this repo
--------------------------

``.github/workflows/hardware-smoke.yml`` calls the reusable workflow
locally (``uses: ./.github/workflows/hw-matrix.yml``) to dogfood the
boot strategies in ``adi_lg_plugins.strategies``. It runs nightly at
06:00 UTC and on ``workflow_dispatch``, targeting one place
(``mini2``) with a minimal "boot to shell and ``uname -r``" test.
Extend by adding entries to ``.github/hw-nodes.json`` and new files
under ``tests/hw/``.

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
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
