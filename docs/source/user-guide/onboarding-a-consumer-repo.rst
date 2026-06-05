Onboarding a Consumer Repo
==========================

This is the single, prescriptive guide for wiring a **new repo** onto the
adi-labgrid-plugins hardware-CI flow. It consolidates what is otherwise spread across the
reference pages (:doc:`github-actions`, :doc:`hw-request`, :doc:`hardware-ci-runner-setup`)
into one ordered procedure with copy-paste templates.

.. admonition:: For AI coding agents
   :class: tip

   An agent can follow ``AGENTS.md`` at the repo root — it is the same procedure in an
   executable, checklist form. This page is the human reference.

How the flow works
------------------

A consumer repo's CI calls a **reusable workflow** hosted here. A *preflight* job asks the
lab **coordinator** which of the consumer's wanted boards are live, then fans out one CI
leg per board onto a self-hosted **runner** co-located with that board. The board is
reserved, provisioned, exercised, and released automatically — the consumer never defines
labgrid drivers or strategies.

Step 1 — choose a mode
----------------------

.. list-table::
   :header-rows: 1
   :widths: 30 12 28 30

   * - If the consumer…
     - Mode
     - Reusable workflow
     - Discovery
   * - runs pytest against a booted Linux board over libIIO (a URI)
     - ``uri``
     - ``hw-request.yml``
     - ``@pytest.mark.iio_hardware(["<part>"])`` markers
   * - builds bare-metal firmware, JTAG-flashes it, validates over serial
     - ``flash``
     - ``noos-hw-request.yml``
     - a ``tools/hw_ci/projects.yaml`` manifest
   * - runs MATLAB ``runHWTests`` against a URI
     - ``matlab``
     - (bespoke) ``hw-matlab.yml``
     - custom + ``board_map.yaml``

Reference consumers: **pyadi-iio** (uri), **no-os** (flash), **TransceiverToolbox**
(matlab). See :doc:`github-actions` for the full when-to-use comparison of every reusable
workflow. MATLAB is bespoke — copy the pattern from TransceiverToolbox's
``hw-matlab.yml`` and the ``adi-lg-matlab`` launcher rather than a template. The rest of
this guide covers **uri** and **flash**.

Step 2 — what you'll touch
--------------------------

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Location
     - What changes
   * - **Consumer repo**
     - the workflow file, markers (uri) or manifest (flash), a ``conftest.py`` (uri), and
       three repo variables
   * - **Hub** (this repo)
     - nothing — you *consume* the reusable workflow and CLI
   * - **Coordinator**
     - a ``board_catalog.yaml`` entry per part + a live place tagged for it (lab admin)
   * - **Lab**
     - runners registered on the consumer's GitHub scope (+ Vivado/JTAG for flash)

uri mode (pytest over libIIO)
-----------------------------

**Workflow** — copy into ``.github/workflows/hw-request.yml`` and set ``test-root`` +
``install-cmd``:

.. literalinclude:: ../onboarding-templates/hw-request-uri.yml
   :language: yaml

**Markers** — decorate the hardware tests; the preflight AST-parses these, so the
arguments must be **string literals**:

.. code-block:: python

   @pytest.mark.iio_hardware(["ad9081"])           # string literals only
   @pytest.mark.iio_carrier(["zcu102"])            # optional carrier narrowing
   def test_something(iio_uri):
       ...

**Conftest** — copy into ``test/hw/conftest.py`` for the ``iio_uri`` fixture
(``adi-lg request`` boots the board out of band and exports ``IIO_URI``):

.. literalinclude:: ../onboarding-templates/conftest-iio-uri.py
   :language: python

flash mode (no-os firmware)
---------------------------

**Workflow** — copy into ``.github/workflows/hw-request.yml``:

.. literalinclude:: ../onboarding-templates/noos-hw-request-flash.yml
   :language: yaml

**Manifest** — copy into ``tools/hw_ci/projects.yaml``, one entry per buildable project
(schema: ``adi_lg_plugins/hw_ci/noos_manifest.py``):

.. literalinclude:: ../onboarding-templates/projects.yaml
   :language: yaml

The reusable workflow's ``build-noos`` step sources each board's HDL ``.xsa`` from the
Kuiper image and composes the Vivado env — the runner only needs Vivado/Vitis installed.
See :doc:`hardware-ci-runner-setup` for the runner details.

Step 3 — set the three repo variables
-------------------------------------

In the consumer repo, **Settings → Secrets and variables → Actions → Variables**:

.. list-table::
   :header-rows: 1
   :widths: 26 24 50

   * - Variable
     - Value
     - Notes
   * - ``LG_COORDINATOR``
     - ``<host>:20408``
     - the **gRPC** port, NOT REST ``:8000``; the workflow derives REST from it
   * - ``HW_REQUEST_RUNNER``
     - e.g. ``hw-lab``
     - fallback runner label for the per-board legs
   * - ``HW_PREFLIGHT_RUNNER``
     - e.g. ``hw-coordinator``
     - runner label that can reach the coordinator

Step 4 — coordinator + lab prerequisites
----------------------------------------

These you do not own — confirm with a lab admin (Step 5 fails clearly if any are missing):

- **Catalog entry** per part in ``coordinator/api/board_catalog.yaml`` (template:
  ``onboarding-templates/board-catalog-entry.yaml``; schema:
  ``coordinator/api/app/catalog.py``). uri needs ``image``; flash needs a ``flash:`` block.
  After any catalog edit the coordinator host must be **redeployed**.
- **A live place** tagged ``daughter-board=<part> carrier=<carrier>
  boot-strategy=<Strategy>`` (+ optional ``runner=<label>``).
- **Runner scope** — the lab runners must be registered on the consumer repo's (or org's)
  scope or legs queue forever; see ``.github/scripts/register-hw-runners.sh --scopes`` and
  :doc:`hardware-ci-runner-setup`.
- **flash only** — the leg runner needs Vivado/Vitis + ~10 GB disk for the Kuiper image.

Step 5 — verify before opening the PR
-------------------------------------

Run the discovery preflight against the live coordinator — no hardware needed. This proves
the markers/manifest + catalog + places line up:

.. code-block:: bash

   export LG_COORDINATOR=<host>:20408

   # uri mode
   adi-lg-hw-ci request-matrix --test-root test/hw --coord "$LG_COORDINATOR"

   # flash mode
   adi-lg-hw-ci noos-matrix --manifest tools/hw_ci/projects.yaml --coord "$LG_COORDINATOR"

**Success** is one ``matrix.include`` leg per board you expect, each with a non-empty
``runner``. A wanted board with no live place is emitted as a ``::warning::`` skip (fix it
in Step 4). For flash, also prove the ``.xsa`` is extractable:

.. code-block:: bash

   adi-lg-hw-ci fetch-xsa --release 2023_R2_P1 --board <canonical-board> --carrier <carrier>

Then trigger the workflow (``workflow_dispatch`` or the ``hw-request`` PR label) and
confirm the preflight and the per-board legs go green.

Drop in an ``AGENTS.md``
------------------------

Add an ``AGENTS.md`` to the consumer repo so the next agent/human knows the wiring — copy
``onboarding-templates/AGENTS-consumer-stub.md`` and fill in the mode + boards.

Troubleshooting
---------------

- **Jobs queue forever** — no runner with the requested label is registered on this repo's
  scope. Register with ``register-hw-runners.sh --scopes``.
- **A board is always skipped** — its catalog entry or a live place is missing/mistagged,
  or (uri) its marker uses a non-literal argument.
- **``Unknown release version``** — the coordinator is stale (returns no ``image``);
  redeploy it after catalog merges.
- **flash build fails extracting the ``.xsa``** — the board's Kuiper folder is a family
  name; set ``flash.kuiper_xsa_dir`` in the catalog (e.g. ``zynq-zc706-adv7511-adrv937x``
  for adrv9371).
- **Reservation HTTP 400** — ``LG_COORDINATOR`` points at REST ``:8000``; use gRPC
  ``:20408``.
