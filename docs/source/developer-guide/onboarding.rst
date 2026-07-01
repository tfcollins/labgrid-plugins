Developer Onboarding
====================

The front door for contributing to **labgrid-plugins** itself: clone the repo, install
the dev environment, learn the day-to-day ``nox`` loop, understand how the plugins register,
and add a driver, resource, or strategy. For the design and component model read
:doc:`architecture`; for the bare lint/test/doc commands see :doc:`contributing`.

.. admonition:: Three different "onboardings" — don't confuse them
   :class: tip

   - **This page** — working *inside* the ``labgrid-plugins`` package.
   - :doc:`../user-guide/onboarding-a-consumer-repo` — wiring *another* repo onto the
     hardware-CI flow.
   - :doc:`../user-guide/onboarding-a-lab-host` — bringing *hardware* online to serve those
     consumers.

Prerequisites
-------------

- **Python 3.10+** and **git**.
- **uv** (recommended) — the ``nox`` automation uses the uv backend.
- A **C toolchain** only if you need the ``kuiper`` extra (it builds ``pytsk3`` for the
  ``KuiperDLDriver``); everything else installs as pure Python.

Step 1 — clone and install
--------------------------

.. code-block:: bash

   git clone https://github.com/tfcollins/labgrid-plugins.git
   cd labgrid-plugins
   pip install -e ".[dev,docs]"      # editable install with dev + docs tooling
   pip install -e ".[kuiper]"        # optional: adds pytsk3 for KuiperDLDriver

Prefer an isolated environment:

.. code-block:: bash

   uv venv venv --python 3.10 && source venv/bin/activate
   uv pip install -e ".[dev,docs]"

Step 2 — the repo at a glance
-----------------------------

The repository is more than the package — two sibling subprojects carry their **own**
toolchains and are not exercised by the top-level ``nox``:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Path
     - What lives there
   * - ``adi_lg_plugins/drivers``
     - hardware control (power, shell, JTAG, TFTP, downloads, mass storage)
   * - ``adi_lg_plugins/resources``
     - passive config containers (outlets, device paths, release info)
   * - ``adi_lg_plugins/strategies``
     - boot-workflow state machines (SoC, FPGA fabric, SelMap, RPi, SSH, TFTP)
   * - ``adi_lg_plugins/tools``
     - the ``adi-lg`` CLI (Click), the ``adi-lg-mcp`` server (FastMCP), utilities
   * - ``adi_lg_plugins/hw_ci``
     - hardware-CI helpers + the consumer ``onboarding_templates/``
   * - ``coordinator/``
     - **sibling** — Docker stack: coordinator, FastAPI bridge (own ``pyproject.toml`` +
       tests under ``coordinator/api/tests/``), React/Vite dashboard
   * - ``exporter_configs/``
     - **sibling** — exporter YAML templates, ``validate.py``, and JSON schemas
   * - ``tests/`` / ``docs/``
     - package tests and this Sphinx documentation

See :doc:`architecture` "Directory Structure" for the file-level layout.

Step 3 — the development loop
-----------------------------

``nox`` (uv backend) is the canonical entry point:

.. code-block:: bash

   nox                          # default sessions: lint, tests, docs (NOT typecheck)
   nox -s lint                  # ruff check + format check
   nox -s format                # auto-fix: ruff format + ruff check --fix
   nox -s tests                 # run pytest
   nox -s tests -- -k test_name # a single test
   nox -s docs                  # build the Sphinx docs
   nox -s typecheck             # opt-in: ty static check (baseline not yet clean)

Or run the tools directly: ``ruff check . --fix && ruff format .`` and ``pytest tests/``.

**Style:** ruff with line length 100, double quotes, spaces, rules ``E/W/F/I/UP/B`` (``E501``
ignored). **Types:** ``ty`` intentionally ignores ``unresolved-attribute`` and
``too-many-positional-arguments`` — labgrid injects binding attributes at bind time and
``@step()`` mangles signatures, so don't "fix" those by annotating bindings.

Step 4 — how the plugins register (read once)
---------------------------------------------

This is the one piece of framework wiring you must understand.

**Upstream labgrid has no entry-point auto-discovery** (that was a fork-only feature).
Registration happens by **import side effect** instead:

#. ``import adi_lg_plugins`` runs ``adi_lg_plugins/__init__.py``, which imports the
   ``drivers``, ``resources``, and ``strategies`` subpackages.
#. Each subpackage ``__init__`` imports its individual modules (a ``_MODULES`` tuple) so the
   ``@target_factory.reg_driver`` / ``@reg_resource`` decorators run and register the class
   by name. A module whose optional dependency is missing on this host logs a warning and is
   skipped rather than breaking the whole import.
#. Therefore **every labgrid env YAML that names an ADI component must carry**
   ``imports: [adi_lg_plugins]`` (or the consuming process must ``import adi_lg_plugins``).

.. admonition:: The entry points in ``pyproject.toml`` are not discovery
   :class: warning

   ``[project.entry-points."labgrid.drivers"]`` (and ``.resources`` / ``.strategies``) are
   kept as a manifest/reference, but upstream labgrid never reads them. Adding an entry there
   alone does **not** register a component — the module must be imported (step 2). The
   fork-only ``never_retry`` strategy decorator is shimmed in
   ``adi_lg_plugins/strategies/_compat.py``.

Step 5 — add a component
------------------------

For a new driver, resource, or strategy:

#. **Create the class** in the matching subdirectory, following the existing files — use
   ``@attr.s(eq=False)`` and the registration decorator (``@target_factory.reg_driver`` for
   drivers and strategies, ``@target_factory.reg_resource`` for resources). See
   :doc:`architecture` "Extensibility" for full templates.
#. **Wire it into discovery** — add the module name to the subpackage's ``_MODULES`` import
   list so ``import adi_lg_plugins`` registers it (Step 4).
#. **Add the entry point** in ``pyproject.toml`` under the matching
   ``[project.entry-points."labgrid.*"]`` section (convention/manifest).
#. **Add tests** in ``tests/`` — and opt new unit tests into CI (next step) if they should
   run there.

Step 6 — testing
----------------

Two categories live in ``tests/``:

- **Unit/integration** — run without hardware (``test_cli.py``, ``test_mcp.py``,
  ``test_fabric_strat.py``, …): ``pytest tests/``.
- **Hardware** — marked ``@pytest.mark.hardware``; require ``--run-hardware`` and a labgrid
  config via ``--lg-config``. Some modules (``test_soc_strat*.py``, ``test_rpi_hw.py``) are
  excluded from default collection in ``conftest.py`` because they crash without ``--lg-env``.

**CI** (``.github/workflows/tests.yml``) runs a Python 3.10/3.11/3.12 matrix: ``nox -s lint``
(blocking) → ``nox -s typecheck`` (``continue-on-error`` / informational) → ``nox -s tests --
tests/test_cli.py tests/test_mcp.py``. A new unit test must be **added to that list** to be
exercised by CI.

Step 7 — submit changes
-----------------------

Branch, make ``nox -s lint`` and ``nox -s tests`` green locally, then open a PR; CI re-runs
the same gates.

.. note::

   The project's license is **unresolved** — ``pyproject.toml`` declares LGPL-2.1-or-later
   while ``LICENSE``/``README`` say Apache 2.0. **Ask before adding license headers** to new
   files.

See also
--------

- :doc:`architecture` — component model, bindings, lifecycle, extensibility.
- :doc:`contributing` — the condensed command reference.
- :doc:`../user-guide/onboarding-a-consumer-repo` / :doc:`../user-guide/onboarding-a-lab-host`
  — the consumer- and lab-side onboarding flows.
