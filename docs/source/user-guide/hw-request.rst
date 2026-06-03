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

Requirements
------------

* Self-hosted runners: one reachable by the coordinator REST API
  (``preflight-runner-label``) and a pool that can reach the coordinator and
  actuate the lab (``runner-label``).
* The coordinator must serve the Plan-1 board catalog (``GET /api/match``).
