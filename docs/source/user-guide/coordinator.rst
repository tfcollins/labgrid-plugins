Coordinator Setup
=================

The labgrid coordinator provides centralized management of hardware resources
across multiple exporter hosts. The adi-labgrid-plugins project includes a
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

**Resources**

- ``GET /api/resources`` - List all resources (filters: ``?exporter=``, ``?cls=``, ``?avail=``\ )
- ``GET /api/exporters`` - List exporters with grouped resources

**Reservations**

- ``GET /api/reservations`` - List all reservations
- ``POST /api/reservations`` - Create reservation
- ``DELETE /api/reservations/{token}`` - Cancel reservation
- ``POST /api/reservations/{token}/poll`` - Poll reservation status

**WebSocket**

- ``WS /api/ws`` - Real-time updates. On connect, receives full state snapshot.
  Subsequent messages are incremental updates:

  .. code-block:: json

     {"type": "place_update", "data": {...}}
     {"type": "resource_delete", "data": {"exporter": "...", "group": "...", "name": "..."}}
