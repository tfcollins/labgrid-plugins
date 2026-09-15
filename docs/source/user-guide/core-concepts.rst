Core Concepts
=============

Fundamental building blocks and architecture of the ``labgrid-plugins`` ecosystem.

.. grid:: 1 2 2 2
   :gutter: 3
   :class-container: sd-mb-4

   .. grid-item-card:: Drivers
      :link: drivers
      :link-type: doc

      Low-level hardware control, protocol implementations, power switches, and flashers.

   .. grid-item-card:: Resources
      :link: resources
      :link-type: doc

      Hardware and network descriptor configuration parameters.

   .. grid-item-card:: Strategies
      :link: strategies
      :link-type: doc

      State machines orchestrating boot, staging, flashing, and recovery workflows.

   .. grid-item-card:: Execution Topology
      :link: access-topology
      :link-type: doc

      Architectural separation between client control logic and exporter hardware access.

   .. grid-item-card:: Common Use Cases
      :link: examples
      :link-type: doc

      Reference configuration recipes and Python examples for typical tasks.

.. toctree::
   :maxdepth: 2
   :hidden:

   drivers
   resources
   strategies
   access-topology
   examples
