GitHub Actions (Reusable Workflows)
====================================

This repo hosts reusable GitHub Actions workflows that consumer repos
(``pyadi-iio``, ``pyadi-dt``, ``vrt49``, ``no-os``) call via
``uses: tfcollins/labgrid-plugins/.github/workflows/<name>.yml@<ref>``.
The repo must remain **public** so cross-org callers can reference it
without an enterprise allowlist.  Each workflow runs a preflight job that
discovers live boards from the coordinator and fans out one CI leg per
matching board; no test will queue against hardware that is currently
unreachable.

.. note::

   Two composite actions (``setup-uv-venv``, ``acquire-place``) and a
   runner-registration helper (``register-hw-runners.sh``) are documented
   in the :ref:`composite-actions` and :ref:`runner-registration` sections
   below.


.. _choosing-a-workflow:

Choosing a workflow
-------------------

.. warning::

   ``hw-matrix.yml`` and ``hw-matrix-v2.yml`` are **deprecated**.  New consumers must
   use the hw-request family (``hw-request.yml``, ``noos-hw-request.yml``,
   ``matlab-hw-request.yml``) pinned at ``@v3.1`` (current release).  Removal of the
   deprecated workflows is tracked by the HW-CI convergence effort.

.. list-table::
   :widths: 20 25 30 25
   :header-rows: 1

   * - Workflow
     - What it runs
     - Discovery mechanism
     - Use when
   * - ``hw-matrix.yml`` (v1) — **deprecated**
     - pytest against places from a committed manifest
     - ``labgrid-client places`` filtered by ``hw-nodes.json``
     - Do not adopt for new consumers; use ``hw-request.yml@v3.1`` instead.
   * - ``hw-matrix-v2.yml`` (v2) — **deprecated**
     - pytest against discovered places; renders env.yaml per shard
     - ``/api/places`` ∩ ``@pytest.mark.iio_hardware`` markers
     - Do not adopt for new consumers; use ``hw-request.yml@v3.1`` instead.
   * - ``hw-request.yml``
     - ``adi-lg request --part <p>`` per part; hands a booted board URI
       to pytest via ``IIO_URI``
     - ``adi-lg-hw-ci request-matrix`` (markers ∩ ``/api/match``)
     - Low-config: consumers name a part, labgrid boots and hands over a
       URI (pyadi-iio pattern).
   * - ``matlab-hw-request.yml``
     - MATLAB ``runHWTests(<board>)`` against the booted board's
       ``IIO_URI``
     - ``adi-lg-hw-ci matlab-matrix`` (``board_map.yaml`` ∩ live places)
     - MATLAB toolbox hardware tests (TransceiverToolbox pattern).
   * - ``noos-hw-request.yml``
     - Build no-os firmware → JTAG-flash → validate on serial (flash mode)
     - ``adi-lg-hw-ci noos-matrix`` (project manifest ∩
       ``/api/match?mode=flash``)
     - no-os bare-metal firmware on real boards.


``hw-matrix.yml`` — manifest-first matrix
------------------------------------------

Probes the coordinator for available labgrid places listed in a committed
``hw-nodes.json`` manifest, then fans out a per-place matrix with optional
``hw-direct`` and/or ``hw-coord`` legs.  Includes a ``dynamic_mode`` option
that switches to API-driven discovery without the static manifest.  See
:doc:`hardware-ci` for the full consumer contract, manifest schema, and
migration notes.

``hw-matrix.yml`` example
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   # .github/workflows/hw.yml (consumer repo)
   name: HW
   on: [pull_request]
   jobs:
     hw:
       uses: tfcollins/labgrid-plugins/.github/workflows/hw-matrix.yml@main
       with:
         venv_install_cmd: >-
           uv pip install --quiet --python "$VENV_DIR/bin/python" -e ".[dev]"
         pytest_cmd_template: >-
           "$VENV_DIR/bin/pytest" $TESTS --junitxml="$JUNIT" -v
       secrets:
         PYADI_BUILD_TOKEN: ${{ secrets.PYADI_BUILD_TOKEN }}

``hw-matrix.yml`` inputs
~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 26 10 30 34
   :header-rows: 1

   * - Input
     - Required
     - Default
     - Description
   * - ``coordinator``
     - No
     - ``""``
     - Coordinator ``host:port``.  Defaults to ``vars.ADI_LG_COORDINATOR``
       when empty.
   * - ``manifest_path``
     - No
     - ``.github/hw-nodes.json``
     - Repo-relative path to the hw-nodes manifest.
   * - ``venv_install_cmd``
     - **Yes**
     - —
     - Shell command run with ``$VENV_DIR`` exported; installs the caller's
       test deps into the persistent venv.
   * - ``venv_dir``
     - No
     - ``$HOME/.cache/hw-ci/venv``
     - Persistent venv root on each runner host.
   * - ``pre_pytest_cmd``
     - No
     - ``""``
     - Shell command run in each matrix leg before pytest (cmake builds,
       cross-compilation, fixture pre-staging).
   * - ``pytest_cmd_template``
     - **Yes**
     - —
     - Shell command run after ``pre_pytest_cmd``. The workflow exports
       ``$TESTS``, ``$JUNIT``, ``$LG_ENV``, ``$LG_COORDINATOR``,
       ``$LG_PLACE``, and ``$VENV_DIR``.
   * - ``artifact_glob``
     - No
     - ``**/*.log``, ``uart_log_*.txt``, ``junit-hw-*.xml``
     - Newline-separated globs uploaded on every leg.
   * - ``legs``
     - No
     - ``direct,coord``
     - Comma-separated subset of legs to consider.  Per-place legs in the
       manifest override this.
   * - ``timeout_minutes``
     - No
     - ``40``
     - Per-leg timeout (covers acquire-wait + pytest + teardown).
   * - ``place_wait_minutes``
     - No
     - ``30``
     - How long to wait for a busy place before failing the leg.
   * - ``vivado_settings``
     - No
     - ``/tools/Xilinx/2025.1/Vivado/settings64.sh``
     - Path to a ``settings64.sh``; sourced if it exists, else skipped.
   * - ``prism_upload``
     - No
     - ``false``
     - Post JUnit + artifact bundle to Prism after each leg.
   * - ``prism_url``
     - No
     - ``""``
     - Prism base URL.  Defaults to ``vars.PRISM_URL`` when empty.
   * - ``prism_project``
     - No
     - ``""``
     - Prism project slug.  Required when ``prism_upload`` is ``true``.
   * - ``prism_upload_cmd``
     - No
     - ``""``
     - Consumer-supplied shell command to upload results to Prism.  The
       step exports ``PRISM_URL``, ``PRISM_EMAIL``, ``PRISM_PASSWORD``,
       ``PRISM_PROJECT``, ``PRISM_JUNIT``, ``PRISM_RUN_NAME``,
       ``PRISM_BOARD``, ``PRISM_CARRIER``, ``PRISM_PLACE``.  Runs only
       when ``prism_upload`` is ``true`` and this is non-empty.
   * - ``dynamic_mode``
     - No
     - ``false``
     - Opt in to API-driven discovery: places are fetched from the
       coordinator and filtered against ``supported_boards_path``.  The
       static ``hw-nodes.json`` manifest and ``hw-direct``/``hw-coord``
       legs are not used.
   * - ``supported_boards_path``
     - No
     - ``.github/supported-boards.yml``
     - Repo-relative path to a YAML with a ``boards:`` list of board tags.
       Used only when ``dynamic_mode`` is ``true``.
   * - ``coordinator_api_url``
     - No
     - ``""``
     - Base URL of the coordinator FastAPI bridge (e.g.
       ``http://coord-host:8000``).  When empty, derived from
       ``coordinator`` by substituting port 8000.  Used only when
       ``dynamic_mode`` is ``true``.
   * - ``dynamic_runner_label_default``
     - No
     - ``hw-coordinator``
     - Fallback runner label for dynamic-mode legs when the place has no
       ``runner`` tag on the coordinator.
   * - ``board_tag_key``
     - No
     - ``daughter-board``
     - Place-tag key matched against ``supported-boards.yml``.  Default
       matches the lab convention where each place is tagged with its
       daughter-board (e.g. ``ad9081``).
   * - ``dynamic_env_tier``
     - No
     - ``boot``
     - ``tier`` query param passed to
       ``/api/places/<name>/env-yaml`` in dynamic-mode legs.  One of
       ``shell``, ``drivers``, or ``boot``.


``hw-matrix-v2.yml`` — discovery-driven matrix
-----------------------------------------------

Unlike v1, v2 discovers live hardware from the coordinator's ``/api/places``
endpoint and intersects it with the caller's ``@pytest.mark.iio_hardware``
and ``@pytest.mark.iio_carrier`` markers.  The consumer repo ships **no**
``hw-nodes.json`` manifest and **no** per-place env yaml; the env yaml is
rendered per-shard from the place's ``boot-strategy`` tag.  See
:doc:`hw-ci-v2` for the full consumer contract.

``hw-matrix-v2.yml`` example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   # .github/workflows/hw.yml (consumer repo)
   name: HW
   on: [pull_request]
   jobs:
     hw:
       uses: tfcollins/labgrid-plugins/.github/workflows/hw-matrix-v2.yml@main
       with:
         venv_install_cmd: >-
           uv pip install --quiet --python "$VENV_DIR/bin/python" -e ".[dev]"
           "adi-labgrid-plugins @ git+https://github.com/tfcollins/labgrid-plugins@main"
         pytest_cmd_template: >-
           "$VENV_DIR/bin/pytest" -m "$MARKER_FILTER" --junitxml="$JUNIT"
       secrets:
         PYADI_BUILD_TOKEN: ${{ secrets.PYADI_BUILD_TOKEN }}

``hw-matrix-v2.yml`` inputs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 26 10 30 34
   :header-rows: 1

   * - Input
     - Required
     - Default
     - Description
   * - ``coordinator``
     - No
     - ``""``
     - Coordinator ``host:port``.  Defaults to ``vars.ADI_LG_COORDINATOR``
       when empty.
   * - ``marker_filter``
     - No
     - ``iio_hardware``
     - Top-level pytest marker used to harvest test-to-hardware affinity.
       Non-IIO projects can swap this.
   * - ``test_root``
     - No
     - ``.``
     - Path (relative to repo root) for ``pytest --collect-only``.
   * - ``venv_install_cmd``
     - **Yes**
     - —
     - Shell command run with ``$VENV_DIR`` exported; must install the
       caller's test deps **plus** ``adi-labgrid-plugins`` (so the marker
       plugin is available during the discover step).
   * - ``venv_dir``
     - No
     - ``$HOME/.cache/hw-ci/venv``
     - Persistent venv root on each runner host.
   * - ``pre_pytest_cmd``
     - No
     - ``""``
     - Optional command run inside each shard before pytest (cmake builds,
       fixture pre-staging).
   * - ``pytest_cmd_template``
     - **Yes**
     - —
     - Shell command run in each shard.  The workflow exports
       ``$MARKER_FILTER``, ``$JUNIT``, ``$LG_ENV``, ``$LG_COORDINATOR``,
       ``$LG_PLACE``, ``$VENV_DIR``.
   * - ``artifact_glob``
     - No
     - ``**/*.log``, ``uart_log_*.txt``, ``junit-hw-*.xml``
     - Newline-separated globs uploaded on every leg.
   * - ``timeout_minutes``
     - No
     - ``40``
     - Per-leg timeout.
   * - ``place_wait_minutes``
     - No
     - ``30``
     - Maximum wait time for a busy place.
   * - ``prism_upload``
     - No
     - ``false``
     - Post results to Prism after each leg.
   * - ``prism_url``
     - No
     - ``""``
     - Prism base URL.  Defaults to ``vars.PRISM_URL`` when empty.
   * - ``prism_project``
     - No
     - ``""``
     - Prism project slug.  Required when ``prism_upload`` is ``true``.
   * - ``coordinator_runner_label``
     - No
     - ``hw-coordinator``
     - Extra label the coordinator-adjacent runner must carry (alongside
       ``self-hosted``).  Used by the ``discover`` and ``summary`` jobs.
       Per-shard ``hw`` jobs pin automatically to ``hw-<place>``.


``hw-request.yml`` — low-config by-part
-----------------------------------------

Runs a consumer repo's hardware tests **by part**: ``adi-lg-hw-ci
request-matrix`` intersects the caller's ``@pytest.mark.iio_hardware``
markers with the coordinator's ``/api/match`` endpoint, then fans out one
independent job per matching part.  Each leg calls ``adi-lg request --part
<p>`` which boots a free board and runs pytest with ``IIO_URI`` injected.
No place names, env yaml, or board maps are needed in the consumer repo.
See :doc:`hw-request` for the full consumer contract.

``hw-request.yml`` example
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   # .github/workflows/hw.yml (consumer repo, e.g. pyadi-iio)
   name: HW
   on: [pull_request]
   jobs:
     hw:
       uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@v3.1  # bump when a new release tags
       with:
         coordinator: ${{ vars.ADI_LG_COORDINATOR }}
         test-root: "test"
         install-cmd: >-
           uv pip install --quiet --python "$VENV_DIR/bin/python" -e "."
           "adi-labgrid-plugins @ git+https://github.com/tfcollins/labgrid-plugins@v3.1"

``hw-request.yml`` inputs
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 26 10 30 34
   :header-rows: 1

   * - Input
     - Required
     - Default
     - Description
   * - ``coordinator``
     - **Yes**
     - —
     - Coordinator ``host:port`` for the REST API (``GET /api/match``) and
       reservations.
   * - ``test-root``
     - No
     - ``test``
     - Path to the test directory to harvest markers from and run.
   * - ``marker``
     - No
     - ``iio_hardware``
     - Top-level pytest marker gating hardware tests.
   * - ``wait``
     - No
     - ``1800``
     - Seconds each leg queues for a free matching board (``0`` = fail
       fast).
   * - ``runner-label``
     - No
     - ``hw-lab``
     - Fallback self-hosted runner label for per-board legs.  Each leg
       prefers the runner its board is wired to (the place's ``runner``
       tag); this is used only when a board's place carries no ``runner``
       tag.
   * - ``preflight-runner-label``
     - No
     - ``hw-coordinator``
     - Runner label for the discovery preflight (must reach the coordinator
       REST API).
   * - ``pytest-args``
     - No
     - ``""``
     - Extra args appended to the per-leg pytest command.
   * - ``venv-dir``
     - No
     - ``$HOME/.cache/hw-request/venv``
     - Absolute path for the persistent uv venv on the runner.
   * - ``install-cmd``
     - No
     - ``uv pip install --quiet --python "$VENV_DIR/bin/python" -e "." "adi-labgrid-plugins @ git+…"``
     - Shell command (run with ``$VENV_DIR`` exported) to install the
       consumer package + ``adi-labgrid-plugins`` into the per-leg venv.
   * - ``request-mode``
     - No
     - ``uri``
     - ``adi-lg request`` mode for each leg.  ``uri`` (default) boots the
       board, verifies iiod, and exports ``IIO_URI``.  ``reserve`` only
       acquires the place and exports ``LG_ENV``/``LG_COORDINATOR`` — for
       suites that drive boot themselves via the labgrid pytest plugin
       (e.g. pyadi-dt).  See :doc:`hw-request` ("Reserve mode").
   * - ``prism-upload``
     - No
     - ``false``
     - Post each leg's JUnit to Prism after the test run.  The upload step
       runs with ``continue-on-error`` — a Prism outage never fails a
       hardware leg.  See :doc:`hw-request` ("Uploading results to Prism").
   * - ``prism-url``
     - No
     - ``""``
     - Prism base URL.  Defaults to the caller's ``vars.PRISM_URL`` when
       empty.
   * - ``prism-project``
     - No
     - ``""``
     - Prism project slug.  Required when ``prism-upload`` is ``true``.
   * - ``prism-upload-cmd``
     - No
     - ``""``
     - Consumer-supplied shell command that uploads results to Prism
       (vendored-uploader escape hatch, e.g. for a private Prism repo).
       Used **instead of** the built-in uploader when non-empty.  The step
       exports ``PRISM_URL``, ``PRISM_API_TOKEN``, ``PRISM_EMAIL``,
       ``PRISM_PASSWORD``, ``PRISM_PROJECT``, ``PRISM_JUNIT``,
       ``PRISM_RUN_NAME``, ``PRISM_BOARD``, ``PRISM_CARRIER``,
       ``PRISM_PLACE``.

``hw-request.yml`` secrets
~~~~~~~~~~~~~~~~~~~~~~~~~~~

All secrets are optional; the Prism ones are only consulted when
``prism-upload`` is ``true``.  Cross-org callers must pass them
**explicitly** in the caller's ``secrets:`` block — ``secrets: inherit``
does not cross org boundaries.

.. list-table::
   :widths: 26 10 64
   :header-rows: 1

   * - Secret
     - Required
     - Description
   * - ``INSTALL_GIT_TOKEN``
     - No
     - PAT exposed as a ``github.com`` ``insteadOf`` credential during the
       per-leg venv install, for consumers whose test deps live in private
       git repos (e.g. pyadi-dt's ``pyadi-build``).  Scoped to the install
       step only; never persists in the runner's git config.
   * - ``PRISM_API_TOKEN``
     - No
     - API token used by the Prism upload step.
   * - ``PRISM_EMAIL``
     - No
     - Login email for the Prism upload step (login-auth uploaders).
   * - ``PRISM_PASSWORD``
     - No
     - Login password for the Prism upload step (login-auth uploaders).


``matlab-hw-request.yml`` — MATLAB by-part
--------------------------------------------

Boots a matching board via labgrid, runs the MATLAB toolbox's
``runHWTests(<board>)`` against the booted board's libIIO URI, collects the
JUnit, and releases the board — one independent job per board.  The
preflight runs ``adi-lg-hw-ci matlab-matrix``, intersecting the consumer's
``board_map.yaml`` with the coordinator's live places.  Each leg uses the
same ``adi-lg request`` core as the uri/flash flows.  The leg runner must
have MATLAB installed (+ a reachable license) and the libIIO libs.

``matlab-hw-request.yml`` example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   # .github/workflows/hw-matlab.yml (consumer repo, e.g. TransceiverToolbox)
   name: HW MATLAB
   on: [pull_request]
   jobs:
     hw-matlab:
       uses: tfcollins/labgrid-plugins/.github/workflows/matlab-hw-request.yml@v3.1  # bump when a new release tags
       with:
         coordinator: ${{ vars.LG_COORDINATOR }}
         board-map: "test/hw_ci/board_map.yaml"
         matlab-bin: ${{ vars.MATLAB_BIN }}

``matlab-hw-request.yml`` inputs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 26 10 30 34
   :header-rows: 1

   * - Input
     - Required
     - Default
     - Description
   * - ``coordinator``
     - **Yes**
     - —
     - gRPC coordinator ``host:port`` (e.g. ``host:20408``).
   * - ``board-map``
     - No
     - ``test/hw_ci/board_map.yaml``
     - Path (in the consumer checkout) to the MATLAB ``board_map.yaml``.
   * - ``runner-label``
     - No
     - ``hw-lab``
     - Fallback self-hosted runner label for the per-board legs.
   * - ``preflight-runner-label``
     - No
     - ``hw-coordinator``
     - Runner label for the discovery preflight (reaches the coordinator).
   * - ``matlab-bin``
     - No
     - ``/opt/MATLAB/R2025b/bin/matlab``
     - Path to the MATLAB binary on the leg runner.
   * - ``wait``
     - No
     - ``1800``
     - Seconds each leg queues for a free matching board (``0`` = fail
       fast).
   * - ``venv-dir``
     - No
     - ``$HOME/.cache/matlab-hw-request/venv``
     - Absolute path for the persistent uv venv on the runner.
   * - ``install-cmd``
     - No
     - ``uv pip install --quiet --python "$VENV_DIR/bin/python" "adi-labgrid-plugins[kuiper] @ git+…"``
     - Command (with ``$VENV_DIR`` exported) to install
       ``adi-labgrid-plugins``.  The ``[kuiper]`` extra (pytsk3) is needed
       to boot Kuiper uri-mode boards.
   * - ``prism-upload``
     - No
     - ``false``
     - Post each leg's JUnit to Prism after the test run.  The upload step
       runs with ``continue-on-error`` — a Prism outage never fails a
       hardware leg.  See :doc:`hw-request` ("Uploading results to Prism").
   * - ``prism-url``
     - No
     - ``""``
     - Prism base URL.  Defaults to the caller's ``vars.PRISM_URL`` when
       empty.
   * - ``prism-project``
     - No
     - ``""``
     - Prism project slug.  Required when ``prism-upload`` is ``true``.
   * - ``prism-upload-cmd``
     - No
     - ``""``
     - Consumer-supplied shell command that uploads results to Prism
       (vendored-uploader escape hatch, e.g. for a private Prism repo).
       Used **instead of** the built-in uploader when non-empty.  The step
       exports ``PRISM_URL``, ``PRISM_API_TOKEN``, ``PRISM_EMAIL``,
       ``PRISM_PASSWORD``, ``PRISM_PROJECT``, ``PRISM_JUNIT``,
       ``PRISM_RUN_NAME``, ``PRISM_BOARD``, ``PRISM_CARRIER``,
       ``PRISM_PLACE``.

``matlab-hw-request.yml`` secrets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Identical to the ``hw-request.yml`` secrets above: optional
``PRISM_API_TOKEN`` / ``PRISM_EMAIL`` / ``PRISM_PASSWORD``, only consulted
when ``prism-upload`` is ``true``, and passed explicitly in the caller's
``secrets:`` block (cross-org ``secrets: inherit`` does not work).


``noos-hw-request.yml`` — no-os firmware flash
-----------------------------------------------

Builds a no-os reference project, JTAG-flashes it onto a matching physical
board via labgrid, and validates it on-target with a serial banner assertion —
one independent job per project.  The preflight runs ``adi-lg-hw-ci
noos-matrix``, intersecting the consumer's ``projects.yaml`` manifest with
the coordinator's live FLASH-capable boards (``GET /api/match?mode=flash``).
See :doc:`hardware-ci-runner-setup` for runner requirements, Vivado setup,
and the manifest reference.

``noos-hw-request.yml`` example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   # .github/workflows/noos-hw.yml (consumer repo, e.g. no-os)
   name: no-os HW
   on: [pull_request]
   jobs:
     noos-hw:
       uses: tfcollins/labgrid-plugins/.github/workflows/noos-hw-request.yml@v3.1  # bump when a new release tags
       with:
         coordinator: ${{ vars.ADI_LG_COORDINATOR }}
         manifest: "tools/hw_ci/projects.yaml"

``noos-hw-request.yml`` inputs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 26 10 30 34
   :header-rows: 1

   * - Input
     - Required
     - Default
     - Description
   * - ``coordinator``
     - **Yes**
     - —
     - Coordinator ``host:port`` for ``/api/match`` (REST).
   * - ``manifest``
     - No
     - ``tools/hw_ci/projects.yaml``
     - Path (in the consumer checkout) to the no-os hw-ci
       ``projects.yaml``.
   * - ``runner-label``
     - No
     - ``hw-lab``
     - Fallback self-hosted runner label for per-project legs.  Each leg
       prefers the runner co-located with its board's JTAG + Vivado (the
       place's ``runner`` tag); this is the fallback.
   * - ``preflight-runner-label``
     - No
     - ``hw-coordinator``
     - Runner label for the discovery preflight (must reach the REST API).
   * - ``build-cmd``
     - No
     - ``adi-lg-hw-ci build-noos …``
     - Shell command to build a project (cwd = consumer checkout).
       Receives ``$NOOS_PROJECT``, ``$CARRIER``, ``$BOARD``, ``$RELEASE``,
       and ``$VALIDATE_BANNER``.  Default delegates to
       ``adi-lg-hw-ci build-noos``, which sources Vivado, ensures the
       libtinfo shim, fetches the board's ``.xsa`` from the Kuiper image,
       and runs ``make``.
   * - ``firmware-path``
     - No
     - ``projects/$NOOS_PROJECT/build/$NOOS_PROJECT.elf``
     - Built ``.elf`` path template (``$NOOS_PROJECT`` expanded at
       runtime).
   * - ``bitstream-path``
     - No
     - ``projects/$NOOS_PROJECT/build_hw/system_top.bit``
     - FPGA bitstream path to flash before the ``.elf``.
   * - ``ps7-init-path``
     - No
     - ``projects/$NOOS_PROJECT/build_hw/ps7_init.tcl``
     - ``ps7_init.tcl`` path for PS init (``$NOOS_PROJECT`` expanded).
   * - ``validate-banner``
     - No
     - ``Successfully initialized``
     - Fallback serial banner asserted on-target after flashing.  Each
       matrix leg uses its own manifest-declared banner; this is the
       global default.
   * - ``wait``
     - No
     - ``1800``
     - Seconds each leg queues for a free matching board (``0`` = fail
       fast).
   * - ``venv-dir``
     - No
     - ``$HOME/.cache/noos-hw-request/venv``
     - Absolute path for the persistent uv venv on the runner.
   * - ``install-cmd``
     - No
     - ``uv pip install --quiet --python "$VENV_DIR/bin/python" "adi-labgrid-plugins @ git+…"``
     - Shell command (run with ``$VENV_DIR`` exported) to install
       ``adi-labgrid-plugins`` into the per-leg venv.


.. _composite-actions:

Composite actions
-----------------

Both composite actions are used internally by every reusable workflow above
and can also be called standalone from any consumer repo.

``setup-uv-venv``
~~~~~~~~~~~~~~~~~

Ensures ``uv`` is installed on the runner, creates (or reuses) a persistent
venv at the requested path, runs the caller's install command, and adds the
venv's ``bin/`` directory to ``$GITHUB_PATH`` for subsequent steps.

.. code-block:: yaml

   - uses: tfcollins/labgrid-plugins/.github/actions/setup-uv-venv@v3.1  # bump when a new release tags
     with:
       venv_dir: "$HOME/.cache/hw-ci/venv"
       install_cmd: >-
         uv pip install --quiet --python "$VENV_DIR/bin/python" -e ".[dev]"

.. list-table::
   :widths: 20 10 20 50
   :header-rows: 1

   * - Input
     - Required
     - Default
     - Description
   * - ``venv_dir``
     - **Yes**
     - —
     - Absolute path to the persistent venv directory (created if missing).
   * - ``install_cmd``
     - **Yes**
     - —
     - Shell command run with ``$VENV_DIR`` exported.  Typically
       ``uv pip install --python "$VENV_DIR/bin/python" -e ".[dev]"`` or a
       wrapper script.
   * - ``python_version``
     - No
     - ``""``
     - Python interpreter passed to ``uv venv --python``.  Empty = uv
       default.

**Outputs**

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Output
     - Description
   * - ``python``
     - Absolute path to the venv's Python interpreter.

``acquire-place``
~~~~~~~~~~~~~~~~~

Reserves and acquires a labgrid place via the coordinator, waiting up to
``wait_minutes`` for it to become free.  Uses labgrid's reservation queue
when available, falling back to a jittered polling loop.

.. warning::

   Composite actions cannot run post-job cleanup.  Every caller **must**
   pair this action with a release step guarded by ``if: always()`` that
   calls ``labgrid-client … release``.

.. code-block:: yaml

   - uses: tfcollins/labgrid-plugins/.github/actions/acquire-place@v3.1  # bump when a new release tags
     with:
       coordinator: ${{ env.COORDINATOR }}
       place: my-zcu102
       labgrid_client: "$HOME/.cache/hw-ci/venv/bin/labgrid-client"
       wait_minutes: "30"

.. list-table::
   :widths: 20 10 25 45
   :header-rows: 1

   * - Input
     - Required
     - Default
     - Description
   * - ``coordinator``
     - **Yes**
     - —
     - Coordinator URL (``host:port``).
   * - ``place``
     - **Yes**
     - —
     - labgrid place name to acquire.
   * - ``labgrid_client``
     - No
     - ``${HOME}/.cache/hw-ci/venv/bin/labgrid-client``
     - Path to the ``labgrid-client`` binary.
   * - ``wait_minutes``
     - No
     - ``30``
     - Maximum time to wait for the place to become free, in minutes.

**Outputs**

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Output
     - Description
   * - ``reservation_token``
     - Reservation token string, if a reservation was created.
   * - ``acquired_at``
     - ISO-8601 timestamp when the place was successfully acquired.


.. _runner-registration:

Registering self-hosted runners
---------------------------------

``.github/scripts/register-hw-runners.sh`` installs GitHub Actions
self-hosted runner services on lab hosts via SSH.  A single physical host
can serve multiple GitHub scopes simultaneously — for example, both an org
scope and a personal-repo scope — with one runner service per scope sharing
the same lab YAML via the same ``LG_DIRECT_ENV`` path.

Prerequisites (on the machine **running** the script):

* ``gh`` CLI authenticated against ``github.com`` with ``admin:org`` for any
  ``org:`` scopes, and ``repo`` for any ``repo:`` scopes.
* SSH key-based access as the target user on each lab host.
* Local tools: ``gh``, ``jq``, ``ssh``, ``scp``, ``mktemp``.

Flags
~~~~~

``--hosts-file <path>`` *(required)*
  TSV file listing the lab hosts to configure (see format below).

``--scopes <list>`` *(required)*
  Comma-separated GitHub scopes to register against.  Each scope must be
  prefixed with either ``org:`` (for an organisation) or ``repo:`` (for a
  specific repository, as ``owner/repo``).
  Example: ``org:analogdevicesinc,repo:tfcollins/labgrid-plugins``

``-h`` / ``--help``
  Print usage and exit.

Hosts-file format
~~~~~~~~~~~~~~~~~

A TSV file; lines beginning with ``#`` are comments.  Five
tab-separated columns:

.. code-block:: text

   # alias  ssh_target  runner_label  runner_name_base  lg_direct_env_path
   bq       bq          hw-bq         bq                /home/tcollins/dev/dt-fix/lg_adrv9371_zc706_tftp.yaml
   mini2    mini2       hw-mini2      mini2

Columns:

* **alias** — short name used on the command line as an optional filter.
* **ssh_target** — SSH host (name or ``user@host``) used by ``ssh``/``scp``.
* **runner_label** — label attached to every runner on this host (e.g.
  ``hw-bq``); used as the ``runs-on`` label in per-leg jobs.
* **runner_name_base** — base for the runner name; the script appends
  ``-<scope-slug>`` to produce the final name (e.g. ``bq-org-analogdevicesinc``).
* **lg_direct_env_path** — (optional) path on the *remote* host to write as
  ``LG_DIRECT_ENV=<path>`` in the runner's ``.env`` file.  Omit for
  coordinator-only runners.

For each host × scope pair the script installs a runner under
``~/actions-runner-<scope-slug>/``, configures it with
``--labels "self-hosted,<runner_label>"``, and starts a ``systemd`` service.

Worked example
~~~~~~~~~~~~~~

.. code-block:: bash

   .github/scripts/register-hw-runners.sh \
       --hosts-file ./hosts.tsv \
       --scopes org:analogdevicesinc,repo:tfcollins/labgrid-plugins,repo:tfcollins/vrt49 \
       bq mini2      # optional: restrict to these two hosts only

After registration the script waits 60 seconds and queries GitHub to confirm
every runner is ``online``.

Cross-reference: :doc:`hardware-ci-runner-setup` documents the additional
Vivado/``xsdb`` requirements for no-os flash-mode runners.


Runner labels and cross-org scope
----------------------------------

Each per-board leg in the reusable workflows pins its runner with:

.. code-block:: yaml

   runs-on: [self-hosted, "${{ matrix.runner || inputs.runner-label }}"]

The ``matrix.runner`` value comes from the place's ``runner`` tag on the
coordinator — it is the label of the GitHub Actions runner co-located with
that board.  When a place carries no ``runner`` tag the workflow falls back
to its ``runner-label`` input (the ``hw-request`` / ``noos-hw-request`` /
``hw-matrix-v2`` workflows), or to ``dynamic_runner_label_default`` in
``hw-matrix.yml``'s dynamic mode.

**Cross-org consumers** must register the lab runners on their repo or org
scope using ``register-hw-runners.sh --scopes``.  If no runner carrying the
required label is online in the consuming repo's scope, the job will queue
indefinitely rather than fail immediately — use ``RUNNER_QUERY_TOKEN`` in
``hw-matrix.yml`` (``dynamic_mode``) to enable availability filtering that
skips legs with no reachable runner.
