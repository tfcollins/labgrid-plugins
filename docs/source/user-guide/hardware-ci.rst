Hardware CI Matrix
==================

The ``hardware-tests`` GitHub Actions workflow runs the
``@pytest.mark.hardware`` test suite against real boards by asking the
labgrid coordinator which places are currently registered and fanning
out one job per place.

Trigger
-------

``.github/workflows/hardware-tests.yml`` runs on:

* ``workflow_dispatch`` — manual via the Actions UI or ``gh workflow run``.
* nightly schedule (``0 7 * * *`` UTC).
* pushes to ``main``.

Per-place jobs are marked ``continue-on-error: true``: a flaky board
will surface in the run UI but won't redden the workflow.

Opting a board into the matrix
------------------------------

Two steps. They're independent — order doesn't matter.

1. **Tag the place** with its FPGA carrier. The workflow dispatches on
   ``tags.carrier``.

   .. code-block:: bash

      labgrid-client -x $LG_COORDINATOR -p <place> set-tags carrier=zc706

   Or via the coordinator REST API:

   .. code-block:: bash

      curl -X PUT $COORDINATOR_API_URL/api/places/<place>/tags \
          -H 'Content-Type: application/json' \
          -d '{"tags": {"carrier": "zc706"}}'

2. **Add the carrier to** ``ci/hardware_targets.yml`` if it's not already
   listed:

   .. code-block:: yaml

      boards:
        zc706:
          lg_env: examples/zynq7000_recovery/lg_zc706_recovery.yaml
          tests:
            - tests/test_zynq7000_recovery_hw.py
          runner_labels: [self-hosted, lab, zc706]

   ``runner_labels`` pin the per-place job to a self-hosted runner
   that's physically wired to the board (serial / power / JTAG).

Places that are tagged but missing from the dispatch map, untagged, or
currently acquired are listed in the workflow's step summary and
skipped — they never fail the job.

How discovery works
-------------------

The ``discover`` job runs ``ci/discover_places.py``, which:

1. ``GET``s ``$COORDINATOR_API_URL/api/places`` (the unauthenticated
   FastAPI route in ``coordinator/api/app/routers/places.py``).
2. Joins each place against ``ci/hardware_targets.yml`` on ``tags.carrier``.
3. Emits a GHA matrix JSON of ``{place, carrier, lg_env, tests,
   runner_labels, python_version}`` on stdout to ``$GITHUB_OUTPUT``.

The downstream ``hardware-test`` job consumes that JSON via
``fromJSON(needs.discover.outputs.matrix)`` and invokes
``nox -s tests -- <tests> --run-hardware --lg-config <lg_env>`` on the
runner the labels selected.

Coordinator URL
---------------

The discover job reads ``vars.COORDINATOR_API_URL`` (e.g.
``http://coordinator.lab:8000``) — a GitHub Actions **repository
variable**, not a secret, because the API is unauthenticated on the lab
network and a place list contains nothing sensitive. Promote to a
secret with a one-line change if your deployment differs.

Running the discovery script locally
------------------------------------

.. code-block:: bash

   COORDINATOR_API_URL=http://localhost:8000 \
   GITHUB_OUTPUT=/tmp/out GITHUB_STEP_SUMMARY=/tmp/sum \
       python ci/discover_places.py
   cat /tmp/out /tmp/sum

Useful while testing tag changes without triggering the workflow.

Destructive tests
-----------------

Tests marked ``@pytest.mark.destructive`` (e.g. SD-card overwrite for
the Zynq-7000 recovery flow) are **not** part of this matrix. They
still require ``--run-destructive`` and a manual invocation; we'll wire
them into a separate, manually-triggered workflow when there's demand.
