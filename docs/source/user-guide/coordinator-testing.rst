Running Coordinator Tests
=========================

Exercise ``tests/coordinator/`` against a running coordinator. The
suite splits into a smoke tier (no hardware, runs always) and a
hardware tier (real boards, gated by ``--run-hardware``).

Prerequisites
-------------

- Dev install: ``pip install -e ".[dev]"`` in this repo
- ``LG_COORDINATOR`` set to ``host:port`` of the coordinator gRPC
  endpoint (e.g. ``10.0.0.41:20408``). ``host`` alone uses the default
  port
- For the hardware tier, at least one exporter published on the
  coordinator — either already running or spawnable by the fixture
  (see below)

Smoke Tier
----------

Run against a local Docker coordinator (see :doc:`coordinator`):

.. code-block:: bash

   cd coordinator
   docker compose up -d
   cd ..
   pytest -v tests/coordinator/test_coordinator_integration.py

The smoke tier spawns its own mock exporter, verifies every plugin
resource class round-trips through the coordinator, and tears down.
No ``--run-hardware`` flag needed.

Hardware Tier: Three Exporter Modes
-----------------------------------

The ``remote_exporters`` fixture in ``tests/coordinator/conftest.py``
picks one of three modes based on the environment. Pick the row that
matches your setup:

.. list-table::
   :header-rows: 1
   :widths: 20 40 40

   * - Mode
     - Env vars
     - Use when
   * - Discovery
     - *(none)*
     - An exporter is already running on the target host (systemd,
       Jenkins, long-lived ``nohup``). Fastest loop; the fixture only
       acquires the place.
   * - Multi-spawn
     - ``LG_EXPORTERS_CONFIG=<yaml>``
     - You want the test session to own the exporter lifecycle.
       Exporters spawn at session setup, tear down at session teardown.
   * - Single-spawn
     - ``LG_EXPORTER_HOST``, ``LG_EXPORTER_NAME``,
       ``LG_EXPORTER_YAML`` (all three)
     - One-off bring-up of a single exporter.

In every mode, ``--lg-config <env.yaml>`` binds the coordinator's
places to labgrid ``Target`` objects for the tests to consume. The env
yaml and the exporter yaml are **different files** (see below).

Discovery mode
~~~~~~~~~~~~~~

.. code-block:: bash

   LG_COORDINATOR=10.0.0.41 \
   pytest -v tests/coordinator/test_soc_strat_coordinator.py \
       --run-hardware \
       --lg-config tests/coordinator/env_remote_mini2.yaml

The fixture queries the coordinator for published places
(``labgrid-client -x $LG_COORDINATOR places``) and acquires any that
the env yaml references.

Multi-spawn mode
~~~~~~~~~~~~~~~~

.. code-block:: bash

   LG_COORDINATOR=10.0.0.41 \
   LG_EXPORTERS_CONFIG=tests/coordinator/exporters_all.yaml \
   pytest -v tests/coordinator/ \
       --run-hardware \
       --lg-config tests/coordinator/env_remote_all.yaml

The fixture spawns each exporter listed in
``tests/coordinator/exporters_all.yaml``. Hosts are reached over SSH
unless the name resolves to the test runner itself, in which case the
exporter runs locally.

Single-spawn mode
~~~~~~~~~~~~~~~~~

.. code-block:: bash

   LG_COORDINATOR=10.0.0.41 \
   LG_EXPORTER_HOST=mini2 \
   LG_EXPORTER_NAME=mini2 \
   LG_EXPORTER_YAML=examples/lg_ad9081_zcu102_mini2_exporter.yaml \
   pytest -v tests/coordinator/test_soc_strat_coordinator.py \
       --run-hardware \
       --lg-config tests/coordinator/env_remote_mini2.yaml

All three ``LG_EXPORTER_*`` vars must be set — there are no defaults.

Env YAML vs. Exporter YAML
--------------------------

Two YAML files bracket every hardware test run, and they serve
opposite sides of the coordinator:

.. list-table::
   :header-rows: 1
   :widths: 25 25 50

   * - File
     - Example
     - Consumed by
   * - Exporter YAML
     - ``examples/lg_ad9081_zcu102_mini2_exporter.yaml``
     - The ``labgrid-exporter`` process on the lab host. Publishes
       resources to the coordinator.
   * - Env YAML
     - ``tests/coordinator/env_remote_mini2.yaml``
     - The test runner. Binds a ``RemotePlace`` name to a labgrid
       ``Target`` with drivers.

They pair up by place name. Example:

.. code-block:: text

   exporters_all.yaml                  env_remote_all.yaml
     - name: mini2       ────────────►   targets:
       host: mini2                         mini2:
       yaml: lg_ad9081_zcu102_               resources:
             mini2_exporter.yaml               RemotePlace:
                                                 name: mini2

Troubleshooting
---------------

``<place> place not available in this session``
    The fixture built the set of available places but this one is not
    in it. Run ``labgrid-client -x $LG_COORDINATOR places``. If the
    place is missing, no exporter is publishing it — start one (see
    :doc:`exporter-deployment`) or switch to multi-spawn/single-spawn
    mode. If the place is present, confirm the ``RemotePlace.name`` in
    your env yaml matches it.

``timeout while waiting for option 'purge'``
    The running ``labgrid-exporter`` spawned ``ser2net`` 4.6.0 instead
    of 4.6.1. See :ref:`ser2net-install`.

``exporter '<name>' never appeared in coordinator within 45s``
    Multi-spawn mode waited for registration and timed out. Check the
    exporter's stdout on the target host, confirm SSH works
    non-interactively from the test runner, and confirm the exporter
    yaml path exists on the remote.
