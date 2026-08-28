Coordinator Setup
=================

The labgrid coordinator provides centralized management of hardware resources
across multiple exporter hosts. The labgrid-plugins project includes a
Docker-based deployment of the coordinator, a REST/WebSocket API bridge, and a
web dashboard.

Architecture
------------

.. mermaid::

   graph LR
       subgraph Docker ["Docker Compose"]
           C[Coordinator<br/>gRPC :20408]
           A[API Server<br/>FastAPI :8000]
           W[Web Dashboard<br/>nginx :3000]
       end

       E1[Exporter Host 1] -->|gRPC ExporterStream| C
       E2[Exporter Host 2] -->|gRPC ExporterStream| C
       A -->|gRPC ClientStream| C
       W -->|/api proxy| A
       B[Browser] -->|HTTP + WebSocket| W

.. image:: /_static/screenshots/dashboard.png
   :alt: Coordinator web dashboard
   :width: 100%

The stack consists of three Docker services:

- **Coordinator**: The labgrid coordinator gRPC server. Tracks places,
  resources, exporters, and reservations. Persists state to a Docker volume.
- **API**: A FastAPI server that connects to the coordinator as a gRPC client,
  caches all state in memory, and exposes a REST + WebSocket API.
- **Web**: An nginx server hosting the React dashboard and proxying ``/api``
  requests to the API service.

Exporters run on physical hosts (not in Docker) and connect to the coordinator
over the network.

Prerequisites
-------------

- Docker and Docker Compose
- Network connectivity between exporter hosts and the coordinator

Quick Start
-----------

.. code-block:: bash

   cd coordinator
   docker compose up -d

This starts all three services:

- Coordinator at ``localhost:20408``
- API at ``localhost:8000``
- Web dashboard at ``http://localhost:3000``

Configuration
-------------

Copy ``.env.example`` to ``.env`` and adjust ports if needed:

.. code-block:: bash

   # coordinator/.env
   LG_COORDINATOR_PORT=20408
   API_PORT=8000
   WEB_PORT=3000

Connecting Exporters
--------------------

From any host with labgrid and the ADI plugins installed:

.. code-block:: bash

   labgrid-exporter -c <coordinator-host>:20408 -n my-exporter resources.yaml

Or set the environment variable:

.. code-block:: bash

   export LG_COORDINATOR=<coordinator-host>:20408
   labgrid-exporter -n my-exporter resources.yaml

See :doc:`exporter-setup` for resource YAML configuration details.

Testing Without Hardware
------------------------

A mock exporter is included for development and testing:

.. code-block:: bash

   cd coordinator
   docker compose up -d  # starts coordinator, api, web

   # Run the mock exporter (connects to coordinator)
   cd mock-exporter
   python mock_exporter.py -c localhost:20408

The mock exporter registers fake VCU118 and Raspberry Pi resources, allowing
you to test the full dashboard workflow without any hardware.

API Reference
-------------

The API server exposes the following endpoints:

**Health**

- ``GET /api/health`` - Coordinator connectivity status

**Places**

- ``GET /api/places`` - List all places
- ``GET /api/places/{name}`` - Get place details
- ``POST /api/places`` - Create a place (body: ``{"name": "..."}``\ )
- ``DELETE /api/places/{name}`` - Delete a place
- ``POST /api/places/{name}/acquire`` - Acquire a place
- ``POST /api/places/{name}/release`` - Release a place
- ``PUT /api/places/{name}/tags`` - Set tags (body: ``{"tags": {...}}``\ )
- ``PUT /api/places/{name}/comment`` - Set comment
- ``POST /api/places/{name}/matches`` - Add resource match
- ``DELETE /api/places/{name}/matches`` - Remove resource match
- ``GET /api/places/{name}/env-yaml`` - Render a labgrid client env YAML for the
  place and return it as a downloadable ``application/x-yaml`` attachment. Query
  param ``tier`` (one of ``shell`` | ``drivers`` | ``boot``, default ``shell``)
  selects how much of the stack to emit; the ``boot`` tier resolves the place's
  boot strategy. Returns ``404`` for an unknown place and ``422`` for an invalid
  tier. Consumed by the ``hw-matrix-v2`` workflow's env-render step.

**Matching / Catalog**

- ``GET /api/match`` - Decide whether a part can be satisfied by a live board and
  how to provision it. Query params: ``part`` (required, e.g. ``adrv9002``),
  ``carrier`` (optional FPGA carrier), ``bootfile`` (optional image/version pin),
  and ``mode`` (``uri`` | ``flash``, default ``uri``). It only decides
  satisfiability and returns the provisioning plan; it never acquires or
  reserves. Consumed by the ``hw-request``, ``noos-hw-request``, and
  ``hw-matrix-v2`` workflows. Returns a ``MatchResult``:

  .. code-block:: json

     {
       "satisfiable": true,
       "reservation_filter": {"daughter-board": "adrv9002"},
       "image": "2023_R2_P1",
       "strategy": "BootFPGASoC",
       "place": "my-zcu102",
       "runner": "hw-runner-1",
       "flash": null,
       "reason": null
     }

  ``satisfiable`` is ``false`` (with a ``reason``) for an unknown part, a part
  with no ``flash`` support in ``mode=flash``, an invalid carrier, or no live
  place. ``place`` / ``runner`` are an informational free candidate; ``flash``
  carries the no-os flash metadata only when ``mode=flash``.

- ``GET /api/catalog`` - Return the board catalog (``part`` -> default image,
  aliases, optional ``flash`` block, and valid carriers). Consumed by the
  ``request-matrix`` discovery step.

  .. code-block:: json

     {
       "boards": {
         "adrv9002": {
           "image": "2023_R2_P1",
           "aliases": [],
           "flash": null,
           "carriers": {"zcu102": {}}
         }
       }
     }

**Resources**

- ``GET /api/resources`` - List all resources (filters: ``?exporter=``, ``?cls=``, ``?avail=``\ )
- ``GET /api/exporters`` - List exporters with grouped resources

**Reservations**

- ``GET /api/reservations`` - List all reservations
- ``POST /api/reservations`` - Create reservation
- ``DELETE /api/reservations/{token}`` - Cancel reservation
- ``POST /api/reservations/{token}/poll`` - Poll reservation status

**Auth**

- ``POST /api/auth/bootstrap`` - One-time creation of the first admin account
  (body: ``{"token": "...", "username": "...", "password": "..."}``\ ). Only
  works while zero users exist; see :doc:`web-ui-auth`.
- ``POST /api/auth/login`` - Local username/password login (body:
  ``{"username": "...", "password": "..."}``\ ). Sets the session cookie.
- ``POST /api/auth/logout`` - Clear the session
- ``GET /api/auth/me`` - Current authenticated user (``{"username": "...", "role": "..."}``\ )
- ``GET /api/auth/oidc/login`` - Redirect to the configured OIDC provider (``404`` if OIDC is disabled)
- ``GET /api/auth/oidc/callback`` - OIDC redirect target; exchanges the code and sets the session cookie

**Users** (admin role required)

- ``GET /api/users`` - List all users
- ``POST /api/users`` - Create a user (body: ``{"username": "...", "password": "...", "role": "admin"|"user"}``\ )
- ``DELETE /api/users/{user_id}`` - Delete a user
- ``PUT /api/users/{user_id}/password`` - Set a user's password
- ``PUT /api/users/{user_id}/role`` - Change a user's role
- ``PUT /api/users/{user_id}/disabled`` - Enable/disable a user

See :doc:`web-ui-auth` for the full authentication and user-management guide.

**WebSocket**

- ``WS /api/ws`` - Real-time updates. On connect, receives full state snapshot.
  Subsequent messages are incremental updates:

  .. code-block:: text

     {"type": "place_update", "data": {...}}
     {"type": "resource_delete", "data": {"exporter": "...", "group": "...", "name": "..."}}
