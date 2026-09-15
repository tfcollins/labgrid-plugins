CLI & Tooling
=============

Command-line interfaces, LLM integration, and runtime IP deployment tools.

.. grid:: 1 2 2 2
   :gutter: 3
   :class-container: sd-mb-4

   .. grid-item-card:: Command Line Interface
      :link: cli
      :link-type: doc

      Execute strategies and CI discovery directly from the terminal via ``adi-lg`` and ``adi-lg-hw-ci``.

   .. grid-item-card:: Model Context Protocol (MCP) Server
      :link: mcp
      :link-type: doc

      FastMCP server enabling Large Language Models (LLMs) to interact directly with hardware targets.

   .. grid-item-card:: Tick Runtime Deployment
      :link: tick
      :link-type: doc

      Deploy the ``axi_timed_command_scheduler`` IP onto booted Kuiper systems over SSH.

.. toctree::
   :maxdepth: 2
   :hidden:

   cli
   mcp
   tick
