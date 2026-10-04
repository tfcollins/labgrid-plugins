Prism reporting
===============

``labgrid-plugins`` supports two distinct ways to report hardware-test results
to Prism:

#. the reusable workflows' built-in **JUnit uploader**; and
#. the optional ``pytest-prism`` **enriched reporter**, which discovers the
   labgrid session hook shipped by this package.

Choose one upload owner for each test leg. Enabling both direct
``pytest-prism`` upload and the workflow's ``prism-upload`` step creates two
Prism runs for the same pytest invocation.

Feature matrix
--------------

.. list-table::
   :header-rows: 1
   :widths: 24 34 42

   * - Capability
     - Workflow JUnit uploader
     - ``pytest-prism`` enriched reporter
   * - JUnit test results
     - Yes
     - Yes
   * - Place/board/carrier tags
     - Yes, from the workflow leg
     - Yes, from the labgrid session hook
   * - Allowlisted coordinator metadata
     - No
     - Yes
   * - Pre/post/diff dmesg
     - No
     - Yes, for ``ip:`` IIO URIs reachable over SSH
   * - Labgrid console logs
     - No
     - Yes, by copying files already produced by ``pytest --lg-log``
   * - Consumer renderers and measurements
     - JUnit properties only
     - Yes, through ``pytest-prism``
   * - Prism dependency in the test environment
     - No
     - Yes

Workflow JUnit upload
---------------------

The ``hw-request.yml`` and ``matlab-hw-request.yml`` reusable workflows can
upload each leg's JUnit after pytest exits. Set ``prism-upload: true``, provide
``prism-project``, and set ``PRISM_URL`` as a repository variable (or use the
``prism-url`` input). Pass credentials explicitly from the caller:

.. code-block:: yaml

   jobs:
     hardware:
       uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@v3.5
       with:
         coordinator: ${{ vars.LG_COORDINATOR }}
         test-root: test
         prism-upload: true
         prism-project: my-project
       secrets:
         PRISM_API_TOKEN: ${{ secrets.PRISM_API_TOKEN }}
         PRISM_EMAIL: ${{ secrets.PRISM_EMAIL }}
         PRISM_PASSWORD: ${{ secrets.PRISM_PASSWORD }}

The built-in uploader accepts either ``PRISM_API_TOKEN`` as bearer
authentication or ``PRISM_EMAIL`` plus ``PRISM_PASSWORD`` for login-based
deployments. Custom uploaders receive the same values.
Cross-organization reusable-workflow calls must pass these secrets explicitly:
``secrets: inherit`` does not cross organization boundaries.

The upload step is ``continue-on-error``. A Prism outage does not change the
hardware leg's result. The built-in path uploads JUnit and run tags only; it
does **not** upload the labgrid session-hook files. Use ``prism-upload-cmd`` to
replace it with a consumer-owned uploader when needed. The command receives
``PRISM_URL``, ``PRISM_API_TOKEN``, ``PRISM_EMAIL``, ``PRISM_PASSWORD``,
``PRISM_PROJECT``, ``PRISM_JUNIT``, ``PRISM_RUN_NAME``, ``PRISM_BOARD``,
``PRISM_CARRIER``, and ``PRISM_PLACE``.

Enriched pytest reporting
-------------------------

Install ``pytest-prism`` from the Prism repository alongside
``labgrid-plugins``. ``pytest-prism`` is not a dependency of this package and,
until it has a published package release, should be installed from its source
subdirectory. Pin a reviewed tag or commit rather than mutable repository
HEAD; the following commit is the contract validated for this integration:

.. code-block:: bash

   python -m pip install \
     "pytest-prism @ git+https://github.com/tfcollins/prism.git@f6bc1cf3bec925ddd7956d9a0e5617dc885385d1#subdirectory=clients/python-pytest"

Installing both distributions registers
``adi_lg_plugins.prism:LabgridSessionHook`` through the
``pytest_prism.session_hooks`` entry-point group. No additional plugin import
is needed.

Local artifact bundle
~~~~~~~~~~~~~~~~~~~~~

This command writes JUnit, terminal output, run metadata, labgrid metadata,
dmesg, and console artifacts beneath ``./prism-out`` without uploading them:

.. code-block:: bash

   export PRISM_LABGRID_LOG_DIR="$PWD/prism-console"
   pytest test/hw \
     --lg-log "$PRISM_LABGRID_LOG_DIR" \
     --prism-report \
     --prism-out ./prism-out \
     --prism-labgrid-place "$LG_PLACE" \
     --prism-dmesg-via auto

The output directory must be new or empty. Choose a per-run path, or pass
``--prism-out-overwrite`` when replacing a known disposable directory.

pytest-prism owns JUnit output while enabled: it sets the destination to
``<prism-out>/junit.xml``, overriding a path supplied with ``--junitxml``.
Reusable hardware workflows often expect another path such as ``$JUNIT`` or
``results-*.xml``. Stage the generated file after pytest while preserving the
test exit status:

.. code-block:: bash

   set +e
   pytest test/hw --prism-report --prism-out "$RUNNER_TEMP/prism-out" ...
   pytest_status=$?
   set -e
   stage_status=0
   cp "$RUNNER_TEMP/prism-out/junit.xml" "$JUNIT" || stage_status=$?
   if [ "$pytest_status" -ne 0 ]; then
     exit "$pytest_status"
   fi
   exit "$stage_status"

Use an ``if: always()`` staging step instead when pytest and publication are
separate workflow steps. Without this staging, existing JUnit publication and
the built-in workflow uploader may not find their expected file.

Pass the place explicitly. The hook deliberately does not fall back to
``LG_PLACE`` because a stale environment value could associate results with
the wrong reservation.

Direct upload
~~~~~~~~~~~~~

To let ``pytest-prism`` upload the enriched bundle itself, provide an explicit
output directory, Prism URL, project, and either a token or login credentials:

.. code-block:: bash

   pytest test/hw \
     --prism-report \
     --prism-out "$RUNNER_TEMP/prism-out" \
     --prism-out-overwrite \
     --prism-url "$PRISM_URL" \
     --prism-project "$PRISM_PROJECT" \
     --prism-token "$PRISM_TOKEN" \
     --prism-run-name "$GITHUB_WORKFLOW-$GITHUB_RUN_NUMBER" \
     --prism-tag "git-sha=$GITHUB_SHA" \
     --prism-labgrid-place "$LG_PLACE" \
     --prism-dmesg-via auto

For this direct path, ``pytest-prism`` uses ``PRISM_TOKEN`` rather than the
workflow uploader's ``PRISM_API_TOKEN`` name. It also accepts ``PRISM_EMAIL``
and ``PRISM_PASSWORD``. Use ``--prism-fail-on-upload-error`` when upload
failure should fail pytest; the default preserves the local bundle and keeps
the test result.

Use the explicit ``--prism-report`` flag. The current Prism client resolves
most ``PRISM_*`` settings from the environment, but CLI activation is the
qualified path for this integration.

Captured metadata and artifacts
-------------------------------

``session/labgrid/metadata.json`` contains only the reporting contract:

* selected place;
* whether a coordinator was configured;
* the basename of ``LG_ENV``;
* a sanitized ``ip:HOST`` IIO URI (credentials, query, and fragment removed);
* acquisition state and exporter names; and
* allowlisted tags: ``board-location``, ``boot-strategy``, ``carrier``,
  ``daughter-board``, ``disabled``, ``hdl-config``, and ``runner``.

Raw resource dictionaries, coordinator comments, coordinator addresses, and
unknown tags are not reported. If coordinator discovery fails, pytest
continues and metadata records ``metadata_status=unavailable``.

Dmesg modes
~~~~~~~~~~~

``--prism-dmesg-via auto``
   Attempt bounded pre-test and post-test dmesg over batch-mode SSH. If SSH is
   unavailable and copied console files exist, run metadata records
   ``fallback=console_logs``.

``--prism-dmesg-via ssh``
   Attempt SSH dmesg only. The host comes from a validated ``IIO_URI=ip:HOST``.
   The default user is ``root``; override it with
   ``--prism-dmesg-ssh-user`` and optionally provide
   ``--prism-dmesg-ssh-key``.

``--prism-dmesg-via console``
   Do not run dmesg over SSH. Copy existing labgrid console logs. This does not
   execute ``dmesg`` through the serial console.

``--prism-dmesg-via none``
   Disable dmesg collection. Console files are still copied when
   ``PRISM_LABGRID_LOG_DIR`` is configured. Omit that environment variable for
   metadata-only reporting.

Successful SSH capture produces ``dmesg_pre.log``, ``dmesg_post.log``, and
``dmesg_diff.log``. The diff preserves line order and repeated messages, and
handles a wrapped kernel ring buffer by retaining unmatched post-test output.
Each dmesg artifact is limited to the newest 4 MiB.

Console capture
~~~~~~~~~~~~~~~

The hook never opens another console process. A second reader could contend
with the test and cannot reconstruct bytes already consumed during boot.
Instead, configure labgrid's own reporter and point the Prism hook at the same
directory:

.. code-block:: bash

   export PRISM_LABGRID_LOG_DIR="$RUNNER_TEMP/lg-console"
   pytest --lg-log "$PRISM_LABGRID_LOG_DIR" ...

At session end, regular files named ``console_*`` are copied into the Prism
bundle and given a ``.log`` suffix when needed. Symlinks are ignored. Capture
is bounded to 16 files, 4 MiB per file, and 16 MiB in aggregate; when a file is
too large, its newest bytes are retained.

Only output consumed while pytest's labgrid console reporter is active can be
captured. If another workflow step boots the board before pytest, that step
must preserve and stage its own serial log.

Failure and security behavior
-----------------------------

* ``--prism-no-labgrid`` disables labgrid metadata, dmesg, and console
  collection while leaving generic pytest-prism reporting available.
* Hook failures are non-fatal by default and are recorded by pytest-prism.
  Add ``--prism-fail-on-hook-error`` for a strict reporting gate.
* SSH runs with ``BatchMode=yes`` and a bounded connection/process timeout; it
  does not prompt for credentials or alter host-key policy.
* Treat the entire report as sensitive. ``terminal.log``, captured JUnit
  output, renderer artifacts, dmesg, console logs, and metadata can expose
  credentials, commands, lab topology, network identities, or DUT data.
  Upload only to a Prism project with appropriate access controls and retention
  policy, and keep secret values out of test output.
* Use one pytest-prism writer per hardware leg. Multi-process/xdist ownership
  of one report directory is not qualified by this integration.

Troubleshooting
---------------

No ``session/labgrid`` directory
   Confirm both packages are installed in the interpreter that runs pytest,
   pass ``--prism-report``, and inspect the entry point with
   ``python -c 'from importlib.metadata import entry_points; print(entry_points(group="pytest_prism.session_hooks"))'``.

``no explicit place selected``
   Pass ``--prism-labgrid-place "$LG_PLACE"``. Merely exporting ``LG_PLACE``
   does not activate the hook for that place.

No dmesg files
   Confirm ``IIO_URI`` uses ``ip:HOST``, SSH is non-interactive for the selected
   user/key, and the target permits ``dmesg``. Errors appear in run metadata.

No console files
   Set ``PRISM_LABGRID_LOG_DIR`` to the exact path passed to ``pytest --lg-log``
   and ensure the tests actually read from a labgrid console driver.

Duplicate Prism runs
   Do not combine direct pytest-prism upload with workflow
   ``prism-upload: true``. Disable one upload owner.

Missing workflow JUnit
   pytest-prism writes ``<prism-out>/junit.xml`` regardless of ``--junitxml``.
   Copy that file to the workflow's expected path after pytest, including on a
   failing test run.

Output directory is not empty
   Select a unique ``--prism-out`` for each run, clean the directory first, or
   pass ``--prism-out-overwrite`` only for a known disposable path.
