Web Dashboard
=============

The web dashboard provides a real-time view of the labgrid coordinator's state,
including exporters, places, resources, and reservations.

Access the dashboard at ``http://localhost:3000`` after starting the Docker
compose stack (see :doc:`coordinator`).

Dashboard Page
--------------

The main dashboard shows:

- **Summary cards**: Total places, acquired places, total resources, available
  resources
- **Exporter health grid**: A card for each connected exporter showing its
  resource groups and availability status (green/yellow/red badges)

.. image:: /_static/screenshots/dashboard.png
   :alt: Dashboard overview showing summary statistics and exporter health cards
   :width: 100%

Places Page
-----------

The places page provides full place management:

- **Table view**: Name, tags, match count, acquired by, and action buttons
- **Expandable rows**: Click a row to see full match patterns, acquired
  resources, aliases, and comments
- **Actions**: Acquire/Release toggle, delete
- **Create Place**: Modal dialog for creating new places

.. image:: /_static/screenshots/places.png
   :alt: Places table with tags, match counts, and action buttons
   :width: 100%

Clicking a row expands the detail panel, showing match patterns and acquired
resources:

.. image:: /_static/screenshots/places-detail.png
   :alt: Place detail panel showing match patterns and acquired resources
   :width: 100%

Resources Page
--------------

The resources page shows all resources from all connected exporters:

- **Filterable table**: Exporter, group, class, name, availability, acquired by
- **Filter controls**: Dropdown filters for exporter and class, toggle for
  available-only
- **Real-time updates**: Resource availability changes are reflected immediately
  via WebSocket

.. image:: /_static/screenshots/resources.png
   :alt: Resource table with exporter, group, class, and availability filters
   :width: 100%

Reservations Page
-----------------

The reservations page manages resource reservations:

- **Table**: Token, owner, state, priority, filters, allocations
- **Create Reservation**: Modal form with tag-based filter configuration and
  priority setting
- **Cancel**: Cancel active reservations

.. image:: /_static/screenshots/reservations.png
   :alt: Reservation management page
   :width: 100%

Real-Time Updates
-----------------

The dashboard connects to the API via WebSocket at ``/api/ws``. All state
changes from the coordinator (place updates, resource availability changes,
exporter connect/disconnect) are streamed to the browser in real time.

If the WebSocket connection drops, the dashboard automatically reconnects
after 3 seconds.

Color Mode
----------

The dashboard supports both light and dark modes. Toggle via the icon button
in the top-right header. The color scheme uses Analog Devices brand colors
(ADI blue ``#0071ba``) throughout.

.. image:: /_static/screenshots/dashboard-dark.png
   :alt: Dashboard in dark mode with ADI brand colors
   :width: 100%
